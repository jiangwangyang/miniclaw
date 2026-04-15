import json
import logging
import os
from contextlib import asynccontextmanager

AGENTS_FILE_LIST = ["AGENTS.md", os.path.expanduser("~/.miniclaw/AGENTS.md"), os.path.expanduser("~/.agents/AGENTS.md")]
agents: str = ""


async def load_agents():
    global agents
    for agents_file in AGENTS_FILE_LIST:
        if os.path.isfile(agents_file):
            with open(agents_file, "r", encoding="utf-8") as f:
                agents = f.read()
            break
    logging.info(f"Loaded agents: {json.dumps(agents, ensure_ascii=False)}")


@asynccontextmanager
async def lifespan(**kwargs):
    await load_agents()
    logging.info("Agents plugin started")
    yield
    logging.info("Agents plugin stopped")


async def before_chat(messages: list, **kwargs):
    if messages[0]["role"] == "system":
        messages[0]["content"] += f"{agents}\n\n"
