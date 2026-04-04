import json
import logging
import os
from datetime import datetime

MEMORY_DIR = "data/memory"
MEMORY_FILE = "data/memory/MEMORY.md"


async def before_application(**kwargs):
    if not os.path.exists(MEMORY_DIR):
        os.makedirs(MEMORY_DIR)
    logging.info("Memory plugin started")


async def after_application(**kwargs):
    logging.info("Memory plugin stopped")


async def before_chat(**kwargs):
    pass


async def after_chat(user_content: str, assistant_content: str, **kwargs):
    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\nUser: {json.dumps(user_content, ensure_ascii=False)}\nAssistant: {json.dumps(assistant_content, ensure_ascii=False)}\n---\n\n")


async def before_model(**kwargs):
    pass


async def after_model(**kwargs):
    pass


async def before_tool(**kwargs):
    pass


async def after_tool(**kwargs):
    pass
