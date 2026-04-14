import asyncio
import json
import logging
import os
import pathlib
import platform
import sys
from asyncio import subprocess

WORK_DIR = pathlib.Path.home() / "miniclaw"
PYTHON_TOOL = {
    "type": "function",
    "function": {
        "name": "python",
        "description": f"Execute python code. Python version: {platform.python_version()}.",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "python code"
                }
            },
            "required": ["code"]
        }
    }
}


async def execute_python_code(code: str) -> str:
    if not os.path.exists(WORK_DIR):
        os.makedirs(WORK_DIR)
    process = await asyncio.create_subprocess_exec(sys.executable, "-c", code, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=WORK_DIR)
    stdout, stderr = await process.communicate()
    return f"{stdout.decode("utf-8", errors="replace")}{stderr.decode("utf-8", errors="replace")}"


async def before_application(tools: list, **kwargs):
    tools.append(PYTHON_TOOL)
    logging.info(f"Adding python tool: {json.dumps(PYTHON_TOOL, ensure_ascii=False)}")


async def after_application(**kwargs):
    pass


async def before_chat(**kwargs):
    pass


async def after_chat(**kwargs):
    pass


async def before_model(**kwargs):
    pass


async def after_model(**kwargs):
    pass


async def before_tool(messages: list, tool_call: dict, **kwargs):
    if tool_call["function"]["name"] != "python":
        return
    try:
        args = json.loads(tool_call["function"]["arguments"])
        tool_content = await execute_python_code(args.get("code", ""))
    except Exception as e:
        tool_content = f"Error: {e}"
    tool_message = {"role": "tool", "tool_call_id": tool_call["id"], "content": tool_content}
    messages.append(tool_message)


async def after_tool(**kwargs):
    pass
