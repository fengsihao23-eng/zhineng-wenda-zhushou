# 快速启动

仓库的正式 Compose 服务是 `db`、`redis`、`api`、`web` 和 `nginx`。只有
Nginx 对外发布端口；API 文档和前端都通过 `http://localhost` 访问。

## Docker 启动

```bash
cp .env.example .env
# 编辑 .env，至少设置 POSTGRES_PASSWORD、SECRET_KEY 和 JWT_SECRET_KEY
docker compose up -d --build
docker compose ps
```

API 容器启动时会执行 `alembic upgrade head`。需要演示数据时执行幂等的
ORM seed 脚本：

```bash
docker compose exec api python scripts/init_test_data.py
```

访问地址：

- 前端：<http://localhost>
- Swagger：<http://localhost/docs>
- ReDoc：<http://localhost/redoc>
- 健康检查：<http://localhost/api/health>

## 本地开发

```bash
# 先启动依赖服务
docker compose up -d db redis

# 后端
cd apps/api
python -m pip install -r requirements.txt
export DATABASE_URL='postgresql+asyncpg://postgres:<password>@localhost:5432/intelligent_qa'
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 另开终端启动前端
cd apps/web
npm ci
npm run dev
```

本地开发时前端 Vite 默认在 <http://localhost:5173>，开发代理默认通过宿主机的
<http://localhost> 网关访问 API。若只启动了本地 uvicorn（没有 Nginx 网关），将
代理指向 API 端口：

```bash
VITE_PROXY_TARGET=http://localhost:8000 npm run dev
```

生产 Compose 入口仍为 <http://localhost>。

## 测试

```bash
./scripts/run_tests.sh
./scripts/run_quality.sh
```

后端测试默认使用内存 SQLite；要使用隔离的 PostgreSQL 测试库，先设置
`TEST_DATABASE_URL`。完整说明见 [TESTING.md](TESTING.md)。
