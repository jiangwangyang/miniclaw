import json
import logging
import os

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


async def before_application(**kwargs):
    await load_agents()
    logging.info("System prompt plugin started")


async def after_application(**kwargs):
    logging.info("System prompt plugin stopped")


async def before_chat(messages: list, **kwargs):
    if messages[0]["role"] == "system":
        messages[0]["content"] += f"{agents}\n\n"


async def after_chat(**kwargs):
    pass


async def before_model(**kwargs):
    pass


async def after_model(**kwargs):
    pass


async def before_tool(**kwargs):
    pass


async def after_tool(**kwargs):
    pass
