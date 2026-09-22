# Phase 3 验证指南

本文只记录当前代码可执行的验证入口。功能完成度以代码、测试输出和试点
验收为准，不以旧阶段报告中的勾选项作为证据。

## 启动

```bash
cp .env.example .env
# 设置真实 POSTGRES_PASSWORD、SECRET_KEY 和 JWT_SECRET_KEY
docker compose up -d --build
docker compose ps
```

生产入口由 Nginx 提供：<http://localhost>。API 文档为
<http://localhost/docs>，健康检查为 <http://localhost/api/health>。

## 初始化演示数据

迁移由 API 容器启动命令自动执行；种子脚本使用当前 ORM 模型并且可重复运行：

```bash
docker compose exec api python scripts/init_test_data.py
```

## Chat 契约

学生登录后，调用以下版本化路由：

```text
POST /api/v1/chat/sessions
GET  /api/v1/chat/sessions
GET  /api/v1/chat/sessions/{session_id}/messages
POST /api/v1/chat/sessions/{session_id}/messages
POST /api/v1/chat/sessions/{session_id}/stream   (SSE)
DELETE /api/v1/chat/sessions/{session_id}
POST /api/v1/chat/messages/{message_id}/feedback
```

SSE 事件统一包含 `request_id`、单调递增 `seq` 和 `data`，事件名包括
`message_start`、`tool_call_start`、`tool_call_end`、`source`、
`content_delta`、`message_end`、`done` 和 `error`。

## 测试

```bash
./scripts/run_tests.sh
./scripts/run_quality.sh
```

后端测试默认使用 SQLite；CI 还会将同一套测试运行在 PostgreSQL 15 上。
详见 [TESTING.md](TESTING.md)。
