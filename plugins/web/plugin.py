import json
import logging
import pathlib
from contextlib import asynccontextmanager

import anyio
from fastapi import FastAPI, APIRouter, HTTPException, Query, Body
from starlette.responses import RedirectResponse
from starlette.staticfiles import StaticFiles

SETTINGS_FILE = "settings.json"
STATIC_DIR = str(pathlib.Path(__file__).parent / "static")
router = APIRouter()


@router.get("/")
async def index():
    return RedirectResponse(url="/static/chat.html")


@router.get("/dir/list")
async def list_directory(path: str = Query(...)):
    # 如果没有传入路径，默认显示用户目录
    target_path = anyio.Path(path) if path else await anyio.Path.home()
    if not await target_path.exists() or not await target_path.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")
    directories = []
    # 只列出目录
    async for child_path in target_path.iterdir():
        if await child_path.is_dir():
            directories.append({
                "name": child_path.name,
                "path": str(await child_path.absolute())
            })
    return {
        "current_path": str(await target_path.absolute()),
        "parent_path": str(await target_path.parent.absolute()),
        "directories": sorted(directories, key=lambda x: x['name'])
    }


@router.get("/setting")
async def get_settings():
    settings_file = anyio.Path(SETTINGS_FILE)
    if not await settings_file.exists():
        raise HTTPException(status_code=404, detail="Settings file not found")
    return json.loads(await settings_file.read_text(encoding="utf-8"))


@router.post("/setting")
async def save_settings(content: str = Body(...)):
    content = json.dumps(json.loads(content), ensure_ascii=False, indent=4)
    settings_file = anyio.Path(SETTINGS_FILE)
    await settings_file.write_text(content, encoding="utf-8")


@asynccontextmanager
async def lifespan(app: FastAPI, **kwargs):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(router)
    logging.info("Web plugin started")
    yield
    logging.info("Web plugin stopped")
