---
name: sub-agent
description: 将复杂任务分配给子 Agent 处理的技能。当用户明确要求将任务交给子 Agent、拆分子任务、多线程处理独立任务，或需要并行执行多个子任务时启用。
---

# 子 Agent 任务分配

本技能用于将复杂任务拆解并分配给子 Agent 并行或单独处理。

## 适用场景

- **任务拆分**：复杂任务可分解为多个独立子任务时
- **并行处理**：多个子任务可同时执行以提高效率时
- **专业处理**：特定领域任务需要专门的 Agent 处理时

## 使用原则

1. **显式触发**：除非用户明确声明需要使用子 Agent，否则不要自行决定使用
2. **任务明确**：在 message 参数中清晰描述子任务的具体要求
3. **结果整合**：收集子 Agent 的处理结果后整合输出

## 调用方式

使用 miniclaw 的 `/chat` POST 接口指派任务：

```python
import uuid
import httpx

# 生成子 Agent 会话 ID（使用 uuid4 的 hex 格式）
sub_id = f"tmp-{uuid.uuid4().hex}"

# 准备请求数据
payload = {
    "message": "子任务的具体描述",
    "workdir": "/tmp",
    "stream": False
}

# 发送请求
response = httpx.post(f"http://localhost:11223/chat/{sub_id}", json=payload, timeout=60)
print(response.json().get("content"))
```

## 参数说明

| 参数        | 类型     | 必填 | 说明                               |
|-----------|--------|----|----------------------------------|
| `id`      | string | 是  | 子任务会话标识，格式为 `tmp-` 前缀 + UUID hex |
| `message` | string | 是  | 子任务的具体描述                         |
| `workdir` | string | 是  | 工作目录，固定为 `tmp`                   |
| `stream`  | bool   | 是  | 是否流式返回，固定为 `False`               |

## 示例

用户要求：「分别用中文和英文写一篇对于 AI 的短文」

```python
import asyncio
import uuid

import httpx

# 为两个子任务生成独立的会话 ID
sub_id1 = f"tmp-{uuid.uuid4().hex}"
sub_id2 = f"tmp-{uuid.uuid4().hex}"

# 准备两个任务的消息
messages = [
    "用中文写一篇关于 AI 的短文，200字左右",
    "Write a short paragraph about AI in English, about 200 words"
]


# 并行调用两个子 Agent
async def main():
    async with httpx.AsyncClient() as async_client:
        # 创建两个异步请求
        task1 = async_client.post(
            f"http://localhost:11223/chat/{sub_id1}",
            json={"message": messages[0], "workdir": "/tmp", "stream": False},
            timeout=60
        )
        task2 = async_client.post(
            f"http://localhost:11223/chat/{sub_id2}",
            json={"message": messages[1], "workdir": "/tmp", "stream": False},
            timeout=60
        )

        # 并行执行
        responses = await asyncio.gather(task1, task2, return_exceptions=True)

        # 打印结果
        for i, resp in enumerate(responses):
            print(f"=== 子 Agent {i + 1} 响应 ===")
            if isinstance(resp, Exception):
                print(resp)
            else:
                print(resp.text)
            print()


if __name__ == "__main__":
    asyncio.run(main())
```
