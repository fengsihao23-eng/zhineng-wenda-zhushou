#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ ! -f .env ]]; then
  echo "缺少 .env。请先 cp .env.example .env，并填写数据库密码和两个随机密钥。" >&2
  exit 1
fi

# The Compose stack keeps PostgreSQL/Redis private and exposes only the Nginx
# gateway. Set DEPLOY_APP_ENV=development explicitly when developing.
docker compose up -d --build
echo "服务已启动："
echo "  应用: http://localhost"
echo "  API 文档: http://localhost/docs"
echo "  健康检查: http://localhost/health"
