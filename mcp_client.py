# chatbot.py - 修复版

import asyncio
import json
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

class MCPChatbot:
    def __init__(self):
        self.mcp_session = None
        self.tools_definitions = []
        self.gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        self.chat = None
    
    def clean_schema(self, schema: dict) -> dict:
        """清理 JSON Schema，移除 Gemini 不支持的字段"""
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
    
    async def connect_mcp(self):
        """连接到 MCP Server"""
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
                print(f"✅ Connected, loaded {len(tools.tools)} tools")
                
                self.tools_definitions = []
                for tool in tools.tools:
                    parameters = self.clean_schema(tool.inputSchema.copy())
                    
                    if "type" not in parameters:
                        parameters["type"] = "object"
                    
                    function_declaration = types.FunctionDeclaration(
                        name=tool.name,
                        description=tool.description or f"Tool: {tool.name}",
                        parameters=parameters
                    )
                    
                    gemini_tool = types.Tool(
                        function_declarations=[function_declaration]
                    )
                    self.tools_definitions.append(gemini_tool)
                
                await self.chat_loop()
    
    async def call_tool(self, tool_name: str, args: dict):
        """call MCP tool"""
        try:
            result = await self.mcp_session.call_tool(tool_name, args)
            for content in result.content:
                if content.type == "text":
                    try:
                        return json.loads(content.text)
                    except:
                        return content.text
            return {"error": "No content returned"}
        except Exception as e:
            return {"error": str(e)}
    
    async def chat_loop(self):
        """Main chat loop"""
        self.chat = self.gemini_client.chats.create(
            model="gemini-3.1-flash-lite",
            config={
                "system_instruction": """
                You are a helpful travel assistant. You have access to flight search tools.
                
                When a user asks about flights:
                1. Understand the user's intent
                2. Call the appropriate tool
                3. Use natural language to format the result and reply to the user
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
                
                # 🔥 改动 1: 用 while 循环持续处理，直到 Gemini 不再调用工具
                while True:
                    if not response.candidates or not response.candidates[0].content.parts:
                        break
                    
                    has_function_call = False
                    
                    # 🔥 改动 2: 遍历所有 parts，处理每个 function_call
                    for part in response.candidates[0].content.parts:
                        if part.function_call:
                            has_function_call = True
                            tool_name = part.function_call.name
                            tool_args = part.function_call.args
                            
                            print(f"\n🔧 Calling tool: {tool_name}")
                            print(f"📝 Parameters: {json.dumps(tool_args, indent=2, ensure_ascii=False)}")
                            
                            result = await self.call_tool(tool_name, tool_args)
                            
                            print(f"✅ Tool execution completed")
                            
                            response_part = types.Part.from_function_response(
                                name=tool_name,
                                response={"result": result}
                            )
                            
                            # 把工具结果发回给 Gemini，获取新的响应
                            response = self.chat.send_message(response_part)
                            break  # 处理完一个 function_call 后，重新检查响应
                    
                    # 🔥 改动 3: 如果没有 function_call，退出循环
                    if not has_function_call:
                        break
                
                # 🔥 改动 4: 提取所有文本
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

async def main():
    bot = MCPChatbot()
    await bot.connect_mcp()

if __name__ == "__main__":
    asyncio.run(main())