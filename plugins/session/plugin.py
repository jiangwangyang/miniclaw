import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import aiosqlite
import anyio
from fastapi import FastAPI, APIRouter, Path, HTTPException

DB_FILE = "data/session.db"
router: APIRouter = APIRouter(prefix="/session")


# 初始化数据库
async def init_db():
    await anyio.Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_FILE) as db:
        # 会话表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS t_session (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                work_dir TEXT NOT NULL,
                create_time DATETIME NOT NULL,
                update_time DATETIME NOT NULL
            )
        """)
        # 消息表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS t_message (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                time DATETIME NOT NULL,
                FOREIGN KEY (session_id) REFERENCES t_session(id) ON DELETE CASCADE
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_message_session ON t_message(session_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_message_request ON t_message(request_id)")
        await db.commit()


# 获取所有会话列表
@router.get("/list")
async def get_sessions():
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        # 直接查询 t_session 表，按更新时间倒序
        sql = """
            SELECT id, title, work_dir, create_time, update_time
            FROM t_session
            ORDER BY update_time DESC
        """
        async with db.execute(sql) as cursor:
            rows = await cursor.fetchall()
    return [{
        "id": row["id"],
        "title": row["title"],
        "work_dir": row["work_dir"],
        "create_time": row["create_time"],
        "updated_at": row["update_time"],
    } for row in rows]


# 获取单个会话详情
@router.get("/{id}")
async def get_session(session_id: str = Path(..., alias="id")):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        # 查询会话基本信息
        sql = "SELECT id, title, work_dir FROM t_session WHERE id = ?"
        async with db.execute(sql, (session_id,)) as cursor:
            sess = await cursor.fetchone()
            if not sess:
                raise HTTPException(status_code=404, detail="Session not found")
        # 查询所有消息，按 id 升序
        sql = "SELECT role, content, time FROM t_message WHERE session_id = ? ORDER BY id ASC"
        async with db.execute(sql, (session_id,)) as cursor:
            rows = await cursor.fetchall()
    messages = [{
        "role": row["role"],
        "content": json.loads(row["content"]),
        "time": row["time"]
    } for row in rows]
    return {
        "id": sess["id"],
        "title": sess["title"],
        "work_dir": sess["work_dir"],
        "messages": messages
    }


# 删除会话
@router.delete("/{id}")
async def delete_session(session_id: str = Path(..., alias="id")):
    async with aiosqlite.connect(DB_FILE) as db:
        # 由于外键设置了 ON DELETE CASCADE，只需删除会话记录
        sql = "DELETE FROM t_session WHERE id = ?"
        await db.execute(sql, (session_id,))
        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI, **kwargs):
    await init_db()
    app.include_router(router)
    logging.info("Session plugin started")
    yield
    logging.info("Session plugin stopped")


async def before_chat(session_id: str, messages: list, **kwargs):
    # 从数据库加载历史
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        sql = """
            SELECT id, role, content
            FROM (
                SELECT id, role, content, request_id,
                       ROW_NUMBER() OVER (PARTITION BY request_id ORDER BY id ASC) AS rn_asc,
                       ROW_NUMBER() OVER (PARTITION BY request_id ORDER BY id DESC) AS rn_desc
                FROM t_message
                WHERE session_id = ?
            ) sub
            WHERE rn_asc = 1 OR rn_desc = 1
            ORDER BY id ASC
        """
        async with db.execute(sql, (session_id,)) as cursor:
            rows = await cursor.fetchall()
            history_messages = [{
                "id": row["id"],
                "role": row["role"],
                "content": json.loads(row["content"])
            } for row in rows]
    # 在消息列表前增加历史消息
    if history_messages:
        messages[:0] = history_messages


async def after_chat(session_id: str, work_dir: str, messages: list, user_content: str, **kwargs):
    # 1 找出本次对话消息
    new_messages = [msg for msg in messages if not "id" in msg]
    request_id = uuid.uuid4().hex
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 2 准备插入 t_message 的记录
    records = [(
        request_id,
        session_id,
        msg["role"],
        json.dumps(msg["content"], ensure_ascii=False),
        current_time
    ) for msg in new_messages]

    # 3. 写入数据库
    async with aiosqlite.connect(DB_FILE) as db:
        # 先检查会话是否存在
        async with db.execute("SELECT id FROM t_session WHERE id = ?", (session_id,)) as cursor:
            exists = await cursor.fetchone() is not None
        # 如果会话存在 创建新会话：从第一条用户消息中提取文本作为标题
        if exists:
            sql = "UPDATE t_session SET update_time = ? WHERE id = ?"
            await db.execute(sql, (current_time, session_id))
        # 如果会话不存在 更新会话的 update_time
        else:
            title = "新对话" if not user_content else user_content[:20]
            sql = "INSERT INTO t_session (id, title, work_dir, create_time, update_time) VALUES (?, ?, ?, ?, ?)"
            await db.execute(sql, (session_id, title, work_dir, current_time, current_time))
        # 插入消息
        sql = "INSERT INTO t_message (request_id, session_id, role, content, time) VALUES (?, ?, ?, ?, ?)"
        await db.executemany(sql, records)
        await db.commit()
