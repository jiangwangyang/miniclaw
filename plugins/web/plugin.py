import logging
import pathlib
from contextlib import asynccontextmanager

import anyio
from fastapi import FastAPI, APIRouter, HTTPException, Query
from starlette.responses import RedirectResponse
from starlette.staticfiles import StaticFiles

TMP_DIR = "/tmp"
STATIC_DIR = str(pathlib.Path(__file__).parent / "static")
ROUTER = APIRouter()


@ROUTER.get("/")
async def index():
    return RedirectResponse(url="/static/chat.html")


@ROUTER.get("/dir/list")
async def list_directory(path: str = Query(...)):
    # 如果没有传入路径，默认使用tmp目录
    if path:
        target_path = anyio.Path(path)
        if not await target_path.exists() or not await target_path.is_dir():
            raise HTTPException(status_code=404, detail="Directory not found")
    else:
        target_path = anyio.Path(TMP_DIR)
        await target_path.mkdir(parents=True, exist_ok=True)
    # 只列出目录
    directories = [{
        "name": child_path.name,
        "path": str(await child_path.absolute())
    } async for child_path in target_path.iterdir() if await child_path.is_dir()]
    return {
        "current_path": str(await target_path.absolute()),
        "parent_path": str(await target_path.parent.absolute()),
        "directories": sorted(directories, key=lambda x: x['name'])
    }


@asynccontextmanager
async def lifespan(app: FastAPI, **kwargs):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(ROUTER)
    logging.info("Web plugin started")
    yield
    logging.info("Web plugin stopped")
