# PRD-10: Response Guard 设计

---
Status: draft
Type: DESIGN-REFERENCE
Owner: 安全与 AI 平台
Last verified: 2026-09-11
Evidence: 设计参考；数字溯源、权限边界和注入防护须以测试报告为准。
Supersedes: 旧版 Response Guard 示例
---

> 本文描述 Guard 目标与算法思路，不代表当前回答链路已经接入 Guard。

## 1. 概述

Response Guard 是模型生成答案后的最后一道防线，用于验证答案的合规性和准确性。

### 1.1 为什么需要 Response Guard

**问题**：
- 模型可能生成包含其他学生信息的答案
- BASIC 用户可能得到诊断性结论
- 答案中的数字可能不在 Context 中
- 排名变化方向可能说反

**解决**：
在返回给用户前进行最后检查。

---

## 2. Guard 检查项

### 2.1 数字准确性检查

```python
def check_numbers(answer: str, context: StudentContext) -> list[str]:
    """检查答案中的数字是否来自 Context"""
    issues = []
    
    # 提取答案中的数字
    numbers = extract_numbers(answer)
    
    # 收集 Context 中的所有数字
    context_numbers = extract_context_numbers(context)
    
    for num in numbers:
        if num not in context_numbers:
            issues.append(f"数字{num}不在Context中，可能是模型捏造")
    
    return issues
```

### 2.2 BASIC 权益检查

```python
def check_basic_boundary(answer: str, entitlement: str) -> list[str]:
    """检查 BASIC 用户是否出现诊断性措辞"""
    
    if entitlement != "BASIC":
        return []
    
    issues = []
    
    # 敏感词列表（辅助）
    forbidden_words = [
        "薄弱", "基础不扎实", "理解不够", "能力不足",
        "粗心", "学习习惯", "掌握不牢", "概念模糊"
    ]
    
    for word in forbidden_words:
        if word in answer:
            issues.append(f"BASIC用户不应出现诊断性措辞: '{word}'")
    
    return issues
```

### 2.3 学生隐私检查

```python
def check_privacy(answer: str, identity: StudentIdentity) -> list[str]:
    """检查是否泄漏其他学生信息"""
    issues = []
    
    # 提取答案中的人名
    names = extract_person_names(answer)
    
    for name in names:
        if name != identity.student_name:
            issues.append(f"答案包含其他学生姓名: {name}")
    
    return issues
```

### 2.4 DIAGNOSIS Evidence 检查

```python
def check_diagnosis_evidence(
    answer: str,
    context: StudentContext
) -> list[str]:
    """检查诊断结论是否映射到 evidence"""
    
    if not context.diagnosis:
        return []
    
    issues = []
    
    # 提取答案中的诊断性陈述
    diagnosis_claims = extract_diagnosis_claims(answer)
    
    # 获取报告中的 evidence
    report_evidence = context.diagnosis.evidence
    
    for claim in diagnosis_claims:
        if not has_evidence_support(claim, report_evidence):
            issues.append(f"诊断陈述缺少报告依据: '{claim}'")
    
    return issues
```

---

## 3. ResponseGuard 实现

### 3.1 核心类

```python
class ResponseGuard:
    """响应守卫"""
    
    def __init__(self, config: GuardConfig):
        self.config = config
        self.rules = self._load_rules()
    
    async def validate(
        self,
        answer: str,
        context: StudentContext,
        entitlement: str
    ) -> GuardResult:
        """
        验证答案
        
        Returns:
            GuardResult: 验证结果
        """
        issues = []
        
        # 1. 数字准确性
        issues.extend(self.check_numbers(answer, context))
        
        # 2. 权限边界
        if entitlement == "BASIC":
            issues.extend(self.check_basic_boundary(answer))
        elif entitlement == "DIAGNOSIS":
            issues.extend(self.check_diagnosis_evidence(answer, context))
        
        # 3. 隐私保护
        issues.extend(self.check_privacy(answer, context.identity))
        
        # 4. 逻辑一致性
        issues.extend(self.check_logic_consistency(answer, context))
        
        return GuardResult(
            ok=len(issues) == 0,
            issues=issues,
            action=self._decide_action(issues)
        )
    
    def _decide_action(self, issues: list[str]) -> str:
        """决定处理动作"""
        if not issues:
            return "pass"
        
        # 根据严重程度决定
        high_severity = any(
            "其他学生" in issue or "捏造" in issue
            for issue in issues
        )
        
        if high_severity:
            return "block"  # 阻断
        else:
            return "warn"   # 警告但放行
```

### 3.2 GuardResult

```python
class GuardResult(BaseModel):
    """Guard 验证结果"""
    ok: bool
    issues: list[str] = []
    action: str  # 'pass', 'warn', 'block'
    corrected_answer: str | None = None
```

---

## 4. 使用方式

### 4.1 在 Agent Loop 中使用

```python
class AgentLoop:
    async def run(self, ...):
        # ... 模型生成答案
        
        # Response Guard 验证
        guard_result = await self.response_guard.validate(
            answer=response.text,
            context=state.context,
            entitlement=state.entitlement
        )
        
        if guard_result.action == "block":
            # 阻断，返回安全的通用答案
            logger.error(f"Response blocked: {guard_result.issues}")
            final_answer = "抱歉，我无法回答这个问题。请联系老师获取帮助。"
        
        elif guard_result.action == "warn":
            # 警告但放行，记录日志
            logger.warning(f"Response warning: {guard_result.issues}")
            final_answer = response.text
        
        else:
            # 通过
            final_answer = response.text
        
        # 记录 Guard 结果
        await self._log_guard_result(state.run_id, guard_result)
        
        return final_answer
```

---

## 5. Evidence / Provenance

### 5.1 Evidence 数据结构

```python
class EvidenceRef(BaseModel):
    """数据来源证据"""
    type: str                    # 'student_exam_score', 'diagnosis_report'
    resource_id: str             # 资源ID
    label: str                   # 用户可读标签
    as_of: datetime | None       # 数据时间戳
```

### 5.2 Evidence 用途

**调试追踪**：
```text
回答："数学 92 分"
    ↓
来自 student_subject_scores.id=abc123
    ↓
exam_id=exam_456, subject_id=math_789
```

**用户信任**：
```text
前端可显示：
"✓ 数据来源：2026秋季期中考试"
```

---

## 6. 一期实现策略

### 6.1 轻量级实现

一期可以用**规则检查**而不是再调用一个大模型：

```python
class LightweightResponseGuard:
    """轻量级 Guard（规则为主）"""
    
    async def validate(self, answer: str, context, entitlement) -> GuardResult:
        issues = []
        
        # 规则1：敏感词检查（BASIC）
        if entitlement == "BASIC":
            for word in FORBIDDEN_WORDS:
                if word in answer:
                    issues.append(f"包含敏感词: {word}")
        
        # 规则2：检查是否提及其他学生
        other_names = extract_names(answer)
        if len(other_names) > 1:  # 超过当前学生
            issues.append("可能包含其他学生信息")
        
        # 规则3：检查数字范围合理性
        numbers = extract_numbers(answer)
        for num in numbers:
            if num < 0 or num > 200:  # 分数不合理
                issues.append(f"数字{num}超出合理范围")
        
        return GuardResult(
            ok=len(issues) == 0,
            issues=issues,
            action="block" if issues else "pass"
        )
```

### 6.2 后续可升级为模型驱动

V2+ 可以用轻量模型（如 gpt-4o-mini）做更智能的检查：

```python
class ModelDrivenResponseGuard:
    """模型驱动的 Guard"""
    
    async def validate(self, answer: str, context, entitlement) -> GuardResult:
        # 调用轻量模型检查
        check_result = await self.model_gateway.structured(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": GUARD_PROMPT},
                {"role": "user", "content": f"Answer: {answer}\nContext: {context}"}
            ],
            response_schema=GuardResultSchema
        )
        
        return GuardResult(**check_result)
```

---

## 7. 测试要点

### 7.1 单元测试

```python
async def test_basic_forbidden_words():
    """测试 BASIC 敏感词检查"""
    guard = ResponseGuard()
    
    answer = "你函数概念薄弱，基础不扎实"
    result = await guard.validate(
        answer=answer,
        context=basic_context,
        entitlement="BASIC"
    )
    
    assert result.ok == False
    assert any("薄弱" in issue for issue in result.issues)
    assert result.action == "block" or result.action == "warn"
```

### 7.2 集成测试

```python
async def test_guard_in_agent_loop():
    """测试 Guard 在 Agent Loop 中工作"""
    
    # 模拟模型返回不合规答案
    with patch.object(model_gateway, 'chat') as mock_chat:
        mock_chat.return_value = ModelResponse(
            text="张三这次考得比你好，他数学95分",  # 包含其他学生
            ...
        )
        
        response = await agent_loop.run(...)
        
        # Guard 应该阻断
        assert "张三" not in response.text
        assert "抱歉" in response.text or "无法" in response.text
```

---

## 8. 监控指标

### 8.1 Guard 触发率

```sql
SELECT 
    DATE(created_at) as date,
    COUNT(*) as total_runs,
    SUM(CASE WHEN guard_action = 'block' THEN 1 ELSE 0 END) as blocked,
    SUM(CASE WHEN guard_action = 'warn' THEN 1 ELSE 0 END) as warned
FROM agent_runs
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY DATE(created_at);
```

### 8.2 Guard 问题分类

```sql
SELECT 
    guard_issue_type,
    COUNT(*) as count
FROM agent_run_guard_issues
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY guard_issue_type
ORDER BY count DESC;
```

---

## 9. 关键要点

1. **一期用规则检查，简单有效**
2. **后续可升级为模型驱动**
3. **每次 Guard 结果都记录到数据库**
4. **高危问题（隐私泄漏）必须 block**
5. **低危问题（措辞）可以 warn**
6. **Evidence 链随 Context 一起返回**
