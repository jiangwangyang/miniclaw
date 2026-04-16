import logging
from contextlib import asynccontextmanager
from datetime import datetime

import anyio

MEMORY_DIR = "data/memory"
MEMORY_FILE = "data/memory/MEMORY.md"


@asynccontextmanager
async def lifespan(**kwargs):
    logging.info("Memory plugin started")
    yield
    logging.info("Memory plugin stopped")


async def before_chat(messages: list, **kwargs):
    if messages[0]["role"] == "system":
        messages[0]["content"] += f"---\nHistory memory: {str(await anyio.Path(MEMORY_FILE).absolute())}\n---\n\n"


async def after_chat(user_content: str, assistant_content: str, **kwargs):
    await anyio.Path(MEMORY_DIR).mkdir(parents=True, exist_ok=True)
    async with await anyio.Path(MEMORY_FILE).open(mode="a", encoding="utf-8") as f:
        await f.write(f"{user_content}\n\n{assistant_content}\n\n---\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n---\n\n")
