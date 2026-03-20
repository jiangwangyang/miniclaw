import importlib
import json
import logging
import os
import subprocess
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


# 加载 plugins 目录下的所有模块并执行对应函数
async def execute_plugins(action: str, **kwargs):
    for filename in os.listdir("plugins"):
        if filename.endswith(".py") and filename != "__init__.py":
            module_name = f"plugins.{filename[:-3]}"
            module = importlib.import_module(module_name)
            # 执行对应函数
            func = getattr(module, action, None)
            if func:
                try:
                    await func(**kwargs)
                except Exception as e:
                    logging.error(e)


# 生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行插件
    await execute_plugins(action="start", app=app)
    # 应用运行阶段
    yield
    # 结束时执行插件
    await execute_plugins(action="stop", app=app)


# 执行本地命令
def execute_command(command: str, encoding: str, timeout: int) -> str:
    try:
        result = subprocess.run(command, capture_output=True, shell=True, errors="replace", encoding=encoding, timeout=timeout)
        return f"RETURN_CODE: {result.returncode}\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    except Exception as e:
        return f"ERROR: {str(e)}"


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


# 对话
async def chat_generator(id: str, user_content: str) -> AsyncGenerator[str, None]:
    # 确保 sessions 目录存在
    if not os.path.exists("sessions"):
        os.makedirs("sessions")
    session_file = os.path.join("sessions", f"{id}.json")
    # 加载 messages
    if os.path.exists(session_file):
        with open(session_file, "r", encoding="utf-8") as f:
            messages = json.load(f)
    else:
        system_content = ""
        if os.path.exists("AGENTS.md"):
            with open("AGENTS.md", "r", encoding="utf-8") as f:
                system_content = f.read()
        messages = [{"role": "system", "content": system_content}]
    # 添加用户消息
    messages.append({"role": "user", "content": user_content})
    await execute_plugins(action="before_chat", messages=messages, user_content=user_content)

    while True:
        # 1. 模型生成
        response = await client.chat.completions.create(model=MODEL, messages=messages, tools=tools, stream=True)

        # 2. 收集内容
        await execute_plugins(action="before_model", messages=messages)
        assistant_content = ""
        assistant_tool_calls = []
        async for chunk in response:
            chunk = json.loads(json.dumps(chunk, default=lambda o: o.__dict__))
            # SSE 流式响应
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            # 收集工具调用
            delta = chunk["choices"][0]["delta"]
            for tool_call in delta["tool_calls"] or []:
                if tool_call["index"] < len(assistant_tool_calls):
                    assistant_tool_calls[tool_call["index"]]["function"]["arguments"] += tool_call["function"]["arguments"]
                else:
                    assistant_tool_calls.append(tool_call)
            # 收集普通文本
            if delta["content"]:
                assistant_content += delta["content"]
        messages.append({
            "role": "assistant",
            "content": assistant_content,
            "tool_calls": assistant_tool_calls
        })
        await execute_plugins(action="after_model", messages=messages)

        # 3. 处理工具调用
        for tool_call in assistant_tool_calls:
            await execute_plugins(action="before_tool", messages=messages, tool_call=tool_call)
            try:
                args = json.loads(tool_call["function"]["arguments"])
                tool_response = execute_command(args.get("command", ""), args.get("encoding", "utf-8"), args.get("timeout", 30))
            except json.JSONDecodeError:
                tool_response = "Error: Invalid JSON arguments."
            tool_response_message = {
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": tool_response
            }
            yield f"data: {json.dumps(tool_response_message, ensure_ascii=False)}\n\n"
            messages.append(tool_response_message)
            await execute_plugins(action="after_tool", messages=messages, tool_call=tool_call, tool_response=tool_response)

        # 4. 判断结束
        if not assistant_tool_calls:
            break
    yield "data: [DONE]\n\n"
    # 保存消息
    with open(session_file, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=4)
    await execute_plugins(action="after_chat", messages=messages, user_content=user_content, assistant_content=assistant_content)


app: FastAPI = FastAPI(lifespan=lifespan)


# 对话接口
@app.api_route("/chat", methods=["GET", "POST"])
async def chat(id: str, message: str):
    return StreamingResponse(chat_generator(id, message), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("miniclaw:app", host="0.0.0.0", port=11223, reload=True)
