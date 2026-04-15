import json
import logging
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(**kwargs):
    logging.info("Logging plugin started")
    yield
    logging.info("Logging plugin stopped")


async def before_chat(user_content: str, **kwargs):
    logging.info(f"User: {json.dumps(user_content, ensure_ascii=False)}")


async def after_chat(assistant_content: str, **kwargs):
    logging.info(f"Assistant: {json.dumps(assistant_content, ensure_ascii=False)}")


async def after_model(messages: list, **kwargs):
    logging.info(f"Model: {json.dumps(messages[-1], ensure_ascii=False)}")


async def after_tool(messages: list, **kwargs):
    logging.info(f"Tool: {json.dumps(messages[-1], ensure_ascii=False)}")
