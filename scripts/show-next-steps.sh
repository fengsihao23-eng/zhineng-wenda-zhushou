#!/usr/bin/env bash
set -euo pipefail

cat <<'EOF'
下一步：

1. cp .env.example .env
2. 为 POSTGRES_PASSWORD、SECRET_KEY、JWT_SECRET_KEY 填入真实值
3. ./scripts/start-local.sh
4. 打开 http://localhost，API 文档位于 http://localhost/docs

运行质量检查：
  ./scripts/run_quality.sh
EOF
