import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import aiosqlite
import anyio
from fastapi import FastAPI, APIRouter, Path, HTTPException

DATA_DIR = "data"
DB_FILE = "data/session.db"
router: APIRouter = APIRouter(prefix="/session")


# 初始化数据库
async def init_db():
    await anyio.Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS t_message (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                request_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tool_calls TEXT,
                tool_call_id TEXT,
                work_dir TEXT NOT NULL,
                time DATETIME NOT NULL
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_session_id ON t_message(session_id)")
        await db.commit()


# 获取所有会话列表
@router.get("/list")
async def get_sessions():
    sessions = []
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        sql = """
            SELECT t_group.session_id, t_group.create_time, t_group.update_time, first_msg.content, last_msg.work_dir
            FROM (
                SELECT session_id, MIN(id) as first_id, MAX(id) as last_id, MIN(time) as create_time, MAX(time) as update_time
                FROM t_message
                GROUP BY session_id
            ) AS t_group
            JOIN t_message first_msg ON first_msg.id = t_group.first_id
            JOIN t_message last_msg ON last_msg.id = t_group.last_id
            ORDER BY t_group.update_time DESC
        """
        async with db.execute(sql) as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                sessions.append({
                    "id": row["session_id"],
                    "title": row["content"].replace("\n", " ")[:30],
                    "work_dir": row["work_dir"],
                    "create_time": row["create_time"],
                    "updated_at": row["update_time"],
                })
    return sessions


# 获取单个会话详情
@router.get("/{id}")
async def get_session(session_id: str = Path(..., alias="id")):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        sql = "SELECT role, content, tool_calls, tool_call_id, request_id, work_dir, time FROM t_message WHERE session_id = ? ORDER BY id ASC"
        async with db.execute(sql, (session_id,)) as cursor:
            rows = await cursor.fetchall()
            if not rows:
                raise HTTPException(status_code=404, detail="Session not found")
            messages = []
            last_work_dir = ""
            for row in rows:
                msg = dict(row)
                if msg.get("tool_calls"):
                    msg["tool_calls"] = json.loads(msg["tool_calls"])
                last_work_dir = msg["work_dir"]
                messages.append(msg)
    return {
        "id": session_id,
        "title": messages[0]["content"][:20],
        "work_dir": last_work_dir,
        "messages": messages
    }


# 删除会话
@router.delete("/{id}")
async def delete_session(session_id: str = Path(..., alias="id")):
    async with aiosqlite.connect(DB_FILE) as db:
        sql = "DELETE FROM t_message WHERE session_id = ?"
        await db.execute(sql, (session_id,))
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
        sql = """
            SELECT role, content
            FROM (
                SELECT id, role, content,
                       ROW_NUMBER() OVER (PARTITION BY request_id ORDER BY id ASC) as rank_asc,
                       ROW_NUMBER() OVER (PARTITION BY request_id ORDER BY id DESC) as rank_desc
                FROM t_message
                WHERE session_id = ?
            )
            WHERE rank_asc = 1 OR rank_desc = 1
            ORDER BY id ASC;
        """
        async with db.execute(sql, (session_id,)) as cursor:
            rows = await cursor.fetchall()
            loaded_messages = [dict(r) for r in rows]
    # 拼接开头系统消息和当前用户消息
    if loaded_messages:
        messages[:] = messages[:1] + loaded_messages + messages[1:]
        print(messages)


async def after_chat(session_id: str, messages: list, work_dir: str, **kwargs):
    last_user_index = next((i for i in range(len(messages) - 1, -1, -1) if messages[i]["role"] == "user"), -1)
    if last_user_index == -1:
        return
    request_id = uuid.uuid4().hex
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sql = "INSERT INTO t_message (session_id, request_id, role, content, tool_calls, tool_call_id, work_dir, time) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    records = [(
        session_id,
        request_id,
        msg["role"],
        msg["content"],
        json.dumps(msg.get("tool_calls")) if msg.get("tool_calls") else None,
        msg.get("tool_call_id"),
        work_dir,
        current_time
    ) for msg in messages[last_user_index:]]
    async with aiosqlite.connect(DB_FILE) as db:
        await db.executemany(sql, records)
        await db.commit()
