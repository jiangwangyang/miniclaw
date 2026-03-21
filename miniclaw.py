import importlib
import json
import logging
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
BASE_URL = "https://api.minimaxi.com/v1"
API_KEY = os.getenv("MINIMAX_API_KEY")
MODEL = "MiniMax-M2.7"
client: AsyncOpenAI = AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY)

# 将 plugins 目录加入 sys.path
PLUGIN_DIR = "plugins"
plugins_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), PLUGIN_DIR)
if plugins_dir not in sys.path:
    sys.path.insert(0, plugins_dir)

# 工具定义
tools = [{
    "type": "function",
    "function": {
        "name": "execute_command",
        "description": "执行本地命令",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的命令"},
                "encoding": {"type": "string", "description": "编码格式", "default": "utf-8"},
                "timeout": {"type": "integer", "description": "超时时间", "default": 30}
            },
            "required": ["command"],
        },
    }
}]


# 执行本地命令
def execute_command(command: str, encoding: str, timeout: int) -> str:
    try:
        result = subprocess.run(command, capture_output=True, shell=True, errors="replace", encoding=encoding, timeout=timeout)
        return f"RETURN_CODE: {result.returncode}\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    except Exception as e:
        return f"ERROR: {str(e)}"


# 加载 plugins 目录下的所有模块并执行对应函数
async def execute_plugins(action: str, **kwargs):
    for entry in os.listdir(plugins_dir):
        plugin_path = os.path.join(plugins_dir, entry)
        # 检查是否是目录且包含 plugin.py
        if os.path.isdir(plugin_path) and os.path.isfile(os.path.join(plugin_path, "plugin.py")):
            module_name = f"{entry}.plugin"
            try:
                module = importlib.import_module(module_name)
                # 执行对应函数
                func = getattr(module, action, None)
                if func:
                    try:
                        await func(**kwargs)
                    except Exception as e:
                        logging.error(e)
            except Exception as e:
                logging.error(f"加载插件 {entry} 失败: {e}")


# 生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    # start
    await execute_plugins(action="start", app=app)
    # 应用运行阶段
    yield
    # stop
    await execute_plugins(action="stop", app=app)


# 对话
async def chat_generator(id: str, user_content: str) -> AsyncGenerator[str, None]:
    messages = [{"role": "user", "content": user_content}]
    # before_chat
    await execute_plugins(action="before_chat", id=id, messages=messages, user_content=user_content)

    while True:
        # 1. 模型生成
        response = await client.chat.completions.create(model=MODEL, messages=messages, tools=tools, stream=True)

        # 2. 收集内容
        # before model
        await execute_plugins(action="before_model", id=id, messages=messages)
        assistant_content = ""
        assistant_tool_calls = []
        async for chunk in response:
            chunk = json.loads(json.dumps(chunk, default=lambda o: o.__dict__))
            delta = chunk["choices"][0]["delta"]
            # SSE 流式响应
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            # 收集工具调用
            for tool_call in delta["tool_calls"] or []:
                if tool_call["index"] < len(assistant_tool_calls):
                    assistant_tool_calls[tool_call["index"]]["function"]["arguments"] += tool_call["function"]["arguments"]
                else:
                    assistant_tool_calls.append(tool_call)
            # 收集普通文本
            if delta["content"]:
                assistant_content += delta["content"]
        messages.append({"role": "assistant", "content": assistant_content, "tool_calls": assistant_tool_calls})
        # after model
        await execute_plugins(action="after_model", id=id, messages=messages)

        # 3. 处理工具调用
        for tool_call in assistant_tool_calls:
            # before tool
            await execute_plugins(action="before_tool", id=id, messages=messages, tool_call=tool_call)
            try:
                args = json.loads(tool_call["function"]["arguments"])
                tool_content = execute_command(args.get("command", ""), args.get("encoding", "utf-8"), args.get("timeout", 30))
            except json.JSONDecodeError:
                tool_content = "Error: Invalid JSON arguments."
            tool_message = {"role": "tool", "tool_call_id": tool_call["id"], "content": tool_content}
            yield f"data: {json.dumps(tool_message, ensure_ascii=False)}\n\n"
            messages.append(tool_message)
            # after tool
            await execute_plugins(action="after_tool", id=id, messages=messages, tool_call=tool_call, tool_content=tool_content)

        # 4. 判断结束
        if not assistant_tool_calls:
            break
    yield "data: [DONE]\n\n"
    # after chat
    await execute_plugins(action="after_chat", id=id, messages=messages, user_content=user_content, assistant_content=assistant_content)


app: FastAPI = FastAPI(lifespan=lifespan)


# 对话接口
@app.api_route("/chat", methods=["GET", "POST"])
async def chat(id: str, message: str):
    return StreamingResponse(chat_generator(id, message), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("miniclaw:app", host="0.0.0.0", port=11223, reload=True)
