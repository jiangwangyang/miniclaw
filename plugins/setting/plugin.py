import json
import logging
import pathlib
from contextlib import asynccontextmanager

import anyio
from fastapi import FastAPI, APIRouter, Body

SETTINGS_FILE = str(pathlib.Path.home() / ".miniclaw" / "settings.json")
ROUTER = APIRouter(prefix="/setting")


async def init_settings_file():
    settings_file = anyio.Path(SETTINGS_FILE)
    await settings_file.parent.mkdir(parents=True, exist_ok=True)
    if not await settings_file.exists():
        await settings_file.write_text("{}", encoding="utf-8")


@ROUTER.get("")
async def get_settings():
    settings_file = anyio.Path(SETTINGS_FILE)
    content = await settings_file.read_text(encoding="utf-8") if await settings_file.exists() else ""
    return json.loads(content) if content else {}


@ROUTER.post("")
async def save_settings(content: dict = Body(...)):
    settings_file = anyio.Path(SETTINGS_FILE)
    await settings_file.parent.mkdir(parents=True, exist_ok=True)
    file_content = await settings_file.read_text(encoding="utf-8") if await settings_file.exists() else ""
    file_json = json.loads(file_content) if file_content else {}
    file_json.update(content)
    file_content = json.dumps(file_json, ensure_ascii=False, indent=4)
    await settings_file.write_text(file_content, encoding="utf-8")


@asynccontextmanager
async def lifespan(app: FastAPI, **kwargs):
    await init_settings_file()
    app.include_router(ROUTER)
    logging.info("Setting plugin started")
    yield
    logging.info("Setting plugin stopped")
