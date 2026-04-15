import asyncio
import json
import logging
import platform
import sys
from asyncio import subprocess
from contextlib import asynccontextmanager

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


async def execute_python_code(code: str, work_dir: str) -> str:
    process = await asyncio.create_subprocess_exec(sys.executable, "-c", code, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=work_dir)
    stdout, stderr = await process.communicate()
    return f"{stdout.decode("utf-8", errors="replace")}{stderr.decode("utf-8", errors="replace")}"


@asynccontextmanager
async def lifespan(tools: list, **kwargs):
    tools.append(PYTHON_TOOL)
    logging.info(f"Python tool plugin started, adding python tool: {json.dumps(PYTHON_TOOL, ensure_ascii=False)}")
    yield
    logging.info("Python tool plugin stopped")


async def before_tool(messages: list, tool_call: dict, work_dir: str, **kwargs):
    if tool_call["function"]["name"] != "python":
        return
    try:
        args = json.loads(tool_call["function"]["arguments"])
        tool_content = await execute_python_code(args.get("code", ""), work_dir)
    except Exception as e:
        tool_content = f"Error: {e}"
    tool_message = {"role": "tool", "tool_call_id": tool_call["id"], "content": tool_content}
    messages.append(tool_message)
