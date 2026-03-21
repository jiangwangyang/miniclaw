import logging
from pathlib import Path

from fastapi import FastAPI, APIRouter
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# 获取 static 目录路径
STATIC_DIR = Path(__file__).parent / "static"

# 初始化路由
router = APIRouter(prefix="")


# 首页
@router.get("/")
@router.get("/index")
@router.get("/index.html")
async def index():
    index_path = STATIC_DIR / "index.html"
    return FileResponse(index_path, media_type="text/html")


async def before_application(app: FastAPI, **kwargs):
    # 挂载静态文件目录到 /static
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(router)
    logging.info("Web plugin started")


async def after_application(app: FastAPI, **kwargs):
    logging.info("Web plugin stopped")


async def before_chat(session_id: str, messages: list, user_content: str, **kwargs):
    pass


async def after_chat(session_id: str, messages: list, user_content: str, assistant_content: str, **kwargs):
    pass


async def before_model(session_id: str, messages: list, **kwargs):
    pass


async def after_model(session_id: str, messages: list, **kwargs):
    pass


async def before_tool(session_id: str, messages: list, tool_call: dict, **kwargs):
    pass


async def after_tool(session_id: str, messages: list, tool_call: dict, tool_content: str, **kwargs):
    pass
