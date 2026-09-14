# 快速开始

当前可执行的 Docker、本地开发和测试命令集中在
[docs/QUICKSTART.md](docs/QUICKSTART.md)。

```bash
cp .env.example .env
# 设置真实 POSTGRES_PASSWORD、SECRET_KEY 和 JWT_SECRET_KEY
docker compose up -d --build
docker compose ps
```

公开入口由 Nginx 提供：<http://localhost>；API 文档为
<http://localhost/docs>，健康检查为 <http://localhost/api/health>。

运行测试和质量门禁：

```bash
./scripts/run_tests.sh
./scripts/run_quality.sh
```

后端测试默认使用内存 SQLite，CI 还运行 PostgreSQL 15。详见
[docs/TESTING.md](docs/TESTING.md)。
