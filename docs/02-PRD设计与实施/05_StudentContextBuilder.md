# PRD-05: Student Context Builder 设计

---
Status: draft
Type: DESIGN-REFERENCE
Owner: Agent 平台
Last verified: 2026-09-11
Evidence: 设计参考；当前实现接口可能变化，以 V2 Agent 契约测试为准。
Supersedes: 旧版 Context Builder 示例
---

> 本文保留上下文构建思路，示例代码不代表已接入当前主链路。

## 1. 概述

这是系统核心组件。参考 OpenTutor `services/agent/context_builder.py` 的职责分离思想，但一期实现更轻。

### 1.1 核心职责

- 根据学生身份加载上下文
- 根据问题意图按需加载数据
- 控制 Context 大小和预算
- 处理加载失败降级

---

## 2. 接口设计

### 2.1 核心接口

```python
class StudentContextBuilder:
    async def build(
        self,
        actor: AuthenticatedStudent,
        query: str,
        session: ChatSession,
        selected_exam_id: UUID | None,
    ) -> StudentContext:
        """
        构建学生上下文
        
        Args:
            actor: 已认证的学生身份
            query: 用户问题
            session: 当前会话
            selected_exam_id: 选中的考试ID（可选）
        
        Returns:
            StudentContext: 结构化上下文
        """
        pass
```

---

## 3. StudentContext 数据结构

### 3.1 核心结构

```python
class StudentContext(BaseModel):
    # 身份信息
    identity: StudentIdentity
    
    # 意图分析
    intent: QueryIntent
    
    # 权益等级
    entitlement_level: Literal["BASIC", "DIAGNOSIS"]
    
    # 考试相关
    current_exam: ExamFact | None = None
    exam_summary: ExamSummary | None = None
    
    # 成绩数据
    subject_scores: list[SubjectScoreFact] = []
    rank_change: RankChangeFact | None = None
    score_trend: list[ScoreTrendPoint] = []
    question_losses: list[QuestionLossFact] = []
    
    # 诊断数据（DIAGNOSIS权益）
    diagnosis: DiagnosisContext | None = None
    
    # 会话历史
    recent_messages: list[Message] = []
    
    # 证据链
    evidence: list[EvidenceRef] = []
```

### 3.2 子结构定义

```python
class StudentIdentity(BaseModel):
    student_id: UUID
    student_name: str
    school_id: UUID
    grade: str | None
    class_name: str | None

class QueryIntent(BaseModel):
    type: Literal[
        "EXAM_SUMMARY",
        "SUBJECT_SCORE",
        "RANK_CHANGE",
        "SCORE_TREND",
        "QUESTION_LOSS",
        "DIAGNOSIS",
        "GENERAL_STUDENT_DATA",
        "OUT_OF_SCOPE"
    ]
    subject: str | None = None
    exam_hint: str | None = None
    needs_diagnosis: bool = False
    confidence: float = 0.0

class ExamFact(BaseModel):
    exam_id: UUID
    exam_name: str
    exam_type: str
    exam_date: date
    grade: str | None

class ExamSummary(BaseModel):
    total_score: Decimal
    full_score: Decimal
    class_rank: int | None
    grade_rank: int | None
    class_student_count: int | None
    grade_student_count: int | None

class SubjectScoreFact(BaseModel):
    subject: str
    score: Decimal
    full_score: Decimal
    class_rank: int | None
    grade_rank: int | None
    class_avg: Decimal | None
    grade_avg: Decimal | None

class RankChangeFact(BaseModel):
    current_rank: int
    previous_rank: int
    rank_delta: int  # 正数表示上升
    current_score: Decimal
    previous_score: Decimal
    score_delta: Decimal
    subject: str | None

class ScoreTrendPoint(BaseModel):
    exam_id: UUID
    exam_name: str
    exam_date: date
    score: Decimal
    rank: int | None

class QuestionLossFact(BaseModel):
    question_no: str
    score: Decimal
    full_score: Decimal
    lost_score: Decimal
    knowledge_point: str | None

class DiagnosisContext(BaseModel):
    report_id: UUID
    exam_id: UUID
    subject: str | None
    weaknesses: list[str] = []
    strengths: list[str] = []
    loss_reasons: list[str] = []
    suggestions: list[str] = []
    evidence: list[str] = []
```

---

## 4. 不要一开始加载所有东西

### 4.1 ContextPlan - 按需加载计划

```python
class ContextPlan(BaseModel):
    need_latest_exam: bool = False
    need_subject_scores: bool = False
    need_rank: bool = False
    need_history: bool = False
    need_question_losses: bool = False
    need_diagnosis: bool = False
    max_history_count: int = 5
```

### 4.2 根据意图生成计划

```python
def plan_context_loading(self, intent: QueryIntent) -> ContextPlan:
    """根据意图决定加载什么"""
    
    if intent.type == "EXAM_SUMMARY":
        return ContextPlan(
            need_latest_exam=True,
            need_subject_scores=True,
            need_rank=True
        )
    
    elif intent.type == "SCORE_TREND":
        return ContextPlan(
            need_history=True,
            max_history_count=10,
            need_rank=True
        )
    
    elif intent.type == "RANK_CHANGE":
        return ContextPlan(
            need_latest_exam=True,
            need_history=True,
            need_rank=True,
            max_history_count=2  # 只需最近两次
        )
    
    elif intent.type == "QUESTION_LOSS":
        return ContextPlan(
            need_latest_exam=True,
            need_question_losses=True
        )
    
    elif intent.type == "DIAGNOSIS":
        return ContextPlan(
            need_latest_exam=True,
            need_diagnosis=True
        )
    
    else:
        # 默认最小加载
        return ContextPlan(
            need_latest_exam=True
        )
```

---

## 5. 构建流程

### 5.1 完整流程

```python
class StudentContextBuilder:
    def __init__(
        self,
        student_repo: StudentRepository,
        exam_repo: ExamRepository,
        score_repo: ScoreRepository,
        diagnosis_repo: DiagnosisRepository,
        entitlement_service: EntitlementService,
        intent_router: IntentRouter
    ):
        self.student_repo = student_repo
        self.exam_repo = exam_repo
        self.score_repo = score_repo
        self.diagnosis_repo = diagnosis_repo
        self.entitlement_service = entitlement_service
        self.intent_router = intent_router
    
    async def build(
        self,
        actor: AuthenticatedStudent,
        query: str,
        session: ChatSession,
        selected_exam_id: UUID | None
    ) -> StudentContext:
        
        # 1. 加载学生身份
        identity = await self._load_identity(actor)
        
        # 2. 检查权益等级
        entitlement_level = await self._check_entitlement(actor.student_id)
        
        # 3. 意图识别
        intent = await self.intent_router.route(query, session.recent_messages)
        
        # 4. 生成加载计划
        plan = self.plan_context_loading(intent)
        
        # 5. 并行加载数据
        context_data = await self._load_data_parallel(
            student_id=actor.student_id,
            plan=plan,
            selected_exam_id=selected_exam_id,
            entitlement_level=entitlement_level
        )
        
        # 6. 组装上下文
        return StudentContext(
            identity=identity,
            intent=intent,
            entitlement_level=entitlement_level,
            **context_data
        )
    
    async def _load_data_parallel(
        self,
        student_id: UUID,
        plan: ContextPlan,
        selected_exam_id: UUID | None,
        entitlement_level: str
    ) -> dict:
        """并行加载数据"""
        
        tasks = []
        
        if plan.need_latest_exam:
            tasks.append(("current_exam", self._load_current_exam(student_id, selected_exam_id)))
        
        if plan.need_subject_scores:
            tasks.append(("subject_scores", self._load_subject_scores(student_id, selected_exam_id)))
        
        if plan.need_rank:
            tasks.append(("rank_change", self._load_rank_change(student_id, selected_exam_id)))
        
        if plan.need_history:
            tasks.append(("score_trend", self._load_score_trend(student_id, plan.max_history_count)))
        
        if plan.need_question_losses:
            tasks.append(("question_losses", self._load_question_losses(student_id, selected_exam_id)))
        
        if plan.need_diagnosis and entitlement_level == "DIAGNOSIS":
            tasks.append(("diagnosis", self._load_diagnosis(student_id, selected_exam_id)))
        
        # 并行执行
        results = await asyncio.gather(
            *[task for _, task in tasks],
            return_exceptions=True
        )
        
        # 组装结果（失败则为None，实现降级）
        data = {}
        for i, (key, _) in enumerate(tasks):
            if isinstance(results[i], Exception):
                logger.warning(f"Failed to load {key}: {results[i]}")
                data[key] = None
            else:
                data[key] = results[i]
        
        return data
```

---

## 6. 数据加载示例

### 6.1 加载最近考试

```python
async def _load_current_exam(
    self,
    student_id: UUID,
    selected_exam_id: UUID | None
) -> ExamFact | None:
    
    if selected_exam_id:
        exam = await self.exam_repo.get_by_id(selected_exam_id)
    else:
        # 获取最近一次有成绩的考试
        exam = await self.exam_repo.get_latest_for_student(student_id)
    
    if not exam:
        return None
    
    return ExamFact(
        exam_id=exam.id,
        exam_name=exam.name,
        exam_type=exam.exam_type,
        exam_date=exam.start_date,
        grade=exam.grade
    )
```

### 6.2 加载成绩总结

```python
async def _load_exam_summary(
    self,
    student_id: UUID,
    exam_id: UUID
) -> ExamSummary | None:
    
    score = await self.score_repo.get_student_exam_score(
        student_id=student_id,
        exam_id=exam_id
    )
    
    if not score:
        return None
    
    return ExamSummary(
        total_score=score.total_score,
        full_score=score.full_score or Decimal("150"),
        class_rank=score.class_rank,
        grade_rank=score.grade_rank,
        class_student_count=score.class_student_count,
        grade_student_count=score.grade_student_count
    )
```

### 6.3 加载排名变化

```python
async def _load_rank_change(
    self,
    student_id: UUID,
    current_exam_id: UUID | None
) -> RankChangeFact | None:
    
    # 获取最近两次考试
    recent = await self.score_repo.get_recent_exams(
        student_id=student_id,
        limit=2
    )
    
    if len(recent) < 2:
        return None
    
    current, previous = recent[0], recent[1]
    
    return RankChangeFact(
        current_rank=current.grade_rank,
        previous_rank=previous.grade_rank,
        rank_delta=previous.grade_rank - current.grade_rank,  # 正数=上升
        current_score=current.total_score,
        previous_score=previous.total_score,
        score_delta=current.total_score - previous.total_score
    )
```

---

## 7. Context 预算控制

### 7.1 Token 预算

```python
class ContextBudget:
    IDENTITY: int = 100           # 身份信息
    INTENT: int = 50              # 意图
    EXAM_SUMMARY: int = 200       # 考试总结
    SUBJECT_SCORE: int = 150      # 单科成绩
    RANK: int = 100               # 排名
    QUESTION_PER_ITEM: int = 80   # 每道题
    HISTORY_PER_EXAM: int = 120   # 每次历史考试
    DIAGNOSIS: int = 500          # 诊断报告
    MESSAGE_PER_TURN: int = 200   # 每轮对话
    
    MAX_TOTAL: int = 4000         # 总预算
```

### 7.2 超预算处理

```python
def trim_context(self, context: StudentContext, max_tokens: int) -> StudentContext:
    """
    Context 太大时裁剪
    
    优先级：
    1. Identity + Intent（必需）
    2. Current Exam（必需）
    3. 核心数据（根据 intent）
    4. 历史数据（可裁剪）
    5. 对话历史（可裁剪）
    """
    
    estimated = self.estimate_tokens(context)
    
    if estimated <= max_tokens:
        return context
    
    # 裁剪历史
    if context.score_trend and len(context.score_trend) > 5:
        context.score_trend = context.score_trend[:5]
    
    # 裁剪对话
    if context.recent_messages and len(context.recent_messages) > 6:
        context.recent_messages = context.recent_messages[-6:]
    
    # 裁剪小题
    if context.question_losses and len(context.question_losses) > 10:
        context.question_losses = context.question_losses[:10]
    
    return context
```

---

## 8. 失败降级

### 8.1 降级策略

```python
async def _load_with_fallback(
    self,
    primary_fn: Callable,
    fallback_fn: Callable | None = None,
    error_default: Any = None
) -> Any:
    """
    带降级的加载
    """
    try:
        return await primary_fn()
    except Exception as e:
        logger.warning(f"Primary load failed: {e}")
        
        if fallback_fn:
            try:
                return await fallback_fn()
            except Exception as e2:
                logger.error(f"Fallback also failed: {e2}")
        
        return error_default
```

### 8.2 部分失败容忍

> Context 获取失败时可降级，不一定让整轮对话失败。

示例：
- 诊断报告加载失败 → 降级为 BASIC 模式
- 历史趋势加载失败 → 只返回当前考试数据
- 排名数据缺失 → 只返回分数

---

## 9. 与 OpenTutor 对比

### 9.1 OpenTutor 的 Context

```text
Preference + Memory + RAG + TeachingState + Assignment
```

### 9.2 我们的简化版（一期）

```text
Identity + Exam + Score + Rank + QuestionLoss + DiagnosisEntitlement
```

### 9.3 借鉴的设计

✅ **借鉴**：
- Context 不在 API Router 内拼
- 不同类型 Context 可以并行加载
- 不同类型 Context 有独立 budget
- Context 太大时会 trim
- Context 是 AgentState 的一部分
- Context 获取失败时可降级

❌ **一期不做**：
- 长期 Memory
- RAG 知识库
- TeachingState
- Planner

---

## 10. 测试要点

### 10.1 单元测试

```python
async def test_context_builder_basic():
    builder = StudentContextBuilder(...)
    
    context = await builder.build(
        actor=test_student,
        query="我这次考得怎样？",
        session=test_session,
        selected_exam_id=None
    )
    
    assert context.identity.student_id == test_student.id
    assert context.intent.type == "EXAM_SUMMARY"
    assert context.current_exam is not None
    assert context.exam_summary is not None
```

### 10.2 权益测试

```python
async def test_diagnosis_only_for_entitled():
    # BASIC 学生
    context_basic = await builder.build(
        actor=basic_student,
        query="我为什么数学考差？",
        session=session,
        selected_exam_id=exam_id
    )
    
    assert context_basic.diagnosis is None
    
    # DIAGNOSIS 学生
    context_diag = await builder.build(
        actor=diagnosis_student,
        query="我为什么数学考差？",
        session=session,
        selected_exam_id=exam_id
    )
    
    assert context_diag.diagnosis is not None
```

---

## 11. 关键要点

1. **按需加载，不要一次性加载所有数据**
2. **并行加载多个独立数据源**
3. **失败降级，部分数据缺失不影响整体**
4. **Context 预算控制，避免超token**
5. **权益检查在加载时就执行**
6. **Evidence 链随 Context 一起返回**
