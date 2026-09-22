# PRD-12: API 接口规范

---
Status: active
Owner: API 平台
Last verified: 2026-09-11
Evidence: V2 API 唯一规范；OpenAPI、契约测试和端到端测试是实现证据。
Supersedes: 旧版 API 路径和响应约定
---

> 本文是唯一正式 API 规范。旧路由和示例不再作为兼容接口；实现完成前不得标记为生产就绪。

## 1. API 总览

### 1.1 基础信息

- **Base URL**: `https://api.example.com/api/v1`
- **认证方式**: JWT Bearer Token
- **内容类型**: `application/json`
- **API 文档**: `/docs` (Swagger UI)

### 1.2 API 分组

| 分组 | 路径前缀 | 说明 |
|---|---|---|
| 认证 | `/auth` | 登录、刷新 Token |
| 学生 | `/students` | 学生信息 |
| 考试 | `/exams` | 考试与成绩 |
| 对话 | `/chat` | Chat 会话与消息 |
| 权益 | `/entitlements` | 学生权益查询 |
| 管理 | `/admin` | 管理后台 |

V1 试点正式开放的只有认证和 Chat 会话/消息接口；`students`、`exams`、`entitlements`、`admin` 作为后续扩展保留，未通过实现与权限验收前不得对外发布。

---

## 2. 认证 API

### 2.1 登录

```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "username": "student_001",
  "password": "password123"
}
```

**响应**：
```json
{
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "uuid",
    "username": "student_001",
    "display_name": "张三",
    "roles": ["STUDENT"]
  }
}
```

### 2.2 刷新 Token

```http
POST /api/v1/auth/refresh
Content-Type: application/json

{
  "refresh_token": "eyJhbGc..."
}
```

### 2.3 当前用户

```http
GET /api/v1/auth/me
Authorization: Bearer {access_token}
```

**响应**：
```json
{
  "user_id": "uuid",
  "student_id": "uuid",
  "school_id": "uuid",
  "username": "student_001",
  "display_name": "张三",
  "roles": ["STUDENT"]
}
```

### 2.4 登出

```http
POST /api/v1/auth/logout
Authorization: Bearer {access_token}
Content-Type: application/json

{"refresh_token": "eyJhbGc..."}
```

服务端撤销 refresh token；重复登出返回幂等成功。access token 不得被当作 refresh token 接受。

---

## 3. 学生 API

### 3.1 获取学生信息

```http
GET /api/v1/students/me
Authorization: Bearer {token}
```

**响应**：
```json
{
  "id": "uuid",
  "name": "张三",
  "student_no": "2024001",
  "grade": "高一",
  "class_name": "1班",
  "school": {
    "id": "uuid",
    "name": "示例中学"
  }
}
```

### 3.2 获取学生权益

```http
GET /api/v1/students/me/entitlements
Authorization: Bearer {token}
```

**响应**：
```json
{
  "entitlements": [
    {
      "product_code": "DIAGNOSIS_REPORT",
      "status": "active",
      "resource_type": "exam",
      "resource_ids": ["exam_123"],
      "expires_at": "2026-12-31T23:59:59Z"
    }
  ]
}
```

---

## 4. 考试 API

### 4.1 获取考试列表

```http
GET /api/v1/students/me/exams?limit=10&offset=0
Authorization: Bearer {token}
```

**响应**：
```json
{
  "total": 25,
  "items": [
    {
      "id": "uuid",
      "name": "2026秋季期中考试",
      "exam_type": "midterm",
      "start_date": "2026-11-01",
      "has_score": true
    }
  ]
}
```

### 4.2 获取考试成绩

```http
GET /api/v1/students/me/exams/{exam_id}/score
Authorization: Bearer {token}
```

**响应**：
```json
{
  "exam": {
    "id": "uuid",
    "name": "2026秋季期中考试"
  },
  "total_score": 128.5,
  "full_score": 150,
  "class_rank": 31,
  "grade_rank": 128,
  "class_student_count": 45,
  "grade_student_count": 420,
  "subjects": [
    {
      "subject": "数学",
      "score": 92,
      "full_score": 100,
      "class_rank": 25,
      "grade_rank": 115
    }
  ]
}
```

---

## 5. Chat API

### 5.1 创建会话

```http
POST /api/v1/chat/sessions
Authorization: Bearer {token}
Content-Type: application/json

{
  "title": "期中考试问答",
  "selected_exam_id": "exam_uuid"
}
```

**响应**：
```json
{
  "id": "session_uuid",
  "title": "期中考试问答",
  "selected_exam_id": "exam_uuid",
  "created_at": "2026-09-09T10:00:00Z"
}
```

### 5.2 列出会话

```http
GET /api/v1/chat/sessions?limit=20&offset=0
Authorization: Bearer {token}
```

**响应**：
```json
{
  "total": 5,
  "items": [
    {
      "id": "uuid",
      "title": "期中考试问答",
      "status": "active",
      "last_message_at": "2026-09-09T10:05:00Z",
      "created_at": "2026-09-09T10:00:00Z"
    }
  ]
}
```

### 5.3 发送消息（非流式）

```http
POST /api/v1/chat/sessions/{session_id}/messages
Authorization: Bearer {token}
Content-Type: application/json

{
  "content": "我这次考得怎样？"
}
```

**响应**：
```json
{
  "session_id": "session_uuid",
  "message": {
    "id": "message_uuid",
    "role": "assistant",
    "content": "你这次考试总分128.5分（满分150），班级排名第31名，年级排名第128名。",
    "created_at": "2026-09-09T10:05:30Z"
  },
  "agent_run_id": "run_uuid",
  "tools_called": [],
  "sources": []
}
```

### 5.4 发送消息（流式 SSE）

```http
POST /api/v1/chat/sessions/{session_id}/stream
Authorization: Bearer {token}
Content-Type: application/json
Accept: text/event-stream

{
  "content": "我这次考得怎样？"
}
```

**SSE 响应**：
```text
event: message_start
data: {"request_id":"uuid","seq":1,"data":{"session_id":"uuid"}}

event: content_delta
data: {"request_id":"uuid","seq":2,"data":{"content":"你这次"}}

event: content_delta
data: {"request_id":"uuid","seq":3,"data":{"content":"考试总分"}}

event: message_end
data: {"request_id":"uuid","seq":4,"data":{"message_id":"uuid","agent_run_id":"run_uuid"}}

event: done
data: {"request_id":"uuid","seq":5,"data":{"session_id":"uuid"}}
```

当 Agent 执行只读 Tool 时，服务端还会发送 `tool_call_start` 和 `tool_call_end`；客户端只展示最终答案和来源，不依赖工具事件顺序。

### 5.5 获取会话消息

```http
GET /api/v1/chat/sessions/{session_id}/messages?limit=50&offset=0
Authorization: Bearer {token}
```

**响应**：
```json
[
  {
    "id": "uuid",
    "role": "user",
    "content": "我这次考得怎样？",
    "created_at": "2026-09-09T10:05:00Z"
  },
  {
    "id": "uuid",
    "role": "assistant",
    "content": "你这次考试总分128.5分...",
    "agent_run_id": "run_uuid",
    "created_at": "2026-09-09T10:05:30Z"
  }
]
```

### 5.6 消息反馈

```http
POST /api/v1/chat/messages/{message_id}/feedback
Authorization: Bearer {token}
Content-Type: application/json

{"rating":"up", "reason": null}
```

`rating` 仅允许 `up` 或 `down`；反馈必须只能提交给当前学生有权访问的 assistant 消息。

---

## 6. 统一响应格式

### 6.1 成功响应

```json
{
  "data": { ... },
  "meta": {
    "request_id": "req_123",
    "timestamp": "2026-09-09T10:00:00Z"
  }
}
```

### 6.2 错误响应

```json
{
  "error": {
    "code": "AUTHENTICATION_REQUIRED",
    "message": "需要登录",
    "request_id": "req_123",
    "details": {}
  }
}
```

---

## 7. 错误码

| HTTP | 错误码 | 说明 |
|---|---|---|
| 400 | INVALID_REQUEST | 请求参数错误 |
| 401 | AUTHENTICATION_REQUIRED | 需要认证 |
| 401 | TOKEN_EXPIRED | Token 过期 |
| 403 | PERMISSION_DENIED | 权限不足 |
| 403 | ENTITLEMENT_REQUIRED | 需要购买权益 |
| 404 | RESOURCE_NOT_FOUND | 资源不存在 |
| 429 | RATE_LIMIT_EXCEEDED | 请求过于频繁 |
| 500 | INTERNAL_SERVER_ERROR | 服务器错误 |

---

## 8. 分页规范

**请求参数**：
- `limit`: 每页数量（默认 20，最大 100）
- `offset`: 偏移量（默认 0）

**响应格式**：
```json
{
  "total": 100,
  "limit": 20,
  "offset": 0,
  "items": [...]
}
```

---

## 9. 安全规范

### 9.1 认证

所有需要认证的接口必须包含 Authorization 头：
```http
Authorization: Bearer {access_token}
```

### 9.2 CORS

```python
# FastAPI CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://example.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"]
)
```

### 9.3 Rate Limit

- 普通接口：60 次/分钟
- Chat 接口：20 次/分钟
- 登录接口：5 次/分钟

---

## 10. Swagger 文档

FastAPI 自动生成文档：
- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`
