#!/usr/bin/env python3
"""Compatibility wrapper for the single supported seed-data command.

The old script embedded a PostgreSQL password and duplicated the schema. Use
``DATABASE_URL`` plus Alembic and the idempotent ORM seed implementation.
"""
from __future__ import annotations

import runpy
from pathlib import Path


if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).resolve().parent / "setup_database.py"),
        run_name="__main__",
    )
