"""Initialize safe r92 baselines without changing archives, scores, reports or grants."""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from types import SimpleNamespace
from sqlalchemy import select, func
from app.core.database import AsyncSessionLocal
from app.db.models import School
from app.db.models.answer_workbench import AnswerScope
from app.services.answer_workbench import ensure_scopes


async def main():
    async with AsyncSessionLocal() as db:
        before = await db.scalar(select(func.count()).select_from(AnswerScope))
        schools = list((await db.scalars(select(School.id).where(School.status == 'active'))).all())
        for school_id in schools:
            await ensure_scopes(db, SimpleNamespace(school_id=school_id))
        after = await db.scalar(select(func.count()).select_from(AnswerScope))
        print(f'active_schools={len(schools)}; new_baseline_scopes={after-before}; total_scopes={after}')


if __name__ == '__main__':
    asyncio.run(main())
