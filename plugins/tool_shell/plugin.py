import asyncio
import json
import logging
import platform
import sys
from asyncio import subprocess
from contextlib import asynccontextmanager

SHELL_TOOL = {
    "name": "shell",
    "description": f"Execute shell command. System platform: {platform.system()}-{platform.release()}-{platform.machine()}.",
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "shell command"
            }
        },
        "required": ["command"]
    }
}


async def shell(command: str, work_dir: str) -> str:
    process = await asyncio.create_subprocess_shell(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=work_dir)
    stdout, stderr = await process.communicate()
    return f"{stdout.decode("utf-8", errors="replace")}{stderr.decode("utf-8", errors="replace")}"


@asynccontextmanager
async def lifespan(**kwargs):
    if sys.platform.startswith("win"):
        logging.info("Shell tool plugin not supported on Windows")
        yield
    else:
        logging.info(f"Shell tool plugin started, having shell tool: {json.dumps(SHELL_TOOL, ensure_ascii=False)}")
        yield
        logging.info("Shell tool plugin stopped")


async def before_chat(tools: list, **kwargs):
    if not sys.platform.startswith("win"):
        tools += [SHELL_TOOL]


async def before_tool(messages: list, tool_call: dict, work_dir: str, **kwargs):
    if tool_call["name"] != "shell":
        return
    try:
        command = tool_call["input"].get("command", "")
        tool_content = await shell(command, work_dir)
        is_error = False
    except Exception as e:
        tool_content = f"Error: {e}"
        is_error = True
    content_block = {"type": "tool_result", "tool_use_id": tool_call["id"], "content": tool_content, "is_error": is_error}
    messages[-1]["content"].append(content_block)
