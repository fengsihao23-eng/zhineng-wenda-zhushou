# 快速部署指南

由于你的系统是Python 3.13（较新版本），某些包的预编译版本可能不兼容。我建议使用Docker部署，这样更简单可靠。

## 方案1: Docker部署（推荐）

### 1. 确保Docker已安装
```bash
docker --version
docker-compose --version
```

如果没有安装：
```bash
brew install docker
brew install docker-compose
```

### 2. 配置环境变量
```bash
cd /Users/hao/智能问答助手
cp .env.example .env
# 编辑.env文件，配置必要的变量
```

### 3. 启动所有服务
```bash
docker-compose up -d
```

这将启动：
- PostgreSQL数据库
- Redis缓存
- API后端服务
- Web前端服务
- Nginx网关

### 4. 查看服务状态
```bash
docker-compose ps
```

### 5. 访问应用
- 前端: http://localhost
- API文档: http://localhost/api/docs

### 6. 查看日志
```bash
docker-compose logs -f api
docker-compose logs -f web
```

---

## 方案2: 本地开发（使用Python 3.11）

如果你需要本地开发环境，建议安装Python 3.11：

### 1. 安装Python 3.11
```bash
brew install python@3.11
```

### 2. 创建虚拟环境（使用Python 3.11）
```bash
cd /Users/hao/智能问答助手
python3.11 -m venv venv
source venv/bin/activate
```

### 3. 安装依赖
```bash
pip install --upgrade pip
pip install -r apps/api/requirements.txt
pip install -r apps/api/requirements-test.txt
```

### 4. 配置数据库
```bash
# 安装PostgreSQL
brew install postgresql@15

# 启动PostgreSQL
brew services start postgresql@15

# 创建数据库
createdb intelligent_qa
```

### 5. 运行迁移
```bash
cd apps/api
alembic upgrade head
```

### 6. 初始化Prompt
```bash
python -m scripts.init_prompts
```

### 7. 启动后端
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 8. 启动前端（新终端）
```bash
cd apps/web
npm install
npm run dev
```

---

## 方案3: 最小化手动部署

如果只是想快速测试Phase 3的功能，可以：

### 1. 使用SQLite（无需PostgreSQL）
修改 `apps/api/app/core/config.py`：
```python
DATABASE_URL = "sqlite+aiosqlite:///./test.db"
```

### 2. 安装最小依赖
```bash
cd /Users/hao/智能问答助手
python3 -m venv venv
source venv/bin/activate

# 只安装核心包
pip install fastapi uvicorn sqlalchemy aiosqlite alembic pydantic jinja2
```

### 3. 运行测试
```bash
cd apps/api
pytest tests/ -v
```

---

## 当前问题原因

Python 3.13是非常新的版本（2024年10月发布），某些包（特别是pydantic 2.6.0的Rust扩展）还没有预编译的二进制文件支持3.13，需要从源码编译，这需要Rust编译器。

**建议**: 
1. **生产环境**: 使用Docker（最稳定）
2. **开发环境**: 使用Python 3.11（兼容性最好）
3. **快速测试**: 使用SQLite + 最小依赖

---

## 你想选择哪个方案？

告诉我你的选择，我会帮你完成部署！
