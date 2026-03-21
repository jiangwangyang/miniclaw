import json
import logging
import os

from fastapi import FastAPI, APIRouter, Path
from fastapi.responses import JSONResponse

# 会话存储目录
SESSION_DIR = "sessions"

# 初始化路由
router = APIRouter(prefix="")


# 加载会话消息
def load_session_messages(session_id: str) -> list:
    filepath = os.path.join(SESSION_DIR, f"{session_id}.json")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []


# 获取所有会话列表
@router.get("/session/list")
async def get_sessions():
    sessions = []
    for filename in os.listdir(SESSION_DIR):
        filepath = os.path.join(SESSION_DIR, filename)
        if filename.endswith('.json'):
            session_id = filename[:-5]
            messages = load_session_messages(session_id)
            title = "对话"
            for msg in messages:
                if msg.get('role') == 'user':
                    content = msg.get('content', '')
                    title = content[:20] + '...' if len(content) > 20 else content
                    break
            sessions.append({
                "id": session_id,
                "title": title,
                "updated_at": os.path.getmtime(filepath)
            })
    # 按更新时间排序
    sessions.sort(key=lambda x: x['updated_at'], reverse=True)
    return JSONResponse(content=sessions)


@router.get("/session/{id}")
async def get_session(session_id: str = Path(..., alias="id")):
    messages = load_session_messages(session_id)
    filtered_messages = [msg for msg in messages if msg.get('role') != 'system']
    return JSONResponse(content={"messages": filtered_messages})


async def before_application(app: FastAPI, **kwargs):
    # 创建会话目录
    if not os.path.exists(SESSION_DIR):
        os.makedirs(SESSION_DIR)
    # 注册路由
    app.include_router(router)
    # 记录日志
    logging.info("Session plugin started")


async def after_application(app: FastAPI, **kwargs):
    # 记录日志
    logging.info("Session plugin stopped")


async def before_chat(session_id: str, messages: list, user_content: str, **kwargs):
    loaded_messages = load_session_messages(session_id)
    if loaded_messages:
        messages.clear()
        messages.extend(loaded_messages)
        messages.append({"role": "user", "content": user_content})
        return


async def after_chat(session_id: str, messages: list, user_content: str, assistant_content: str, **kwargs):
    session_file = os.path.join(SESSION_DIR, f"{session_id}.json")
    with open(session_file, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False)


async def before_model(session_id: str, messages: list, **kwargs):
    pass


async def after_model(session_id: str, messages: list, **kwargs):
    pass


async def before_tool(session_id: str, messages: list, tool_call: dict, **kwargs):
    pass


async def after_tool(session_id: str, messages: list, tool_call: dict, tool_content: str, **kwargs):
    pass
