import json
import logging
import os
import pathlib
import sys
from asyncio import subprocess

WORK_DIR = pathlib.Path.home() / "miniclaw"
tool = {
    "type": "function",
    "function": {
        "name": "shell",
        "description": f"Execute shell command. System platform: {sys.platform}. Current working directory: {WORK_DIR}",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "shell command"}
            },
            "required": ["command"],
        },
    }
}


async def shell(command: str) -> str:
    if not os.path.exists(WORK_DIR):
        os.makedirs(WORK_DIR)
    if sys.platform.startswith("win"):
        command = f"chcp 65001 > nul && {command}"
    process = await subprocess.create_subprocess_shell(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=WORK_DIR)
    stdout, stderr = await process.communicate()
    return f"{stdout.decode("utf-8", errors="replace")}{stderr.decode("utf-8", errors="replace")}"


async def before_application(tools: list, **kwargs):
    tools.append(tool)
    logging.info("Shell plugin started")


async def after_application(**kwargs):
    logging.info("Shell plugin stopped")


async def before_chat(**kwargs):
    pass


async def after_chat(**kwargs):
    pass


async def before_model(**kwargs):
    pass


async def after_model(**kwargs):
    pass


async def before_tool(messages: list, tool_call: dict, **kwargs):
    if tool_call["function"]["name"] != "shell":
        return
    try:
        args = json.loads(tool_call["function"]["arguments"])
        tool_content = await shell(args.get("command", ""))
    except json.JSONDecodeError:
        tool_content = "Error: Invalid JSON arguments."
    tool_message = {"role": "tool", "tool_call_id": tool_call["id"], "content": tool_content}
    messages.append(tool_message)


async def after_tool(**kwargs):
    pass
