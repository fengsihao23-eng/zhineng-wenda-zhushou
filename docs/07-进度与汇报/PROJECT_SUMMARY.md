# 项目结构与当前边界

本页是当前仓库的导航。历史阶段报告中的“已完成”和“生产就绪”文字不构成
验收证据；请以代码、CI 输出和试点门禁为准。

## 服务

| 服务 | Compose 名称 | 作用 | 对外暴露 |
| --- | --- | --- | --- |
| PostgreSQL | `db` | 主数据库（pgvector 镜像） | 否 |
| Redis | `redis` | 缓存与限流扩展点 | 否 |
| FastAPI | `api` | 认证、Chat、健康检查 | 否 |
| React/Nginx | `web` | 前端静态文件 | 否 |
| Nginx | `nginx` | 公开网关、SSE、可选 TLS | `80/443` |

```bash
docker compose config
docker compose up -d --build
docker compose ps
```

## 代码入口

```text
apps/api/app/api/v1/endpoints/   API 路由
apps/api/app/agent/              AgentLoop 与上下文构建
apps/api/app/ai/                 ModelGateway 与 Provider
apps/api/app/core/               配置、安全、Trace、Guard、Prompt、限流
apps/api/app/db/models/          SQLAlchemy 模型
apps/api/app/data/               CSV 校验、导入和同步
apps/api/app/tools/              成绩/考试/分析 Tool
apps/web/src/                    React Chat、登录、SSE 客户端
apps/api/alembic/                数据库迁移
apps/api/tests/                  后端测试
```

## 当前验证入口

```bash
./scripts/run_tests.sh
./scripts/run_quality.sh
```

后端测试默认使用 SQLite，并可用 `TEST_DATABASE_URL` 指向隔离的 PostgreSQL
测试库。CI 同时运行两种数据库；前端执行 lint、Vitest 和生产构建。详见
[QUICKSTART.md](../../QUICKSTART.md) 和 [TESTING.md](../08-运维与交付/TESTING.md)。

## 运行时地址

- 前端：<http://localhost>
- API 文档：<http://localhost/docs>
- 健康检查：<http://localhost/api/health>
