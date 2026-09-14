#!/usr/bin/env python3
"""Compatibility wrapper for the idempotent ORM seed command."""
from __future__ import annotations

import runpy
from pathlib import Path


if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).resolve().parent / "setup_database.py"),
        run_name="__main__",
    )
