"""持久化 CSV 批次校验结果，作为正式 upsert 前的 staging 边界。"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.data.csv_importer import REQUIRED_COLUMNS, validate_csv_directory
from app.db.models.import_batch import ImportBatch, ImportRow


def _batch_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.glob("*.csv")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


async def stage_csv_batch(
    db: AsyncSession,
    root: str | Path,
    batch_id: str,
    source_system: str,
    created_by: UUID | None = None,
) -> tuple[ImportBatch, dict]:
    """校验并持久化一个批次；校验失败时不进入正式业务表。"""
    directory = Path(root)
    existing = await db.execute(
        ImportBatch.__table__.select().where(ImportBatch.batch_id == batch_id)
    )
    previous = existing.first()
    if previous:
        return previous[0], {"ok": True, "idempotent": True, "batch_id": batch_id}

    report = validate_csv_directory(directory, batch_id)
    batch = ImportBatch(
        batch_id=batch_id,
        source_system=source_system,
        root_path=str(directory.resolve()),
        content_hash=_batch_hash(directory) if directory.is_dir() else "",
        status="validated" if report.ok else "rejected",
        report_json=report.as_dict(),
        error_count=len(report.issues),
        idempotent=False,
        created_by=created_by,
    )
    db.add(batch)
    await db.flush()

    total_rows = 0
    for filename in REQUIRED_COLUMNS:
        path = directory / filename
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        for row_number, row in enumerate(rows, start=2):
            total_rows += 1
            db.add(ImportRow(
                batch_id=batch.id,
                file_name=filename,
                row_number=row_number,
                row_hash=hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                raw_data=row,
                status="validated" if report.ok else "rejected",
            ))
    batch.total_rows = total_rows
    batch.success_rows = total_rows if report.ok else 0
    batch.failed_rows = 0 if report.ok else len(report.issues)
    await db.commit()
    await db.refresh(batch)
    return batch, report.as_dict()
