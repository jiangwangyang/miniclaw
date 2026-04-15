import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, APIRouter, Path
from fastapi.responses import JSONResponse

SESSIONS_DIR = "data/sessions"
router = APIRouter(prefix="/session")


# 加载会话消息
def load_session_messages(session_id: str) -> list:
    filepath = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []


# 获取所有会话列表
@router.get("/list")
async def get_sessions():
    sessions = []
    for filename in os.listdir(SESSIONS_DIR):
        filepath = os.path.join(SESSIONS_DIR, filename)
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


@router.get("/{id}")
async def get_session(session_id: str = Path(..., alias="id")):
    messages = load_session_messages(session_id)
    filtered_messages = [msg for msg in messages if msg.get('role') != 'system']
    return JSONResponse(content={"messages": filtered_messages})


@router.delete("/{id}")
async def delete_session(session_id: str = Path(..., alias="id")):
    filepath = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if os.path.exists(filepath):
        os.remove(filepath)
    return JSONResponse(content={"success": True, "message": "会话已删除"})


@asynccontextmanager
async def lifespan(app: FastAPI, **kwargs):
    app.include_router(router)
    logging.info("Session plugin started")
    yield
    logging.info("Session plugin stopped")


async def before_chat(session_id: str, messages: list, user_content: str, **kwargs):
    loaded_messages = load_session_messages(session_id)
    if loaded_messages:
        # 过滤消息 每个user消息后只跟一个assistant消息
        filtered_messages, assistant_msg = [], None
        for msg in loaded_messages:
            if msg["role"] == "user":
                if assistant_msg:
                    filtered_messages.append(assistant_msg)
                filtered_messages.append(msg)
            elif msg["role"] == "assistant":
                assistant_msg = msg
        if assistant_msg:
            filtered_messages.append(assistant_msg)
        # 拼接开头系统消息和当前用户消息
        messages[:] = [messages[0]] + filtered_messages + [{"role": "user", "content": user_content}]


async def after_chat(session_id: str, messages: list, **kwargs):
    if not os.path.exists(SESSIONS_DIR):
        os.makedirs(SESSIONS_DIR)
    with open(os.path.join(SESSIONS_DIR, f"{session_id}.json"), "w", encoding="utf-8") as f:
        json.dump([msg for msg in messages if msg["role"] != "system"], f, ensure_ascii=False)
