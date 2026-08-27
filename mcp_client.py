import asyncio
import json
import os
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from google import genai
from google.genai import types
from dotenv import load_dotenv

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import add_messages
from typing import TypedDict, List, Dict, Any, Annotated

from agents.flights_agent import FlightAgent
from agents.hotels_agent import HotelAgent
from agents.weather_agent import WeatherAgent

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Debug: verify that the SerpApi API key is available in the MCP client.
# This helps diagnose environment variable propagation issues between the Docker container, MCP client, and MCP server subprocess.
# print(
#     "[CLIENT] SERPAPI:",
#     bool(os.getenv("SERPAPI_API_KEY")),
#     len(os.getenv("SERPAPI_API_KEY", "")),
#     file=sys.stderr
# )

# ==========================================
# Agent State Definition
# ==========================================
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    supervisor_decision: Dict[str, Any]
    
FLIGHT_TOOL_NAMES = {
    "search_flights_tool",
    "cheapest_date_range_tool",
    "analyze_price_insights_tool",
    "search_airport_tool",
    "search_multi_city_tool",
}

HOTEL_TOOL_NAMES = {
    "search_hotels_tool",
}

WEATHER_TOOL_NAMES = {
    "get_weather_tool",
}


# ==========================================
# Main Agent Class
# ==========================================
class MCPLangGraphAgent:
    def __init__(self):
        """Initialize agent with empty state"""
        self.mcp_session = None              # MCP server connection

        self.flight_tools = []
        self.hotel_tools = []
        self.weather_tools = []

        self.gemini_client = genai.Client(api_key=GEMINI_API_KEY)

        self.flight_agent = None
        self.hotel_agent = None
        self.weather_agent = None
        self.app = None                      # Compiled LangGraph app (built later)

    # ------------------------------------------
    # Helper: Clean JSON Schema for Gemini
    # ------------------------------------------
    def clean_schema(self, schema: dict) -> dict:
        """
        Clean JSON Schema by removing fields unsupported by Gemini API.
        
        Args:
            schema: Raw JSON Schema from MCP tool
            
        Returns:
            Cleaned schema compatible with Gemini
        """
        unsupported_fields = [
            "$schema",
            "additional_properties",
            "additionalProperties",
            "patternProperties",
            "minItems",
            "maxItems",
            "uniqueItems",
            "minProperties",
            "maxProperties",
            "allOf",
            "oneOf",
            "anyOf",
            "not",
            "propertyNames",
            "const",
            "default",
            "examples"
        ]

        cleaned = {}
        for key, value in schema.items():
            # Skip unsupported fields
            if key in unsupported_fields:
                continue

            # Recursively clean nested properties
            if key == "properties" and isinstance(value, dict):
                cleaned["properties"] = {}
                for prop_name, prop_schema in value.items():
                    if isinstance(prop_schema, dict):
                        cleaned["properties"][prop_name] = self.clean_schema(prop_schema)
                    else:
                        cleaned["properties"][prop_name] = prop_schema

            # Recursively clean array items
            elif key == "items" and isinstance(value, dict):
                cleaned["items"] = self.clean_schema(value)

            else:
                cleaned[key] = value

        return cleaned

    def format_conversation(self, messages) -> str:
        conversation = []

        for msg in messages:
            if isinstance(msg, dict):
                role = msg.get("role")
                content = msg.get("content", "")
            else:
                role = getattr(msg, "type", "")
                content = getattr(msg, "content", "")

            if isinstance(content, list):
                content = " ".join(
                    str(item) for item in content
                )

            if role in ("user", "human"):
                conversation.append(f"User: {content}")

            elif role in ("assistant", "ai"):
                conversation.append(f"Assistant: {content}")

        return "\n".join(conversation)

    def get_flight_tools(
        self,
        task_type: str
    ):

        tool_map = {

            "multi_city": [
                "search_multi_city_tool",
                "search_airport_tool"
            ],

            "one_way": [
                "search_flights_tool",
                "search_airport_tool"
            ],

            "round_trip": [
                "search_flights_tool",
                "search_airport_tool"
            ],

            "cheapest": [
                "cheapest_date_range_tool",
                "search_airport_tool"
            ],

            "price_analysis": [
                "analyze_price_insights_tool"
            ]
        }

        return tool_map.get(task_type)

    # ------------------------------------------
    # Helper: Execute MCP Tool
    # ------------------------------------------
    async def call_tool(self, tool_name: str, args: dict):
        """
        Execute a tool via MCP session.
        
        Args:
            tool_name: Name of the tool to call
            args: Tool arguments
            
        Returns:
            Tool result (parsed JSON or text)
        """
        try:
            if not self.mcp_session:
                return {"error": "Local MCP not connected"}

            print(f"\n🔧 Calling tool: {tool_name}")
            print(f"📝 Final Parameters: {json.dumps(args, indent=2, ensure_ascii=False)}")

            result = await self.mcp_session.call_tool(tool_name, args)
            
            # DEBUG: print raw MCP result
            # print("\n========== RAW MCP RESULT ==========")
            # print(result)
            # print("====================================\n")

            for content in result.content:
                # DEBUG: print content type and text
                # print(f"Content type: {content.type}")
                # if content.type == "text":
                #     print("Content text:")
                #     print(content.text)

                if content.type == "text":
                    try:
                        parsed = json.loads(content.text)

                        # DEBUG: print parsed result
                        # print("\n========== PARSED RESULT ==========")
                        # print(json.dumps(
                        #     parsed,
                        #     indent=2,
                        #     ensure_ascii=False
                        # ))
                        # print("===================================\n")

                        return parsed

                    except Exception:
                        return content.text

            return {"error": "No content returned"}

        except Exception as e:
            print(f"\n❌ TOOL ERROR: {type(e).__name__}: {e}")

            import traceback
            traceback.print_exc()

            return {
                "error": f"{type(e).__name__}: {str(e)}"
        }

    # ------------------------------------------
    # LangGraph Node 1: supervisor_node decision
    # ------------------------------------------
    async def supervisor_node(
        self,
        state: AgentState
    ) -> AgentState:

        recent_messages = state["messages"][-10:]

        conversation = self.format_conversation(
            recent_messages
        )

        system_instruction = """
        You are a Supervisor Agent for a travel assistant.

        Your ONLY job is to analyze the user's request and break it into one or more tasks.

        Available specialist agents:

        1. flight
        - flight search
        - airport search
        - cheapest flights
        - multi-city flights
        - flight price analysis

        2. hotel
        - hotel search

        3. weather
        - weather forecasts


        For flight tasks, classify the task type as one of:

        - one_way
        - round_trip
        - multi_city
        - airport
        - cheapest
        - price_analysis


        IMPORTANT:

        - Assume current year is 2026 if not provided.
        - Use the entire conversation history.
        - Resolve references such as:
        "there"
        "that place"
        "same date"
        "same hotel"
        "tomorrow"

        - Do NOT call tools.
        - Do NOT answer the user's request.
        - Rewrite every task into a complete, self-contained request.

        - A user request may contain multiple tasks.
        - Multiple tasks may belong to different agents.
        - Return ALL tasks.

        Return ONLY valid JSON in this format:

        {
            "tasks": [
                {
                    "agent": "flight",
                    "task_type": "one_way",
                    "request": "Find a one-way flight from KUL to BKI on 2026-08-29."
                }
            ]
        }


        Example: multiple domains

        User request:
        "Find me a flight from KUL to Tokyo on 2026-09-01,
        a hotel in Tokyo, and the weather there."

        Return:

        {
            "tasks": [
                {
                    "agent": "flight",
                    "task_type": "one_way",
                    "request": "Find a one-way flight from KUL to Tokyo on 2026-09-01."
                },
                {
                    "agent": "hotel",
                    "task_type": null,
                    "request": "Find a hotel in Tokyo."
                },
                {
                    "agent": "weather",
                    "task_type": null,
                    "request": "Provide the weather forecast for Tokyo."
                }
            ]
        }


        Example: multi-city flight

        {
            "tasks": [
                {
                    "agent": "flight",
                    "task_type": "multi_city",
                    "request": "Search a multi-city itinerary with these segments: KUL to BKI on 2026-08-29, then BKI to SBW on 2026-09-04."
                }
            ]
        }


        If the request is unrelated to flights, hotels, or weather:

        {
            "tasks": [
                {
                    "agent": "none",
                    "task_type": null,
                    "request": "I can only help with flights, hotels, and weather."
                }
            ]
        }
        """

        response = self.gemini_client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            text=conversation
                        )
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json"
            )
        )

        try:
            decision = json.loads(response.text)

            allowed_agents = {
                "flight",
                "hotel",
                "weather",
                "none"
            }

            valid = True

            # Must be an object
            if not isinstance(decision, dict):
                valid = False

            # Must contain tasks
            elif not isinstance(decision.get("tasks"), list):
                valid = False

            # Must contain at least one task
            elif len(decision["tasks"]) == 0:
                valid = False

            else:
                for task in decision["tasks"]:

                    if not isinstance(task, dict):
                        valid = False
                        break

                    agent = task.get("agent")
                    task_type = task.get("task_type")
                    request = task.get("request")

                    # Validate agent
                    if agent not in allowed_agents:
                        valid = False
                        break

                    # Validate request
                    if not isinstance(request, str) or not request.strip():
                        valid = False
                        break

                    # Flight must have a task_type
                    if agent == "flight":

                        allowed_task_types = {
                            "one_way",
                            "round_trip",
                            "multi_city",
                            "airport",
                            "cheapest",
                            "price_analysis"
                        }

                        if task_type not in allowed_task_types:
                            valid = False
                            break

                    # Non-flight tasks should have no task_type
                    else:

                        if task_type is not None:
                            valid = False
                            break

            if not valid:
                decision = {
                    "tasks": [
                        {
                            "agent": "none",
                            "task_type": None,
                            "request": (
                                "I can only help with "
                                "flights, hotels, and weather."
                            )
                        }
                    ]
                }

        except json.JSONDecodeError:
            decision = {
                "tasks": [
                    {
                        "agent": "none",
                        "task_type": None,
                        "request": (
                            "I can only help with "
                            "flights, hotels, and weather."
                        )
                    }
                ]
            }

        print("\n🧭 Supervisor Decision:")
        print(
            json.dumps(
                decision,
                indent=2,
                ensure_ascii=False
            )
        )

        return {
            "supervisor_decision": decision
        }

    async def dispatcher_node(
        self,
        state: AgentState
    ) -> AgentState:

        decision = state["supervisor_decision"]

        tasks = decision.get("tasks", [])

        results = []

        for task in tasks:

            agent_name = task.get("agent")
            task_type = task.get("task_type")
            request = task.get("request")

            if agent_name == "flight":

                allowed_tools = self.get_flight_tools(
                    task_type
                )

                result = await self.flight_agent.run(
                    request,
                    allowed_tool_names=allowed_tools
                )

            elif agent_name == "hotel":

                result = await self.hotel_agent.run(
                    request
                )

            elif agent_name == "weather":

                result = await self.weather_agent.run(
                    request
                )

            else:

                result = (
                    "I can only help with flights, "
                    "hotels, and weather."
                )

            results.append(result)

        return {
            "messages": [
                {
                    "role": "assistant",
                    "content": "\n\n".join(results)
                }
            ]
        }

    # ------------------------------------------
    # Build LangGraph Workflow
    # ------------------------------------------
    def build_graph(self):

        workflow = StateGraph(AgentState)

        workflow.add_node(
            "supervisor",
            self.supervisor_node
        )

        workflow.add_node(
            "dispatcher",
            self.dispatcher_node
        )

        workflow.set_entry_point(
            "supervisor"
        )

        workflow.add_edge(
            "supervisor",
            "dispatcher"
        )

        workflow.add_edge(
            "dispatcher",
            END
        )

        memory = MemorySaver()

        return workflow.compile(
            checkpointer=memory
        )

    # ------------------------------------------
    # Main Entry Point
    # ------------------------------------------
    async def run(self):
        """
        Main entry point: connect to MCP, build graph, start chat loop.
        """
        # Connect to MCP Server
        # Pass the current process environment to the MCP server subprocess.
        # This ensures that environment variables such as API keys are available
        # inside the MCP server when running locally or inside Docker.
        server_params = StdioServerParameters(
            command="python",
            args=["mcp_server.py"],
            env=os.environ.copy()
        )
        print("🔄 Connecting to MCP Server...")

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                self.mcp_session = session
                await session.initialize()

                # Load MCP tools
                tools = await session.list_tools()

                # Convert MCP tools to Gemini format
                self.flight_tools = []
                self.hotel_tools = []
                self.weather_tools = []

                for tool in tools.tools:

                    parameters = self.clean_schema(
                        tool.inputSchema.copy()
                    )

                    function_decl = types.FunctionDeclaration(
                        name=tool.name,
                        description=tool.description,
                        parameters=parameters
                    )

                    gemini_tool = types.Tool(
                        function_declarations=[function_decl]
                    )

                    if tool.name in FLIGHT_TOOL_NAMES:
                        self.flight_tools.append(gemini_tool)

                    elif tool.name in HOTEL_TOOL_NAMES:
                        self.hotel_tools.append(gemini_tool)

                    elif tool.name in WEATHER_TOOL_NAMES:
                        self.weather_tools.append(gemini_tool)

                print(
                    f"✈️ Flight tools: "
                    f"{[t.function_declarations[0].name for t in self.flight_tools]}"
                )

                print(
                    f"🏨 Hotel tools: "
                    f"{[t.function_declarations[0].name for t in self.hotel_tools]}"
                )

                print(
                    f"🌤️ Weather tools: "
                    f"{[t.function_declarations[0].name for t in self.weather_tools]}"
                )


                # ==========================================
                # Create Specialist Agents
                # ==========================================

                self.flight_agent = FlightAgent(
                    self.gemini_client,
                    self.flight_tools,
                    self.call_tool
                )

                self.hotel_agent = HotelAgent(
                    self.gemini_client,
                    self.hotel_tools,
                    self.call_tool
                )

                self.weather_agent = WeatherAgent(
                    self.gemini_client,
                    self.weather_tools,
                    self.call_tool
                )

                # Build Supervisor LangGraph
                self.app = self.build_graph()

                await self.chat_loop()

    # ------------------------------------------
    # Chat Loop
    # ------------------------------------------
    async def chat_loop(self):

        print("\n🤖 Travel Assistant started!")
        print("Enter 'exit' to quit\n")
        print("-" * 50)

        config = {
            "configurable": {
                "thread_id": "user-1"
            }
        }

        while True:

            user_input = input("\nYou: ").strip()

            if user_input.lower() in ["exit", "quit"]:
                print("👋 Goodbye!")
                break

            if not user_input:
                continue

            try:

                final_state = await self.app.ainvoke(
                    {
                        "messages": [
                            {
                                "role": "user",
                                "content": user_input
                            }
                        ]
                    },
                    config
                )

                # Get latest assistant response
                for msg in reversed(final_state["messages"]):

                    if isinstance(msg, dict):
                        role = msg.get("role")
                        content = msg.get("content")

                    else:
                        role = getattr(msg, "type", None)
                        content = getattr(msg, "content", None)

                    if role in ("assistant", "ai") and content:
                        print(f"\n🤖 {content}")
                        break

            except Exception as e:

                print(f"\n❌ Error: {e}")

                import traceback
                traceback.print_exc()

# ==========================================
# Entry Point
# ==========================================
async def main():
    agent = MCPLangGraphAgent()
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())