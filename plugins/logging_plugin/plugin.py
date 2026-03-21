import logging

from fastapi import FastAPI

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


async def before_application(app: FastAPI, **kwargs):
    logging.info("logging plugin started")


async def after_application(app: FastAPI, **kwargs):
    logging.info("logging plugin stopped")


async def before_chat(id: str, messages: list, user_content: str, **kwargs):
    logging.info(user_content)


async def after_chat(id: str, messages: list, user_content: str, assistant_content: str, **kwargs):
    logging.info(assistant_content)


async def before_model(id: str, messages: list, **kwargs):
    pass


async def after_model(id: str, messages: list, **kwargs):
    logging.info(messages[-1])


async def before_tool(id: str, messages: list, tool_call: dict, **kwargs):
    pass


async def after_tool(id: str, messages: list, tool_call: dict, tool_content: str, **kwargs):
    logging.info(messages[-1])
