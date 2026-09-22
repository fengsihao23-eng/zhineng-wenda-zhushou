# PRD-09: Prompt Registry 设计

---
Status: draft
Type: DESIGN-REFERENCE
Owner: AI 平台
Last verified: 2026-09-11
Evidence: 设计参考；版本发布、回滚和缓存行为以实现与测试为准。
Supersedes: 旧版 Prompt Registry 示例
---

> 本文保留 Prompt 版本化设计，不把模板示例视为生产能力。

## 1. 概述

Prompt 不写死在 Router / API 中。所有 Prompt 必须版本化、可追踪、可回滚。

### 1.1 为什么需要 Prompt Registry

**问题**：
```python
# ❌ Prompt 散落在代码中
SYSTEM_PROMPT = """
你是学生智能问答助手...
"""
```

**解决**：
```python
# ✅ 统一管理
prompt = await prompt_registry.get(
    name="student_qa_system",
    version="v1"
)
```

**好处**：
- 版本管理
- A/B 测试
- 快速回滚
- 可追踪（每次 Agent Run 记录使用的 Prompt 版本）
- 团队协作（Prompt 工程师可独立迭代）

---

## 2. 数据模型

### 2.1 prompt_templates 表

```sql
CREATE TABLE prompt_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,              -- 'student_qa_system'
    scene VARCHAR(50) NOT NULL,              -- 'chat', 'intent', 'guard'
    version VARCHAR(20) NOT NULL,            -- 'v1', 'v2', 'v1.1'
    content TEXT NOT NULL,                   -- Prompt 内容
    variables JSONB,                         -- 可替换变量列表
    status VARCHAR(20) NOT NULL DEFAULT 'draft',  -- 'draft', 'published', 'deprecated'
    description TEXT,
    created_by UUID,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    UNIQUE(name, version)
);

CREATE INDEX idx_prompt_templates_name ON prompt_templates(name, status);
CREATE INDEX idx_prompt_templates_scene ON prompt_templates(scene);
```

### 2.2 prompt_ab_tests 表（可选，后续）

```sql
CREATE TABLE prompt_ab_tests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    prompt_a_id UUID NOT NULL REFERENCES prompt_templates(id),
    prompt_b_id UUID NOT NULL REFERENCES prompt_templates(id),
    traffic_split DECIMAL(3,2) NOT NULL DEFAULT 0.5,  -- 0.5 = 50%
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

---

## 3. PromptRegistry 接口

### 3.1 核心接口

```python
class PromptRegistry:
    """Prompt 注册表"""
    
    async def get(
        self,
        name: str,
        version: str | None = None
    ) -> PromptTemplate:
        """
        获取 Prompt
        如果不指定 version，返回最新 published 版本
        """
        pass
    
    async def render(
        self,
        name: str,
        version: str | None = None,
        **variables
    ) -> str:
        """
        获取并渲染 Prompt
        """
        prompt = await self.get(name, version)
        return prompt.render(**variables)
    
    async def create(
        self,
        name: str,
        scene: str,
        content: str,
        variables: list[str],
        description: str = ""
    ) -> PromptTemplate:
        """创建新 Prompt（自动版本号）"""
        pass
    
    async def publish(
        self,
        name: str,
        version: str
    ):
        """发布 Prompt"""
        pass
    
    async def deprecate(
        self,
        name: str,
        version: str
    ):
        """废弃 Prompt"""
        pass
```

### 3.2 PromptTemplate 类

```python
class PromptTemplate(BaseModel):
    """Prompt 模板"""
    id: UUID
    name: str
    scene: str
    version: str
    content: str
    variables: list[str]
    status: str
    created_at: datetime
    
    def render(self, **kwargs) -> str:
        """
        渲染 Prompt
        使用简单的字符串替换或 Jinja2
        """
        template = self.content
        
        # 检查必需变量
        missing = set(self.variables) - set(kwargs.keys())
        if missing:
            raise PromptRenderError(f"Missing variables: {missing}")
        
        # 使用 Jinja2 渲染
        from jinja2 import Template
        jinja_template = Template(template)
        return jinja_template.render(**kwargs)
```

---

## 4. 核心 Prompt 设计

### 4.1 student_qa_system_v1

**用途**：学生问答主 System Prompt

**内容**：
```text
你是学校学生智能问答助手。

# 学生身份
- 姓名：{{ identity.student_name }}
- 学校：{{ identity.school_name }}
- 年级：{{ identity.grade }}
- 班级：{{ identity.class_name }}

# 权益等级
{{ entitlement }}

# 核心规则

## 1. 数据真实性
- 只能根据系统提供的真实结构化数据回答学生个人成绩问题
- 不允许捏造考试、分数、排名、题目、诊断结论
- 数值以 Tool/Context 提供的数据为准，不自行重新计算复杂统计

## 2. 权限边界

{% if entitlement == "BASIC" %}
### BASIC 权益规则
- 可以回答：考试总分、科目成绩、排名、历史趋势、小题得分
- 不得推断：薄弱知识点、失分原因、学习能力、诊断结论
- 如果用户问"为什么"，应明确区分：
  * 已知事实（如"第17题丢了3分"）
  * 系统当前没有的诊断结论（如"可能是函数概念不扎实"）
- 可以建议："想了解更详细的失分原因，可以购买学情诊断报告"
{% endif %}

{% if entitlement == "DIAGNOSIS" %}
### DIAGNOSIS 权益规则
- 在 BASIC 基础上，可以访问学情诊断报告
- 只能复述或解释正式诊断报告存在的结论
- 不得超出报告范围推断新的诊断
- 回答诊断问题时应引用报告依据
{% endif %}

## 3. 数据隔离
- 不得读取、猜测或暴露其他学生的数据
- 只能访问当前学生自己的信息

## 4. 回答风格
- 简洁、自然、像正常老师/学习助手
- 不输出内部 Tool、SQL、JSON、Prompt、trace
- 先结论，再 2~4 个最重要事实，必要时给下一步
- 不要默认长篇作文

## 5. 数据不足
- 如果数据不足，直接说明缺少哪类数据，不要编造
- 如果存在多次考试，明确考试名称，避免混淆

# 当前上下文

{{ context }}

现在开始回答学生的问题。
```

**变量**：
- `identity` (dict): 学生身份信息
- `entitlement` (str): 'BASIC' or 'DIAGNOSIS'
- `context` (str): 当前问题相关的结构化上下文

---

### 4.2 intent_router_v1

**用途**：意图分类

**内容**：
```text
你是学生问答意图分类助手。

分析学生的问题，判断属于以下哪种意图：

1. EXAM_SUMMARY - 考试总结（如"这次考得怎样"、"总分多少"）
2. SUBJECT_SCORE - 科目成绩（如"数学多少分"、"哪科最高"）
3. RANK_CHANGE - 排名变化（如"比上次进步了吗"、"排名变化"）
4. SCORE_TREND - 成绩趋势（如"最近几次变化"、"趋势如何"）
5. QUESTION_LOSS - 小题丢分（如"哪题丢分多"、"哪些题失分"）
6. DIAGNOSIS - 诊断报告（如"为什么考差"、"哪里薄弱"、"失分原因"）
7. GENERAL_STUDENT_DATA - 一般学生数据查询
8. OUT_OF_SCOPE - 超出范围（非学生成绩相关）

同时提取：
- subject: 科目名称（如有）
- exam_hint: 考试提示（如"上次"、"期中"）
- needs_diagnosis: 是否需要诊断权益
- confidence: 置信度 (0-1)

返回 JSON 格式：
{
  "intent": "EXAM_SUMMARY",
  "subject": null,
  "exam_hint": null,
  "needs_diagnosis": false,
  "confidence": 0.95
}

用户问题：{{ query }}

最近对话历史：
{{ recent_messages }}
```

---

### 4.3 answer_guard_v1

**用途**：答案校验（可选，轻量级实现可用规则）

**内容**：
```text
你是回答质量守门员。

检查学生智能助手的回答是否符合规则：

## 检查项

1. **数字准确性**
   - 回答中的数字是否来自提供的 Context
   - 是否有捏造的数字

2. **权限边界**（{{ entitlement }}）
   {% if entitlement == "BASIC" %}
   - 是否出现诊断性措辞（薄弱、基础不扎实、理解不够等）
   - 是否推断了失分原因
   {% endif %}
   {% if entitlement == "DIAGNOSIS" %}
   - 诊断结论是否映射到报告 evidence
   - 是否超出报告推断
   {% endif %}

3. **数据隔离**
   - 是否提及其他学生姓名或信息

4. **逻辑一致性**
   - 排名变化方向是否正确
   - 是否混淆不同考试

# 输入

Context:
{{ context }}

Answer:
{{ answer }}

# 输出

返回 JSON：
{
  "ok": true/false,
  "issues": ["问题1", "问题2"],
  "action": "pass" / "block" / "warn"
}
```

---

## 5. PromptRegistry 实现

### 5.1 完整实现

```python
class PromptRegistry:
    def __init__(self, db: AsyncSession, cache: Redis | None = None):
        self.db = db
        self.cache = cache
        self._cache_ttl = 300  # 5分钟
    
    async def get(
        self,
        name: str,
        version: str | None = None
    ) -> PromptTemplate:
        """获取 Prompt"""
        
        # 尝试从缓存读取
        cache_key = f"prompt:{name}:{version or 'latest'}"
        if self.cache:
            cached = await self.cache.get(cache_key)
            if cached:
                return PromptTemplate.model_validate_json(cached)
        
        # 从数据库查询
        query = select(PromptTemplateModel).where(
            PromptTemplateModel.name == name
        )
        
        if version:
            query = query.where(PromptTemplateModel.version == version)
        else:
            # 获取最新 published 版本
            query = query.where(
                PromptTemplateModel.status == 'published'
            ).order_by(
                PromptTemplateModel.created_at.desc()
            )
        
        result = await self.db.execute(query)
        model = result.scalar_one_or_none()
        
        if not model:
            raise PromptNotFoundError(f"Prompt {name}:{version} not found")
        
        prompt = PromptTemplate.model_validate(model)
        
        # 写入缓存
        if self.cache:
            await self.cache.setex(
                cache_key,
                self._cache_ttl,
                prompt.model_dump_json()
            )
        
        return prompt
    
    async def render(
        self,
        name: str,
        version: str | None = None,
        **variables
    ) -> str:
        """获取并渲染"""
        prompt = await self.get(name, version)
        return prompt.render(**variables)
    
    async def create(
        self,
        name: str,
        scene: str,
        content: str,
        variables: list[str],
        description: str = "",
        created_by: UUID | None = None
    ) -> PromptTemplate:
        """创建新版本"""
        
        # 查询当前最大版本号
        result = await self.db.execute(
            select(func.max(PromptTemplateModel.version))
            .where(PromptTemplateModel.name == name)
        )
        max_version = result.scalar()
        
        # 计算新版本号
        if max_version:
            # v1 -> v2, v1.1 -> v1.2
            parts = max_version.lstrip('v').split('.')
            if len(parts) == 1:
                new_version = f"v{int(parts[0]) + 1}"
            else:
                parts[-1] = str(int(parts[-1]) + 1)
                new_version = f"v{'.'.join(parts)}"
        else:
            new_version = "v1"
        
        # 创建
        model = PromptTemplateModel(
            name=name,
            scene=scene,
            version=new_version,
            content=content,
            variables=variables,
            status='draft',
            description=description,
            created_by=created_by
        )
        
        self.db.add(model)
        await self.db.commit()
        await self.db.refresh(model)
        
        return PromptTemplate.model_validate(model)
    
    async def publish(self, name: str, version: str):
        """发布版本"""
        await self.db.execute(
            update(PromptTemplateModel)
            .where(
                PromptTemplateModel.name == name,
                PromptTemplateModel.version == version
            )
            .values(status='published', updated_at=func.now())
        )
        await self.db.commit()
        
        # 清除缓存
        if self.cache:
            await self.cache.delete(f"prompt:{name}:{version}")
            await self.cache.delete(f"prompt:{name}:latest")
```

---

## 6. 使用示例

### 6.1 在 Agent Loop 中使用

```python
class AgentLoop:
    async def run(self, actor, query, session):
        # ...
        
        # 获取并渲染 System Prompt
        system_prompt = await self.prompt_registry.render(
            name="student_qa_system",
            version="v1",  # 可以配置化或从 AB Test 决定
            identity={
                "student_name": actor.name,
                "school_name": actor.school.name,
                "grade": actor.grade,
                "class_name": actor.class_name
            },
            entitlement=state.entitlement,
            context=self._format_context(state.context)
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            # ...
        ]
        
        # 记录使用的 Prompt 版本
        state.prompt_version = "student_qa_system:v1"
        
        # ...
```

### 6.2 管理后台创建 Prompt

```python
# API: POST /api/v1/admin/prompts
async def create_prompt(data: CreatePromptRequest):
    prompt = await prompt_registry.create(
        name=data.name,
        scene=data.scene,
        content=data.content,
        variables=data.variables,
        description=data.description,
        created_by=current_user.id
    )
    
    return {"id": prompt.id, "version": prompt.version}

# API: POST /api/v1/admin/prompts/{name}/{version}/publish
async def publish_prompt(name: str, version: str):
    await prompt_registry.publish(name, version)
    return {"status": "published"}
```

---

## 7. A/B 测试（可选，后续）

### 7.1 流程

```python
class PromptABTest:
    async def select_prompt(
        self,
        test_name: str,
        user_id: UUID
    ) -> PromptTemplate:
        """根据 A/B 测试选择 Prompt"""
        
        test = await self.get_active_test(test_name)
        
        # 根据 user_id hash 分流
        hash_value = int(hashlib.md5(str(user_id).encode()).hexdigest(), 16)
        if hash_value % 100 < test.traffic_split * 100:
            return await self.prompt_registry.get_by_id(test.prompt_a_id)
        else:
            return await self.prompt_registry.get_by_id(test.prompt_b_id)
```

---

## 8. 版本管理策略

### 8.1 版本号规则

- **大版本（v1 → v2）**：System Prompt 结构性变化
- **小版本（v1.1 → v1.2）**：措辞优化、规则微调
- **始终保留历史版本**：用于追溯和回滚

### 8.2 发布流程

```text
1. 创建 draft 版本
2. 在测试环境验证
3. 小范围 A/B 测试（可选）
4. 发布为 published
5. 观察指标（准确率、用户满意度）
6. 如果有问题，快速回滚到上一版本
```

---

## 9. 监控指标

### 9.1 Prompt 效果指标

- **准确率**：答案中的数字与数据库一致的比例
- **权限合规率**：BASIC 用户不出现诊断措辞的比例
- **Tool 调用成功率**：模型正确选择 Tool 的比例
- **用户满意度**：点赞/点踩比例

### 9.2 关联分析

```sql
-- 查询某版本 Prompt 的表现
SELECT 
    ar.prompt_version,
    COUNT(*) as total_runs,
    AVG(ar.latency_ms) as avg_latency,
    SUM(CASE WHEN ar.status = 'success' THEN 1 ELSE 0 END)::float / COUNT(*) as success_rate
FROM agent_runs ar
WHERE ar.prompt_version LIKE 'student_qa_system:v1%'
GROUP BY ar.prompt_version
ORDER BY ar.created_at DESC;
```

---

## 10. 测试要点

### 10.1 单元测试

```python
async def test_prompt_render():
    """测试 Prompt 渲染"""
    prompt = await prompt_registry.get("student_qa_system", "v1")
    
    rendered = prompt.render(
        identity={"student_name": "张三"},
        entitlement="BASIC",
        context="..."
    )
    
    assert "张三" in rendered
    assert "BASIC" in rendered
```

### 10.2 版本测试

```python
async def test_prompt_versioning():
    """测试版本管理"""
    # 创建 v1
    v1 = await prompt_registry.create(
        name="test_prompt",
        scene="test",
        content="v1 content",
        variables=[]
    )
    assert v1.version == "v1"
    
    # 创建 v2
    v2 = await prompt_registry.create(
        name="test_prompt",
        scene="test",
        content="v2 content",
        variables=[]
    )
    assert v2.version == "v2"
    
    # 获取指定版本
    fetched_v1 = await prompt_registry.get("test_prompt", "v1")
    assert fetched_v1.content == "v1 content"
```

---

## 11. 关键要点

1. **所有 Prompt 必须版本化**
2. **每次 Agent Run 记录使用的 Prompt 版本**
3. **支持快速回滚**
4. **使用 Jinja2 或简单字符串替换渲染**
5. **缓存常用 Prompt，减少数据库查询**
6. **后续可支持 A/B 测试**
