import asyncio
import logging
import platform
import sys
from asyncio import subprocess
from contextlib import asynccontextmanager

PYTHON_CMD_TOOL = {
    "name": "python_cmd",
    "description": f"Run python program passed in as string. Python version: {platform.python_version()}.",
    "input_schema": {
        "type": "object",
        "properties": {
            "cmd": {
                "type": "string",
                "description": "python command"
            }
        },
        "required": ["cmd"]
    }
}
PYTHON_FILE_TOOL = {
    "name": "python_file",
    "description": f"Run python program read from script file. Python version: {platform.python_version()}.",
    "input_schema": {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "python file path"
            },
            "args": {
                "type": "array",
                "items": {
                    "type": "string"
                },
                "description": "arguments passed to program in sys.argv[1:]"
            }
        },
        "required": ["file"]
    }
}


@asynccontextmanager
async def lifespan(**kwargs):
    logging.info("Python tool plugin started, having 2 tools: python_cmd, python_file")
    yield
    logging.info("Python tool plugin stopped")


async def before_chat(tools: list, **kwargs):
    tools += [PYTHON_CMD_TOOL, PYTHON_FILE_TOOL]


async def before_tool(messages: list, tool_call: dict, work_dir: str, **kwargs):
    try:
        if tool_call["name"] == "python_cmd":
            python_cmd = tool_call["input"].get("cmd", "")
            process = await asyncio.create_subprocess_exec(sys.executable, "-c", python_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=work_dir)
        elif tool_call["name"] == "python_file":
            python_file = tool_call["input"].get("file", "")
            args = tool_call["input"].get("args", [])
            process = await asyncio.create_subprocess_exec(sys.executable, python_file, *args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=work_dir)
        else:
            return
        stdout, stderr = await process.communicate()
        tool_content = f"{stdout.decode("utf-8", errors="replace")}{stderr.decode("utf-8", errors="replace")}"
        is_error = process.returncode != 0
    except Exception as e:
        tool_content = f"Error: {e}"
        is_error = True
    messages[-1]["content"] += [{"type": "tool_result", "tool_use_id": tool_call["id"], "content": tool_content, "is_error": is_error}]
