import importlib
import json
import logging
import os
import sys
from contextlib import asynccontextmanager, AsyncExitStack

import anyio
from fastapi import FastAPI, Path, Body, Query
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from starlette.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
DATA_DIR = "data"
SETTINGS_FILE = "data/settings.json"
PLUGINS_DIR_LIST = ["external_plugins/", "plugins/"]
PLUGINS: list[object] = []
SESSIONS: set[str] = set()


# 加载插件
async def load_plugins():
    PLUGINS.clear()
    loaded_plugin_names = set()
    # 遍历插件目录
    for plugins_dir in PLUGINS_DIR_LIST:
        if not os.path.exists(plugins_dir):
            continue
        # 加入插件目录到 sys.path
        if plugins_dir not in sys.path:
            sys.path.insert(0, plugins_dir)
        # 加载插件
        for entry in os.listdir(plugins_dir):
            if entry in loaded_plugin_names:
                continue
            if os.path.isfile(os.path.join(plugins_dir, entry, "plugin.py")):
                module_name = f"{entry}.plugin"
                try:
                    module = importlib.import_module(module_name)
                    PLUGINS.append(module)
                    loaded_plugin_names.add(entry)
                except Exception as e:
                    logging.error(f"加载插件 {entry} 失败: {e}")
    logging.info(f"Loaded {len(PLUGINS)} plugins: {PLUGINS}")


# 执行插件钩子函数
async def execute_plugins(action: str, **kwargs):
    for module in PLUGINS:
        action_function = getattr(module, action, None)
        if action_function:
            try:
                await action_function(**kwargs)
            except Exception as e:
                logging.error(f"执行插件 {module.__name__} 的 {action} 钩子函数失败: {e}")


# 模型对话
async def chat_generator(session_id: str, messages: list, tools: list, user_content: str, work_dir: str):
    # session start
    SESSIONS.add(session_id)
    assistant_content = ""
    # before_chat
    await execute_plugins(action="before_chat", session_id=session_id, work_dir=work_dir, messages=messages, tools=tools, user_content=user_content)

    while True:
        if not session_id in SESSIONS:
            break

        # 1. 发送请求
        settings = {}
        if await anyio.Path(SETTINGS_FILE).exists():
            settings = json.loads(await anyio.Path(SETTINGS_FILE).read_text(encoding="utf-8"))
        client = AsyncOpenAI(base_url=settings.get("base_url"), api_key=settings.get("api_key"))
        response = await client.chat.completions.create(model=settings.get("model"), messages=messages, tools=tools, stream=True)

        # 2. 收集内容
        # before model
        await execute_plugins(action="before_model", session_id=session_id, work_dir=work_dir, messages=messages, tools=tools)
        assistant_content = ""
        assistant_tool_calls = []
        async for chunk in response:
            if not session_id in SESSIONS:
                assistant_tool_calls.clear()
                break
            chunk = json.loads(json.dumps(chunk, default=lambda o: o.__dict__))
            delta = chunk["choices"][0]["delta"]
            # SSE 流式响应
            yield f"data: {json.dumps({"role": "assistant", "content": delta["content"]}, ensure_ascii=False)}\n\n"
            # 收集工具调用
            for tool_call in delta["tool_calls"] or []:
                tool_call["function"]["arguments"] = tool_call["function"]["arguments"] or ""
                if tool_call["index"] < len(assistant_tool_calls):
                    assistant_tool_calls[tool_call["index"]]["function"]["arguments"] += tool_call["function"]["arguments"]
                else:
                    assistant_tool_calls.append(tool_call)
            # 收集普通文本
            if delta["content"]:
                assistant_content += delta["content"]
        yield f"data: {json.dumps({"role": "assistant", "content": "", "tool_calls": assistant_tool_calls}, ensure_ascii=False)}\n\n"
        messages.append({"role": "assistant", "content": assistant_content, "tool_calls": assistant_tool_calls})
        # after model
        await execute_plugins(action="after_model", session_id=session_id, work_dir=work_dir, messages=messages, tools=tools)

        # 3. 工具调用
        for tool_call in assistant_tool_calls:
            # before tool
            await execute_plugins(action="before_tool", session_id=session_id, work_dir=work_dir, messages=messages, tools=tools, tool_call=tool_call)
            # yield tool
            if messages[-1]["role"] != "tool" or messages[-1]["tool_call_id"] != tool_call["id"]:
                messages.append({"role": "tool", "tool_call_id": tool_call["id"], "content": "Can't find tool"})
            yield f"data: {json.dumps(messages[-1], ensure_ascii=False)}\n\n"
            # after tool
            await execute_plugins(action="after_tool", session_id=session_id, work_dir=work_dir, messages=messages, tools=tools, tool_call=tool_call)

        # 4. 判断结束
        if not assistant_tool_calls:
            break

    # after chat
    await execute_plugins(action="after_chat", session_id=session_id, work_dir=work_dir, messages=messages, tools=tools, user_content=user_content, assistant_content=assistant_content)
    # session end
    yield "data: [DONE]\n\n"
    SESSIONS.discard(session_id)


# 生命周期管理
@asynccontextmanager
async def lifespan(_app: FastAPI):
    await load_plugins()
    async with AsyncExitStack() as stack:
        for module in PLUGINS:
            if hasattr(module, "lifespan"):
                try:
                    await stack.enter_async_context(module.lifespan(app=_app))
                except Exception as e:
                    logging.error(f"执行插件 {module.__name__} 的 lifespan 钩子函数失败: {e}", e)
        yield


app: FastAPI = FastAPI(lifespan=lifespan)


# 对话接口
@app.get("/chat/{id}")
async def chat_get(session_id: str = Path(..., alias="id"), message: str = Query(...), workdir: str = Query(...), stream: bool = Query(...)):
    if session_id in SESSIONS:
        return JSONResponse(status_code=403, content=f"会话 {session_id} 正在处理中")
    messages = [
        {"role": "system", "content": ""},
        {"role": "user", "content": message}
    ]
    if stream:
        return StreamingResponse(chat_generator(session_id, messages, [], message, workdir), media_type="text/event-stream")
    async for _ in chat_generator(session_id, messages, [], message, workdir):
        pass
    return messages[-1]


# 对话接口
@app.post("/chat/{id}")
async def chat_post(session_id: str = Path(..., alias="id"), message: str = Body(...), workdir: str = Body(...), stream: bool = Body(...)):
    if session_id in SESSIONS:
        return JSONResponse(status_code=403, content=f"会话 {session_id} 正在处理中")
    messages = [
        {"role": "system", "content": ""},
        {"role": "user", "content": message}
    ]
    if stream:
        return StreamingResponse(chat_generator(session_id, messages, [], message, workdir), media_type="text/event-stream")
    async for _ in chat_generator(session_id, messages, [], message, workdir):
        pass
    return messages[-1]


# 中断接口
@app.api_route("/interrupt/{id}", methods=["GET", "POST"])
async def interrupt(session_id: str = Path(..., alias="id")):
    SESSIONS.discard(session_id)
