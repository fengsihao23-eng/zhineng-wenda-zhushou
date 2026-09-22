# 学生智能问答系统 - AI 构建指令

---
Status: archived
Owner: 产品与平台工程
Last verified: 2026-09-11
Evidence: 历史构建提示词；当前实施以 docs/01-需求文档/市级学生智能问答助手_PRD_v1.0.md 和 docs/02-PRD设计与实施/21-25 为准。
Supersedes: 旧版 AI 构建顺序和阶段完成声明
---

> **历史参考（DESIGN-REFERENCE）**：本文保留早期构建思路和代码示例，不再作为执行指令、验收依据或生产就绪声明。请先遵循 V2 阶段 0—1 契约冻结与基础平台计划。

## 项目概述

你需要帮我构建一个**学生智能问答系统**，这是一个基于真实学校业务数据的 AI Agent 应用。

**核心特点**：
- 学生可以用自然语言问"我这次考得怎样？"、"比上次进步了吗？"
- 系统从数据库读取真实成绩数据，通过 Agent + Tool Calling 返回准确答案
- 有严格的权限控制：BASIC 用户只能看客观数据，DIAGNOSIS 用户可以看诊断报告
- 使用轻量 Agent 架构，不用复杂的 Multi-Agent，一期不依赖 RAG

**重要原则**：
- ✅ 真实数据优先于模型能力
- ✅ 权限优先于 Prompt
- ✅ 计算交给代码，不交给 LLM
- ✅ 一期不用 RAG，不用复杂 Multi-Agent
- ✅ 旧系统是资产，通过 Adapter 渐进迁移

---

## 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 前端 | React + TypeScript + Vite | 复用现有前端资产 |
| 后端 | FastAPI + Python 3.11+ | 异步高性能 |
| 数据库 | PostgreSQL 15+ | 关系型数据 + pgvector 扩展 |
| ORM | SQLAlchemy 2.x Async | 异步 ORM |
| Migration | Alembic | 数据库版本管理 |
| 数据校验 | Pydantic v2 | 类型安全 |
| 缓存/队列 | Redis | Session、Rate Limit、Job Queue |
| 网关 | Nginx | TLS、反向代理、SSE 支持 |
| 部署 | Docker Compose | 一期本地/单服务器部署 |
| AI | 自研 Model Gateway + Prompt Registry + Tool Calling | 不用 LangChain/Dify |

---

## 项目结构

```text
student-agent/
├── apps/
│   ├── api/                      # FastAPI 后端
│   │   ├── app/
│   │   │   ├── api/              # API 路由
│   │   │   │   ├── deps.py       # 依赖注入
│   │   │   │   └── v1/
│   │   │   │       ├── auth.py   # 认证 API
│   │   │   │       ├── chat.py   # 对话 API
│   │   │   │       └── health.py # 健康检查
│   │   │   │
│   │   │   ├── ai/               # AI 核心
│   │   │   │   ├── gateway.py    # Model Gateway
│   │   │   │   ├── agent/
│   │   │   │   │   ├── loop.py   # Agent Loop
│   │   │   │   │   └── context_builder.py  # 上下文构建
│   │   │   │   ├── tools/
│   │   │   │   │   ├── base.py   # Tool 基类
│   │   │   │   │   └── registry.py  # Tool 注册
│   │   │   │   ├── prompts/
│   │   │   │   │   └── registry.py  # Prompt 版本管理
│   │   │   │   └── providers/
│   │   │   │       ├── base.py
│   │   │   │       ├── openai_compatible.py
│   │   │   │       └── deepseek.py
│   │   │   │
│   │   │   ├── adapters/          # 数据适配层
│   │   │   │   ├── student_data.py
│   │   │   │   ├── legacy_mysql/  # 旧系统适配
│   │   │   │   └── postgres/      # 新系统原生
│   │   │   │
│   │   │   ├── domains/           # 业务领域
│   │   │   │   ├── auth/
│   │   │   │   ├── school/
│   │   │   │   ├── student/
│   │   │   │   └── exam/
│   │   │   │
│   │   │   ├── db/
│   │   │   │   ├── base.py        # Base Model
│   │   │   │   ├── session.py     # 数据库会话
│   │   │   │   └── models/        # SQLAlchemy Models
│   │   │   │
│   │   │   ├── core/
│   │   │   │   ├── config.py      # 配置
│   │   │   │   ├── security.py    # JWT
│   │   │   │   ├── errors.py      # 错误处理
│   │   │   │   └── logging.py     # 日志
│   │   │   │
│   │   │   └── main.py            # FastAPI App
│   │   │
│   │   ├── alembic/               # 数据库迁移
│   │   │   ├── versions/
│   │   │   └── env.py
│   │   │
│   │   ├── tests/                 # 测试
│   │   │   ├── conftest.py
│   │   │   ├── test_auth.py
│   │   │   └── test_agent.py
│   │   │
│   │   └── pyproject.toml
│   │
│   └── web/                       # React 前端
│       ├── src/
│       │   ├── components/
│       │   │   └── Chat/
│       │   ├── api/
│       │   └── App.tsx
│       │
│       ├── package.json
│       └── vite.config.ts
│
├── infra/
│   ├── docker/
│   │   ├── postgres/
│   │   │   └── init.sql
│   │   ├── redis/
│   │   │   └── redis.conf
│   │   └── nginx/
│   │       └── nginx.conf
│   └── scripts/
│
├── docs/
│   ├── legacy/
│   │   ├── LEGACY_MAP.md          # 旧系统映射
│   │   └── MIGRATION_MAPPING.md   # 迁移映射
│   └── adr/                       # 架构决策记录
│
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 阶段一：底座搭建（Week 1-2）

### 目标
建立完整的技术基础设施，验证技术栈可行性。

### 任务清单

#### 1. 项目初始化（Day 1-2）
```bash
# 创建项目结构
# 初始化 FastAPI 项目（pyproject.toml）
# 初始化 React 项目（Vite + TypeScript）
# 配置代码规范（ESLint、Black、Ruff）
# 创建 README.md
```

**依赖**：
- FastAPI
- SQLAlchemy[asyncio]
- alembic
- pydantic[email]
- python-jose[cryptography]
- passlib[bcrypt]
- asyncpg
- redis
- pytest
- pytest-asyncio

#### 2. Docker Compose（Day 3-4）
```yaml
services:
  postgres:
    image: pgvector/pgvector:pg15
    environment:
      POSTGRES_DB: student_agent
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  api:
    build: ./apps/api
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@postgres/student_agent
      REDIS_URL: redis://redis:6379
    depends_on:
      - postgres
      - redis
    ports:
      - "8000:8000"

  nginx:
    image: nginx:alpine
    volumes:
      - ./infra/docker/nginx/nginx.conf:/etc/nginx/nginx.conf
    ports:
      - "80:80"
    depends_on:
      - api
```

#### 3. 认证系统（Day 5-6）
**核心表**：
- users（用户表）
- roles（角色表：SUPER_ADMIN, SCHOOL_ADMIN, TEACHER, STUDENT, QA）
- user_roles（用户角色关联）
- students（学生表，关联 users）

**API 端点**：
- POST /api/v1/auth/login
- POST /api/v1/auth/refresh
- GET /api/v1/auth/me

**关键点**：
- JWT Token + Refresh Token
- 所有业务表必须有 school_id（数据隔离）
- 学生身份来自 JWT → current_user → bound_student_id
- **禁止 Tool 接受任意 student_id 参数**

#### 4. 核心数据模型（Day 7-8）
**必需表**：
- schools（学校）
- students（学生）
- exams（考试）
- subjects（科目）
- exam_subjects（考试科目关联）
- student_exam_scores（学生考试总分）
- student_subject_scores（学生科目成绩）
- question_scores（小题得分）
- diagnosis_reports（诊断报告，JSONB存储）
- student_entitlements（学生权益：BASIC / DIAGNOSIS）
- chat_sessions（对话会话）
- chat_messages（对话消息）
- agent_runs（Agent 运行记录）
- tool_call_logs（Tool 调用日志）

**关键约束**：
- 所有业务表必须有 school_id
- 确定性计算字段（lost_score、rank_delta）由代码计算，不让 LLM 算
- 外部系统数据必须有 external_id + source_system + source_updated_at

#### 5. Model Gateway（Day 9-10）
```python
class ModelGateway:
    """统一模型调用入口"""
    
    async def chat(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None
    ) -> ModelResponse:
        """调用模型"""
        pass
    
    async def chat_with_tools(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict],
        max_tool_rounds: int = 2
    ) -> ModelResponse:
        """调用模型并支持 Tool Calling"""
        pass
```

**Provider 适配**：
- OpenAI Compatible（通用接口）
- DeepSeek
- 其他国产模型

**功能**：
- Retry 逻辑
- Fallback 降级
- Usage Tracking（token 统计）
- Circuit Breaker（熔断）

#### 6. Prompt Registry（Day 11）
```python
class PromptRegistry:
    """Prompt 版本管理"""
    
    async def get(
        self,
        name: str,
        version: str | None = None
    ) -> PromptTemplate:
        """获取 Prompt 模板"""
        pass
    
    async def render(
        self,
        name: str,
        version: str,
        context: dict
    ) -> str:
        """渲染 Prompt"""
        pass
```

**第一个 System Prompt**：
```text
你是一个学生智能助手。你的职责是基于学生的真实成绩数据，回答学生的问题。

## 身份信息
学生姓名：{{ student_name }}
所在班级：{{ class_name }}
当前权益：{{ entitlement_level }}

## 权限规则
{% if entitlement_level == "BASIC" %}
- 你只能回答客观数据（分数、排名、小题得分）
- 你不能推断或解释失分原因、薄弱知识点、学习问题
- 如果学生问"为什么"，告诉他需要购买诊断报告
{% elif entitlement_level == "DIAGNOSIS" %}
- 你可以读取学生已购买的诊断报告
- 只解释报告内已有的诊断结论，不能自己推断
{% endif %}

## 数据来源
- 所有数据来自 Tool 调用返回的 evidence
- 确定性数值（分数、排名、差值）已经由系统计算好
- 你不需要自己计算，直接引用即可

## 回答要求
- 简洁、准确、友好
- 引用具体数字时使用 Tool 返回的 evidence
- 不要编造数据
- 不确定时可以说"我需要查询一下"
```

#### 7. 旧系统映射（Day 12-13）
**任务**：
- 扫描 `/Users/hao/智能问答助手/旧产物/09-旧代码`
- 输出 `docs/legacy/LEGACY_MAP.md`：
  - 所有表结构
  - 所有 API 端点
  - 数据模型
- 输出 `docs/legacy/MIGRATION_MAPPING.md`：
  - 旧字段 → 新字段映射
  - 迁移策略

#### 8. Health Check（Day 14）
```python
@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat()
    }

@router.get("/health/db")
async def health_check_db(db: AsyncSession = Depends(get_db)):
    await db.execute("SELECT 1")
    return {"status": "ok"}

@router.get("/health/redis")
async def health_check_redis(redis: Redis = Depends(get_redis)):
    await redis.ping()
    return {"status": "ok"}
```

### 阶段一验收标准
- [ ] `docker-compose up -d` 所有服务启动成功（需在全新环境验证）
- [ ] 数据库连接正常，Migration 可执行（需附空库迁移证据）
- [ ] 用户可以登录并获得 JWT Token（需附认证集成测试）
- [ ] Model Gateway 可调用 DeepSeek（需附供应商集成测试）
- [ ] 基础数据模型创建成功（需附模型/迁移一致性证据）
- [ ] 测试覆盖率 > 60%（需附可重复命令和报告）
- [ ] LEGACY_MAP.md 和 MIGRATION_MAPPING.md 完成（当前仓库未以此项作为 V2 门槛）

---

## 阶段二：BASIC 问答闭环（Week 3）

### 目标
让学生能基于真实成绩数据进行准确的问答，完成核心业务价值验证。

### 核心任务

#### 1. Student Context Builder（Day 3-4）
```python
class StudentContextBuilder:
    """学生上下文构建器 - 按需加载"""
    
    async def build(
        self,
        actor: AuthenticatedStudent,
        query: str,
        session: ChatSession,
        selected_exam_id: UUID | None = None
    ) -> StudentContext:
        """
        构建学生上下文
        
        步骤：
        1. 意图识别（Intent Router）
        2. 生成加载计划（ContextPlan）
        3. 并行加载数据
        4. 组装上下文
        """
        # 1. 意图识别
        intent = await self.intent_router.route(query, session)
        
        # 2. 生成加载计划
        plan = self._plan_context_loading(intent, selected_exam_id)
        
        # 3. 并行加载数据
        data = await self._load_data_parallel(actor.student_id, plan)
        
        # 4. 组装上下文
        return StudentContext(
            student=data.student,
            current_exam=data.current_exam,
            exam_summary=data.exam_summary,
            subject_scores=data.subject_scores,
            entitlement=data.entitlement,
            intent=intent
        )
```

**Intent 类型**：
- EXAM_SUMMARY（考试总结）
- SUBJECT_DETAIL（科目详情）
- RANK_CHANGE（排名变化）
- TREND_ANALYSIS（趋势分析）
- QUESTION_LOSS（小题丢分）
- DIAGNOSIS（诊断分析）

#### 2. Tool Registry（Day 5）
**6个核心 Tool**：

```python
# 1. get_exam_summary - 获取考试总结
{
  "exam_id": "uuid"
}
→ {
  "total_score": 128,
  "full_score": 150,
  "grade_rank": 31,
  "grade_student_count": 420,
  "class_rank": 5,
  "class_student_count": 50,
  "subjects": [...]
}

# 2. get_subject_scores - 获取科目成绩
{
  "exam_id": "uuid",
  "subject_codes": ["MATH", "CHINESE"]
}
→ [
  {
    "subject": "数学",
    "score": 92,
    "full_score": 100,
    "grade_rank": 15,
    "grade_avg": 85.3
  }
]

# 3. get_rank_change - 获取排名变化
{
  "current_exam_id": "uuid",
  "previous_exam_id": "uuid"
}
→ {
  "rank_delta": 5,  # 正数=进步
  "score_delta": 8.5
}

# 4. get_score_trend - 获取成绩趋势
{
  "subject_code": "MATH",
  "limit": 5
}
→ [
  {"exam": "期中考试", "score": 92, "rank": 15},
  {"exam": "月考", "score": 88, "rank": 20}
]

# 5. get_question_losses - 获取小题丢分
{
  "exam_id": "uuid",
  "subject_code": "MATH",
  "top_n": 5
}
→ [
  {"question_no": "17", "lost_score": 5, "full_score": 5},
  {"question_no": "20", "lost_score": 3, "full_score": 5}
]

# 6. get_diagnosis - 获取诊断报告（验证权益）
{
  "exam_id": "uuid",
  "subject_code": "MATH"
}
→ {
  "allowed": true,
  "report": {
    "weaknesses": ["函数综合题失分多"],
    "loss_reasons": ["函数定义域判断错误"],
    "suggestions": ["专项练习函数复合"]
  }
}
```

**Tool 实现要点**：
- 每个 Tool 必须校验 student_id（来自 JWT，不允许传参）
- 每个 Tool 返回必须包含 evidence（数据来源）
- get_diagnosis 必须先校验 student_entitlements
- 所有数值计算在 Tool 内完成，不让 LLM 算

#### 3. Agent Loop（Day 6-7）
```python
class AgentLoop:
    """轻量 Agent 循环"""
    
    async def run(
        self,
        actor: AuthenticatedStudent,
        query: str,
        session: ChatSession
    ) -> AgentResponse:
        """
        执行一次完整的 Agent 循环
        
        流程：
        1. Authenticate
        2. Create AgentRun
        3. Load Context (via ContextBuilder)
        4. Build Messages (System + History + Query)
        5. Call Model
        6. If tool_calls: Execute Tools (最多2轮)
        7. Return final answer
        8. Persist state
        """
        # 1. 创建 AgentRun 记录
        agent_run = await self._create_agent_run(actor, query, session)
        
        # 2. 构建上下文
        context = await self.context_builder.build(
            actor, query, session, session.selected_exam_id
        )
        
        # 3. 构建消息
        messages = await self._build_messages(context, session, query)
        
        # 4. 调用模型（最多2轮 Tool）
        response = await self.model_gateway.chat_with_tools(
            model=self.model_name,
            messages=messages,
            tools=self._get_available_tools(context.entitlement),
            max_tool_rounds=2
        )
        
        # 5. 持久化状态
        await self._persist_agent_run(agent_run, response)
        
        return AgentResponse(
            text=response.text,
            state=response.state
        )
```

**关键限制**：
- MAX_TOOL_ROUNDS = 2（硬限制，防止循环）
- Tool 超时 = 10s
- 总超时 = 30s

#### 4. Chat API（Day 8）
```python
# POST /api/v1/chat/sessions - 创建会话
# GET /api/v1/chat/sessions - 列出会话
# GET /api/v1/chat/sessions/{id} - 获取会话
# POST /api/v1/chat/sessions/{id}/messages - 发送消息
# POST /api/v1/chat/sessions/{id}/stream - SSE 流式（基础版）
```

#### 5. 前端 Chat 界面（Day 9-10）
- 基础 Chat 组件（消息列表 + 输入框）
- API 集成
- 基础样式
- 阶段二先用普通 HTTP，不做 SSE 流式

#### 6. 测试（Day 11-12）
**40+ 测试用例**：
- 考试总结（10个）
- 科目成绩（10个）
- 排名变化（10个）
- 历史趋势（5个）
- 小题丢分（5个）

**验证**：
- 数字准确率 = 100%
- 问答成功率 > 90%
- 平均响应时间 < 3s

### 阶段二验收标准
- [ ] 学生可以登录并进入 Chat 界面
- [ ] 可以问"这次考得怎样"并得到准确答案
- [ ] 可以问"比上次如何"并得到准确比较
- [ ] 可以问"哪科变化最大"并得到正确科目
- [ ] 可以问"哪几题丢分多"并得到正确题号
- [ ] 所有数字与数据库一致（需 Tool 证据）
- [ ] 40+ 测试用例全部通过（不得以测试数量替代通过证据）

---

## 阶段三：DIAGNOSIS + QA（Week 4-5）

### 目标
完成 DIAGNOSIS 权益，增强安全性，完整测试。

### 核心任务

#### 1. DIAGNOSIS 权益（Day 1-2）
- 权益判断逻辑
- get_diagnosis Tool 完整实现
- 诊断报告结构化存储（JSONB）

#### 2. Response Guard（Day 3-4）
```python
class ResponseGuard:
    """答案校验 - 最后一道防线"""
    
    async def validate(
        self,
        response: str,
        context: StudentContext,
        tool_calls: list[ToolCall]
    ) -> GuardResult:
        """
        校验模型回答
        
        检查项：
        1. Evidence 对齐（数字是否来自 Tool）
        2. 权限合规（BASIC 用户是否被诱导说诊断）
        3. 跨学生隔离（是否提到其他学生）
        4. 敏感信息（是否泄露 system prompt）
        """
        pass
```

#### 3. 安全测试（Day 5-6）
- Prompt Injection 防御测试
- 跨学生隔离测试
- 权益绕过测试

#### 4. E2E 测试（Day 7-8）
- Playwright 自动化测试
- 完整用户流程

#### 5. 性能优化（Day 9-10）
- Context Builder 并行加载优化
- Tool 执行缓存
- 压力测试

### 阶段三验收标准
- [ ] DIAGNOSIS 权益正常工作（已后置，不属于 V1 试点范围）
- [ ] Response Guard 拦截率 > 95%（需先定义评估集和误报指标）
- [ ] 所有安全测试通过
- [ ] E2E 测试通过
- [ ] 性能指标达标

---

## 关键配置文件示例

### .env.example
```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/student_agent

# Redis
REDIS_URL=redis://localhost:6379

# JWT
JWT_SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Model Gateway
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com

# App
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=INFO
```

### pyproject.toml
```toml
[project]
name = "student-agent-api"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "sqlalchemy[asyncio]>=2.0.25",
    "alembic>=1.13.1",
    "asyncpg>=0.29.0",
    "pydantic>=2.5.3",
    "pydantic-settings>=2.1.0",
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
    "redis>=5.0.1",
    "httpx>=0.26.0",
    "python-multipart>=0.0.6",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.3",
    "pytest-asyncio>=0.21.1",
    "pytest-cov>=4.1.0",
    "black>=23.12.1",
    "ruff>=0.1.9",
    "mypy>=1.8.0",
]
```

---

## 工作流程

### 每次开始新功能
1. 创建 Alembic Migration（如涉及数据库）
2. 编写 SQLAlchemy Models（如涉及新表）
3. 编写 Pydantic Schemas（API 接口）
4. 编写业务逻辑
5. 编写单元测试
6. 编写集成测试
7. 更新 API 文档

### 代码规范
- 后端：Black + Ruff
- 前端：ESLint + Prettier
- 类型检查：mypy（后端）+ TypeScript（前端）
- 测试覆盖率 > 80%

### Git 规范
```
feat: 新功能
fix: 修复
docs: 文档
test: 测试
refactor: 重构
perf: 性能优化
chore: 构建/工具
```

---

## 重要参考文档

所有 PRD 文档位于：`docs/02-PRD设计与实施/`

**必读**：
- 00_PRD索引.md
- 01_项目概述与目标.md
- 02_技术栈选型.md
- 03_数据模型设计.md
- 21_阶段一实施计划.md
- 22_阶段二实施计划.md
- 25_验收标准.md

**按需阅读**：
- 05_StudentContextBuilder.md
- 06_Tool设计规范.md
- 07_Agent轻量循环.md
- 08_ModelGateway设计.md
- 09_PromptRegistry设计.md

---

## 最重要的 12 条原则

1. **真实数据优先于模型能力**
2. **权限优先于 Prompt**
3. **计算交给代码，不交给 LLM**
4. **一期不用 RAG**
5. **一期不用 Multi-Agent**
6. **Context 按问题动态加载**
7. **BASIC 与 DIAGNOSIS 在 Tool 层隔离**
8. **ModelGateway 是所有模型调用唯一入口**
9. **Prompt 必须版本化**
10. **每轮 Agent 必须可追溯**
11. **旧系统是资产，不是垃圾代码**
12. **成熟开源项目拿来解决成熟问题，不拿来制造新复杂度**

---

## 历史文档使用说明

本文不再作为当前开发任务提示词。新的实现应从 [PRD-21：V2 阶段 0—1 实施计划](21_阶段一实施计划.md) 开始，并以 [市级学生智能问答助手 PRD v1.0](../01-需求文档/市级学生智能问答助手_PRD_v1.0.md) 为唯一产品基线；每个阶段必须按照 PRD-25 的证据门禁验收。
