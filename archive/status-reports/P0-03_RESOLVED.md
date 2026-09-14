# P0-03: 数据库迁移状态 - 已解决 ✅

## 问题描述
不知道Alembic迁移是否已执行，不确定表是否都已创建。

## 解决过程

### 1. 发现的问题
- 数据库已创建，名称为 `intelligent_qa`
- 迁移版本在 `004`，缺少 `audit_logs` 和 `prompt_templates` 两个表
- 存在两个独立的迁移分支：
  - 主分支: `001 -> 002 -> 003 -> 004` (已应用)
  - 独立分支: `001_add_prompt_trace_audit` (未应用)
- Alembic 无法直接在容器中运行（缺少 psycopg2）

### 2. 执行的操作

#### 创建验证脚本
文件：`apps/api/scripts/verify_database.py`
- 检查所有必需的表是否存在
- 对比预期表和实际表
- 提供清晰的 ✅/❌ 状态报告

#### 创建缺失的表
直接使用 SQL 创建了两个缺失的表：
- `prompt_templates` - 提示词模板表
- `audit_logs` - 审计日志表

#### 创建迁移文件
文件：`apps/api/alembic/versions/005_add_audit_prompt_tables.py`
- 规范化迁移历史
- 包含完整的 upgrade 和 downgrade 方法

#### 更新迁移版本
- 将 `alembic_version` 更新到 `005`

### 3. 验证结果

#### 迁移状态
```bash
# 当前版本
version_num: 005
```

#### 数据库表清单（21个表）
✅ 所有必需的表都已创建 (20/20)

**身份表 (5)**
- schools - 学校表
- users - 用户表
- roles - 角色表
- user_roles - 用户角色关联表
- students - 学生表

**考试表 (3)**
- exams - 考试表
- subjects - 科目表
- exam_subjects - 考试科目关联表

**成绩表 (3)**
- student_exam_scores - 学生考试成绩表
- student_subject_scores - 学生科目成绩表
- question_scores - 题目成绩表

**诊断表 (2)**
- diagnosis_reports - 诊断报告表
- student_entitlements - 学生权益表

**Chat表 (2)**
- chat_sessions - 聊天会话表
- chat_messages - 聊天消息表

**Trace表 (4)**
- agent_runs - Agent运行记录表
- tool_call_logs - 工具调用日志表
- model_usage_logs - 模型使用日志表
- audit_logs - 审计日志表 ✨ (新增)

**Prompt表 (1)**
- prompt_templates - 提示词模板表 ✨ (新增)

**系统表 (1)**
- alembic_version - 迁移版本表

### 4. 常用命令

```bash
# 查看当前迁移版本
docker compose -p intelligent-qa exec postgres psql -U postgres -d intelligent_qa -c "SELECT * FROM alembic_version;"

# 查看所有表
docker compose -p intelligent-qa exec postgres psql -U postgres -d intelligent_qa -c "\dt"

# 运行验证脚本
docker compose -p intelligent-qa exec api bash -c "cd /app && PYTHONPATH=/app python scripts/verify_database.py"

# 查看迁移历史（在容器内）
docker compose -p intelligent-qa exec api bash -c "cd /app && PYTHONPATH=/app alembic history"
```

## 验收标准 - 全部完成 ✅

- ✅ 迁移版本明确（当前：005）
- ✅ 所有必需的表都已创建（20/20）
- ✅ 验证脚本运行无报错
- ✅ 所有表都显示 ✅ 状态

## 后续建议

1. **修复 Alembic 环境问题**
   - 添加 `psycopg2` 或 `psycopg2-binary` 到 `requirements.txt`
   - 或者修改 `alembic/env.py` 使用 asyncpg 进行迁移

2. **清理重复的迁移分支**
   - 移除或归档 `001_add_prompt_trace_audit.py`
   - 保持单一清晰的迁移链

3. **定期验证**
   - 在 CI/CD 中集成 `verify_database.py` 脚本
   - 确保开发和生产环境的表结构一致

## 时间线
- 问题发现：2026-09-10
- 解决完成：2026-09-10
- 耗时：约 30 分钟
