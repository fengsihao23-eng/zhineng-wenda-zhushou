# Phase 2 快速开始指南

> 历史阶段指南。旧版路由和服务命令可能已失效；当前 Compose、Chat 契约和
> 测试命令见 [PHASE3_QUICKSTART.md](PHASE3_QUICKSTART.md) 与 [TESTING.md](TESTING.md)。

## 🚀 启动服务

### 1. 确保数据库和Redis运行

```bash
cd /Users/hao/智能问答助手
docker-compose up -d postgres redis
```

### 2. 运行数据库迁移

```bash
cd apps/api
alembic upgrade head
```

### 3. 初始化测试数据

```bash
python init_test_data.py
```

### 4. 启动API服务

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

服务将在 http://localhost:8000 启动

---

## 📚 API文档

启动服务后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## 🧪 测试Phase 2功能

### 方式1: 运行自动化测试

```bash
cd apps/api
python test_phase2.py
```

这将测试：
- ✅ 所有6个Tool的注册和执行
- ✅ StudentContextBuilder
- ✅ Intent Router
- ✅ Agent Schemas

### 方式2: 使用示例客户端

```bash
cd apps/api
python chat_client_example.py
```

选择交互式模式，可以直接对话测试。

### 方式3: 使用curl测试

#### 3.1 获取JWT Token

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "student1",
    "password": "password123"
  }'
```

保存返回的 `access_token`。

#### 3.2 非流式对话

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{
    "message": "这次考试考得怎么样？",
    "stream": false
  }'
```

#### 3.3 流式对话 (SSE)

```bash
curl -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{
    "message": "数学考了多少分？",
    "stream": true
  }'
```

---

## 💬 支持的查询示例

### 考试总结
- "这次考试考得怎么样？"
- "最近一次考试的成绩是多少？"
- "我的总分和排名是多少？"

### 科目成绩
- "数学考了多少分？"
- "各科成绩怎么样？"
- "语文和数学分别多少分？"

### 排名变化
- "比上次进步了吗？"
- "这次排名有变化吗？"
- "和上次考试对比如何？"

### 成绩趋势
- "最近几次考试的趋势如何？"
- "数学成绩是进步还是退步？"
- "我的总分走势怎么样？"

### 小题丢分
- "哪些题目丢分最多？"
- "数学哪几题扣分严重？"
- "我的失分点在哪里？"

### 诊断报告 (需要DIAGNOSIS权益)
- "给我做个诊断分析"
- "我的薄弱知识点是什么？"
- "有什么学习建议吗？"

---

## 🔧 配置环境变量

创建 `.env` 文件（如果还没有）：

```bash
cp .env.example .env
```

必须配置的环境变量：

```env
# 数据库
DATABASE_URL=postgresql+asyncpg://postgres:your_password@localhost:5432/student_agent

# JWT
JWT_SECRET_KEY=your-secret-key-at-least-32-chars-long
JWT_ALGORITHM=HS256

# AI模型 (至少配置一个)
DEEPSEEK_API_KEY=your-deepseek-api-key
OPENAI_API_KEY=your-openai-api-key  # 可选
```

---

## 📊 工具列表

| 工具名称 | 功能 | 权益要求 | 文件位置 |
|---------|------|---------|---------|
| `get_exam_summary` | 获取考试总结 | BASIC | `exam_tools.py` |
| `get_subject_scores` | 获取科目成绩 | BASIC | `score_tools.py` |
| `get_ranking_change` | 获取排名变化 | BASIC | `score_tools.py` |
| `get_score_trend` | 获取成绩趋势 | BASIC | `analysis_tools.py` |
| `get_question_loss` | 获取小题丢分 | BASIC | `analysis_tools.py` |
| `get_diagnosis` | 获取诊断报告 | DIAGNOSIS | `analysis_tools.py` |

---

## 🎯 关键组件说明

### 1. StudentContextBuilder (`app/agent/context.py`)

自动加载：
- 学生基本信息
- 权益等级
- 最近5次考试记录
- 最新考试详情

### 2. Intent Router (`app/agent/intent_router.py`)

识别6种意图：
- `exam_summary` - 考试总结
- `subject_scores` - 科目成绩
- `ranking_change` - 排名变化
- `score_trend` - 成绩趋势
- `question_loss` - 小题丢分
- `diagnosis` - 诊断分析

### 3. Agent Loop (`app/agent/agent_loop.py`)

执行流程：
1. 构建学生上下文
2. 识别用户意图
3. 第一轮：调用相关工具
4. 第二轮：生成最终答案
5. 保存到数据库

最多2轮工具调用，避免无限循环。

### 4. Chat API (`app/api/v1/endpoints/chat.py`)

提供4个端点：
- `POST /api/v1/chat` - 非流式对话
- `POST /api/v1/chat/stream` - 流式对话 (SSE)
- `GET /api/v1/sessions` - 会话列表
- `GET /api/v1/sessions/{id}/messages` - 消息历史
- `DELETE /api/v1/sessions/{id}` - 删除会话

---

## 🐛 常见问题

### 1. 工具未注册

**错误**: `Tool not found: get_exam_summary`

**解决**: 确保 `app/main.py` 中的 `lifespan` 函数正确初始化了工具：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initializing tools...")
    async for db in get_db():
        registry = get_tool_registry()
        init_tools(db, registry)
        print(f"Registered {len(registry.list_all_tools())} tools")
        break
    yield
```

### 2. JWT验证失败

**错误**: `401 Unauthorized`

**解决**: 
1. 确保先调用 `/api/v1/auth/login` 获取token
2. 确保在请求头中正确携带token: `Authorization: Bearer YOUR_TOKEN`

### 3. 找不到学生数据

**错误**: `Student not found`

**解决**: 运行测试数据初始化脚本：
```bash
python init_test_data.py
```

### 4. 模型调用失败

**错误**: `No available provider found`

**解决**: 在 `.env` 中配置至少一个模型的API Key：
```env
DEEPSEEK_API_KEY=your-key-here
```

### 5. SSE流式输出中断

**问题**: 流式输出不完整或中断

**解决**: 
1. 检查nginx配置，确保禁用了缓冲
2. 使用 `X-Accel-Buffering: no` 响应头
3. 客户端超时时间设置足够长（60s+）

---

## 📈 性能指标

### 预期响应时间

- **意图识别**: < 10ms (纯规则匹配)
- **上下文加载**: < 100ms (数据库查询)
- **单次Tool调用**: < 200ms (数据库查询)
- **模型生成**: 1-3s (取决于模型提供商)
- **总响应时间**: 通常 < 3s

### 并发能力

- FastAPI异步架构，支持高并发
- 建议配置连接池大小: 20-50
- 建议使用Redis缓存热数据

---

## 🔒 安全注意事项

1. **JWT Secret**: 生产环境必须使用强随机密钥（至少32字符）
2. **API Key**: 不要将模型API Key提交到代码仓库
3. **数据隔离**: 所有查询都通过 `school_id` 和 `student_id` 过滤
4. **权益验证**: DIAGNOSIS工具会自动验证用户权益
5. **会话隔离**: 学生只能访问自己的会话和消息

---

## 📞 支持

遇到问题？

1. 查看日志: `docker-compose logs -f api`
2. 运行测试: `python test_phase2.py`
3. 查看API文档: http://localhost:8000/docs
4. 阅读完整文档: `PHASE2_COMPLETE.md`

---

**Phase 2 实现完成！开始体验智能问答吧！** 🎉
