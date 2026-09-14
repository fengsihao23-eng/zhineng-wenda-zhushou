#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$PROJECT_ROOT/apps/api"
WEB_DIR="$PROJECT_ROOT/apps/web"
PYTHON_BIN="${PYTHON_BIN:-python}"
if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
fi

echo "Compiling backend Python sources..."
"$PYTHON_BIN" -m compileall -q "$API_DIR/app" "$API_DIR/tests"

echo "Running backend static quality gate..."
(
  cd "$API_DIR"
  "$PYTHON_BIN" -m flake8 app tests --select=E9,F821,F822,F823
)

echo "Running frontend lint, tests, and production build..."
(
  cd "$WEB_DIR"
  npm run lint
  npm test -- --run
  npm run build
)

echo "Quality checks passed."
