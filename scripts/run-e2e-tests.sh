#!/usr/bin/env bash
# Build the deployed version and run the root Playwright configuration.
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
docker compose up -d --build --wait --wait-timeout 180
# Seed only in a deliberately chosen test environment; preserve existing data by default.
if [[ "${E2E_SEED_DATA:-0}" == "1" ]]; then
  docker compose exec -T api python scripts/init_test_data.py
fi
npx playwright test --config=playwright.config.ts "$@"
