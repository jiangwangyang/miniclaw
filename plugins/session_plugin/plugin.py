import json
import logging
import os

from fastapi import FastAPI, APIRouter
from fastapi.responses import JSONResponse

# 会话存储目录
SESSION_DIR = "sessions"

# 初始化路由
router = APIRouter(prefix="")


def load_session_messages(id: str) -> list:
    session_file = os.path.join(SESSION_DIR, f"{id}.json")
    if os.path.exists(session_file):
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"加载会话文件失败 {id}: {e}")
    return []


# 获取所有会话列表
@router.get("/session/list")
async def get_sessions():
    sessions = []
    for filename in os.listdir(SESSION_DIR):
        if filename.endswith('.json'):
            id = filename[:-5]  # 去掉 .json
            file_path = os.path.join(SESSION_DIR, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    title = "对话"
                    for msg in data:
                        if msg.get('role') == 'user':
                            content = msg.get('content', '')
                            title = content[:20] + '...' if len(content) > 20 else content
                            break
                    sessions.append({
                        "id": id,
                        "title": title,
                        "updated_at": os.path.getmtime(file_path)
                    })
            except Exception as e:
                logging.error(f"读取会话文件失败 {filename}: {e}")
    # 按更新时间排序
    sessions.sort(key=lambda x: x['updated_at'], reverse=True)
    return JSONResponse(content=sessions)


@router.get("/session/{id}")
async def get_session(id: str):
    messages = load_session_messages(id)
    filtered_messages = [msg for msg in messages if msg.get('role') != 'system']
    return JSONResponse(content={"messages": filtered_messages})


async def start(app: FastAPI, **kwargs):
    # 创建会话目录
    if not os.path.exists(SESSION_DIR):
        os.makedirs(SESSION_DIR)
    # 注册路由
    app.include_router(router)
    # 记录日志
    logging.info("Session plugin started")


async def stop(app: FastAPI, **kwargs):
    # 记录日志
    logging.info("Session plugin stopped")


async def before_chat(id: str, messages: list, user_content: str, **kwargs):
    loaded_messages = load_session_messages(id)
    if loaded_messages:
        messages.clear()
        messages.extend(loaded_messages)
        return

    system_content = ""
    if os.path.exists("AGENTS.md"):
        try:
            with open("AGENTS.md", "r", encoding="utf-8") as f:
                system_content = f.read()
        except Exception as e:
            logging.error(f"读取 AGENTS.md 失败: {e}")
    messages.clear()
    messages.append({"role": "system", "content": system_content})
    messages.append({"role": "user", "content": user_content})
    return


async def after_chat(id: str, messages: list, user_content: str, assistant_content: str, **kwargs):
    session_file = os.path.join(SESSION_DIR, f"{id}.json")
    try:
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False)
    except Exception as e:
        logging.error(f"保存会话文件失败 {id}: {e}")


async def before_model(id: str, messages: list, **kwargs):
    pass


async def after_model(id: str, messages: list, **kwargs):
    pass


async def before_tool(id: str, messages: list, tool_call: dict, **kwargs):
    pass


async def after_tool(id: str, messages: list, tool_call: dict, tool_content: str, **kwargs):
    pass
