#!/usr/bin/env python3
"""Initialize the database using the current Alembic and ORM seed scripts.

Use ``DATABASE_URL`` to target an isolated database. The seed operation is
idempotent for the built-in ``DEMO_SCHOOL`` fixture.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config


PROJECT_ROOT = Path(__file__).resolve().parent.parent
API_DIR = PROJECT_ROOT / "apps" / "api"


def database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        raise SystemExit("DATABASE_URL must be set; copy .env.example and provide a real password")
    return value


def main() -> None:
    url = database_url()
    sync_url = url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", sync_url)
    command.upgrade(config, "head")

    env = os.environ.copy()
    env["DATABASE_URL"] = url
    subprocess.run(
        [sys.executable, str(API_DIR / "scripts" / "init_test_data.py")],
        cwd=str(API_DIR),
        env=env,
        check=True,
    )
    subprocess.run(
        [sys.executable, str(API_DIR / "scripts" / "seed_platform.py")],
        cwd=str(API_DIR),
        env=env,
        check=True,
    )


if __name__ == "__main__":
    main()
