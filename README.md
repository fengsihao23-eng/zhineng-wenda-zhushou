# 学生智能问答系统

基于真实学校业务数据的学生智能问答助手，以学生身份和权限为边界，以成绩/排名/小题得分/诊断报告为动态上下文，以轻量 Agent + Tool Calling 为交互核心。

## 项目特点

- ✅ 真实数据优先于模型能力
- ✅ 权限优先于 Prompt
- ✅ 计算交给代码，不交给 LLM
- ✅ BASIC / DIAGNOSIS 权益分层
- ✅ 轻量 Agent，非复杂 Multi-Agent 编排
- ✅ 全链路可追溯

## 技术栈

- **前端**: React + TypeScript
- **后端**: FastAPI (Python 3.11+)
- **数据库**: PostgreSQL 15 + pgvector
- **缓存/队列**: Redis 7
- **网关**: Nginx
- **部署**: Docker Compose

## 快速开始

### 1. 环境准备

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 填入必要配置
# - POSTGRES_PASSWORD
# - SECRET_KEY 和 JWT_SECRET_KEY（两个不同的随机值，至少32字符）
# - 模型 API KEY
```

### 2. 启动服务

```bash
# 启动所有服务（公开入口由 Nginx 提供）
docker compose up -d

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f
```

### 3. 数据库初始化

```bash
# 运行数据库迁移
docker compose exec api alembic upgrade head

# 初始化种子数据（可选）
docker compose exec api python scripts/init_test_data.py
```

### 4. 访问应用

- 前端: http://localhost (或配置的域名)
- API文档: http://localhost/docs
- 健康检查: http://localhost/health

## 项目结构

```
.
├── apps/
│   ├── api/                 # FastAPI 后端
│   │   ├── app/
│   │   │   ├── api/        # API 路由
│   │   │   ├── core/       # 核心配置
│   │   │   ├── agent/      # Agent 核心和 Context Builder
│   │   │   ├── ai/         # Model Gateway 和 Providers
│   │   │   ├── db/models/  # SQLAlchemy 数据模型
│   │   │   ├── schemas/    # Pydantic Schema
│   │   │   ├── core/       # 配置、安全、Trace、Guard、Prompt
│   │   │   ├── data/       # CSV 导入和同步
│   │   │   └── tools/      # Tool 实现
│   │   │   └── main.py
│   │   ├── alembic/        # 数据库迁移
│   │   ├── tests/          # 测试
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   └── web/                # React 前端
│       ├── src/
│       │   ├── components/
│       │   ├── pages/
│       │   └── services/
│       ├── Dockerfile
│       └── package.json
│
├── infra/                  # 基础设施配置
│   ├── nginx/
│   │   └── nginx.conf
│   ├── postgres/
│   │   └── init.sql
│   └── scripts/
│       ├── backup-db.sh
│       └── health-check.sh
│
├── docs/                   # 文档
│   └── api/               # API 文档
│
├── 开发/                   # 开发文档（PRD）
├── 旧产物/                 # 旧系统参考
├── 需求文档/               # 需求文档
│
├── docker-compose.yml
├── .env.example
└── README.md
```

## 开发文档

完整的 PRD 文档请参考 [开发/PRD/00_PRD索引.md](开发/PRD/00_PRD索引.md)

### 核心文档

- [项目概述与目标](开发/PRD/01_项目概述与目标.md)
- [技术栈选型](开发/PRD/02_技术栈选型.md)
- [数据模型设计](开发/PRD/03_数据模型设计.md)
- [权限与权益体系](开发/PRD/04_权限与权益体系.md)

### 实施计划

- [阶段一实施计划](开发/PRD/21_阶段一实施计划.md) - 底座搭建
- [阶段二实施计划](开发/PRD/22_阶段二实施计划.md) - BASIC问答闭环
- [阶段三实施计划](开发/PRD/23_阶段三实施计划.md) - DIAGNOSIS + QA

## 数据模型

核心数据表包括：
- 身份表：schools, users, students
- 考试成绩：exams, student_exam_scores, student_subject_scores, question_scores
- 诊断报告：diagnosis_reports, student_entitlements
- Chat: chat_sessions, chat_messages
- Trace: agent_runs, tool_call_logs

详细设计见 [数据模型设计文档](开发/PRD/03_数据模型设计.md)

## 旧系统迁移

本项目通过 Adapter 模式渐进式接入旧系统数据：

1. **阶段一**：新系统通过 Adapter 只读旧数据
2. **阶段二**：数据双写（旧 MySQL + 新 PostgreSQL）
3. **阶段三**：验证稳定后，新系统成为 Source of Truth

详细策略见 [旧系统迁移策略](开发/PRD/14_旧系统迁移策略.md)

## API 文档

启动服务后访问：
- Swagger UI: http://localhost/docs
- ReDoc: http://localhost/redoc

## 测试

详细的测试环境、SQLite/PostgreSQL 选择和 CI 门禁见
[docs/TESTING.md](docs/TESTING.md)。

```bash
# 安装测试依赖并运行后端测试（默认 SQLite；CI 也会跑同一套命令）
./scripts/run_tests.sh

# 前端 lint、单测和生产构建
cd apps/web
npm ci
npm run lint
npm test -- --run
npm run build

# 运行完整质量门禁（后端编译/静态检查 + 前端检查）
cd ../..
./scripts/run_quality.sh
```

`TEST_DATABASE_URL` 可覆盖后端测试数据库，例如
`TEST_DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/testdb ./scripts/run_tests.sh`。

当前仓库门禁覆盖 API/数据库契约、前端单测和生产构建；浏览器级 E2E、压测
及多 worker 的 Redis 限流验证仍需在试点环境执行。

## 健康检查

```bash
# API 健康检查（通过 Nginx 网关）
curl http://localhost/health

# 数据库健康检查
curl http://localhost/api/v1/health/db

# Redis 健康检查
curl http://localhost/api/v1/health/redis
```

## 备份与恢复

```bash
# 备份数据库
./infra/scripts/backup-db.sh

# 恢复数据库
./infra/scripts/restore-db.sh /path/to/backup.sql
```

## 常见问题

### 1. 如何重置数据库？

```bash
docker compose down -v
docker compose up -d
docker compose exec api alembic upgrade head
```

### 2. 如何查看日志？

```bash
# 所有服务日志
docker compose logs -f

# 特定服务日志
docker compose logs -f api
docker compose logs -f db
```

### 3. 如何进入容器调试？

```bash
# 进入 API 容器
docker compose exec api bash

# 进入数据库容器
docker compose exec db psql -U postgres -d intelligent_qa
```

## 许可证

[待定]

## 联系方式

项目负责人: [待补充]
