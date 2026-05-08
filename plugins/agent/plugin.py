import json
import logging
import pathlib
from contextlib import asynccontextmanager

import anyio
from fastapi import APIRouter, Body, FastAPI

AGENTS_FILE_LIST = [str(pathlib.Path.home() / ".miniclaw" / "AGENTS.md"), str(pathlib.Path.home() / ".agents" / "AGENTS.md")]
ROUTER = APIRouter()


async def load_agents():
    for agents_file in map(anyio.Path, AGENTS_FILE_LIST):
        if await agents_file.is_file():
            return await agents_file.read_text()
    return ""


@ROUTER.get("/agent")
async def get_agents():
    return {
        "content": await load_agents()
    }


@ROUTER.post("/agent")
async def save_agents(content: str = Body(...)):
    agents_file = anyio.Path(AGENTS_FILE_LIST[0])
    await agents_file.write_text(content, encoding="utf-8")


@asynccontextmanager
async def lifespan(app: FastAPI, **kwargs):
    app.include_router(ROUTER)
    logging.info("Agent plugin started")
    yield
    logging.info("Agent plugin stopped")


async def before_chat(agents: list, **kwargs):
    if agents and not agents[0]:
        content = await load_agents()
        logging.info(f"Loaded AGENTS.md: {json.dumps(content, ensure_ascii=False)}")
        agents[0] = content
