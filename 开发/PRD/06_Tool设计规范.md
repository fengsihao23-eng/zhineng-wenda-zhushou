# PRD-06: Tool 设计规范

---
Status: active
Owner: Agent 平台
Last verified: 2026-09-11
Evidence: V2 Tool 契约；实现须通过 Tool schema、权限和跨学校隔离测试。
Supersedes: 旧版六工具设计
---

> 第一阶段正式 Tool 以市级 V2 实施计划为准：只读成绩问答五个 Tool。任何“已实现”标记都必须由测试证据支持。

## 1. Tool 总览

一期 Tool 数量要少，只提供核心只读 Tool。

### 1.1 一期 Tool 列表

| Tool 名称 | 用途 | 权益要求 |
|---|---|---|
| get_exam_summary | 获取考试总结（总分、排名） | BASIC |
| get_subject_scores | 获取科目成绩 | BASIC |
| get_rank_change | 获取排名变化 | BASIC |
| get_score_trend | 获取成绩趋势 | BASIC |
| get_question_losses | 获取小题丢分情况 | BASIC |
| get_diagnosis | 获取诊断报告（后置版本） | 不属于 V1 试点 |

---

## 2. Tool 统一协议

### 2.1 ToolContext - 执行上下文

```python
class ToolContext(BaseModel):
    """
    Tool 执行上下文
    从认证信息注入，模型无法控制
    """
    request_id: str
    agent_run_id: str
    user_id: UUID
    school_id: UUID          # 👈 从 JWT 注入
    student_id: UUID         # 👈 从 JWT 注入
    entitlement_level: str   # 'BASIC' or 'DIAGNOSIS'
```

### 2.2 ToolResult - 统一返回

```python
class ToolResult(BaseModel):
    """Tool 执行结果"""
    ok: bool
    data: dict
    evidence: list[EvidenceRef] = []
    error_code: str | None = None
    error_message: str | None = None
```

### 2.3 EvidenceRef - 证据链

```python
class EvidenceRef(BaseModel):
    """数据来源证据"""
    type: str                    # 'student_exam_score', 'diagnosis_report'
    resource_id: str             # 资源ID
    label: str                   # 用户可读标签
    as_of: datetime | None       # 数据时间戳
```

---

## 3. Tool 基类

### 3.1 BaseTool

```python
from abc import ABC, abstractmethod

class BaseTool(ABC):
    """Tool 基类"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Tool 名称"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Tool 描述（给模型看）"""
        pass
    
    @property
    @abstractmethod
    def input_schema(self) -> dict:
        """输入参数 JSON Schema"""
        pass
    
    @property
    def required_entitlement(self) -> str | None:
        """所需权益等级"""
        return None
    
    @property
    def read_only(self) -> bool:
        """是否只读"""
        return True
    
    @property
    def timeout(self) -> int:
        """超时时间（秒）"""
        return 10
    
    @abstractmethod
    async def execute(
        self,
        tool_context: ToolContext,
        args: dict
    ) -> ToolResult:
        """执行 Tool"""
        pass
    
    def validate_entitlement(self, tool_context: ToolContext):
        """验证权益"""
        if self.required_entitlement:
            if tool_context.entitlement_level != self.required_entitlement:
                raise EntitlementRequiredError(
                    product_code=self.required_entitlement
                )
```

---

## 4. Tool 详细设计

### 4.1 get_exam_summary

**用途**：
- 这次考得怎样
- 总分多少
- 排名多少

**定义**：
```python
class GetExamSummaryTool(BaseTool):
    name = "get_exam_summary"
    
    description = """
    获取学生某次考试的总体情况，包括总分和排名。
    如果不指定 exam_id，返回最近一次考试。
    """
    
    input_schema = {
        "type": "object",
        "properties": {
            "exam_id": {
                "type": "string",
                "description": "考试ID，可选，不提供则返回最近一次"
            }
        }
    }
    
    async def execute(
        self,
        tool_context: ToolContext,
        args: dict
    ) -> ToolResult:
        exam_id = args.get("exam_id")
        
        if exam_id:
            exam = await self.exam_repo.get_by_id(UUID(exam_id))
        else:
            exam = await self.exam_repo.get_latest_for_student(
                tool_context.student_id
            )
        
        if not exam:
            return ToolResult(
                ok=False,
                error_code="EXAM_NOT_FOUND",
                data={}
            )
        
        score = await self.score_repo.get_student_exam_score(
            student_id=tool_context.student_id,
            exam_id=exam.id
        )
        
        if not score:
            return ToolResult(
                ok=False,
                error_code="SCORE_NOT_FOUND",
                data={}
            )
        
        return ToolResult(
            ok=True,
            data={
                "exam_name": exam.name,
                "exam_date": exam.start_date.isoformat(),
                "total_score": float(score.total_score),
                "full_score": float(score.full_score or 150),
                "class_rank": score.class_rank,
                "grade_rank": score.grade_rank,
                "class_student_count": score.class_student_count,
                "grade_student_count": score.grade_student_count
            },
            evidence=[
                EvidenceRef(
                    type="student_exam_score",
                    resource_id=str(score.id),
                    label=exam.name,
                    as_of=score.updated_at
                )
            ]
        )
```

---

### 4.2 get_subject_scores

**用途**：
- 各科成绩
- 数学多少
- 哪科最高

**定义**：
```python
class GetSubjectScoresTool(BaseTool):
    name = "get_subject_scores"
    
    description = """
    获取学生某次考试的各科成绩。
    可以指定科目，也可以返回所有科目。
    """
    
    input_schema = {
        "type": "object",
        "properties": {
            "exam_id": {
                "type": "string",
                "description": "考试ID，可选"
            },
            "subject": {
                "type": "string",
                "description": "科目名称，可选，如'数学'、'语文'"
            }
        }
    }
    
    async def execute(
        self,
        tool_context: ToolContext,
        args: dict
    ) -> ToolResult:
        exam_id = args.get("exam_id")
        subject_filter = args.get("subject")
        
        # 确定考试
        if exam_id:
            exam = await self.exam_repo.get_by_id(UUID(exam_id))
        else:
            exam = await self.exam_repo.get_latest_for_student(
                tool_context.student_id
            )
        
        if not exam:
            return ToolResult(ok=False, error_code="EXAM_NOT_FOUND", data={})
        
        # 获取科目成绩
        scores = await self.score_repo.get_subject_scores(
            student_id=tool_context.student_id,
            exam_id=exam.id,
            subject=subject_filter
        )
        
        return ToolResult(
            ok=True,
            data={
                "exam_name": exam.name,
                "subjects": [
                    {
                        "subject": s.subject_name,
                        "score": float(s.score),
                        "full_score": float(s.full_score),
                        "class_rank": s.class_rank,
                        "grade_rank": s.grade_rank,
                        "class_avg": float(s.class_avg) if s.class_avg else None,
                        "grade_avg": float(s.grade_avg) if s.grade_avg else None
                    }
                    for s in scores
                ]
            },
            evidence=[
                EvidenceRef(
                    type="student_subject_score",
                    resource_id=str(s.id),
                    label=f"{exam.name}-{s.subject_name}",
                    as_of=s.updated_at
                )
                for s in scores
            ]
        )
```

---

### 4.3 get_rank_change

**用途**：
- 比上次进步了吗
- 排名上升了多少

**定义**：
```python
class GetRankChangeTool(BaseTool):
    name = "get_rank_change"
    
    description = """
    比较两次考试的排名和分数变化。
    如果不指定考试，自动比较最近两次。
    """
    
    input_schema = {
        "type": "object",
        "properties": {
            "subject": {
                "type": "string",
                "description": "科目名称，可选"
            },
            "current_exam_id": {
                "type": "string",
                "description": "当前考试ID，可选"
            },
            "previous_exam_id": {
                "type": "string",
                "description": "对比考试ID，可选"
            }
        }
    }
    
    async def execute(
        self,
        tool_context: ToolContext,
        args: dict
    ) -> ToolResult:
        subject = args.get("subject")
        
        # 获取最近两次考试
        recent = await self.score_repo.get_recent_scores(
            student_id=tool_context.student_id,
            subject=subject,
            limit=2
        )
        
        if len(recent) < 2:
            return ToolResult(
                ok=False,
                error_code="INSUFFICIENT_DATA",
                data={"message": "至少需要两次考试数据"}
            )
        
        current, previous = recent[0], recent[1]
        
        return ToolResult(
            ok=True,
            data={
                "current": {
                    "exam_name": current.exam_name,
                    "score": float(current.score),
                    "rank": current.rank
                },
                "previous": {
                    "exam_name": previous.exam_name,
                    "score": float(previous.score),
                    "rank": previous.rank
                },
                "score_delta": float(current.score - previous.score),
                "rank_delta": previous.rank - current.rank,  # 正数=上升
                "subject": subject
            },
            evidence=[
                EvidenceRef(
                    type="score_comparison",
                    resource_id=f"{current.id}-{previous.id}",
                    label=f"{current.exam_name} vs {previous.exam_name}",
                    as_of=current.updated_at
                )
            ]
        )
```

---

### 4.4 get_score_trend

**用途**：
- 历史成绩趋势
- 最近几次考试变化

**定义**：
```python
class GetScoreTrendTool(BaseTool):
    name = "get_score_trend"
    
    description = """
    获取学生最近几次考试的成绩趋势。
    """
    
    input_schema = {
        "type": "object",
        "properties": {
            "subject": {
                "type": "string",
                "description": "科目名称，可选"
            },
            "limit": {
                "type": "integer",
                "description": "返回考试数量，默认5次，最多10次",
                "minimum": 1,
                "maximum": 10
            }
        }
    }
    
    async def execute(
        self,
        tool_context: ToolContext,
        args: dict
    ) -> ToolResult:
        subject = args.get("subject")
        limit = min(args.get("limit", 5), 10)  # 👈 硬限制
        
        trend = await self.score_repo.get_score_trend(
            student_id=tool_context.student_id,
            subject=subject,
            limit=limit
        )
        
        return ToolResult(
            ok=True,
            data={
                "subject": subject,
                "exams": [
                    {
                        "exam_name": t.exam_name,
                        "exam_date": t.exam_date.isoformat(),
                        "score": float(t.score),
                        "rank": t.rank
                    }
                    for t in trend
                ]
            },
            evidence=[
                EvidenceRef(
                    type="score_trend",
                    resource_id=str(tool_context.student_id),
                    label=f"最近{len(trend)}次考试",
                    as_of=datetime.utcnow()
                )
            ]
        )
```

---

### 4.5 get_question_losses

**用途**：
- 哪几题丢分多
- 小题失分情况

**定义**：
```python
class GetQuestionLossesTool(BaseTool):
    name = "get_question_losses"
    
    description = """
    获取学生某次考试的小题丢分情况。
    按丢分从多到少排序。
    """
    
    input_schema = {
        "type": "object",
        "properties": {
            "exam_id": {
                "type": "string",
                "description": "考试ID，可选"
            },
            "subject": {
                "type": "string",
                "description": "科目名称，可选"
            },
            "top_n": {
                "type": "integer",
                "description": "返回前N题，默认10",
                "minimum": 1,
                "maximum": 20
            }
        }
    }
    
    async def execute(
        self,
        tool_context: ToolContext,
        args: dict
    ) -> ToolResult:
        exam_id = args.get("exam_id")
        subject = args.get("subject")
        top_n = min(args.get("top_n", 10), 20)
        
        # 确定考试
        if exam_id:
            exam = await self.exam_repo.get_by_id(UUID(exam_id))
        else:
            exam = await self.exam_repo.get_latest_for_student(
                tool_context.student_id
            )
        
        if not exam:
            return ToolResult(ok=False, error_code="EXAM_NOT_FOUND", data={})
        
        # 获取小题丢分（按丢分排序）
        questions = await self.score_repo.get_question_losses(
            student_id=tool_context.student_id,
            exam_id=exam.id,
            subject=subject,
            order_by="lost_score DESC",
            limit=top_n
        )
        
        return ToolResult(
            ok=True,
            data={
                "exam_name": exam.name,
                "subject": subject,
                "questions": [
                    {
                        "question_no": q.question_no,
                        "score": float(q.score),
                        "full_score": float(q.full_score),
                        "lost_score": float(q.lost_score),
                        "knowledge_point": q.knowledge_point_name
                    }
                    for q in questions
                ]
            },
            evidence=[
                EvidenceRef(
                    type="question_score",
                    resource_id=str(q.id),
                    label=f"第{q.question_no}题",
                    as_of=q.updated_at
                )
                for q in questions
            ]
        )
```

**重要**：
> BASIC 模型只能说："第 17 题丢了 3 分。"
> 
> 不能直接说："说明你函数概念不扎实。"
> 
> 除非正式业务数据已经绑定知识点且产品允许展示"事实型知识点关联"。

---

### 4.6 get_diagnosis

**用途**：诊断报告（DIAGNOSIS 专用）

**定义**：
```python
class GetDiagnosisTool(BaseTool):
    name = "get_diagnosis"
    
    description = """
    获取学生的学情诊断报告。
    需要DIAGNOSIS权益。
    """
    
    required_entitlement = "DIAGNOSIS"
    
    input_schema = {
        "type": "object",
        "properties": {
            "exam_id": {
                "type": "string",
                "description": "考试ID，可选"
            },
            "subject": {
                "type": "string",
                "description": "科目名称，可选"
            },
            "section": {
                "type": "string",
                "enum": ["weakness", "strength", "reason", "suggestion", "evidence", "all"],
                "description": "报告部分，默认all"
            }
        }
    }
    
    async def execute(
        self,
        tool_context: ToolContext,
        args: dict
    ) -> ToolResult:
        # 1. 验证权益
        self.validate_entitlement(tool_context)
        
        exam_id = args.get("exam_id")
        subject = args.get("subject")
        section = args.get("section", "all")
        
        # 2. 确定考试
        if exam_id:
            exam = await self.exam_repo.get_by_id(UUID(exam_id))
        else:
            exam = await self.exam_repo.get_latest_for_student(
                tool_context.student_id
            )
        
        if not exam:
            return ToolResult(ok=False, error_code="EXAM_NOT_FOUND", data={})
        
        # 3. 验证报告权益
        entitlement = await self.entitlement_service.check(
            student_id=tool_context.student_id,
            product_code="DIAGNOSIS_REPORT",
            resource_id=exam.id
        )
        
        if not entitlement.is_active:
            return ToolResult(
                ok=False,
                error_code="ENTITLEMENT_REQUIRED",
                data={"message": "此考试的诊断报告需要购买"}
            )
        
        # 4. 获取报告
        report = await self.diagnosis_repo.get_report(
            student_id=tool_context.student_id,
            exam_id=exam.id,
            subject=subject
        )
        
        if not report:
            return ToolResult(
                ok=False,
                error_code="REPORT_NOT_FOUND",
                data={}
            )
        
        # 5. 提取指定部分
        diagnosis_data = report.structured_json
        
        if section != "all":
            diagnosis_data = self._extract_section(diagnosis_data, section, subject)
        
        # 6. 审计日志
        await self.audit_log.record(
            action="READ_DIAGNOSIS",
            student_id=tool_context.student_id,
            resource_id=report.id,
            allowed=True
        )
        
        return ToolResult(
            ok=True,
            data=diagnosis_data,
            evidence=[
                EvidenceRef(
                    type="diagnosis_report",
                    resource_id=str(report.id),
                    label=f"{exam.name}诊断报告",
                    as_of=report.generated_at
                )
            ]
        )
```

---

## 5. Tool Registry

### 5.1 注册机制

```python
class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
    
    def register(self, tool: BaseTool):
        """注册 Tool"""
        self._tools[tool.name] = tool
    
    def get(self, name: str) -> BaseTool | None:
        """获取 Tool"""
        return self._tools.get(name)
    
    def list_for_entitlement(self, entitlement_level: str) -> list[dict]:
        """
        列出可用 Tool（给模型看的 Schema）
        """
        available = []
        
        for tool in self._tools.values():
            if tool.required_entitlement:
                if tool.required_entitlement != entitlement_level:
                    continue
            
            available.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema
                }
            })
        
        return available
```

### 5.2 初始化

```python
def init_tool_registry(
    exam_repo: ExamRepository,
    score_repo: ScoreRepository,
    diagnosis_repo: DiagnosisRepository,
    entitlement_service: EntitlementService,
    audit_log: AuditLogService
) -> ToolRegistry:
    
    registry = ToolRegistry()
    
    # 注册 BASIC Tools
    registry.register(GetExamSummaryTool(exam_repo, score_repo))
    registry.register(GetSubjectScoresTool(exam_repo, score_repo))
    registry.register(GetRankChangeTool(score_repo))
    registry.register(GetScoreTrendTool(score_repo))
    registry.register(GetQuestionLossesTool(exam_repo, score_repo))
    
    # 注册 DIAGNOSIS Tools
    registry.register(GetDiagnosisTool(
        exam_repo,
        diagnosis_repo,
        entitlement_service,
        audit_log
    ))
    
    return registry
```

---

## 6. 限制与约束

### 6.1 硬限制

```python
MAX_TOOL_ROUNDS = 2                # 最多2轮Tool调用
MAX_TOOLS_PER_ROUND = 3            # 每轮最多3个Tool
MAX_TOTAL_TOOL_CALLS = 5           # 总共最多5次
```

### 6.2 一期全部只读

```python
# 所有 Tool
read_only = True
```

学生 Agent 不应拥有：
- ❌ 更新成绩 Tool
- ❌ 删除数据 Tool
- ❌ 修改诊断报告 Tool
- ❌ 任意 SQL Tool
- ❌ 任意 HTTP Tool
- ❌ Shell Tool
- ❌ 文件系统写入 Tool

---

## 7. 关键要点

1. **Tool 参数不暴露 student_id / school_id，从上下文注入**
2. **权限在 Tool 执行层强制检查**
3. **所有 Tool 返回 Evidence 证据链**
4. **V1 试点只提供 5 个核心只读 Tool**：`get_exam_summary`、`get_subject_scores`、`get_rank_change`、`get_score_trend`、`get_question_losses`
5. **Tool 调用次数有硬限制**
6. **DIAGNOSIS Tool 需要额外权益验证**
