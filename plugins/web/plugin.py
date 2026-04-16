import logging
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, APIRouter, HTTPException, Query
from starlette.responses import RedirectResponse
from starlette.staticfiles import StaticFiles

STATIC_PATH = pathlib.Path(__file__).parent / "static"
router = APIRouter()


@router.get("/")
async def index():
    return RedirectResponse(url="/static/chat.html")


@router.get("/dir/list")
async def list_directory(path: str = Query(...)):
    # 如果没有传入路径，默认显示用户目录
    target_path = pathlib.Path(path) if path else pathlib.Path.home()
    if not target_path.exists() or not target_path.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")
    directories = []
    # 只列出目录
    for entry in target_path.iterdir():
        if entry.is_dir():
            directories.append({
                "name": entry.name,
                "path": str(entry.absolute())
            })
    return {
        "current_path": str(target_path.absolute()),
        "parent_path": str(target_path.parent.absolute()),
        "directories": sorted(directories, key=lambda x: x['name'])
    }


@asynccontextmanager
async def lifespan(app: FastAPI, **kwargs):
    app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")
    app.include_router(router)
    logging.info("Web plugin started")
    yield
    logging.info("Web plugin stopped")
