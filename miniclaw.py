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
session_flag: dict[str, bool] = {}
plugins: list[object] = []
tools: list[object] = []


# 加载设置
async def load_settings() -> dict[str, object]:
    if not await anyio.Path(SETTINGS_FILE).exists():
        return {}
    content = await anyio.Path(SETTINGS_FILE).read_text(encoding="utf-8")
    return json.loads(content)


# 加载插件
async def load_plugins():
    plugins.clear()
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
                    plugins.append(module)
                    loaded_plugin_names.add(entry)
                except Exception as e:
                    logging.error(f"加载插件 {entry} 失败: {e}")
    logging.info(f"Loaded {len(plugins)} plugins: {plugins}")


# 执行插件钩子函数
async def execute_plugins(action: str, **kwargs):
    for module in plugins:
        action_function = getattr(module, action, None)
        if action_function:
            try:
                await action_function(**kwargs)
            except Exception as e:
                logging.error(f"执行插件 {module.__name__} 的 {action} 钩子函数失败: {e}")


# 模型对话
async def chat_generator(session_id: str, user_content: str, work_dir: str):
    # session start
    session_flag[session_id] = True
    assistant_content = ""
    messages = [
        {"role": "system", "content": ""},
        {"role": "user", "content": user_content}
    ]
    # before_chat
    await execute_plugins(action="before_chat", session_id=session_id, messages=messages, user_content=user_content, work_dir=work_dir)

    while True:
        if not session_flag.get(session_id, False):
            break

        # 1. 发送请求
        settings = await load_settings()
        client = AsyncOpenAI(base_url=settings.get("base_url"), api_key=settings.get("api_key"))
        response = await client.chat.completions.create(model=settings.get("model"), messages=messages, tools=tools, stream=True)

        # 2. 收集内容
        # before model
        await execute_plugins(action="before_model", session_id=session_id, messages=messages)
        assistant_content = ""
        assistant_tool_calls = []
        async for chunk in response:
            if not session_flag.get(session_id, False):
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
        await execute_plugins(action="after_model", session_id=session_id, messages=messages)

        # 3. 工具调用
        for tool_call in assistant_tool_calls:
            # before tool
            await execute_plugins(action="before_tool", session_id=session_id, messages=messages, tool_call=tool_call, work_dir=work_dir)
            # yield tool
            if messages[-1]["role"] != "tool" or messages[-1]["tool_call_id"] != tool_call["id"]:
                messages.append({"role": "tool", "tool_call_id": tool_call["id"], "content": "Can't find tool"})
            yield f"data: {json.dumps(messages[-1], ensure_ascii=False)}\n\n"
            # after tool
            await execute_plugins(action="after_tool", session_id=session_id, messages=messages, tool_call=tool_call, work_dir=work_dir)

        # 4. 判断结束
        if not assistant_tool_calls:
            break

    # after chat
    await execute_plugins(action="after_chat", session_id=session_id, messages=messages, user_content=user_content, assistant_content=assistant_content, work_dir=work_dir)
    # session end
    if session_id in session_flag:
        del session_flag[session_id]
    yield "data: [DONE]\n\n"


# 生命周期管理
@asynccontextmanager
async def lifespan(_app: FastAPI):
    await load_plugins()
    async with AsyncExitStack() as stack:
        for module in plugins:
            if hasattr(module, "lifespan"):
                try:
                    await stack.enter_async_context(module.lifespan(app=_app, tools=tools))
                except Exception as e:
                    logging.error(f"执行插件 {module.__name__} 的 lifespan 钩子函数失败: {e}", e)
        yield


app: FastAPI = FastAPI(lifespan=lifespan)


# 对话接口
@app.get("/chat/{id}")
async def chat_get(session_id: str = Path(..., alias="id"), message: str = Query(...), workdir: str = Query(...)):
    if session_id in session_flag:
        return JSONResponse(status_code=403, content={"success": False, "message": f"会话 {session_id} 正在处理中"})
    return StreamingResponse(chat_generator(session_id, message, workdir), media_type="text/event-stream")


# 对话接口
@app.post("/chat/{id}")
async def chat_post(session_id: str = Path(..., alias="id"), message: str = Body(...), workdir: str = Body(...)):
    if session_id in session_flag:
        return JSONResponse(status_code=403, content={"success": False, "message": f"会话 {session_id} 正在处理中"})
    return StreamingResponse(chat_generator(session_id, message, workdir), media_type="text/event-stream")


# 中断接口
@app.api_route("/interrupt/{id}", methods=["GET", "POST"])
async def interrupt(session_id: str = Path(..., alias="id")):
    if session_id in session_flag:
        session_flag[session_id] = False
        return {"success": True, "message": f"会话 {session_id} 已标记为中断"}
    return {"success": False, "message": f"会话 {session_id} 不存在或已结束"}
