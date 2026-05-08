import importlib
import json
import logging
import pathlib
import sys
from contextlib import asynccontextmanager, AsyncExitStack
from types import ModuleType

import anyio
from anthropic import AsyncAnthropic, AsyncStream
from anthropic.types.raw_message_stream_event import RawMessageStreamEvent
from fastapi import FastAPI, Path, Body, Query
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionChunk
from starlette.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")


# 加载插件
def load_plugins(plugins_dir_list: list):
    plugins, loaded = [], set()
    for dir_path in map(pathlib.Path, plugins_dir_list):
        if not dir_path.is_dir():
            continue
        if dir_path not in sys.path:
            sys.path.append(str(dir_path))
        for subdir in dir_path.iterdir():
            if subdir.name in loaded or not (subdir / "plugin.py").is_file():
                continue
            try:
                plugins += [importlib.import_module(f"{subdir.name}.plugin")]
                loaded.add(subdir.name)
            except Exception as e:
                logging.error(f"加载插件 {subdir.name} 失败: {e}")
    logging.info(f"Loaded {len(loaded)} plugins: {", ".join(loaded)}")
    return plugins


# 常量
SETTINGS_FILE = str(pathlib.Path.home() / ".miniclaw" / "settings.json")
PLUGINS_DIR_LIST = [str(pathlib.Path.home() / ".miniclaw" / "plugins"), "plugins"]
PLUGINS: list[ModuleType] = load_plugins(PLUGINS_DIR_LIST)
SESSIONS: set[str] = set()


# 执行插件钩子函数
async def execute_plugins(action: str, **kwargs):
    for module in PLUGINS:
        action_function = getattr(module, action, None)
        if action_function:
            try:
                await action_function(**kwargs)
            except Exception as e:
                logging.error(f"执行插件 {module.__name__} 的 {action} 钩子函数失败: {e}")


# anthropic 消息转化为 openai 消息列表
def convert_anthropic_to_openai_messages(system_prompt: str, anthropic_messages: list):
    openai_messages = [{"role": "system", "content": system_prompt}]
    for anthropic_msg in anthropic_messages:
        if anthropic_msg["role"] == "user" and isinstance(anthropic_msg["content"], str):
            openai_messages += [{"role": "user", "content": anthropic_msg["content"]}]
        elif anthropic_msg["role"] == "user":
            openai_messages += [{"role": "tool", "tool_call_id": content_block["tool_use_id"], "content": content_block["content"]} for content_block in anthropic_msg["content"]]
        else:
            content, tool_calls = "", []
            for content_block in anthropic_msg["content"]:
                if content_block["type"] == "thinking":
                    content += f"<think>{content_block["thinking"]}</think>\n\n"
                elif content_block["type"] == "text":
                    content += content_block["text"]
                elif content_block["type"] == "tool_use":
                    tool_calls += [{
                        "id": content_block["id"],
                        "type": "function",
                        "function": {
                            "name": content_block["name"],
                            "arguments": json.dumps(content_block["input"], ensure_ascii=False)
                        }
                    }]
                else:
                    raise RuntimeError(f"Unknown content type: {content_block["type"]}")
            openai_messages += [{"role": "assistant", "content": content, "tool_calls": tool_calls}]
    return openai_messages


# anthropic 工具转为 openai 工具列表
def convert_anthropic_to_openai_tools(anthropic_tools: list):
    return [{
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"]
        }
    } for tool in anthropic_tools]


# 模型对话
async def chat_generator(session_id: str, user_content: str, work_dir: str, messages: list):
    # session start
    SESSIONS.add(session_id)
    agents = [""]
    tools = []

    # before_chat
    await execute_plugins(action="before_chat", session_id=session_id, work_dir=work_dir, messages=messages, agents=agents, tools=tools, user_content=user_content)

    # 初始化客户端
    settings_file = anyio.Path(SETTINGS_FILE)
    settings_file_content = await settings_file.read_text(encoding="utf-8") if await settings_file.exists() else ""
    settings = json.loads(settings_file_content) if settings_file_content else {}
    model, model_provider = settings.get("model", ""), settings.get("model_provider", "")
    model_provider_dict = settings.get("model_providers", {}).get(model_provider, {})
    api, base_url, api_key = model_provider_dict.get("api", "anthropic"), model_provider_dict.get("base_url", ""), model_provider_dict.get("api_key", "")
    anthropic_client: AsyncAnthropic = AsyncAnthropic(base_url=base_url, api_key=api_key)
    openai_client: AsyncOpenAI = AsyncOpenAI(base_url=base_url, api_key=api_key)

    while True:
        # before model
        await execute_plugins(action="before_model", session_id=session_id, work_dir=work_dir, messages=messages, agents=agents, tools=tools)

        # 1. 发送 anthropic 请求
        if api == "anthropic":
            response: AsyncStream[RawMessageStreamEvent] = await anthropic_client.messages.create(messages=messages, tools=tools, system=agents[0], model=model, max_tokens=1 << 17, stream=True)
            assistant_block_list = []
            async for event in response:
                if not session_id in SESSIONS:
                    assistant_block_list[:] = [_ for _ in assistant_block_list if _["type"] != "tool_use"]
                    break
                if event.type == "content_block_start":
                    if event.content_block.type == "thinking":
                        assistant_block_list += [{"type": "thinking", "thinking": "", "signature": ""}]
                        yield f"data: {json.dumps({"type": "thinking", "text": ""}, ensure_ascii=False)}\n\n"
                    elif event.content_block.type == "text":
                        assistant_block_list += [{"type": "text", "text": ""}]
                        yield f"data: {json.dumps({"type": "text", "text": ""}, ensure_ascii=False)}\n\n"
                    elif event.content_block.type == "tool_use":
                        assistant_block_list += [{"type": "tool_use", "id": event.content_block.id, "name": event.content_block.name, "input": ""}]
                        yield f"data: {json.dumps({"type": "tool_use", "text": f"{event.content_block.name}: "}, ensure_ascii=False)}\n\n"
                    else:
                        raise Exception
                elif event.type == "content_block_delta":
                    if event.delta.type == "thinking_delta":
                        assistant_block_list[-1]["thinking"] += event.delta.thinking
                        yield f"data: {json.dumps({"type": "delta", "text": event.delta.thinking}, ensure_ascii=False)}\n\n"
                    elif event.delta.type == "signature_delta":
                        assistant_block_list[-1]["signature"] += event.delta.signature
                    elif event.delta.type == "text_delta":
                        assistant_block_list[-1]["text"] += event.delta.text
                        yield f"data: {json.dumps({"type": "delta", "text": event.delta.text}, ensure_ascii=False)}\n\n"
                    elif event.delta.type == "input_json_delta":
                        assistant_block_list[-1]["input"] += event.delta.partial_json
                        yield f"data: {json.dumps({"type": "delta", "text": event.delta.partial_json}, ensure_ascii=False)}\n\n"
                    else:
                        raise Exception
                elif event.type == "content_block_stop":
                    if assistant_block_list[-1]["type"] == "tool_use":
                        assistant_block_list[-1]["input"] = json.loads(assistant_block_list[-1]["input"])
            messages += [{"role": "assistant", "content": assistant_block_list}]

        # 2. 发送 openai 请求
        elif api == "chat":
            openai_messages = convert_anthropic_to_openai_messages(agents[0], messages)
            openai_tools = convert_anthropic_to_openai_tools(tools)
            response: AsyncStream[ChatCompletionChunk] = await openai_client.chat.completions.create(messages=openai_messages, tools=openai_tools, model=model, max_tokens=1 << 17, stream=True)
            content, tool_calls = "", []
            yield f"data: {json.dumps({"type": "text", "text": ""}, ensure_ascii=False)}\n\n"
            async for chunk in response:
                if not session_id in SESSIONS:
                    tool_calls.clear()
                    break
                for choice in chunk.choices:
                    delta = choice.delta
                    if delta.content:
                        content += delta.content
                        yield f"data: {json.dumps({"type": "delta", "text": delta.content}, ensure_ascii=False)}\n\n"
                    for tool_call in delta.tool_calls or []:
                        if tool_call.index == len(tool_calls):
                            tool_calls += [{"id": tool_call.id, "type": "function", "function": {"name": tool_call.function.name, "arguments": tool_call.function.arguments or ""}}]
                            yield f"data: {json.dumps({"type": "tool_use", "text": f"{tool_call.function.name}: {tool_call.function.arguments or ""}"}, ensure_ascii=False)}\n\n"
                        elif tool_call.index < len(tool_calls):
                            tool_calls[tool_call.index]["function"]["arguments"] += tool_call.function.arguments or ""
                            yield f"data: {json.dumps({"type": "delta", "text": tool_call.function.arguments or ""}, ensure_ascii=False)}\n\n"
                        else:
                            raise RuntimeError(f"Tool index larger than current tool call length: {tool_call.index} {len(tool_calls)}")
            assistant_block_list = [{"type": "text", "text": content}, *[{"type": "tool_use", "id": tool_call["id"], "name": tool_call["function"]["name"], "input": json.loads(tool_call["function"]["arguments"])} for tool_call in tool_calls]]
            messages += [{"role": "assistant", "content": assistant_block_list}]

        else:
            raise RuntimeError(f"Unknown api type: {api}")

        # after model
        await execute_plugins(action="after_model", session_id=session_id, work_dir=work_dir, messages=messages, agents=agents, tools=tools)

        # 3. 判断结束
        if not [_ for _ in assistant_block_list if _["type"] == "tool_use"]:
            final_content = assistant_block_list[-1]["text"]
            break

        # 4. 工具调用
        tool_result_block_list = []
        messages += [{"role": "user", "content": tool_result_block_list}]
        for tool_use_block in [_ for _ in assistant_block_list if _["type"] == "tool_use"]:
            # before tool
            await execute_plugins(action="before_tool", session_id=session_id, work_dir=work_dir, messages=messages, agents=agents, tools=tools, tool_call=tool_use_block)

            # yield tool
            if not tool_result_block_list or tool_result_block_list[-1]["tool_use_id"] != tool_use_block["id"]:
                tool_result_block_list += [{"type": "tool_result", "tool_use_id": tool_use_block["id"], "content": "Can't find tool", "is_error": True}]
            yield f"data: {json.dumps({"type": "tool_result", "text": tool_result_block_list[-1]["content"]}, ensure_ascii=False)}\n\n"

            # after tool
            await execute_plugins(action="after_tool", session_id=session_id, work_dir=work_dir, messages=messages, agents=agents, tools=tools, tool_call=tool_use_block)

    # after chat
    await execute_plugins(action="after_chat", session_id=session_id, work_dir=work_dir, messages=messages, agents=agents, tools=tools, user_content=user_content, assistant_content=final_content)

    # session end
    yield "data: [DONE]\n\n"
    SESSIONS.discard(session_id)


# 生命周期管理
@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with AsyncExitStack() as stack:
        for module in PLUGINS:
            if hasattr(module, "lifespan"):
                try:
                    await stack.enter_async_context(module.lifespan(app=_app))
                except Exception as e:
                    if hasattr(e, 'exceptions'):
                        logging.error(f"执行插件 {module.__name__} 的 lifespan 钩子函数失败: {e.exceptions}")
                    else:
                        logging.error(f"执行插件 {module.__name__} 的 lifespan 钩子函数失败: {e}")
        yield


app: FastAPI = FastAPI(lifespan=lifespan)


# 对话接口
@app.get("/chat/{id}")
async def chat_get(session_id: str = Path(..., alias="id"), message: str = Query(...), workdir: str = Query(...), stream: bool = Query(...)):
    if session_id in SESSIONS:
        return JSONResponse(status_code=403, content=f"会话 {session_id} 正在处理中")
    messages = [{"role": "user", "content": message}]
    if stream:
        return StreamingResponse(chat_generator(session_id, message, workdir, messages), media_type="text/event-stream")
    async for _ in chat_generator(session_id, message, workdir, messages):
        pass
    return messages[-1]["content"][-1]


# 对话接口
@app.post("/chat/{id}")
async def chat_post(session_id: str = Path(..., alias="id"), message: str = Body(...), workdir: str = Body(...), stream: bool = Body(...)):
    if session_id in SESSIONS:
        return JSONResponse(status_code=403, content=f"会话 {session_id} 正在处理中")
    messages = [{"role": "user", "content": message}]
    if stream:
        return StreamingResponse(chat_generator(session_id, message, workdir, messages), media_type="text/event-stream")
    async for _ in chat_generator(session_id, message, workdir, messages):
        pass
    return messages[-1]["content"][-1]


# 中断接口
@app.api_route("/interrupt/{id}", methods=["GET", "POST"])
async def interrupt(session_id: str = Path(..., alias="id")):
    SESSIONS.discard(session_id)
