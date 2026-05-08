import asyncio
import logging
import platform
import sys
from asyncio import subprocess
from contextlib import asynccontextmanager

import anyio

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
READ_FILE_TOOL = {
    "name": "read_file",
    "description": "Read File",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "file path"
            }
        },
        "required": ["path"]
    }
}
WRITE_FILE_TOOL = {
    "name": "write_file",
    "description": "Write File",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "file path"
            },
            "content": {
                "type": "string",
                "description": "file content"
            }
        },
        "required": ["path", "content"]
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


@asynccontextmanager
async def lifespan(**kwargs):
    if sys.platform.startswith("win"):
        logging.info("Tool plugin started, having 4 tools: read_file, write_file, python_file, python_cmd")
    else:
        logging.info("Tool plugin started, having 1 tool: shell")
    yield
    logging.info("Tool plugin stopped")


async def before_chat(tools: list, **kwargs):
    if sys.platform.startswith("win"):
        tools += [READ_FILE_TOOL, WRITE_FILE_TOOL, PYTHON_FILE_TOOL, PYTHON_CMD_TOOL]
    else:
        tools += [SHELL_TOOL]


async def before_tool(messages: list, tool_call: dict, work_dir: str, **kwargs):
    try:
        if tool_call["name"] == "shell":
            command = tool_call["input"].get("command", "")
            process = await asyncio.create_subprocess_shell(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=work_dir)
            stdout, stderr = await process.communicate()
            tool_content = f"{stdout.decode("utf-8", errors="replace")}{stderr.decode("utf-8", errors="replace")}"
            is_error = process.returncode != 0
        elif tool_call["name"] == "read_file":
            path = tool_call["input"].get("path", "")
            tool_content = await anyio.Path(path).read_text(encoding="utf-8")
            is_error = False
        elif tool_call["name"] == "write_file":
            path, content = tool_call["input"].get("path", ""), tool_call["input"].get("content", "")
            await anyio.Path(path).write_text(content, encoding="utf-8")
            tool_content, is_error = "write success", False
        elif tool_call["name"] == "python_file":
            python_file, args = tool_call["input"].get("file", ""), tool_call["input"].get("args", [])
            process = await asyncio.create_subprocess_exec(sys.executable, python_file, *args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=work_dir)
            stdout, stderr = await process.communicate()
            tool_content = f"{stdout.decode("utf-8", errors="replace")}{stderr.decode("utf-8", errors="replace")}"
            is_error = process.returncode != 0
        elif tool_call["name"] == "python_cmd":
            python_cmd = tool_call["input"].get("cmd", "")
            process = await asyncio.create_subprocess_exec(sys.executable, "-c", python_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=work_dir)
            stdout, stderr = await process.communicate()
            tool_content = f"{stdout.decode("utf-8", errors="replace")}{stderr.decode("utf-8", errors="replace")}"
            is_error = process.returncode != 0
        else:
            return
    except Exception as e:
        tool_content, is_error = f"Error: {e}", True
    messages[-1]["content"] += [{"type": "tool_result", "tool_use_id": tool_call["id"], "content": tool_content, "is_error": is_error}]
