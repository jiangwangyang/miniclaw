import json
import logging
import pathlib
from contextlib import asynccontextmanager, AsyncExitStack

import anyio
from fastapi import APIRouter, FastAPI, Body
from mcp import ClientSession, StdioServerParameters, Tool
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

SETTINGS_FILE = str(pathlib.Path.home() / ".miniclaw" / "settings.json")
TOOL_SESSION_DICT: dict[str, ClientSession] = {}
TOOL_DICT: dict[str, Tool] = {}
ROUTER = APIRouter()


@ROUTER.post("/mcp/tool/list")
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
            TOOL_SESSION_DICT[tool.name] = session
            TOOL_DICT[tool.name] = tool
        logging.info(f"MCP client {name} started, having {len(tools_resp.tools)} tools: {json.dumps(tools_resp.tools, ensure_ascii=False, default=lambda o: o.__dict__)}")
        # 等待
        yield
        # 结束
        logging.info(f"MCP client {name} stopped")


@asynccontextmanager
async def lifespan(app: FastAPI, **kwargs):
    # 注册路由
    app.include_router(ROUTER)
    # 加载设置
    settings_file = anyio.Path(SETTINGS_FILE)
    settings_file_content = await settings_file.read_text(encoding="utf-8") if await settings_file.exists() else ""
    settings = json.loads(settings_file_content) if settings_file_content else {}
    mcp_servers = settings.get("mcp_servers", {})
    # 注册MCP客户端
    async with AsyncExitStack() as stack:
        # 创建MCP客户端
        for name, server in mcp_servers.items():
            try:
                if server.get("type") == "streamable_http":
                    await stack.enter_async_context(register_mcp_client(name, "streamable_http", url=server.get("url"), headers=server.get("headers")))
                elif server.get("type") == "sse":
                    await stack.enter_async_context(register_mcp_client(name, "sse", url=server.get("url"), headers=server.get("headers")))
                elif server.get("type") == "stdio":
                    await stack.enter_async_context(register_mcp_client(name, "stdio", command=server.get("command"), args=server.get("args")))
                else:
                    logging.warning(f"Unknown MCP server type: {server.get("type")}")
            except Exception as e:
                if hasattr(e, 'exceptions'):
                    logging.error(f"Error registering {name}: {e.exceptions}")
                else:
                    logging.error(f"Error registering {name}: {e}")
        logging.info(f"MCP plugin started, having {len(TOOL_DICT)} tools: {", ".join(TOOL_DICT.keys())}")
        # 等待
        yield
        # 结束
        logging.info("MCP plugin stopped")


async def before_chat(tools: list, **kwargs):
    tools += [{
        "name": "read_mcp_tool",
        "description": f"Read MCP tool input schema. MCP tools: {json.dumps([{"name": tool.name, "description": tool.description} for tool in TOOL_DICT.values()], ensure_ascii=False)}",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "mcp tool name"
                }
            },
            "required": ["name"]
        }
    }]


async def before_tool(messages: list, tool_call: dict, **kwargs):
    # 执行 read_mcp_tool
    if tool_call["name"] == "read_mcp_tool":
        tool_name = tool_call["input"].get("name", "")
        if tool_name not in TOOL_DICT:
            tool_content, is_error = "Cannot find mcp tool", True
        else:
            tool_content = json.dumps({"name": tool_name, "description": TOOL_DICT[tool_name].description, "input_schema": TOOL_DICT[tool_name].inputSchema}, ensure_ascii=False)
            is_error = False
        messages[-1]["content"] += [{"type": "tool_result", "tool_use_id": tool_call["id"], "content": tool_content, "is_error": is_error}]
        return
    # 执行 mcp tool
    if tool_call["name"] not in TOOL_SESSION_DICT:
        return
    try:
        tool_result = await TOOL_SESSION_DICT[tool_call["name"]].call_tool(tool_call["name"], tool_call["input"])
        tool_content, is_error = str(tool_result.content), tool_result.isError
    except Exception as e:
        tool_content, is_error = f"Error: {e}", True
    messages[-1]["content"] += [{"type": "tool_result", "tool_use_id": tool_call["id"], "content": tool_content, "is_error": is_error}]
