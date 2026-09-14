# 测试与质量门禁

后端测试默认使用内存 SQLite，因此新 checkout 不需要预先启动数据库：

```bash
cd apps/api
python -m pip install -r requirements.txt -r requirements-test.txt
TEST_DATABASE_URL=sqlite+aiosqlite:///:memory: python -m pytest -q
```

生产数据库类型通过 `app.db.types` 在 PostgreSQL 使用原生 UUID/JSONB/INET，
在 SQLite 使用兼容实现。CI 会执行上面的 SQLite 套件；需要 PostgreSQL 集成
验证时，为隔离的测试数据库设置 `TEST_DATABASE_URL`，不要指向开发或生产库。

前端检查命令为：

```bash
cd apps/web
npm ci
npm run lint
npm test -- --run
npm run build
```

仓库级质量入口是 `./scripts/run_quality.sh`，CI 配置位于
`.github/workflows/ci.yml`。静态门禁至少捕获语法错误和未定义名称；完整
覆盖率仍需随业务闭环继续提高，覆盖率报告由 `pytest.ini` 输出到
`apps/api/coverage.xml` 和 `apps/api/htmlcov/`。

当前门禁覆盖 API/数据库契约和前端构建；浏览器级 E2E、长连接压测和多
worker/Redis 限流验证仍需在试点环境补充。
