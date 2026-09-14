# Phase 3 部署说明

Compose 当前包含 `db`、`redis`、`api`、`web` 和 `nginx` 五个服务。API 与
前端仅加入内部网络，由 Nginx 对外提供 HTTP（可选 TLS）入口。

## 部署

```bash
cp .env.example .env
# 生产环境必须替换 POSTGRES_PASSWORD、SECRET_KEY、JWT_SECRET_KEY
docker compose config
docker compose up -d --build
docker compose ps
```

迁移在 API 容器启动时执行。首次试点环境可按需加载演示数据：

```bash
docker compose exec api python scripts/init_test_data.py
```

入口和探针：

```bash
curl http://localhost/api/health
curl http://localhost/docs
```

启用 TLS 前，将证书挂载为 `infra/nginx/certs/fullchain.pem` 和
`infra/nginx/certs/privkey.pem`，并设置 `TLS_ENABLED=true`。入口脚本会在证书
缺失时拒绝启动。

## 备份与恢复

```bash
./infra/scripts/backup-db.sh
./infra/scripts/restore-db.sh /path/to/backup.sql.gz
```

恢复脚本会要求交互确认；请先在隔离环境演练，再操作生产数据。

## 验证

后端测试、SQLite/PostgreSQL 兼容性和前端构建命令见
[TESTING.md](TESTING.md)。本文不将构建成功或容器启动作为“生产就绪”证明，
还需要完成 PRD 中的权限、容量、备份恢复和试点验收门禁。
