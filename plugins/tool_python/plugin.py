import asyncio
import json
import logging
import platform
import sys
from asyncio import subprocess
from contextlib import asynccontextmanager

PYTHON_TOOL = {
    "name": "python",
    "description": f"Execute python code. Python version: {platform.python_version()}.",
    "input_schema": {
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


async def execute_python_code(code: str, work_dir: str) -> str:
    process = await asyncio.create_subprocess_exec(sys.executable, "-c", code, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=work_dir)
    stdout, stderr = await process.communicate()
    return f"{stdout.decode("utf-8", errors="replace")}{stderr.decode("utf-8", errors="replace")}"


@asynccontextmanager
async def lifespan(**kwargs):
    logging.info(f"Python tool plugin started, having python tool: {json.dumps(PYTHON_TOOL, ensure_ascii=False)}")
    yield
    logging.info("Python tool plugin stopped")


async def before_chat(tools: list, **kwargs):
    tools += [PYTHON_TOOL]


async def before_tool(messages: list, tool_call: dict, work_dir: str, **kwargs):
    if tool_call["name"] != "python":
        return
    try:
        python_code = tool_call["input"].get("code", "")
        tool_content = await execute_python_code(python_code, work_dir)
        is_error = False
    except Exception as e:
        tool_content = f"Error: {e}"
        is_error = True
    content_block = {"type": "tool_result", "tool_use_id": tool_call["id"], "content": tool_content, "is_error": is_error}
    messages[-1]["content"].append(content_block)
