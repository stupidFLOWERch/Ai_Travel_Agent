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
from typing import TypedDict, List, Dict, Any

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
    """State shared across all LangGraph nodes"""
    messages: List[Dict[str, Any]]  # Conversation history
    iteration: int                  # Loop counter (safety guard)


# ==========================================
# Main Agent Class
# ==========================================
class MCPLangGraphAgent:
    def __init__(self):
        """Initialize agent with empty state"""
        self.mcp_session = None              # MCP server connection
        self.tools_definitions = []          # Tools in Gemini format
        self.gemini_client = genai.Client(api_key=GEMINI_API_KEY)
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
    # LangGraph Node 1: LLM Decision
    # ------------------------------------------
    async def llm_node(self, state: AgentState) -> AgentState:
        """
        Node 1: Call Gemini LLM with tools.
        
        - Builds conversation history from state
        - Sends to Gemini with tool definitions
        - Extracts function calls or text response
        - Updates state with assistant's response
        """
        # Build conversation history for Gemini
        messages = []
        for msg in state["messages"]:
            role = msg["role"]
            content = msg.get("content", "")
            
            if role == "user":
                messages.append(types.Content(role="user", parts=[types.Part(text=content)]))
                
            elif role == "assistant":
                function_calls = msg.get("function_calls", [])
                if function_calls:
                    # Assistant message with function calls
                    parts = []
                    for fc in function_calls:
                        parts.append(types.Part(
                            function_call=types.FunctionCall(
                                name=fc["name"],
                                args=fc["args"]
                            )
                        ))
                    messages.append(types.Content(role="model", parts=parts))
                elif content:
                    # Assistant message with text only
                    messages.append(types.Content(role="model", parts=[types.Part(text=content)]))

            elif role == "tool":
                # Tool result → function_response
                messages.append(types.Content(
                    role="user",
                    parts=[types.Part(
                        function_response=types.FunctionResponse(
                            name=msg.get("name", "unknown"),
                            response={"result": content}
                        )
                    )]
                ))

        # Create Gemini chat with tools
        chat = self.gemini_client.chats.create(
            model="gemini-3.1-flash-lite",
            config={
                "system_instruction": """
                You are a helpful travel assistant. You have access to flight, hotel, and weather search tools. Current year is 2026.
                
                Available tools:
                1. search_flights_tool - Search flights on a specific date
                2. cheapest_date_range_tool - Find cheapest flights within a date range
                3. analyze_price_insights_tool - Analyze if a flight price is good to buy
                4. search_airport_tool - Find airport IATA codes
                5. search_multi_city_tool - Search multi-city flights
                6. search_hotels_tool - Search for hotels and accommodations via Trivago
                7. get_weather_tool - Get weather forecast for a location
                
                When a user asks about flights:
                - Call search_flights_tool or cheapest_date_range_tool first
                - Then call analyze_price_insights_tool if they ask about price

                When a user asks about hotels:
                - Call search_hotels_tool with query, arrival, departure, adults

                When a user asks about weather:
                - Call get_weather_tool with latitude and longitude (you can help find coordinates)

                Always use natural language to format the result and reply to the user.
                """,
                "tools": self.tools_definitions
            },
            history=messages
        )

        # Send empty message to continue the conversation
        response = chat.send_message("")

        # Parse response
        function_calls = []
        text_response = ""

        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.function_call:
                    function_calls.append({
                        "name": part.function_call.name,
                        "args": part.function_call.args
                    })
                elif part.text:
                    text_response = part.text

        # Update state
        state["messages"].append({
            "role": "assistant",
            "content": text_response,
            "function_calls": function_calls
        })
        state["iteration"] += 1

        return state

    # ------------------------------------------
    # LangGraph Node 2: Execute Tools
    # ------------------------------------------
    async def tool_node(self, state: AgentState) -> AgentState:
        """
        Node 2: Execute all pending tool calls.
        
        - Reads function_calls from last assistant message
        - Executes each tool via MCP
        - Stores results back in state
        """
        last_msg = state["messages"][-1]
        function_calls = last_msg.get("function_calls", [])

        # Execute each tool and store result
        for fc in function_calls:
            result = await self.call_tool(fc["name"], fc["args"])

            state["messages"].append({
                "role": "tool",
                "name": fc["name"],
                "content": result
            })

        return state

    # ------------------------------------------
    # LangGraph Condition: Continue or End?
    # ------------------------------------------
    def should_continue(self, state: AgentState) -> str:
        """
        Conditional edge function - decides whether to continue or end.
        
        Returns:
            "tools" → go to tool_node (continue loop)
            "end"   → stop execution
        """
        last_msg = state["messages"][-1]

        # If there are pending function calls, execute them
        if last_msg.get("function_calls"):
            return "tools"

        # Safety guard: prevent infinite loops
        if state["iteration"] > 10:
            return "end"

        # No more work to do
        return "end"

    # ------------------------------------------
    # Build LangGraph Workflow
    # ------------------------------------------
    def build_graph(self):
        """
        Build and compile the LangGraph workflow.
        
        Structure:
            agent → (conditional) → tools → agent (loop)
                            ↓
                           END
        """
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("agent", self.llm_node)
        workflow.add_node("tools", self.tool_node)

        # Entry point
        workflow.set_entry_point("agent")

        # Conditional routing: agent → tools OR end
        workflow.add_conditional_edges(
            "agent",
            self.should_continue,
            {
                "tools": "tools",
                "end": END
            }
        )

        # Loop back: tools → agent
        workflow.add_edge("tools", "agent")

        # Compile with memory (for conversation persistence)
        memory = MemorySaver()
        return workflow.compile(checkpointer=memory)

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

                # Load tools from MCP
                tools = await session.list_tools()
                print(f"✅ Connected, loaded {len(tools.tools)} tools")

                # Convert MCP tools to Gemini format
                self.tools_definitions = []
                for tool in tools.tools:
                    parameters = self.clean_schema(tool.inputSchema.copy())
                    if "type" not in parameters:
                        parameters["type"] = "object"

                    function_decl = types.FunctionDeclaration(
                        name=tool.name,
                        description=tool.description,
                        parameters=parameters
                    )
                    self.tools_definitions.append(
                        types.Tool(function_declarations=[function_decl])
                    )

                # Build and compile LangGraph workflow
                self.app = self.build_graph()

                # Start chat loop
                await self.chat_loop()

    # ------------------------------------------
    # Chat Loop
    # ------------------------------------------
    async def chat_loop(self):
        """
        Interactive chat loop with LangGraph.
        
        Each user input triggers the LangGraph workflow,
        which may loop multiple times internally.
        """
        print("\n🤖 Travel Assistant (LangGraph Edition) started!")
        print("Enter 'exit' to quit\n")
        print("-" * 50)

        # Thread ID for memory isolation (supports multiple users)
        config = {"configurable": {"thread_id": "user-1"}}

        # Initialize state
        state = {"messages": [], "iteration": 0}

        while True:
            user_input = input("\nYou: ").strip()
            if user_input.lower() in ["exit", "quit"]:
                print("👋 Goodbye!")
                break

            if not user_input:
                continue

            # Add user message to state
            state["messages"].append({"role": "user", "content": user_input})

            try:
                # Run LangGraph workflow
                final_state = await self.app.ainvoke(state, config)

                # Update state
                state = final_state

                # Print final assistant response
                for msg in reversed(state["messages"]):
                    if msg["role"] == "assistant" and msg["content"]:
                        print(f"\n🤖 {msg['content']}")
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