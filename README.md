# MiniClaw

**一个极度轻量的完全自主的 AI Agent**

MiniClaw 是一个极简、高效的 AI Agent 框架，核心代码仅约 **200 行 Python**，却提供了完整的多会话管理、插件扩展和技能系统。

## ✨ 核心特性

- 🚀 **超轻量**: 核心代码精简，依赖极少，启动迅速
- 🔧 **完全自主**: 自主决策、自主执行工具调用，不依赖外部代理
- 🧩 **插件系统**: 支持热插拔插件，可自定义生命周期钩子
- 🛠️ **技能扩展**: 动态加载技能目录，按需扩展 Agent 能力
- 💬 **多会话管理**: 支持多并发会话，互不干扰
- 📡 **流式响应**: SSE 流式输出，实时返回模型推理过程

## 🚀 快速开始

### 环境要求

- Python 3.10+
- [MiniMax API Key](https://platform.minimaxi.com/)

### 安装依赖

```bash
pip install fastapi uvicorn openai
```

### 配置环境变量

```bash
export MINIMAX_API_KEY="your-api-key-here"
```

### 启动服务

```bash
python miniclaw.py
```

服务将在 `http://0.0.0.0:11223` 启动。

### 使用方式

#### HTTP API

```
GET /chat?id=<session_id>&message=<your_message>
```

**示例**:

```bash
curl "http://localhost:11223/chat?id=test-session&message=Hello%20MiniClaw"
```

响应为 SSE 流式输出。

#### 中断会话

```
GET /interrupt?id=<session_id>
```

### Web UI

启用 `web_plugin` 插件后，可通过浏览器访问 `http://localhost:11223/` 使用网页界面。

## 🧩 插件系统

MiniClaw 提供强大的插件扩展机制，支持在 Agent 运行的各个生命周期阶段插入自定义逻辑。

### 插件目录

插件搜索路径（按优先级）:

1. `./plugins/`
2. `~/.miniclaw/plugins/`
3. `~/.agents/plugins/`

### 创建插件

在 `plugins/<plugin_name>/` 目录下创建 `plugin.py`:

```python
from fastapi import FastAPI


# 应用启动/关闭钩子
async def before_application(app: FastAPI, **kwargs):
    print("Agent 启动前")


async def after_application(app: FastAPI, **kwargs):
    print("Agent 关闭后")


# 对话生命周期钩子
async def before_chat(session_id: str, messages: list, user_content: str, **kwargs):
    print(f"用户输入: {user_content}")


async def after_chat(session_id: str, messages: list, user_content: str, assistant_content: str, **kwargs):
    print(f"助手回复: {assistant_content}")


# 模型调用钩子
async def before_model(session_id: str, messages: list, **kwargs):
    pass


async def after_model(session_id: str, messages: list, **kwargs):
    pass


# 工具调用钩子
async def before_tool(session_id: str, messages: list, tool_call: dict, **kwargs):
    pass


async def after_tool(session_id: str, messages: list, tool_call: dict, tool_content: str, **kwargs):
    pass
```

### 内置插件

| 插件               | 说明                 |
|------------------|--------------------|
| `logging_plugin` | 日志记录，记录所有对话和工具调用   |
| `session_plugin` | 会话管理，支持会话持久化和历史记录  |
| `web_plugin`     | Web 界面，提供浏览器访问的 UI |
| `channel_feishu` | 飞书集成，接入飞书机器人消息通道   |

## 🛠️ 技能系统

MiniClaw 支持动态加载技能（Skills），为 Agent 提供专业领域的能力扩展。

### 技能目录

技能搜索路径（按优先级）:

1. `./skills/`
2. `~/.miniclaw/skills/`
3. `~/.agents/skills/`

### 创建技能

在 `skills/<skill_name>/` 目录下创建 `SKILL.md`，使用 YAML frontmatter 格式:

```markdown
---
name: my_skill
description: "技能的详细描述，说明何时以及如何使用此技能"
---

# 技能说明

技能的完整使用指南和规范...
```

### 可用技能

你可以在 `~/.agents/skills/` 目录下查看和添加预置技能，如 `xlsx`、`pdf`、`docx`、`pptx` 等。

## 🔧 配置

### 环境变量

| 变量                | 必填 | 说明               |
|-------------------|----|------------------|
| `MINIMAX_API_KEY` | 是  | MiniMax API 密钥   |
| `LARK_APP_ID`     | 否  | 飞书应用 ID（使用飞书插件时） |
| `LARK_APP_SECRET` | 否  | 飞书应用密钥（使用飞书插件时）  |

## 📜 许可证

MIT License
