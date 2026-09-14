# PRD-16: Trace & Audit 设计

---
Status: active
Owner: 平台与安全工程
Last verified: 2026-09-11
Evidence: V2 追踪审计规范；模型、迁移、AgentRun 和审计查询必须一致并通过集成测试。
Supersedes: 旧版 Trace/Audit 模型声明
---

> 本文是目标审计契约。当前 ORM/迁移不一致项必须修复后才可标记 implemented。

## 1. 概述

全链路追踪和审计日志，确保每次 Agent 运行可追溯、可审计、可调试。

---

## 2. 核心数据模型

### 2.1 agent_runs - Agent 运行记录

```sql
CREATE TABLE agent_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES chat_sessions(id),
    school_id UUID NOT NULL,
    student_id UUID NOT NULL,
    query TEXT NOT NULL,
    intent VARCHAR(50),
    entitlement_level VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    model_profile_id VARCHAR(100),
    prompt_version VARCHAR(50),
    tool_call_count INT DEFAULT 0,
    latency_ms INT,
    input_tokens INT,
    output_tokens INT,
    estimated_cost DECIMAL(10,6),
    error_code VARCHAR(50),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMP
);

CREATE INDEX idx_agent_runs_student ON agent_runs(student_id, created_at DESC);
CREATE INDEX idx_agent_runs_session ON agent_runs(session_id);
CREATE INDEX idx_agent_runs_status ON agent_runs(status, created_at DESC);
```

### 2.2 tool_call_logs - Tool 调用日志

```sql
CREATE TABLE tool_call_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_run_id UUID NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    tool_name VARCHAR(100) NOT NULL,
    input_json JSONB NOT NULL,
    output_summary_json JSONB,
    status VARCHAR(20) NOT NULL,
    latency_ms INT,
    error_code VARCHAR(50),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tool_call_logs_run ON tool_call_logs(agent_run_id);
CREATE INDEX idx_tool_call_logs_tool ON tool_call_logs(tool_name, created_at DESC);
```

### 2.3 model_usage_logs - 模型使用日志

```sql
CREATE TABLE model_usage_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_run_id UUID REFERENCES agent_runs(id),
    provider VARCHAR(50) NOT NULL,
    model VARCHAR(100) NOT NULL,
    prompt_tokens INT NOT NULL,
    completion_tokens INT NOT NULL,
    total_tokens INT NOT NULL,
    estimated_cost DECIMAL(10,6),
    latency_ms INT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_model_usage_logs_run ON model_usage_logs(agent_run_id);
CREATE INDEX idx_model_usage_logs_model ON model_usage_logs(model, created_at DESC);
```

---

## 3. Trace Context

### 3.1 TraceContext 结构

```python
class TraceContext(BaseModel):
    """追踪上下文"""
    request_id: str          # HTTP 请求 ID
    agent_run_id: str        # Agent 运行 ID
    session_id: str          # 会话 ID
    user_id: UUID
    student_id: UUID
    school_id: UUID
```

### 3.2 Context 注入

```python
from contextvars import ContextVar

trace_context: ContextVar[TraceContext | None] = ContextVar(
    'trace_context',
    default=None
)

# Middleware 注入
@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    
    # 设置 context
    ctx = TraceContext(
        request_id=request_id,
        agent_run_id=str(uuid4()),
        session_id=request.path_params.get("session_id", ""),
        user_id=current_user.id,
        student_id=current_user.student_id,
        school_id=current_user.school_id
    )
    trace_context.set(ctx)
    
    # 添加响应头
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
```

---

## 4. 日志记录

### 4.1 Agent Run 记录

```python
class AgentRunTracer:
    """Agent 运行追踪"""
    
    async def start_run(
        self,
        student_id: UUID,
        query: str,
        intent: str,
        entitlement: str
    ) -> str:
        """开始运行"""
        
        ctx = trace_context.get()
        
        run = AgentRun(
            id=ctx.agent_run_id,
            session_id=ctx.session_id,
            school_id=ctx.school_id,
            student_id=student_id,
            query=query,
            intent=intent,
            entitlement_level=entitlement,
            status="running",
            created_at=datetime.utcnow()
        )
        
        await self.db.add(run)
        await self.db.commit()
        
        return run.id
    
    async def finish_run(
        self,
        run_id: str,
        status: str,
        model_profile_id: str,
        prompt_version: str,
        tool_call_count: int,
        latency_ms: int,
        input_tokens: int,
        output_tokens: int,
        estimated_cost: Decimal,
        error_code: str | None = None
    ):
        """完成运行"""
        
        await self.db.execute(
            update(AgentRun)
            .where(AgentRun.id == run_id)
            .values(
                status=status,
                model_profile_id=model_profile_id,
                prompt_version=prompt_version,
                tool_call_count=tool_call_count,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost=estimated_cost,
                error_code=error_code,
                finished_at=datetime.utcnow()
            )
        )
        await self.db.commit()
```

### 4.2 Tool Call 记录

```python
class ToolCallTracer:
    """Tool 调用追踪"""
    
    async def log_tool_call(
        self,
        agent_run_id: str,
        tool_name: str,
        input_args: dict,
        output_summary: dict,
        status: str,
        latency_ms: int,
        error_code: str | None = None
    ):
        """记录 Tool 调用"""
        
        log = ToolCallLog(
            agent_run_id=agent_run_id,
            tool_name=tool_name,
            input_json=input_args,
            output_summary_json=output_summary,
            status=status,
            latency_ms=latency_ms,
            error_code=error_code,
            created_at=datetime.utcnow()
        )
        
        await self.db.add(log)
        await self.db.commit()
```

---

## 5. 结构化日志

### 5.1 日志格式

```python
import structlog

logger = structlog.get_logger()

# 配置
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)

# 使用
logger.info(
    "agent_run_started",
    agent_run_id=run_id,
    student_id=str(student_id),
    query=query,
    entitlement=entitlement
)
```

### 5.2 日志示例

```json
{
  "event": "agent_run_started",
  "timestamp": "2026-09-09T10:05:00Z",
  "level": "info",
  "request_id": "req_abc123",
  "agent_run_id": "run_def456",
  "student_id": "uuid",
  "query": "我这次考得怎样？",
  "entitlement": "BASIC"
}
```

---

## 6. 审计日志

### 6.1 audit_logs 表

```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action VARCHAR(100) NOT NULL,
    actor_type VARCHAR(50) NOT NULL,
    actor_id UUID NOT NULL,
    resource_type VARCHAR(50),
    resource_id UUID,
    allowed BOOLEAN NOT NULL,
    reason VARCHAR(200),
    metadata JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_logs_actor ON audit_logs(actor_id, created_at DESC);
CREATE INDEX idx_audit_logs_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX idx_audit_logs_action ON audit_logs(action, allowed, created_at DESC);
```

### 6.2 审计记录

```python
class AuditLogger:
    """审计日志"""
    
    async def record(
        self,
        action: str,
        actor_type: str,
        actor_id: UUID,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
        allowed: bool = True,
        reason: str | None = None,
        metadata: dict | None = None
    ):
        """记录审计日志"""
        
        ctx = trace_context.get()
        
        log = AuditLog(
            action=action,
            actor_type=actor_type,
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            allowed=allowed,
            reason=reason,
            metadata=metadata,
            request_id=ctx.request_id if ctx else None,
            created_at=datetime.utcnow()
        )
        
        await self.db.add(log)
        await self.db.commit()

# 使用示例
await audit_logger.record(
    action="READ_DIAGNOSIS",
    actor_type="student",
    actor_id=student_id,
    resource_type="diagnosis_report",
    resource_id=report_id,
    allowed=False,
    reason="ENTITLEMENT_REQUIRED"
)
```

---

## 7. 追踪查询

### 7.1 按 Agent Run ID 查询

```python
async def get_agent_run_detail(run_id: str) -> AgentRunDetail:
    """获取 Agent 运行详情"""
    
    # 获取基本信息
    run = await db.get(AgentRun, run_id)
    
    # 获取 Tool 调用
    tool_calls = await db.execute(
        select(ToolCallLog)
        .where(ToolCallLog.agent_run_id == run_id)
        .order_by(ToolCallLog.created_at)
    )
    
    # 获取模型使用
    model_usage = await db.execute(
        select(ModelUsageLog)
        .where(ModelUsageLog.agent_run_id == run_id)
    )
    
    # 获取审计日志
    audit_logs = await db.execute(
        select(AuditLog)
        .where(AuditLog.metadata['agent_run_id'].astext == run_id)
    )
    
    return AgentRunDetail(
        run=run,
        tool_calls=tool_calls.scalars().all(),
        model_usage=model_usage.scalars().all(),
        audit_logs=audit_logs.scalars().all()
    )
```

### 7.2 时间范围统计

```sql
-- 统计某时间段的 Agent 运行
SELECT 
    DATE(created_at) as date,
    status,
    COUNT(*) as count,
    AVG(latency_ms) as avg_latency,
    AVG(input_tokens + output_tokens) as avg_tokens,
    SUM(estimated_cost) as total_cost
FROM agent_runs
WHERE created_at >= '2026-09-01'
  AND created_at < '2026-10-01'
GROUP BY DATE(created_at), status
ORDER BY date DESC, status;
```

---

## 8. 监控指标

### 8.1 关键指标

```python
class MetricsCollector:
    """指标收集"""
    
    async def collect_daily_metrics(self, date: date) -> DailyMetrics:
        """收集每日指标"""
        
        # Agent 运行统计
        run_stats = await db.execute(
            select(
                func.count(AgentRun.id).label('total_runs'),
                func.sum(case((AgentRun.status == 'success', 1), else_=0)).label('success_runs'),
                func.avg(AgentRun.latency_ms).label('avg_latency'),
                func.sum(AgentRun.input_tokens + AgentRun.output_tokens).label('total_tokens'),
                func.sum(AgentRun.estimated_cost).label('total_cost')
            )
            .where(func.date(AgentRun.created_at) == date)
        )
        
        # Tool 调用统计
        tool_stats = await db.execute(
            select(
                ToolCallLog.tool_name,
                func.count(ToolCallLog.id).label('call_count'),
                func.avg(ToolCallLog.latency_ms).label('avg_latency')
            )
            .join(AgentRun, ToolCallLog.agent_run_id == AgentRun.id)
            .where(func.date(AgentRun.created_at) == date)
            .group_by(ToolCallLog.tool_name)
        )
        
        return DailyMetrics(
            date=date,
            run_stats=run_stats.fetchone(),
            tool_stats=tool_stats.fetchall()
        )
```

---

## 9. 日志查询 API

### 9.1 管理后台 API

```python
@router.get("/admin/traces/runs")
async def list_agent_runs(
    student_id: UUID | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 50,
    offset: int = 0
):
    """查询 Agent 运行列表"""
    
    query = select(AgentRun)
    
    if student_id:
        query = query.where(AgentRun.student_id == student_id)
    if status:
        query = query.where(AgentRun.status == status)
    if date_from:
        query = query.where(AgentRun.created_at >= date_from)
    if date_to:
        query = query.where(AgentRun.created_at < date_to)
    
    query = query.order_by(AgentRun.created_at.desc()).limit(limit).offset(offset)
    
    result = await db.execute(query)
    runs = result.scalars().all()
    
    return {"items": runs, "total": len(runs)}
```

---

## 10. 关键要点

1. **每次 Agent 运行都有唯一 run_id**
2. **所有 Tool 调用都关联到 run_id**
3. **模型使用都记录 Token 和成本**
4. **审计日志记录权限拒绝**
5. **结构化日志便于查询和分析**
6. **Trace Context 在整个请求链路传递**
