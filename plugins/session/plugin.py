import json
import logging
from contextlib import asynccontextmanager

import aiosqlite
from fastapi import FastAPI, APIRouter, Path, HTTPException

DB_FILE = "data/session.db"
router: APIRouter = APIRouter(prefix="/session")


# 初始化数据库
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("CREATE TABLE IF NOT EXISTS t_session (id TEXT PRIMARY KEY, title TEXT, work_dir TEXT, create_time DATETIME DEFAULT CURRENT_TIMESTAMP, update_time DATETIME DEFAULT CURRENT_TIMESTAMP)")
        await db.execute("CREATE TABLE IF NOT EXISTS t_message (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, time DATETIME DEFAULT CURRENT_TIMESTAMP, role TEXT, content TEXT, tool_calls TEXT, tool_call_id TEXT, FOREIGN KEY (session_id) REFERENCES t_session (id) ON DELETE CASCADE)")
        await db.commit()


# 获取所有会话列表
@router.get("/list")
async def get_sessions():
    sessions = []
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        sql = "SELECT id, title, work_dir, create_time, update_time FROM t_session ORDER BY update_time DESC"
        async with db.execute(sql) as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                sessions.append({
                    "id": row["id"],
                    "title": row["title"],
                    "work_dir": row["work_dir"],
                    "create_time": row["create_time"],
                    "updated_at": row["update_time"],
                })
    return sessions


@router.get("/{id}")
async def get_session(session_id: str = Path(..., alias="id")):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        sql = "SELECT id, title, work_dir, create_time, update_time FROM t_session WHERE id = ?"
        async with db.execute(sql, (session_id,)) as cursor:
            rows = await cursor.fetchall()
            if not rows:
                raise HTTPException(status_code=404, detail="Session not found")
            session = dict(rows[0])
        sql = "SELECT role, content, tool_calls, tool_call_id FROM t_message WHERE session_id = ? AND role != 'system' ORDER BY time ASC"
        async with db.execute(sql, (session_id,)) as cursor:
            rows = await cursor.fetchall()
            messages = []
            for row in rows:
                msg = dict(row)
                if msg.get("tool_calls"):
                    msg["tool_calls"] = json.loads(msg["tool_calls"])
                messages.append(msg)
    return {
        "id": session["id"],
        "title": session["title"],
        "work_dir": session["work_dir"],
        "create_time": session["create_time"],
        "updated_at": session["update_time"],
        "messages": messages
    }


@router.delete("/{id}")
async def delete_session(session_id: str = Path(..., alias="id")):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM t_session WHERE id = ?", (session_id,))
        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI, **kwargs):
    await init_db()
    app.include_router(router)
    logging.info("Session plugin started")
    yield
    logging.info("Session plugin stopped")


async def before_chat(session_id: str, messages: list, user_content: str, **kwargs):
    # 从数据库加载历史
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        sql = "SELECT role, content FROM t_message WHERE session_id = ? ORDER BY time ASC"
        async with db.execute(sql, (session_id,)) as cursor:
            rows = await cursor.fetchall()
            loaded_messages = [dict(r) for r in rows]
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


async def after_chat(session_id: str, messages: list, user_content: str, work_dir: str, **kwargs):
    title = user_content[:20]
    async with aiosqlite.connect(DB_FILE) as db:
        # 1. session 更新或插入
        sql = "INSERT INTO t_session (id, title, work_dir) VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET work_dir=?, update_time=CURRENT_TIMESTAMP"
        await db.execute(sql, (session_id, title, work_dir, work_dir))

        # 2. 获取数据库中已有的消息数量，实现增量对比
        sql = "SELECT COUNT(*) FROM t_message WHERE session_id = ?"
        async with db.execute(sql, (session_id,)) as cursor:
            row = await cursor.fetchone()
            existing_count = row[0] if row else 0

        # 3. 过滤掉 system 消息后，只插入索引大于 existing_count 的新消息
        new_messages = [m for m in messages if m["role"] != "system"][existing_count:]
        for msg in new_messages:
            tool_calls_str = json.dumps(msg.get("tool_calls")) if msg.get("tool_calls") else None
            sql = "INSERT INTO t_message (session_id, role, content, tool_calls, tool_call_id, time) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)"
            await db.execute(sql, (session_id, msg["role"], msg.get("content", ""), tool_calls_str, msg.get("tool_call_id")))

        await db.commit()
