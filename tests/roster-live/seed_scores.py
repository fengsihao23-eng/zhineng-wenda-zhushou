"""Seed explicit synthetic evidence in the test school only, for live-model QA."""
import asyncio
import json
import os
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4
from sqlalchemy import select
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.db.models import School, User, Student, Subject, Exam, ExamSubject, StudentExamScore, StudentSubjectScore, QuestionScore

ROOT=Path(__file__).resolve().parents[2]
PRIVATE=ROOT/'.local/yjyz-roster'


async def main():
    if settings.DATABASE_URL != 'postgresql+asyncpg://qa_education@127.0.0.1:55449/yjyz_roster_20260922':
        raise RuntimeError('Dedicated isolated database required')
    fixture=json.loads((PRIVATE/'acceptance-fixture.json').read_text())
    school_id=UUID(fixture['sandbox']['school_id'])
    async with AsyncSessionLocal() as db:
        school=await db.get(School,school_id)
        if not school.code.startswith('QA-YJYZ-'):
            raise RuntimeError('Synthetic school required')
        student=await db.scalar(select(Student).join(User,User.id==Student.user_id).where(Student.school_id==school_id,User.username==fixture['students'][0]['账号']))
        subject=await db.scalar(select(Subject).where(Subject.school_id==school_id,Subject.name=='数学'))
        exam=Exam(id=uuid4(),school_id=school_id,name='联调合成数学测验',exam_type='QA',start_date=date(2026,9,22),source_system='QA')
        db.add(exam);await db.flush()
        db.add_all([
            ExamSubject(exam_id=exam.id,subject_id=subject.id,full_score=100),
            StudentExamScore(school_id=school_id,student_id=student.id,exam_id=exam.id,total_score=83,full_score=100),
            StudentSubjectScore(school_id=school_id,student_id=student.id,exam_id=exam.id,subject_id=subject.id,score=83,full_score=100),
            QuestionScore(school_id=school_id,student_id=student.id,exam_id=exam.id,subject_id=subject.id,question_no='1',score=3,full_score=5,lost_score=2),
        ])
        await db.commit()
        result={'school_id':str(school_id),'student_id':str(student.id),'exam_id':str(exam.id),'subject_id':str(subject.id),'score':83,'full_score':100,'question_1_lost_score':2}
    with os.fdopen(os.open(PRIVATE/'score-state.json',os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w') as handle:
        json.dump(result,handle)
    print('Synthetic evidence ready; no real student records or teacher profiles sent to the model.')


if __name__=='__main__':asyncio.run(main())
