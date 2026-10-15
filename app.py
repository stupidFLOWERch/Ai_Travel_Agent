import chainlit as cl
import asyncio
from mcp_client import MCPLangGraphAgent


@cl.on_chat_start
async def on_chat_start():
    """每个新会话开始时触发"""
    agent = MCPLangGraphAgent()
    await agent.setup()  # 建立 MCP 连接，加载工具
    cl.user_session.set("agent", agent)
    await cl.Message(
        content="🤖 Travel Assistant started! Ask me about flights, hotels, or weather."
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    """处理用户消息，复用 on_chat_start 里创建的 agent"""
    agent = cl.user_session.get("agent")
    
    if not agent:
        # 如果 session 丢了 agent（罕见），重新创建
        agent = MCPLangGraphAgent()
        await agent.setup()
        cl.user_session.set("agent", agent)
    
    try:
        # 用 Step 显示中间过程
        async with cl.Step(name="Agent Processing", type="tool") as step:
            result = await agent.query(message.content)
            step.output = result["final_answer"]
        
        # 流式输出最终回答
        msg = cl.Message(content="")
        for token in result["final_answer"]:
            await msg.stream_token(token)
        await msg.send()
        
    except Exception as e:
        await cl.Message(content=f"❌ Error: {e}").send()