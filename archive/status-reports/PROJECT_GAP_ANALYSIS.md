# 项目缺口分析报告

## 现状总结

### ✅ 已实现的部分

#### 后端核心组件（57个Python文件）
- **AgentLoop**: 完整实现，支持同步和流式两种模式
- **StudentContextBuilder**: 上下文构建器
- **IntentRouter**: 意图识别
- **Tools**: 工具注册表和基础工具
- **ModelGateway**: 模型调用网关
- **PromptRegistry**: Prompt版本管理
- **TraceAudit**: 追踪和审计
- **ResponseGuard**: 答案校验
- **Chat API**: `/api/v1/chat/stream` 流式接口已实现
- **Health API**: 健康检查
- **Auth Deps**: JWT认证依赖

#### 前端（7个文件）
- **ChatContainer**: 聊天容器组件
- **MessageList/MessageBubble**: 消息展示
- **InputBox**: 输入框
- **useStreamChat**: 流式聊天Hook

#### 基础设施
- Docker Compose配置
- PostgreSQL + Redis运行中
- Alembic迁移框架

---

## 🔴 关键缺失部分

### 1. **认证系统完全缺失**（阻塞问题）

#### 缺失内容：
- ❌ 登录API实现（`POST /api/v1/auth/login`）
- ❌ Token刷新API（`POST /api/v1/auth/refresh`）
- ❌ 当前用户API（`GET /api/v1/auth/me`）
- ❌ 前端登录页面
- ❌ 前端Token管理

#### 现状：
```python
# apps/api/app/api/deps.py
async def get_current_user(...):
    # 这个函数存在，但没有/auth/login端点可以获取token
    token = credentials.credentials
    payload = decode_token(token)  # 会失败，因为token不存在
```

#### 影响：
前端调用任何需要认证的接口都会返回：
```json
{"detail":"Could not validate credentials"}
```

---

### 2. **测试数据完全缺失**

#### 缺失内容：
- ❌ 学校基础数据（schools）
- ❌ 用户数据（users）
- ❌ 学生数据（students）
- ❌ 考试数据（exams）
- ❌ 成绩数据（student_exam_scores）
- ❌ 诊断报告数据（diagnosis_reports）
- ❌ 权益数据（student_entitlements）

#### 现状：
数据库表结构可能已创建（需验证），但完全没有数据。

#### 影响：
即使认证通过，AgentLoop执行时：
- Context Builder找不到学生数据
- Tools查询不到任何成绩
- 无法展示任何实际效果

---

### 3. **数据库迁移状态未知**

#### 待验证：
- ❌ Alembic迁移是否已执行？
- ❌ 所有表是否已创建？
- ❌ 表结构是否与代码Model匹配？

---

### 4. **前端缺少完整用户流程**

#### 缺失页面：
- ❌ 登录页面（`/login`）
- ❌ 注册页面（如需要）
- ❌ 用户信息页面
- ❌ 考试列表页面（可选，但PRD有提到）
- ❌ Token过期处理

#### 现状：
前端只有一个空壳Chat界面，`getToken()` 从localStorage读取，但从未设置过。

---

### 5. **开发模式缺失**

#### 缺失功能：
- ❌ 开发环境跳过认证的选项
- ❌ Mock用户注入
- ❌ 快速测试脚本

---

## 📋 补全优先级计划

### 🚨 P0 - 立即修复（阻塞性问题）

#### Task 1: 数据库迁移验证与执行
```bash
# 1. 检查迁移状态
cd apps/api
alembic current

# 2. 执行所有迁移
alembic upgrade head

# 3. 验证表创建
psql -U postgres -d intelligent_qa -c "\dt"
```

#### Task 2: 创建开发模式Mock认证
两种方案：

**方案A：开发环境跳过认证（最快）**
- 添加环境变量 `DEV_MODE=true`
- 修改 `get_current_user` 在DEV_MODE下返回Mock用户
- 前端直接调用API，无需token

**方案B：简化登录（推荐）**
- 实现最简单的用户名密码登录
- 不做复杂注册流程
- 创建几个测试账号

#### Task 3: 测试数据初始化脚本
```python
# scripts/init_test_data.py
# 创建：
# - 1个学校
# - 2个学生（1个BASIC，1个DIAGNOSIS）
# - 2次考试
# - 完整成绩数据
# - 1份诊断报告
```

---

### 🟡 P1 - 核心功能（1-2天）

#### Task 4: Auth API实现
```python
# apps/api/app/api/v1/endpoints/auth.py
@router.post("/login")
async def login(...)

@router.post("/refresh")
async def refresh_token(...)

@router.get("/me")
async def get_current_user_info(...)
```

#### Task 5: 前端登录页面
```tsx
// apps/web/src/pages/Login.tsx
// - 用户名/密码输入
// - 登录按钮
// - Token存储到localStorage
// - 跳转到Chat页面
```

#### Task 6: Token管理
```tsx
// apps/web/src/utils/auth.ts
// - setToken(token)
// - getToken()
// - clearToken()
// - isAuthenticated()
```

---

### 🟢 P2 - 完善功能（2-3天）

#### Task 7: 学生信息页面
```
GET /api/v1/students/me
- 展示学生基本信息
- 展示最近考试列表
- 展示权益状态
```

#### Task 8: 考试列表页面
```
GET /api/v1/students/me/exams
- 考试列表
- 点击进入Chat并自动关联考试
```

#### Task 9: E2E测试
```
- 登录流程测试
- Chat对话测试
- 权限隔离测试
```

---

## 🎯 最小可用版本（MVP）范围

### 目标：让系统真正跑起来，能完成一次完整对话

#### MVP包含：
1. ✅ 开发模式Mock认证 或 简单登录
2. ✅ 测试数据初始化（1学校+2学生+2考试+成绩）
3. ✅ 数据库迁移执行
4. ✅ 前端能成功发送消息并收到回复
5. ✅ 验证Agent能调用Tools并返回真实数据

#### MVP不包含：
- ❌ 完整的用户注册流程
- ❌ 密码找回
- ❌ 权限管理后台
- ❌ 生产级安全加固
- ❌ 性能优化

---

## 📊 工作量估算

### 开发模式（最快路径）
- Task 1: 数据库迁移 - **30分钟**
- Task 2: Mock认证 - **1小时**
- Task 3: 测试数据脚本 - **2小时**
- **总计：3.5小时** → **今天可完成**

### 完整登录（推荐路径）
- Task 1: 数据库迁移 - **30分钟**
- Task 3: 测试数据脚本 - **2小时**
- Task 4: Auth API - **3小时**
- Task 5: 登录页面 - **2小时**
- Task 6: Token管理 - **1小时**
- **总计：8.5小时** → **1-2天完成**

---

## 🎬 立即行动建议

### 方案1：极速验证（今天完成）
```bash
1. 执行数据库迁移（30分钟）
2. 添加DEV_MODE跳过认证（1小时）
3. 创建测试数据（2小时）
4. 测试Chat对话（30分钟）
```

### 方案2：完整实现（1-2天）
```bash
Day 1:
- 执行数据库迁移
- 创建测试数据
- 实现Auth API
- 实现登录页面

Day 2:
- 前端Token管理
- 集成测试
- 修复问题
```

---

## 🚦 当前阻塞点

**阻塞原因**：前端无法获取有效Token → 所有API调用失败

**解决方案**：
1. **方案A（开发）**：环境变量跳过认证，Mock一个固定学生
2. **方案B（生产）**：实现完整登录流程

**推荐**：先用方案A验证系统可用，再补全方案B。

---

## 结论

**当前状态**：代码写了很多，但缺少关键的"胶水层"让系统跑起来。

**核心问题**：
1. 认证系统有依赖定义但无实现
2. 测试数据完全缺失
3. 数据库迁移状态未知

**解决路径**：
- **今天**：添加开发模式 + 测试数据，让系统能跑
- **明天**：补全认证API + 登录页面
- **后天**：完善测试和文档

**预期结果**：
- 3.5小时后系统能完成第一次对话
- 2天后系统具备完整用户流程
