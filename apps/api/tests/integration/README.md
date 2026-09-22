# 权限隔离集成测试 🔴 P0

## 测试概述

本测试套件确保智能问答助手系统的权限隔离机制完整有效，防止数据泄露和未授权访问。

## 测试目标

1. ✅ 确保学生无法访问其他学生的数据
2. ✅ 测试权限提升场景
3. ✅ 测试ResponseGuard机制
4. ✅ 验证跨租户数据访问隔离

## 测试统计

- **总测试数**: 22个
- **权限隔离测试**: 10+个
- **ResponseGuard测试**: 6个
- **攻击场景测试**: 3个
- **验收标准测试**: 3个

## 测试分类

### 1. 跨学生数据访问隔离测试 (6个)

#### `test_student_cannot_access_other_student_dashboard`
- **目的**: 验证学生1无法通过参数注入访问学生2的dashboard
- **场景**: 学生1尝试通过`student_id`参数访问学生2的数据
- **预期**: 返回学生1自己的数据，不泄露学生2的信息

#### `test_student_cannot_access_other_student_scores_via_api_injection`
- **目的**: 验证通过URL参数注入无法访问其他学生成绩
- **场景**: 在trends、diagnosis、mistakes等API中注入其他学生ID
- **预期**: 所有请求仍返回当前学生的数据

#### `test_student_cannot_access_other_student_chat_session`
- **目的**: 验证学生无法访问其他学生的聊天会话
- **场景**: 学生1尝试访问学生2的会话消息
- **预期**: 返回404错误，SESSION_NOT_FOUND

#### `test_student_cannot_modify_other_student_authorization`
- **目的**: 验证学生无法撤销其他学生的家长授权
- **场景**: 学生1尝试删除学生2的家长授权
- **预期**: 返回404，授权状态保持不变

#### `test_student_cannot_create_chat_session_for_another_student`
- **目的**: 验证学生无法为其他学生创建聊天会话
- **场景**: 学生1尝试通过参数为学生2创建会话
- **预期**: 会话创建成功但属于学生1

#### `test_cross_tenant_isolation`
- **目的**: 验证跨租户（学校）数据隔离
- **场景**: 学校A的学生尝试访问学校B的学生数据
- **预期**: 只能看到自己学校的数据

### 2. 权限提升场景测试 (3个)

#### `test_student_cannot_access_teacher_management_api`
- **目的**: 验证学生角色无法访问教师管理API
- **场景**: 学生尝试访问management/overview、management/students等端点
- **预期**: 返回403 Forbidden，错误码MANAGEMENT_ROLE_REQUIRED

#### `test_student_cannot_modify_jwt_claims_for_privilege_escalation`
- **目的**: 验证篡改JWT claims无法提升权限
- **场景**: 创建包含SCHOOL_ADMIN角色的恶意token
- **预期**: 系统从数据库重新加载角色，拒绝访问

#### `test_basic_user_cannot_access_diagnosis_features`
- **目的**: 验证BASIC用户无法访问DIAGNOSIS功能
- **场景**: BASIC用户访问诊断报告详情
- **预期**: 返回受限的诊断信息

### 3. ResponseGuard机制测试 (6个)

#### `test_response_guard_blocks_other_student_data_in_answer`
- **检查项**: 隐私保护 - 阻止模型回复中包含其他学生信息
- **测试案例**: "你考了520分，李四同学考了680分"
- **预期**: 检测到"李四"，action=block/warn

#### `test_response_guard_blocks_fabricated_numbers`
- **检查项**: 数字准确性 - 阻止捏造的数字
- **测试案例**: "你考了550分"（context中无此数字）
- **预期**: 检测到捏造数字550

#### `test_response_guard_blocks_basic_forbidden_words`
- **检查项**: 权益边界 - BASIC用户禁用词
- **测试案例**: "你的函数概念薄弱"
- **预期**: 检测到"薄弱"，action=block/warn

#### `test_response_guard_allows_diagnosis_words_for_diagnosis_users`
- **检查项**: 权益边界 - DIAGNOSIS用户允许诊断性措辞
- **测试案例**: "你的函数概念薄弱"
- **预期**: action != block

#### `test_response_guard_tool_numbers_are_allowed`
- **检查项**: 工具返回数字豁免检查
- **测试案例**: "数学得分135分"（工具返回的权威数据）
- **预期**: ok=True，通过验证

#### `test_response_guard_100_percent_coverage`
- **检查项**: 综合测试所有检查维度
- **覆盖**: 隐私、数字、禁用词、逻辑、合规答案

### 4. 复杂攻击场景测试 (3个)

#### `test_sql_injection_in_student_id_parameter`
- **攻击类型**: SQL注入
- **攻击向量**: `1' OR '1'='1`、`1; DROP TABLE students--`
- **预期**: 返回400或正常数据，不泄露其他学生信息

#### `test_idor_attack_on_authorization_endpoints`
- **攻击类型**: IDOR (Insecure Direct Object Reference)
- **攻击向量**: 遍历ID访问其他学生的授权记录
- **预期**: 404错误，无法删除或查看其他学生的授权

#### `test_race_condition_in_session_access`
- **攻击类型**: 并发竞态条件
- **攻击向量**: 10个并发请求尝试访问其他学生会话
- **预期**: 所有请求均被拒绝

### 5. 消息反馈隔离测试 (1个)

#### `test_student_can_only_feedback_own_messages`
- **目的**: 验证学生只能对自己的消息提交反馈
- **场景**: 学生1尝试对学生2的消息提交反馈
- **预期**: 返回404，MESSAGE_NOT_FOUND

## 验收标准

### ✅ 标准1: 10+个权限隔离测试通过
- **实际**: 10个核心隔离测试
- **状态**: 通过 ✓

### ✅ 标准2: 无数据泄露漏洞
- **验证方式**: 
  - 跨学生访问测试 (6个)
  - 跨租户访问测试 (1个)
  - IDOR攻击测试 (1个)
- **状态**: 通过 ✓

### ✅ 标准3: ResponseGuard覆盖率100%
- **覆盖检查点**:
  - `_check_numbers` - 数字准确性
  - `_check_basic_boundary` - 权益边界
  - `_check_privacy` - 隐私保护
  - `_check_logic_consistency` - 逻辑一致性
- **状态**: 通过 ✓

## 运行测试

### 运行所有权限测试
```bash
source .venv/bin/activate
python -m pytest apps/api/tests/integration/test_permissions.py -v
```

### 运行特定类别的测试
```bash
# 只运行跨学生访问测试
python -m pytest apps/api/tests/integration/test_permissions.py -v -k "student_cannot"

# 只运行ResponseGuard测试
python -m pytest apps/api/tests/integration/test_permissions.py -v -k "response_guard"

# 只运行攻击场景测试
python -m pytest apps/api/tests/integration/test_permissions.py -v -k "injection or idor or race"

# 验收标准测试
python -m pytest apps/api/tests/integration/test_permissions.py -v -k "acceptance"
```

### 查看测试覆盖率
```bash
python -m pytest apps/api/tests/integration/test_permissions.py --cov=app.core.response_guard --cov-report=html
```

## 测试数据设计

### 学校架构
- **学校A (SCHOOL_A)**: 
  - 学生1 (张三, S001)
  - 学生2 (李四, S002)
- **学校B (SCHOOL_B)**:
  - 学生3 (王五, S003)

### 考试成绩数据
- **学生1**: 总分520, 班级排名15
- **学生2**: 总分680, 班级排名3
- **用途**: 验证不同成绩数据的隔离

## 安全机制验证

### 1. 数据库层面
- ✅ 所有查询使用`school_id`和`student_id`双重过滤
- ✅ 使用复合外键约束确保租户一致性
- ✅ SQLAlchemy参数化查询防止SQL注入

### 2. API层面
- ✅ `get_current_student`依赖注入强制身份验证
- ✅ 所有学生API使用`_student_scope`函数过滤数据
- ✅ 角色权限从数据库实时加载，不信任JWT claims

### 3. 业务逻辑层面
- ✅ ResponseGuard多维度验证模型输出
- ✅ 工具调用结果标记为权威数据源
- ✅ Context构建时严格限定数据范围

## 已知限制和未来改进

### 当前限制
1. 测试使用内存SQLite数据库，生产环境使用PostgreSQL
2. ResponseGuard规则基于正则表达式，可能有边界情况
3. 并发测试数量有限（10个并发请求）

### 未来改进方向
1. 添加性能测试 - 大规模数据下的权限检查性能
2. 添加模糊测试 - 自动生成各种恶意输入
3. 集成到CI/CD - 每次提交自动运行
4. 添加PostgreSQL集成测试 - 验证生产数据库行为

## 相关文档

- [架构设计文档](../../DESIGN.md)
- [API文档](../../../../docs/)
- [ResponseGuard实现](../../app/core/response_guard.py)
- [权限依赖](../../app/api/deps.py)

## 维护者

- 测试创建: 2024-09-16
- 最后更新: 2024-09-16
- 维护团队: 后端团队

## 问题反馈

如果发现权限漏洞或测试覆盖不足，请立即报告：
1. 创建P0优先级Issue
2. 标签: `security`, `permissions`, `P0`
3. 包含复现步骤和影响范围评估
