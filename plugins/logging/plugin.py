import logging


async def before_application(**kwargs):
    logging.info("Logging plugin started")


async def after_application(**kwargs):
    logging.info("Logging plugin stopped")


async def before_chat(user_content: str, **kwargs):
    logging.info(f"User: {user_content}")


async def after_chat(assistant_content: str, **kwargs):
    logging.info(f"Assistant: {assistant_content}")


async def before_model(**kwargs):
    pass


async def after_model(messages: list, **kwargs):
    logging.info(f"Model: {messages[-1]}")


async def before_tool(**kwargs):
    pass


async def after_tool(messages: list, **kwargs):
    logging.info(f"Tool: {messages[-1]}")
