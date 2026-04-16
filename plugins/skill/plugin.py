import json
import logging
import pathlib
from contextlib import asynccontextmanager

import anyio
from fastapi import APIRouter, Path, Body, FastAPI

SKILLS_DIR_LIST = ["external_skills/", "skills/", str(pathlib.Path.home() / ".agents" / "skills")]
skills: list[dict[str, str]] = []
router: APIRouter = APIRouter()


async def load_skills():
    skills.clear()
    loaded_skill_names = set()
    # 遍历技能目录
    for skills_dir in SKILLS_DIR_LIST:
        skills_dir = anyio.Path(skills_dir)
        if not await skills_dir.exists():
            continue
        # 遍历技能
        async for skill_dir in skills_dir.iterdir():
            if skill_dir.name in loaded_skill_names:
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
            name = ""
            description = ""
            for line in lines[1:second_index]:
                if line.startswith("name:"):
                    name = line[5:].strip()
                elif line.startswith("description:"):
                    description = line[12:].strip()
            if name == skill_dir.name:
                skills.append({"name": name, "description": description, "path": str(await skill_file.absolute())})
                loaded_skill_names.add(name)
    logging.info(f"Loaded {len(skills)} skills: {json.dumps(skills, ensure_ascii=False)}")


@router.get("/skill/list")
async def get_skill_list():
    return skills


@router.get("/skill/{name}")
async def get_skill(name: str = Path(...)):
    filtered_skills = [skill for skill in skills if skill["name"] == name]
    if not filtered_skills:
        return {}
    skill = filtered_skills[0]
    skill_file = anyio.Path(skill["path"])
    content = await skill_file.read_text(encoding="utf-8")
    content = content.split("---\n", 2)[2].strip()
    return {
        "name": skill["name"],
        "description": skill["description"],
        "path": skill["path"],
        "content": content,
    }


@router.post("/skill/{name}")
async def save_skill(name: str = Path(...), description: str = Body(...), content: str = Body(...)):
    skill_dir = anyio.Path("external_skills") / name
    await skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    await skill_file.write_text(f"---\nname: {name}\ndescription: {description}\n---\n\n{content}", encoding="utf-8")
    await load_skills()


@asynccontextmanager
async def lifespan(app: FastAPI, **kwargs):
    await load_skills()
    app.include_router(router)
    logging.info("Skill plugin started")
    yield
    logging.info("Skill plugin stopped")


async def before_chat(messages: list, **kwargs):
    if messages[0]["role"] == "system":
        messages[0]["content"] += f"---\nAvailable Skills: {json.dumps(skills, ensure_ascii=False)}\n---\n\n"
