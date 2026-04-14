import asyncio
import json
import logging
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters, Tool
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

SETTINGS_FILE = "settings.json"
manager = None


# 管理单个MCP客户端连接
class MCPClient:
    def __init__(self, name):
        self.stack: AsyncExitStack = AsyncExitStack()
        self.name: str = name
        self.transport: tuple[asyncio.StreamReader, asyncio.StreamWriter] | tuple[asyncio.StreamReader, asyncio.StreamWriter, str] = None
        self.session: ClientSession = None

    async def connect_streamable(self, url, headers):
        self.transport = await self.stack.enter_async_context(streamablehttp_client(url, headers))
        read, write, session_id = self.transport
        self.session = await self.stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()

    async def connect_sse(self, url, headers):
        self.transport = await self.stack.enter_async_context(sse_client(url, headers))
        read, write = self.transport
        self.session = await self.stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()

    async def connect_stdio(self, command, args):
        params = StdioServerParameters(command=command, args=args)
        self.transport = await self.stack.enter_async_context(stdio_client(params))
        read, write = self.transport
        self.session = await self.stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()

    async def close(self):
        await self.stack.aclose()


# 管理多个MCP客户端连接
class MCPManager:
    def __init__(self):
        self.clients: list[MCPClient] = []
        self.tools: list[Tool] = []
        self.tool_client_dict: dict[str, MCPClient] = {}

    async def register_client(self, name, proto_type, **kwargs):
        client = MCPClient(name)
        if proto_type == "streamable_http":
            await client.connect_streamable(kwargs["url"], kwargs.get("headers"))
        elif proto_type == "sse":
            await client.connect_sse(kwargs["url"], kwargs.get("headers"))
        elif proto_type == "stdio":
            await client.connect_stdio(kwargs["command"], kwargs["args"])
        else:
            raise ValueError(f"Unknown proto type: {proto_type}")
        self.clients.append(client)
        tools_resp = await client.session.list_tools()
        for tool in tools_resp.tools:
            self.tool_client_dict[tool.name] = client
            self.tools.append(tool)

    def get_openai_tools(self):
        return [{
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.inputSchema,
            }
        } for t in self.tools]

    async def call_tool(self, tool_name, arguments):
        client = self.tool_client_dict.get(tool_name)
        return await client.session.call_tool(tool_name, arguments)

    async def close(self):
        await asyncio.gather(*[client.close() for client in self.clients], return_exceptions=True)
        self.clients.clear()


# 加载MCP客户端
async def before_application(tools: list, **kwargs):
    global manager
    manager = MCPManager()
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        settings = json.load(f)
    coroutines = []
    for name, server in (settings.get("mcpServers") or {}).items():
        if server.get("type") == "streamable_http":
            coroutines.append(manager.register_client(name, "streamable_http", url=server.get("url"), headers=server.get("headers")))
        elif server.get("type") == "sse":
            coroutines.append(manager.register_client(name, "sse", url=server.get("url"), headers=server.get("headers")))
        else:
            coroutines.append(manager.register_client(name, "stdio", command=server.get("command"), args=server.get("args")))
    await asyncio.gather(*coroutines, return_exceptions=True)
    mcp_openai_tools = manager.get_openai_tools()
    tools.extend(mcp_openai_tools)
    logging.info(f"MCP plugin started, adding {len(mcp_openai_tools)} MCP tools: {json.dumps(mcp_openai_tools)}")


# 关闭MCP客户端
async def after_application(**kwargs):
    await manager.close()
    logging.info("MCP plugin stopped")


async def before_chat(**kwargs):
    pass


async def after_chat(**kwargs):
    pass


async def before_model(**kwargs):
    pass


async def after_model(**kwargs):
    pass


# 执行工具
async def before_tool(messages: list, tool_call: dict, **kwargs):
    tool_name = tool_call["function"]["name"]
    if tool_name not in manager.tool_client_dict:
        return
    try:
        args = json.loads(tool_call["function"]["arguments"])
        tool_result = await manager.tool_client_dict[tool_name].session.call_tool(tool_name, args)
        tool_content = str(tool_result)
    except Exception as e:
        tool_content = f"Error: {e}"
    tool_message = {"role": "tool", "tool_call_id": tool_call["id"], "content": tool_content}
    messages.append(tool_message)


async def after_tool(**kwargs):
    pass
