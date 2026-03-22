import logging

from fastapi import FastAPI


async def before_application(app: FastAPI, **kwargs):
    logging.info("Logging plugin started")


async def after_application(app: FastAPI, **kwargs):
    logging.info("Logging plugin stopped")


async def before_chat(session_id: str, messages: list, user_content: str, **kwargs):
    logging.info(f"User: {user_content}")


async def after_chat(session_id: str, messages: list, user_content: str, assistant_content: str, **kwargs):
    logging.info(f"Assistant: {assistant_content}")


async def before_model(session_id: str, messages: list, **kwargs):
    pass


async def after_model(session_id: str, messages: list, **kwargs):
    logging.info(f"Model: {messages[-1]}")


async def before_tool(session_id: str, messages: list, tool_call: dict, **kwargs):
    pass


async def after_tool(session_id: str, messages: list, tool_call: dict, tool_content: str, **kwargs):
    logging.info(f"Tool: {messages[-1]}")
