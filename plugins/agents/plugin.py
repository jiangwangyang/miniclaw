import json
import logging
import pathlib
from contextlib import asynccontextmanager

import anyio
from fastapi import APIRouter, Body, FastAPI

AGENTS_FILE_LIST = ["AGENTS.md", str(pathlib.Path.home() / ".agents" / "AGENTS.md")]
agents: str = ""
router: APIRouter = APIRouter()


async def load_agents():
    global agents
    for agents_file in AGENTS_FILE_LIST:
        agents_file = anyio.Path(agents_file)
        if await agents_file.is_file():
            agents = await agents_file.read_text()
            logging.info(f"Loaded agents: {json.dumps(agents, ensure_ascii=False)}")
            break


@router.get("/agents")
async def get_agents():
    return {
        "content": agents
    }


@router.post("/agents")
async def save_agents(content: str = Body(...)):
    agents_file = anyio.Path("AGENTS.md")
    await agents_file.write_text(content, encoding="utf-8")
    await load_agents()


@asynccontextmanager
async def lifespan(app: FastAPI, **kwargs):
    await load_agents()
    app.include_router(router)
    logging.info("Agents plugin started")
    yield
    logging.info("Agents plugin stopped")


async def before_chat(messages: list, **kwargs):
    if messages[0]["role"] == "system":
        messages[0]["content"] += f"{agents}\n\n"
