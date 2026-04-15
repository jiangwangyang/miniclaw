import logging
import pathlib
import tkinter as tk
from contextlib import asynccontextmanager
from tkinter import filedialog

from fastapi import FastAPI, APIRouter
from starlette.responses import RedirectResponse
from starlette.staticfiles import StaticFiles

STATIC_PATH = pathlib.Path(__file__).parent / "static"
router = APIRouter()


@router.get("/")
async def index():
    return RedirectResponse(url="/static/chat.html")


@router.get("/dir/select")
async def select_directory():
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    root.attributes('-topmost', True)  # 置顶对话框
    path = filedialog.askdirectory()
    root.destroy()
    return {
        "path": path
    }


@asynccontextmanager
async def lifespan(app: FastAPI, **kwargs):
    app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")
    app.include_router(router)
    logging.info("Web plugin started")
    yield
    logging.info("Web plugin stopped")
