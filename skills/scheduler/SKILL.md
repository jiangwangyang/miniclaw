---
name: scheduler
description: 定时任务管理技能。支持任务调度、查询、修改、删除、启用/禁用和立即执行。当用户需要创建定时任务、管理任务计划、或查看任务状态时，可使用本技能。
---

# 定时任务管理

本技能提供定时任务的全生命周期管理能力。

## 核心能力

- ✅ 创建定时任务
- ✅ 删除任务
- ✅ 列出所有任务
- ✅ 启用任务
- ✅ 禁用任务
- ✅ 立即执行指定任务

## 服务 URL

```
http://localhost:11223
```

## 特殊字符

- `*`: 匹配任意值
- `,`: 列表分隔符，如 `8,18`
- `-`: 范围，如 `8-18`
- `/`: 步长，如 `*/15`

## API 端点

### 1. 列出所有任务

```
GET /task/list
```

**响应示例:**

```json
{
  "success": true,
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "daily_report",
      "content": "# 每日报告\n生成今日数据报表",
      "year": "*",
      "month": "*",
      "day": "*",
      "week": "*",
      "day_of_week": "*",
      "hour": "8",
      "minute": "0",
      "second": "0",
      "next_run": "2024-03-23T08:00:00",
      "enabled": true
    }
  ],
  "total": 1
}
```

### 2. 创建任务

```
POST /task
Content-Type: application/json

{
  "name": "daily_report",
  "content": "# 每日报告\n生成今日数据报表",
  "year": "*",
  "month": "*",
  "day": "*",
  "week": "*",
  "day_of_week": "*",
  "hour": "8",
  "minute": "0",
  "second": "0"
}
```

**请求体参数说明:**

| 参数          | 类型  | 默认值 | 说明                 |
|-------------|-----|-----|--------------------|
| name        | str | 必填  | 任务名称               |
| content     | str | 必填  | Markdown 格式的定时任务内容 |
| year        | str | "*" | 年（4位数字或*）          |
| month       | str | "*" | 月（1-12或*）          |
| day         | str | "*" | 日（1-31或*）          |
| week        | str | "*" | 周（1-53或*）          |
| day_of_week | str | "*" | 星期（0-6或*，0=周日）     |
| hour        | str | "*" | 小时（0-23或*）         |
| minute      | str | "*" | 分钟（0-59或*）         |
| second      | str | "0" | 秒（0-59或*）          |

**响应示例:**

```json
{
  "success": true,
  "message": "Task 550e8400-e29b-41d4-a716-446655440000 created",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "daily_report",
    "content": "# 每日报告\n生成今日数据报表",
    "year": "*",
    "month": "*",
    "day": "*",
    "week": "*",
    "day_of_week": "*",
    "hour": "8",
    "minute": "0",
    "second": "0",
    "next_run": "2024-03-23T08:00:00",
    "enabled": true
  }
}
```

### 3. 删除任务

```
DELETE /task/{task_id}
```

**参数说明:**

- `task_id`: 任务唯一标识（UUID，从任务列表中获取）

**响应示例:**

```json
{
  "success": true,
  "message": "Task 550e8400-e29b-41d4-a716-446655440000 deleted"
}
```

### 4. 启用任务

```
POST /task/{task_id}/enable
```

**参数说明:**

- `task_id`: 任务唯一标识（UUID，从任务列表中获取）

**响应示例:**

```json
{
  "success": true,
  "message": "Task 550e8400-e29b-41d4-a716-446655440000 enabled"
}
```

### 5. 禁用任务

```
POST /task/{task_id}/disable
```

**参数说明:**

- `task_id`: 任务唯一标识（UUID，从任务列表中获取）

**响应示例:**

```json
{
  "success": true,
  "message": "Task 550e8400-e29b-41d4-a716-446655440000 disabled"
}
```

### 6. 立即执行任务

```
POST /task/{task_id}/run
```

**参数说明:**

- `task_id`: 任务唯一标识（UUID，从任务列表中获取）

**响应示例:**

```json
{
  "success": true,
  "message": "Task 550e8400-e29b-41d4-a716-446655440000 execution started"
}
```
