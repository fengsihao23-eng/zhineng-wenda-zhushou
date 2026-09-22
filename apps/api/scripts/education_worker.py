"""Recover pending education tasks. Configure the same DB as the API via env.

Run under a process supervisor. --once performs one bounded pass; no source
archives, external services or student payloads are printed. Only import/OCR
workspaces already confirmed by authorized API callers are eligible.
"""
import argparse
import asyncio
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.db.models.education import ImportWorkspace, OcrJob
from app.services.import_workbench import execute_import
from app.services.ocr_jobs import execute_ocr


async def pass_once():
    async with AsyncSessionLocal() as db:
        imports = (
            await db.scalars(
                select(ImportWorkspace.id)
                .where(ImportWorkspace.status == "running")
                .order_by(ImportWorkspace.created_at)
                .limit(20)
            )
        ).all()
        jobs = (
            await db.scalars(
                select(OcrJob.id)
                .where(OcrJob.status.in_(["queued", "running"]))
                .order_by(OcrJob.created_at)
                .limit(20)
            )
        ).all()
    for identifier in imports:
        await execute_import(AsyncSessionLocal, identifier)
    for identifier in jobs:
        await execute_ocr(AsyncSessionLocal, identifier)
    return len(imports), len(jobs)


async def main(once):
    while True:
        imports, jobs = await pass_once()
        if once:
            print(
                f"Education worker pass complete: import_candidates={imports}, ocr_candidates={jobs}"
            )
            return
        await asyncio.sleep(2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recover confirmed education tasks")
    parser.add_argument("--once", action="store_true")
    asyncio.run(main(parser.parse_args().once))
