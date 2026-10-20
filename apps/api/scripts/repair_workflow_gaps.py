"""Idempotent repair; defaults to a rolled-back preview. No maxima are inferred."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select, update, func
from app.core.database import AsyncSessionLocal
from app.db.models import School, QuestionScore
from app.services.teaching_assignments import reconcile_school


async def repair(db):
    created, pending = 0, 0
    schools = (await db.scalars(select(School.id).where(School.status == 'active').order_by(School.id))).all()
    for school_id in schools:
        result = await reconcile_school(db, school_id)
        created += result['created']
        pending += len(result['pending'])
    changed = await db.execute(update(QuestionScore).where(QuestionScore.full_score.is_not(None),
        QuestionScore.full_score >= QuestionScore.score, QuestionScore.lost_score.is_(None)).values(
        lost_score=QuestionScore.full_score - QuestionScore.score))
    unknown = await db.scalar(select(func.count(QuestionScore.id)).where(QuestionScore.full_score.is_(None)))
    return {'schools_checked': len(schools), 'assignments_created': created, 'teachers_with_pending_references': pending,
            'question_losses_repaired': changed.rowcount, 'question_scores_needing_maxima': unknown}


async def main(apply):
    async with AsyncSessionLocal() as db:
        result = await repair(db)
        if apply:
            await db.commit()
        else:
            await db.rollback()
        print(json.dumps({'applied': apply, **result}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    asyncio.run(main(parser.parse_args().apply))
