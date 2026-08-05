import asyncio
import json
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from google import genai
from google.genai import types
from dotenv import load_dotenv

from fastmcp import Client

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

class MCPChatbot:
    def __init__(self):
        self.mcp_session = None
        self.tools_definitions = []
        self.gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        self.chat = None

    async def run(self):

        server_params = StdioServerParameters(
            command="python",
            args=["mcp_server.py"]
        )

        print("🔄 Connecting to MCP Server...")

        async with stdio_client(server_params) as (read, write):

            async with ClientSession(read, write) as session:

                self.mcp_session = session

                await session.initialize()

                tools = await session.list_tools()

                print(
                    f"✅ Connected, loaded {len(tools.tools)} tools"
                )


                self.tools_definitions = []

                for tool in tools.tools:

                    parameters = self.clean_schema(
                        tool.inputSchema.copy()
                    )

                    if "type" not in parameters:
                        parameters["type"] = "object"


                    function_declaration = types.FunctionDeclaration(
                        name=tool.name,
                        description=tool.description,
                        parameters=parameters
                    )


                    self.tools_definitions.append(
                        types.Tool(
                            function_declarations=[
                                function_declaration
                            ]
                        )
                    )


                await self.chat_loop()

    async def chat_loop(self):
        """Main chat loop"""
        self.chat = self.gemini_client.chats.create(
            model="gemini-3.1-flash-lite",
            config={
                "system_instruction": """
                You are a helpful travel assistant. You have access to flight and hotel search tools.

                Available tools:
                1. **search_flights_tool** - Search flights on a specific date
                2. **cheapest_date_range_tool** - Find cheapest flights within a date range
                3. **analyze_price_insights_tool** - Analyze if a flight price is good to buy
                4. **search_airport_tool** - Find airport IATA codes for flights only, not for hotels
                5. **search_multi_city_tool** - Search multi-city flights
                6. **search_hotels_tool** - Search for hotels and accommodations

                When a user asks about flights:
                1. **FIRST** call search_flights_tool or cheapest_date_range_tool to get flight options
                2. **THEN** if the user asks about price value, call analyze_price_insights_tool

                When a user asks about hotels:
                - Call search_hotels_tool with destination, check_in, check_out, guests

                Always use natural language to format the result and reply to the user.
                """,
                "tools": self.tools_definitions
            }
        )

        print("\n🤖 Travel assistant is started!")
        print("Enter 'exit' to quit\n")
        print("-" * 50)

        while True:
            user_input = input("\nYou: ").strip()
            if user_input.lower() in ["exit", "quit"]:
                print("👋 Goodbye!")
                break

            if not user_input:
                continue

            try:
                response = self.chat.send_message(user_input)

                # Use while loop to call tools
                while True:
                    if not response.candidates or not response.candidates[0].content.parts:
                        break

                    has_function_call = False

                    # loop all parts, handle all function calls
                    for part in response.candidates[0].content.parts:
                        if part.function_call:
                            has_function_call = True
                            tool_name = part.function_call.name
                            tool_args = part.function_call.args

                            result = await self.call_tool(tool_name, tool_args)

                            print(f"✅ Tool execution completed")

                            response_part = types.Part.from_function_response(
                                name=tool_name,
                                response={"result": result}
                            )

                            # send result after tools call to llm
                            response = self.chat.send_message(response_part)
                            break

                    # exit loop when function call end
                    if not has_function_call:
                        break

                # get all text response
                text_parts = []
                if response.candidates and response.candidates[0].content.parts:
                    for part in response.candidates[0].content.parts:
                        if part.text:
                            text_parts.append(part.text)

                if text_parts:
                    print(f"\n🤖 {''.join(text_parts)}")

            except Exception as e:
                print(f"\n❌ Error: {e}")
                import traceback
                traceback.print_exc()

    def clean_schema(self, schema: dict) -> dict:
        """Clean JSON Schema, remove unsupported fields in Gemini"""
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
            if key in unsupported_fields:
                continue

            if key == "properties" and isinstance(value, dict):
                cleaned["properties"] = {}
                for prop_name, prop_schema in value.items():
                    if isinstance(prop_schema, dict):
                        cleaned["properties"][prop_name] = self.clean_schema(prop_schema)
                    else:
                        cleaned["properties"][prop_name] = prop_schema

            elif key == "items" and isinstance(value, dict):
                cleaned["items"] = self.clean_schema(value)

            else:
                cleaned[key] = value

        return cleaned

    async def call_tool(self, tool_name: str, args: dict):
        """call MCP tool"""
        try:
            if not self.mcp_session:
                return {"error": "Local MCP not connected"}

            print(f"\n🔧 Calling tool: {tool_name}")
            print(f"📝 Final Parameters: {json.dumps(args, indent=2, ensure_ascii=False)}")

            result = await self.mcp_session.call_tool(tool_name, args)

            # get text from content
            for content in result.content:
                if content.type == "text":
                    try:
                        return json.loads(content.text)
                    except:
                        return content.text

            return {"error": "No content returned"}

        except Exception as e:
            print(f"❌ TOOL ERROR: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}

async def main():
    bot = MCPChatbot()
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())