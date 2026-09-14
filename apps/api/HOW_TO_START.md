# 🚀 如何启动 Phase 2 服务

## 方式1: 快速启动（查看API文档）

最简单的方式，不需要数据库，直接启动查看API文档：

```bash
cd /Users/hao/智能问答助手/apps/api
python start_simple.py
```

然后访问：http://localhost:8000/docs

---

## 方式2: 完整启动（含数据库）

### 步骤1: 配置 API Key

编辑 `/Users/hao/智能问答助手/apps/api/.env` 文件：

```env
# 至少配置一个模型的 API Key
DEEPSEEK_API_KEY=your_deepseek_api_key_here
# 或
OPENAI_API_KEY=your_openai_api_key_here
```

### 步骤2: 启动数据库

```bash
cd /Users/hao/智能问答助手

# 方式A: 使用 Docker（推荐）
docker compose up -d db redis

# 方式B: 使用本地 PostgreSQL
# 确保 PostgreSQL 在 localhost:5432 运行
```

### 步骤3: 初始化数据库

```bash
cd apps/api

# 运行迁移
alembic upgrade head

# 初始化测试数据
python init_test_data.py
```

### 步骤4: 启动 API

```bash
./start.sh
# 或
python start_simple.py
```

---

## 方式3: 手动启动

```bash
cd /Users/hao/智能问答助手/apps/api

# 安装依赖（首次）
pip install -r requirements.txt

# 启动服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 访问地址

启动成功后：

- **API文档 (Swagger)**: http://localhost:8000/docs
- **API文档 (ReDoc)**: http://localhost:8000/redoc
- **健康检查**: http://localhost:8000/api/v1/health
- **根路径**: http://localhost:8000/

---

## 常见问题

### Q1: 端口8000被占用

```bash
# 查找占用进程
lsof -i :8000

# 杀死进程
kill -9 <PID>

# 或使用其他端口
uvicorn app.main:app --port 8001
```

### Q2: 模块导入错误

```bash
cd /Users/hao/智能问答助手/apps/api
export PYTHONPATH=$PWD:$PYTHONPATH
python start_simple.py
```

### Q3: 数据库连接失败

检查 `.env` 文件中的 `DATABASE_URL` 是否正确：

```env
# Docker 方式
DATABASE_URL=postgresql+asyncpg://postgres:${POSTGRES_PASSWORD}@db:5432/intelligent_qa

# 本地 PostgreSQL
DATABASE_URL=postgresql+asyncpg://postgres:your_password@db:5432/intelligent_qa
```

### Q4: 缺少依赖

```bash
cd apps/api
pip install -r requirements.txt
```

---

## 快速测试

启动服务后，在浏览器访问 http://localhost:8000/docs，你会看到：

- ✅ `/api/v1/health` - 健康检查
- ✅ `/api/v1/auth/login` - 登录认证
- ✅ `/api/v1/chat` - 对话接口（非流式）
- ✅ `/api/v1/chat/stream` - 对话接口（流式）
- ✅ `/api/v1/sessions` - 会话管理

---

## 下一步

1. 在 Swagger UI 中测试 `/api/v1/health` 端点
2. 如果有测试数据，尝试 `/api/v1/auth/login`
3. 查看完整文档：`PHASE2_COMPLETE.md`

有问题随时问我！
