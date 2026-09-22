# PRD-07: Agent 轻量循环设计

---
Status: active
Owner: Agent 平台
Last verified: 2026-09-11
Evidence: 目标 Agent 主链路；当前主链路是否接通以 FakeModelProvider、Tool、Guard 和 Trace 集成测试为准。
Supersedes: 旧版 Agent Loop 实现声明
---

> 第一阶段只保留一套可测试 AgentLoop；增强循环文档中的示例不构成功能完成证据。

## 1. 概述

Agent Loop 不需要 LangGraph / CrewAI / AutoGen 才能做。一期直接写清晰可测试的 Loop。

### 1.1 设计原则

- 轻量级，可测试
- 明确的状态管理
- 硬限制防止无限循环
- 可追踪每一步

---

## 2. Agent Loop 流程

### 2.1 完整流程

```text
1. Authenticate（认证）
2. Create AgentRun（创建运行记录）
3. Load recent session（加载会话历史）
4. Route intent（意图识别）
5. Build minimal structured context（构建上下文）
6. Build system prompt（构建系统提示）
7. Call model（调用模型）
8. If tool_calls:
      validate tool name（验证工具名）
      validate max tool rounds（验证轮次限制）
      inject ToolContext（注入工具上下文）
      execute read-only tool（执行只读工具）
      append structured result（附加结果）
      call model again（再次调用模型）
9. Response Guard（响应守卫）
10. Stream final answer（流式返回答案）
11. Persist messages（持久化消息）
12. Persist model/tool trace（持久化追踪）
```

---

## 3. AgentState 数据结构

### 3.1 核心状态

```python
class AgentState(BaseModel):
    """Agent 运行状态"""
    
    # 运行标识
    run_id: str
    session_id: str
    school_id: UUID
    student_id: UUID
    
    # 输入
    query: str
    intent: QueryIntent
    entitlement: str  # 'BASIC' or 'DIAGNOSIS'
    
    # 上下文
    context: StudentContext
    
    # Tool 执行
    tool_round: int = 0
    tool_calls: list[ToolCallTrace] = []
    
    # 模型配置
    model_id: str
    prompt_version: str
    
    # 时间
    started_at: datetime
    finished_at: datetime | None = None
```

### 3.2 ToolCallTrace

```python
class ToolCallTrace(BaseModel):
    """Tool 调用追踪"""
    tool_name: str
    input_args: dict
    output_summary: dict
    status: str  # 'success', 'error'
    latency_ms: int
    error_code: str | None = None
    executed_at: datetime
```

---

## 4. 硬限制

### 4.1 防止无限循环

```python
class AgentLimits:
    MAX_TOOL_ROUNDS = 2           # 最多2轮Tool调用
    MAX_TOOLS_PER_ROUND = 3       # 每轮最多3个Tool
    MAX_TOTAL_TOOL_CALLS = 5      # 总共最多5次
    MAX_TURN_TIME_SECONDS = 60    # 单次对话最长60秒
```

### 4.2 超限处理

```python
if state.tool_round >= AgentLimits.MAX_TOOL_ROUNDS:
    raise AgentLimitExceededError(
        code="AGENT_TOOL_BUDGET_EXCEEDED",
        message="已达到工具调用次数上限"
    )
```

---

## 5. Intent Router

### 5.1 意图分类

```python
class QueryIntent(BaseModel):
    type: Literal[
        "EXAM_SUMMARY",      # 考试总结
        "SUBJECT_SCORE",     # 科目成绩
        "RANK_CHANGE",       # 排名变化
        "SCORE_TREND",       # 成绩趋势
        "QUESTION_LOSS",     # 小题丢分
        "DIAGNOSIS",         # 诊断报告
        "GENERAL_STUDENT_DATA",  # 一般学生数据
        "OUT_OF_SCOPE"       # 超出范围
    ]
    subject: str | None = None
    exam_hint: str | None = None
    needs_diagnosis: bool = False
    confidence: float = 0.0
```

### 5.2 路由策略

一期不要上复杂 Router Agent。推荐先做：

```text
规则命中
   ↓
不明确时才用轻量模型分类
```

**示例规则**：
```python
def route_by_rules(query: str) -> QueryIntent | None:
    """基于规则的快速路由"""
    
    query_lower = query.lower()
    
    if any(kw in query_lower for kw in ["这次", "考得", "总分", "多少分"]):
        return QueryIntent(type="EXAM_SUMMARY", confidence=0.9)
    
    if any(kw in query_lower for kw in ["比上次", "进步", "退步", "变化"]):
        return QueryIntent(type="RANK_CHANGE", confidence=0.9)
    
    if any(kw in query_lower for kw in ["哪题", "丢分", "失分", "小题"]):
        return QueryIntent(type="QUESTION_LOSS", confidence=0.9)
    
    if any(kw in query_lower for kw in ["为什么", "原因", "薄弱", "问题"]):
        return QueryIntent(type="DIAGNOSIS", needs_diagnosis=True, confidence=0.7)
    
    return None  # 需要模型分类
```

### 5.3 模型分类（降级）

```python
async def route_by_model(
    query: str,
    recent_messages: list[Message]
) -> QueryIntent:
    """使用轻量模型分类"""
    
    response = await model_gateway.structured(
        model="gpt-4o-mini",  # 轻量快速模型
        messages=[
            {"role": "system", "content": INTENT_CLASSIFICATION_PROMPT},
            {"role": "user", "content": query}
        ],
        response_schema=QueryIntent.model_json_schema(),
        temperature=0.1
    )
    
    return QueryIntent(**response)
```

---

## 6. Agent Loop 实现

### 6.1 主循环

```python
class AgentLoop:
    def __init__(
        self,
        context_builder: StudentContextBuilder,
        intent_router: IntentRouter,
        tool_registry: ToolRegistry,
        model_gateway: ModelGateway,
        prompt_registry: PromptRegistry,
        response_guard: ResponseGuard
    ):
        self.context_builder = context_builder
        self.intent_router = intent_router
        self.tool_registry = tool_registry
        self.model_gateway = model_gateway
        self.prompt_registry = prompt_registry
        self.response_guard = response_guard
    
    async def run(
        self,
        actor: AuthenticatedStudent,
        query: str,
        session: ChatSession
    ) -> AgentResponse:
        """执行 Agent 循环"""
        
        # 1. 创建运行记录
        state = AgentState(
            run_id=generate_id(),
            session_id=str(session.id),
            school_id=actor.school_id,
            student_id=actor.student_id,
            query=query,
            started_at=datetime.utcnow()
        )
        
        # 2. 意图识别
        state.intent = await self.intent_router.route(
            query=query,
            recent_messages=session.recent_messages
        )
        
        # 3. 构建上下文
        state.context = await self.context_builder.build(
            actor=actor,
            query=query,
            session=session,
            selected_exam_id=session.selected_exam_id
        )
        
        state.entitlement = state.context.entitlement_level
        
        # 4. 准备消息
        messages = self._build_messages(state)
        
        # 5. 准备工具列表
        available_tools = self.tool_registry.list_for_entitlement(
            state.entitlement
        )
        
        # 6. 主循环
        while state.tool_round < AgentLimits.MAX_TOOL_ROUNDS:
            # 调用模型
            response = await self.model_gateway.chat(
                model=state.model_id,
                messages=messages,
                tools=available_tools,
                temperature=0.3
            )
            
            # 没有 tool_calls，返回最终答案
            if not response.tool_calls:
                break
            
            # 执行 tools
            tool_results = await self._execute_tools(
                state=state,
                tool_calls=response.tool_calls
            )
            
            # 附加到消息
            messages.append({
                "role": "assistant",
                "content": response.text,
                "tool_calls": response.tool_calls
            })
            
            for result in tool_results:
                messages.append({
                    "role": "tool",
                    "tool_call_id": result.tool_call_id,
                    "content": json.dumps(result.data)
                })
            
            state.tool_round += 1
        
        # 7. Response Guard
        final_answer = await self.response_guard.validate(
            answer=response.text,
            context=state.context,
            entitlement=state.entitlement
        )
        
        # 8. 持久化
        state.finished_at = datetime.utcnow()
        await self._persist_state(state)
        
        return AgentResponse(
            text=final_answer,
            state=state
        )
```

### 6.2 执行 Tools

```python
async def _execute_tools(
    self,
    state: AgentState,
    tool_calls: list[ToolCall]
) -> list[ToolResult]:
    """执行工具调用"""
    
    # 检查数量限制
    if len(tool_calls) > AgentLimits.MAX_TOOLS_PER_ROUND:
        raise AgentLimitExceededError(
            code="TOO_MANY_TOOLS_PER_ROUND",
            message=f"每轮最多{AgentLimits.MAX_TOOLS_PER_ROUND}个工具"
        )
    
    total_calls = len(state.tool_calls) + len(tool_calls)
    if total_calls > AgentLimits.MAX_TOTAL_TOOL_CALLS:
        raise AgentLimitExceededError(
            code="TOO_MANY_TOTAL_TOOLS",
            message=f"总共最多{AgentLimits.MAX_TOTAL_TOOL_CALLS}次工具调用"
        )
    
    # 准备工具上下文
    tool_context = ToolContext(
        request_id=state.run_id,
        agent_run_id=state.run_id,
        user_id=state.student_id,  # 简化，实际可能不同
        school_id=state.school_id,
        student_id=state.student_id,
        entitlement_level=state.entitlement
    )
    
    # 并行执行
    results = []
    for tool_call in tool_calls:
        tool = self.tool_registry.get(tool_call.name)
        
        if not tool:
            results.append(ToolResult(
                ok=False,
                error_code="TOOL_NOT_FOUND",
                data={}
            ))
            continue
        
        try:
            result = await tool.execute(
                tool_context=tool_context,
                args=tool_call.arguments
            )
            results.append(result)
            
            # 追踪
            state.tool_calls.append(ToolCallTrace(
                tool_name=tool_call.name,
                input_args=tool_call.arguments,
                output_summary=result.data,
                status="success" if result.ok else "error",
                latency_ms=0,  # 实际应测量
                error_code=result.error_code,
                executed_at=datetime.utcnow()
            ))
            
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            results.append(ToolResult(
                ok=False,
                error_code="TOOL_EXECUTION_ERROR",
                data={"error": str(e)}
            ))
    
    return results
```

---

## 7. System Prompt 构建

```python
def _build_messages(self, state: AgentState) -> list[dict]:
    """构建消息列表"""
    
    # 获取 System Prompt
    system_prompt = self.prompt_registry.get(
        name="student_qa_system",
        version="v1"
    )
    
    # 注入上下文
    context_str = self._format_context(state.context)
    
    messages = [
        {
            "role": "system",
            "content": system_prompt.render(
                identity=state.context.identity,
                entitlement=state.entitlement,
                context=context_str
            )
        }
    ]
    
    # 附加历史消息（最近N轮）
    for msg in state.context.recent_messages[-8:]:
        messages.append({
            "role": msg.role,
            "content": msg.content
        })
    
    # 当前问题
    messages.append({
        "role": "user",
        "content": state.query
    })
    
    return messages
```

---

## 8. 状态持久化

```python
async def _persist_state(self, state: AgentState):
    """持久化状态"""
    
    # 保存 agent_runs
    await self.db.execute(
        insert(AgentRun).values(
            id=state.run_id,
            session_id=state.session_id,
            school_id=state.school_id,
            student_id=state.student_id,
            query=state.query,
            intent=state.intent.type,
            entitlement_level=state.entitlement,
            status="success",
            model_profile_id=state.model_id,
            prompt_version=state.prompt_version,
            tool_call_count=len(state.tool_calls),
            latency_ms=int((state.finished_at - state.started_at).total_seconds() * 1000),
            created_at=state.started_at,
            finished_at=state.finished_at
        )
    )
    
    # 保存 tool_call_logs
    for trace in state.tool_calls:
        await self.db.execute(
            insert(ToolCallLog).values(
                agent_run_id=state.run_id,
                tool_name=trace.tool_name,
                input_json=trace.input_args,
                output_summary_json=trace.output_summary,
                status=trace.status,
                latency_ms=trace.latency_ms,
                error_code=trace.error_code,
                created_at=trace.executed_at
            )
        )
```

---

## 9. 错误处理

### 9.1 超时处理

```python
async def run_with_timeout(self, *args, **kwargs) -> AgentResponse:
    """带超时的运行"""
    try:
        return await asyncio.wait_for(
            self.run(*args, **kwargs),
            timeout=AgentLimits.MAX_TURN_TIME_SECONDS
        )
    except asyncio.TimeoutError:
        raise AgentTimeoutError(
            message=f"对话处理超过{AgentLimits.MAX_TURN_TIME_SECONDS}秒"
        )
```

### 9.2 Tool 失败降级

```python
# Tool 执行失败不应让整个对话失败
try:
    result = await tool.execute(...)
except Exception as e:
    logger.warning(f"Tool {tool.name} failed: {e}")
    result = ToolResult(
        ok=False,
        error_code="TOOL_ERROR",
        data={"message": "工具执行失败，已跳过"}
    )
```

---

## 10. 与复杂框架对比

### 10.1 为什么不用 LangGraph

❌ **LangGraph 的问题**：
- 过度抽象，学习曲线陡峭
- 状态管理复杂
- 调试困难
- 一期不需要复杂状态图

✅ **轻量 Loop 的优势**：
- 代码清晰，易于理解
- 状态明确，易于调试
- 测试简单
- 符合一期需求

### 10.2 后续何时考虑框架

只有当出现以下需求：
- 复杂的多分支决策
- 需要回溯的状态机
- 多Agent协作编排

目前一期完全不需要。

---

## 11. 测试要点

### 11.1 单轮对话测试

```python
async def test_simple_query():
    loop = AgentLoop(...)
    
    response = await loop.run(
        actor=test_student,
        query="我这次考得怎样？",
        session=test_session
    )
    
    assert response.state.tool_round == 1
    assert response.state.tool_calls[0].tool_name == "get_exam_summary"
    assert "总分" in response.text
```

### 11.2 Tool 限制测试

```python
async def test_tool_limit():
    # 模拟模型尝试调用过多工具
    with pytest.raises(AgentLimitExceededError):
        await loop.run(...)
```

### 11.3 权限测试

```python
async def test_diagnosis_blocked_for_basic():
    response = await loop.run(
        actor=basic_student,
        query="我为什么数学考差？",
        session=session
    )
    
    # 不应调用 get_diagnosis
    tool_names = [t.tool_name for t in response.state.tool_calls]
    assert "get_diagnosis" not in tool_names
```

---

## 12. 关键要点

1. **轻量级实现，不依赖复杂框架**
2. **硬限制防止无限循环**
3. **Tool 执行失败不影响整体**
4. **状态明确可追踪**
5. **Intent Router 先规则后模型**
6. **所有 Tool 调用都记录 Trace**
