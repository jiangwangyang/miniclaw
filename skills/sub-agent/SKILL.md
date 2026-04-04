---
name: sub-agent
description: 将复杂任务分配给子 Agent 处理的技能。当用户明确要求将任务交给子 Agent、拆分子任务、多线程处理独立任务，或需要并行执行多个子任务时启用。
---

# 子 Agent 任务分配

本技能用于将复杂任务拆解并分配给子 Agent 并行或单独处理。

## 调用方式

使用 miniclaw 的 `/chat` 接口指派任务：

```bash
curl -X GET "http://localhost:11223/chat?id=sub-<随机字符串>&message=<URL编码的任务描述>"
```

### 参数说明

| 参数        | 类型     | 必填 | 说明                                    |
|-----------|--------|----|---------------------------------------|
| `id`      | string | 是  | 子任务会话标识，格式为 `sub-` 前缀 + 随机字符串（如 UUID） |
| `message` | string | 是  | 子任务的具体描述（需 URL 编码）                    |

### 会话标识规则

- **前缀**：`sub-` 固定前缀，用于区分子任务会话
- **随机标识**：使用 UUID，由 shell 命令自动生成
- **目的**：确保每个子任务拥有独立的会话上下文，避免相互干扰

### 生成会话 ID

使用以下命令自动生成带 `sub-` 前缀的会话 ID：

```bash
# 方法1: 使用 uuidgen（推荐）
SUB_ID="sub-$(uuidgen)"

# 方法2: 使用 /proc 文件系统
SUB_ID="sub-$(cat /proc/sys/kernel/random/uuid)"
```

### URL 编码说明

`message` 参数中的特殊字符必须进行 URL 编码，避免破坏请求格式：

| 字符类型 | 示例         | 编码后示例                                  |
|------|------------|----------------------------------------|
| 空格   | `中文 描述`    | `中文%2020描述`                            |
| 换行   | `第一行\n第二行` | `第一行%0A第二行`                            |
| 中文   | `你好世界`     | `%E4%BD%A0%E5%A5%BD%E4%B8%96%E7%95%8C` |
| 特殊符号 | `问: 你好?`   | `%E9%97%AE%3A%20%E4%BD%A0%E5%A5%BD%3F` |

可使用 `python3 -c "import urllib.parse; print(urllib.parse.quote('你的消息'))"` 或 `jq -Rs '.' <<< '消息'` 配合 `tr -d '\n'` 进行编码。

## 适用场景

- **任务拆分**：复杂任务可分解为多个独立子任务时
- **并行处理**：多个子任务可同时执行以提高效率时
- **专业处理**：特定领域任务需要专门的 Agent 处理时

## 使用原则

1. **显式触发**：除非用户明确声明需要使用子 Agent，否则不要自行决定使用
2. **任务明确**：在 message 参数中清晰描述子任务的具体要求
3. **结果整合**：收集子 Agent 的处理结果后整合输出

## 示例

用户要求：「分别用中文和英文写一篇对于 AI 的短文」

```bash
# 生成子 Agent 会话 ID
SUB_ID1="sub-$(uuidgen)"
SUB_ID2="sub-$(uuidgen)"

# 准备 URL 编码的消息
MSG1=$(python3 -c "import urllib.parse; print(urllib.parse.quote('用中文写一篇关于 AI 的短文，200字左右'))")
MSG2=$(python3 -c "import urllib.parse; print(urllib.parse.quote('Write a short paragraph about AI in English, about 200 words'))")

# 并行调用两个子 Agent，响应分别保存到文件
curl -s "http://localhost:11223/chat?id=${SUB_ID1}&message=${MSG1}" > sub-agent-1.txt &

curl -s "http://localhost:11223/chat?id=${SUB_ID2}&message=${MSG2}" > sub-agent-2.txt &

wait  # 等待所有后台任务完成

echo "=== 子Agent 1 响应 ==="
cat sub-agent-1.txt

echo "=== 子Agent 2 响应 ==="
cat sub-agent-2.txt
```

### 示例说明

| 要素       | 说明                        |
|----------|---------------------------|
| `uuidgen` | 自动生成 UUID，无需手动指定           |
| `&`      | 将命令放入后台并行执行               |
| `> file` | 将响应重定向到独立文件，避免多个响应混在一起    |
| `-s`     | silent 模式，减少 curl 自身的干扰信息 |
| `wait`   | 等待所有后台任务完成后，再执行后续查看操作     |
| `id` 参数  | 响应 JSON 中会包含 id，可用于确认对应关系 |
