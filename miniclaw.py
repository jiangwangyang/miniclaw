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
AGENTS_FILE_LIST = ["AGENTS.md", os.path.expanduser("~/.miniclaw/AGENTS.md"), os.path.expanduser("~/.agents/AGENTS.md")]
SKILLS_DIR_LIST = ["skills/", os.path.expanduser("~/.miniclaw/skills/"), os.path.expanduser("~/.agents/skills/")]
PLUGINS_DIR_LIST = ["plugins/", os.path.expanduser("~/.miniclaw/plugins/"), os.path.expanduser("~/.agents/miniclaw_plugins/")]
client: AsyncOpenAI = AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY)
agents: str = ""
tools: list[object] = []
skills: list[dict[str, str]] = []
plugins: list[object] = []
session_flag: dict[str, bool] = {}


# 加载AGENTS文件
async def load_agents():
    global agents
    for agents_file in AGENTS_FILE_LIST:
        if os.path.isfile(agents_file):
            with open(agents_file, "r", encoding="utf-8") as f:
                agents = f.read()
            break
    logging.info(f"Loaded agents: {json.dumps(agents, ensure_ascii=False)}")


# 加载技能
async def load_skills():
    skills.clear()
    loaded_skill_names = set()
    # 遍历技能目录
    for skills_dir in SKILLS_DIR_LIST:
        if not os.path.exists(skills_dir):
            continue
        # 遍历技能
        for entry in os.listdir(skills_dir):
            if entry in loaded_skill_names:
                continue
            skill_file_path = os.path.join(skills_dir, entry, "SKILL.md")
            if not os.path.isfile(skill_file_path):
                continue
            # 尝试读取 SKILL.md 提取 name 和 description
            with open(skill_file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) >= 4 and lines[0].strip() == "---" and lines[1].strip().startswith("name:") and lines[2].strip().startswith("description:"):
                name = lines[1].strip()[5:].strip()
                description = lines[2].strip()[12:].strip()
                if name == entry:
                    skills.append({"name": name, "description": description, "path": os.path.abspath(skill_file_path)})
                    loaded_skill_names.add(name)
    logging.info(f"Loaded skills: {json.dumps(skills, ensure_ascii=False)}")


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
    await load_agents()
    await load_skills()
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
        system_content = f"# Available Skills\n{json.dumps(skills, ensure_ascii=False)}\n\n{agents}"
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content}
        ]
        # before_chat
        await execute_plugins(action="before_chat", session_id=session_id, messages=messages, user_content=user_content)

        while True:
            if not session_flag.get(session_id, False):
                break

            # 1. 模型生成
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

            # 3. 处理工具调用
            for tool_call in assistant_tool_calls:
                # before tool
                await execute_plugins(action="before_tool", session_id=session_id, messages=messages, tool_call=tool_call)
                if messages[-1]["role"] == "tool" and messages[-1]["tool_call_id"] == tool_call["id"]:
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
