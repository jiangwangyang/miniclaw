import json
import logging
import pathlib
from contextlib import asynccontextmanager

import anyio
from fastapi import APIRouter, Path, Body, FastAPI, HTTPException

SKILLS_DIR_LIST = [str(pathlib.Path.home() / ".miniclaw" / "skills"), "skills", str(pathlib.Path.home() / ".agents" / "skills")]
SKILL_DICT: dict[str, dict] = {}
ROUTER = APIRouter()


async def load_skills():
    skills, loaded = [], set()
    # 遍历技能目录
    for skills_dir in map(anyio.Path, SKILLS_DIR_LIST):
        if not await skills_dir.exists():
            continue
        # 遍历技能
        async for skill_dir in skills_dir.iterdir():
            if skill_dir.name in loaded:
                continue
            skill_file = skill_dir / "SKILL.md"
            if not await skill_file.is_file():
                continue
            # 尝试读取 SKILL.md 提取 name 和 description
            text = await skill_file.read_text(encoding="utf-8")
            lines = [line.strip() for line in text.split("\n")]
            if len(lines) > 0 and lines[0] == "---" and "---" in lines[1:]:
                second_index = lines.index("---", 1)
            else:
                continue
            name, description = "", ""
            for line in lines[1:second_index]:
                if line.startswith("name:"):
                    name = line[5:].strip()
                elif line.startswith("description:"):
                    description = line[12:].strip()
            if name == skill_dir.name:
                content = text.split("---\n", 2)[2].strip()
                skills += [{"name": name, "description": description, "path": str(await skill_file.absolute()), "content": content}]
                loaded.add(name)
    return skills


@ROUTER.get("/skill/list")
async def get_skill_list():
    return await load_skills()


@ROUTER.get("/skill/{name}")
async def get_skill(name: str = Path(...)):
    skills = await load_skills()
    for skill in skills:
        if name == skill["name"]:
            return skill
    raise HTTPException(status_code=404, detail="Skill not found")


@ROUTER.post("/skill/{name}")
async def save_skill(name: str = Path(...), description: str = Body(...), content: str = Body(...)):
    skill_dir = anyio.Path(SKILLS_DIR_LIST[0]) / name
    await skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    await skill_file.write_text(f"---\nname: {name}\ndescription: {description}\n---\n\n{content}", encoding="utf-8")
    await load_skills()


@asynccontextmanager
async def lifespan(app: FastAPI, **kwargs):
    skills = await load_skills()
    for skill in skills:
        SKILL_DICT[skill["name"]] = skill
    logging.info(f"Skill plugin started, Loaded {len(SKILL_DICT)} skills: {", ".join(SKILL_DICT.keys())}")
    app.include_router(ROUTER)
    yield
    logging.info("Skill plugin stopped")


async def before_chat(tools: list, **kwargs):
    tools += [{
        "name": "read_skill",
        "description": f"Read skill detail. Skills: {json.dumps([{"name": skill["name"], "description": skill["description"]} for skill in SKILL_DICT.values()], ensure_ascii=False)}",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "skill name or other file in the skill like skill_name/dir/file.md"
                }
            },
            "required": ["name"]
        }
    }]


# 执行工具
async def before_tool(messages: list, tool_call: dict, **kwargs):
    if tool_call["name"] != "read_skill":
        return
    name = tool_call["input"].get("name", "").replace("\\", "/")
    if name in SKILL_DICT:
        tool_content = SKILL_DICT[name]["content"]
        is_error = False
    elif name.split("/")[0] in SKILL_DICT:
        skill_file = anyio.Path(SKILL_DICT[name.split("/")[0]]["path"]).parent.parent / name
        if await skill_file.is_file():
            tool_content = await skill_file.read_text(encoding="utf-8")
            is_error = False
        elif await skill_file.is_dir():
            tool_content = json.dumps([child async for child in skill_file.iterdir()], ensure_ascii=False)
            is_error = False
        else:
            tool_content, is_error = "Cannot find skill file", True
    else:
        tool_content, is_error = "Cannot find skill", True
    messages[-1]["content"] += [{"type": "tool_result", "tool_use_id": tool_call["id"], "content": tool_content, "is_error": is_error}]
