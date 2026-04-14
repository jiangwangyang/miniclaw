import json
import logging
import os

SKILLS_DIR_LIST = ["skills/", "external_skills/", os.path.expanduser("~/.miniclaw/skills/"), os.path.expanduser("~/.agents/skills/")]
skills: list[dict[str, str]] = []


async def load_skills():
    skills.clear()
    loaded_skill_names = set()
    # 遍历技能目录
    for skills_dir in SKILLS_DIR_LIST:
        if not os.path.exists(skills_dir):
            continue
        # 遍历技能
        for entry in os.listdir(skills_dir):
            if entry in loaded_skill_names:
                continue
            skill_file_path = os.path.join(skills_dir, entry, "SKILL.md")
            if not os.path.isfile(skill_file_path):
                continue
            # 尝试读取 SKILL.md 提取 name 和 description
            with open(skill_file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) >= 4 and lines[0].strip() == "---" and lines[1].strip().startswith("name:") and lines[2].strip().startswith("description:"):
                name = lines[1].strip()[5:].strip()
                description = lines[2].strip()[12:].strip()
                if name == entry:
                    skills.append({"name": name, "description": description, "path": os.path.abspath(skill_file_path)})
                    loaded_skill_names.add(name)
    logging.info(f"Loaded {len(skills)} skills: {json.dumps(skills, ensure_ascii=False)}")


async def before_application(tools: list, **kwargs):
    await load_skills()
    logging.info("Skill plugin started")


async def after_application(**kwargs):
    logging.info("Skill plugin stopped")


async def before_chat(messages: list, **kwargs):
    if messages[0]["role"] == "system":
        messages[0]["content"] += f"---\nAvailable Skills: {json.dumps(skills, ensure_ascii=False)}\n---\n\n"


async def after_chat(**kwargs):
    pass


async def before_model(**kwargs):
    pass


async def after_model(**kwargs):
    pass


async def before_tool(messages: list, tool_call: dict, **kwargs):
    pass


async def after_tool(**kwargs):
    pass
