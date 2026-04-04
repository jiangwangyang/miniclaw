import importlib
import json
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from starlette.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
BASE_URL = "https://api.minimaxi.com/v1"
API_KEY = os.getenv("MINIMAX_API_KEY")
MODEL = "MiniMax-M2.7"
PLUGINS_DIR_LIST = ["plugins/", "external_plugins/", os.path.expanduser("~/.miniclaw/plugins/")]
client: AsyncOpenAI = AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY)
plugins: list[object] = []
tools: list[object] = []
session_flag: dict[str, bool] = {}


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
    logging.info(f"Loaded plugins: {plugins}")


# 执行插件钩子函数
async def execute_plugins(action: str, **kwargs):
    for module in plugins:
        func = getattr(module, action, None)
        if func:
            try:
                await func(**kwargs)
            except Exception as e:
                logging.error(f"执行插件 {module.__name__} 的 {action} 钩子函数失败: {e}")


# 生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    # load plugins
    await load_plugins()
    # before application
    await execute_plugins(action="before_application", app=app, tools=tools)
    # 应用运行阶段
    yield
    # after application
    await execute_plugins(action="after_application", app=app)


app: FastAPI = FastAPI(lifespan=lifespan)


# 对话接口
@app.api_route("/chat", methods=["GET", "POST"])
async def chat(session_id: str = Query(..., alias="id"), user_content: str = Query(..., alias="message")):
    if session_id in session_flag:
        return JSONResponse(status_code=403, content={"success": False, "message": f"会话 {session_id} 正在处理中"})

    async def chat_generator():
        # session start
        session_flag[session_id] = True
        assistant_content = ""
        messages = [
            {"role": "system", "content": ""},
            {"role": "user", "content": user_content}
        ]
        # before_chat
        await execute_plugins(action="before_chat", session_id=session_id, messages=messages, user_content=user_content)

        while True:
            if not session_flag.get(session_id, False):
                break

            # 1. 发送请求
            response = await client.chat.completions.create(model=MODEL, messages=messages, tools=tools, stream=True)

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
                await execute_plugins(action="before_tool", session_id=session_id, messages=messages, tool_call=tool_call)
                # yield tool
                if messages[-1]["role"] != "tool" or messages[-1]["tool_call_id"] != tool_call["id"]:
                    messages.append({"role": "tool", "tool_call_id": tool_call["id"], "content": "Can't find tool"})
                yield f"data: {json.dumps(messages[-1], ensure_ascii=False)}\n\n"
                # after tool
                await execute_plugins(action="after_tool", session_id=session_id, messages=messages, tool_call=tool_call)

            # 4. 判断结束
            if not assistant_tool_calls:
                break

        # after chat
        await execute_plugins(action="after_chat", session_id=session_id, messages=messages, user_content=user_content, assistant_content=assistant_content)
        # session end
        if session_id in session_flag:
            del session_flag[session_id]
        yield "data: [DONE]\n\n"

    return StreamingResponse(chat_generator(), media_type="text/event-stream")


# 中断接口
@app.api_route("/interrupt", methods=["GET", "POST"])
async def interrupt(session_id: str = Query(..., alias="id")):
    if session_id in session_flag:
        session_flag[session_id] = False
        return {"success": True, "message": f"会话 {session_id} 已标记为中断"}
    return {"success": False, "message": f"会话 {session_id} 不存在或已结束"}
