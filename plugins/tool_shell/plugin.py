import asyncio
import json
import logging
import platform
import sys
from asyncio import subprocess
from contextlib import asynccontextmanager

SHELL_TOOL = {
    "type": "function",
    "function": {
        "name": "shell",
        "description": f"Execute shell command. System platform: {platform.system()}-{platform.release()}-{platform.machine()}.",
        "parameters": {
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
}


async def shell(command: str, work_dir: str) -> str:
    process = await asyncio.create_subprocess_shell(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=work_dir)
    stdout, stderr = await process.communicate()
    return f"{stdout.decode("utf-8", errors="replace")}{stderr.decode("utf-8", errors="replace")}"


@asynccontextmanager
async def lifespan(tools: list, **kwargs):
    if sys.platform.startswith("win"):
        logging.info("Shell tool plugin not supported on Windows")
        yield
    else:
        tools.append(SHELL_TOOL)
        logging.info(f"Shell tool plugin started, adding shell tool: {json.dumps(SHELL_TOOL, ensure_ascii=False)}")
        yield
        logging.info("Shell tool plugin stopped")


async def before_tool(messages: list, tool_call: dict, work_dir: str, **kwargs):
    if tool_call["function"]["name"] != "shell":
        return
    try:
        args = json.loads(tool_call["function"]["arguments"])
        tool_content = await shell(args.get("command", ""), work_dir)
    except Exception as e:
        tool_content = f"Error: {e}"
    tool_message = {"role": "tool", "tool_call_id": tool_call["id"], "content": tool_content}
    messages.append(tool_message)
