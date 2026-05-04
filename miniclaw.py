import importlib
import json
import logging
import pathlib
import sys
from contextlib import asynccontextmanager, AsyncExitStack

import anyio
from anthropic import AsyncAnthropic, AsyncStream
from anthropic.types.raw_message_stream_event import RawMessageStreamEvent
from fastapi import FastAPI, Path, Body, Query
from fastapi.responses import StreamingResponse
from starlette.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
SETTINGS_FILE = str(pathlib.Path.home() / ".miniclaw" / "settings.json")
PLUGINS_DIR_LIST = [str(pathlib.Path.home() / ".miniclaw" / "plugins"), "plugins"]
PLUGINS: list[object] = []
SESSIONS: set[str] = set()
pathlib.Path(SETTINGS_FILE).parent.mkdir(parents=True, exist_ok=True)
if not pathlib.Path(SETTINGS_FILE).exists():
    pathlib.Path(SETTINGS_FILE).write_text("{}", encoding="utf-8")


# 加载插件
async def load_plugins():
    PLUGINS.clear()
    loaded_plugin_names = set()
    # 遍历插件目录
    for plugins_dir in PLUGINS_DIR_LIST:
        plugins_dir = anyio.Path(plugins_dir)
        if not await plugins_dir.exists() or not await plugins_dir.is_dir():
            continue
        # 加入插件目录到 sys.path
        if plugins_dir not in sys.path:
            sys.path.append(str(plugins_dir))
        # 加载插件
        async for plugin_dir in plugins_dir.iterdir():
            if plugin_dir.name in loaded_plugin_names:
                continue
            plugin_path = plugins_dir / plugin_dir.name / "plugin.py"
            if not await plugin_path.is_file():
                continue
            module_name = f"{plugin_dir.name}.plugin"
            try:
                module = importlib.import_module(module_name)
                PLUGINS.append(module)
                loaded_plugin_names.add(plugin_dir.name)
            except Exception as e:
                logging.error(f"加载插件 {plugin_dir.name} 失败: {e}")
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
async def chat_generator(session_id: str, user_content: str, work_dir: str, messages: list):
    # session start
    SESSIONS.add(session_id)
    agents = [""]
    tools = []

    # before_chat
    await execute_plugins(action="before_chat", session_id=session_id, work_dir=work_dir, messages=messages, agents=agents, tools=tools, user_content=user_content)

    # 初始化客户端
    settings = {}
    if await anyio.Path(SETTINGS_FILE).exists():
        settings = json.loads(await anyio.Path(SETTINGS_FILE).read_text(encoding="utf-8"))
    model = settings.get("model", "")
    client: AsyncAnthropic = AsyncAnthropic(base_url=settings.get("base_url"), api_key=settings.get("api_key"))

    while True:
        # before model
        await execute_plugins(action="before_model", session_id=session_id, work_dir=work_dir, messages=messages, agents=agents, tools=tools)

        # 1. 发送请求
        response: AsyncStream[RawMessageStreamEvent] = await client.messages.create(messages=messages, tools=tools, system=agents[0], model=model, max_tokens=1 << 18, stream=True)

        # 2. 收集内容
        assistant_block_list = []
        messages += [{"role": "assistant", "content": assistant_block_list}]
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
    await load_plugins()
    async with AsyncExitStack() as stack:
        for module in PLUGINS:
            if hasattr(module, "lifespan"):
                try:
                    await stack.enter_async_context(module.lifespan(app=_app))
                except Exception as e:
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
