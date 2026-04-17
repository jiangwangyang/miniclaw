import json
import logging
from contextlib import asynccontextmanager, AsyncExitStack

import anyio
from fastapi import APIRouter, FastAPI, Body
from mcp import ClientSession, StdioServerParameters, Tool
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

SETTINGS_FILE = "settings.json"
tool_session_dict: dict[str, ClientSession] = {}
mcp_tools: list[Tool] = []
mcp_openai_tools: list[dict] = []
router: APIRouter = APIRouter()


@router.post("/mcp/tool/list")
async def get_mcp_tools(body: dict = Body(...)):
    proto_type = body.get("type")
    async with AsyncExitStack() as stack:
        if proto_type == "streamable_http":
            transport = await stack.enter_async_context(streamablehttp_client(body["url"], body.get("headers")))
        elif proto_type == "sse":
            transport = await stack.enter_async_context(sse_client(body["url"], body.get("headers")))
        elif proto_type == "stdio":
            transport = await stack.enter_async_context(stdio_client(StdioServerParameters(command=body["command"], args=body["args"])))
        else:
            raise ValueError(f"Unknown proto type: {proto_type}")
        read, write = transport[:2]
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        tools_resp = await session.list_tools()
        return [dict(tool) for tool in tools_resp.tools]


@asynccontextmanager
async def register_mcp_client(name, proto_type, **kwargs):
    async with AsyncExitStack() as stack:
        # 创建客户端
        if proto_type == "streamable_http":
            transport = await stack.enter_async_context(streamablehttp_client(kwargs["url"], kwargs.get("headers")))
        elif proto_type == "sse":
            transport = await stack.enter_async_context(sse_client(kwargs["url"], kwargs.get("headers")))
        elif proto_type == "stdio":
            transport = await stack.enter_async_context(stdio_client(StdioServerParameters(command=kwargs["command"], args=kwargs["args"])))
        else:
            raise ValueError(f"Unknown proto type: {proto_type}")
        read, write = transport[:2]
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        # 获取工具列表
        tools_resp = await session.list_tools()
        for tool in tools_resp.tools:
            tool_session_dict[tool.name] = session
            mcp_tools.append(tool)
            mcp_openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                }
            })
        logging.info(f"MCP client {name} started, having {len(tools_resp.tools)} tools: {json.dumps(tools_resp.tools, ensure_ascii=False, default=lambda o: o.__dict__)}")
        # 等待
        yield
        # 结束
        logging.info(f"MCP client {name} stopped")


@asynccontextmanager
async def lifespan(app: FastAPI, tools: list, **kwargs):
    app.include_router(router)
    async with AsyncExitStack() as stack:
        # 加载设置
        settings_content = await anyio.Path(SETTINGS_FILE).read_text(encoding="utf-8")
        settings = json.loads(settings_content)
        # 创建MCP客户端
        for name, server in (settings.get("mcpServers") or {}).items():
            try:
                if server.get("type") == "streamable_http":
                    await stack.enter_async_context(register_mcp_client(name, "streamable_http", url=server.get("url"), headers=server.get("headers")))
                elif server.get("type") == "sse":
                    await stack.enter_async_context(register_mcp_client(name, "sse", url=server.get("url"), headers=server.get("headers")))
                elif server.get("type") == "stdio":
                    await stack.enter_async_context(register_mcp_client(name, "stdio", command=server.get("command"), args=server.get("args")))
                else:
                    logging.warning(f"Unknown MCP server type: {server.get('type')}")
            except Exception as e:
                logging.error(f"Error registering {name}: {e}")
        # 添加MCP工具
        tools.extend(mcp_openai_tools)
        logging.info(f"MCP plugin started, adding {len(mcp_openai_tools)} MCP tools: {json.dumps(mcp_openai_tools)}")
        # 等待
        yield
        # 结束
        logging.info("MCP plugin stopped")


# 执行工具
async def before_tool(messages: list, tool_call: dict, **kwargs):
    tool_name = tool_call["function"]["name"]
    if tool_name not in tool_session_dict:
        return
    try:
        args = json.loads(tool_call["function"]["arguments"])
        tool_result = await tool_session_dict[tool_name].call_tool(tool_name, args)
        tool_content = str(tool_result)
    except Exception as e:
        tool_content = f"Error: {e}"
    tool_message = {"role": "tool", "tool_call_id": tool_call["id"], "content": tool_content}
    messages.append(tool_message)
