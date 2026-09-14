#!/usr/bin/env python3
"""Validate and atomically import one complete CSV batch."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

from app.core.database import AsyncSessionLocal
from app.data.import_service import CsvImportService


async def _run(directory: Path, batch_id: str, source_system: str, created_by: UUID | None) -> int:
    async with AsyncSessionLocal() as db:
        report = await CsvImportService(db).import_directory(
            directory,
            batch_id=batch_id,
            source_system=source_system,
            created_by=created_by,
        )
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    return 0 if report.status == "succeeded" else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--source-system", default="csv")
    parser.add_argument("--created-by", type=UUID)
    args = parser.parse_args()
    return asyncio.run(_run(args.directory, args.batch_id, args.source_system, args.created_by))


if __name__ == "__main__":
    sys.exit(main())
