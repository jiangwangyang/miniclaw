import json
import logging
import os

SKILLS_DIR_LIST = ["skills/", os.path.expanduser("~/.miniclaw/skills/"), os.path.expanduser("~/.agents/skills/")]
skills: list[dict[str, str]] = []
tool = {
    "type": "function",
    "function": {
        "name": "activate_skill",
        "description": "",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "skill name"}
            },
            "required": ["name"],
        },
    }
}


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
    # 将技能列表更新到工具描述中
    tool["function"]["description"] = f"Available Skills: {json.dumps(skills, ensure_ascii=False)}"
    logging.info(f"Loaded skills: {json.dumps(skills, ensure_ascii=False)}")


async def before_application(tools: list, **kwargs):
    await load_skills()
    tools.append(tool)
    logging.info("Skill plugin started")


async def after_application(**kwargs):
    logging.info("Skill plugin stopped")


async def before_chat(**kwargs):
    pass


async def after_chat(**kwargs):
    pass


async def before_model(**kwargs):
    pass


async def after_model(**kwargs):
    pass


async def before_tool(messages: list, tool_call: dict, **kwargs):
    if tool_call["function"]["name"] != "activate_skill":
        return
    try:
        args = json.loads(tool_call["function"]["arguments"])
        tool_content = "Can't find skill"
        skill_name = args.get("name", "")
        for skill in skills:
            if skill["name"] == skill_name:
                with open(skill["path"], "r", encoding="utf-8") as f:
                    tool_content = f.read()
                break
    except json.JSONDecodeError:
        tool_content = "Error: Invalid JSON arguments."
    tool_message = {"role": "tool", "tool_call_id": tool_call["id"], "content": tool_content}
    messages.append(tool_message)


async def after_tool(**kwargs):
    pass
