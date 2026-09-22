"""Add only synthetic education evidence to the isolated browser fixture."""
import asyncio
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.db.models import School, Student, Subject, ExamSubject, QuestionScore
from app.db.models.education import Question, QuestionVersion


async def main():
    if (
        settings.DATABASE_URL
        != "postgresql+asyncpg://qa_education@127.0.0.1:55449/qa_education"
    ):
        raise RuntimeError("Refusing non-disposable database")
    fixture = json.loads(sys.stdin.read())
    scratch = Path(sys.argv[1])
    image = Image.new("RGB", (900, 1100), "white")
    draw = ImageDraw.Draw(image)
    draw.text(
        (100, 100),
        "Question 1: 2 + 2 = ?",
        font=ImageFont.load_default(size=44),
        fill="black",
    )
    image.save(scratch / "paper.png")
    second = Image.new("RGB", (900, 1100), "white")
    ImageDraw.Draw(second).text(
        (100, 100),
        "Question 2: 3 + 3 = ?",
        font=ImageFont.load_default(size=44),
        fill="black",
    )
    image.save(scratch / "paper-two-pages.pdf", save_all=True, append_images=[second])
    async with AsyncSessionLocal() as db:
        school = await db.get(School, UUID(fixture["school_id"]))
        if not school.code.startswith("QA-"):
            raise RuntimeError("Synthetic school required")
        student = await db.get(Student, UUID(fixture["student_id"]))
        student.external_student_id = "qa-evidence-student"
        subject = await db.scalar(select(Subject).where(Subject.school_id == school.id))
        subject.external_subject_id = "qa-math"
        subject.source_system = "native"
        score = await db.scalar(
            select(QuestionScore).where(
                QuestionScore.school_id == school.id,
                QuestionScore.student_id == student.id,
            )
        )
        db.add(
            ExamSubject(exam_id=score.exam_id, subject_id=subject.id, full_score=100)
        )
        question = Question(
            id=uuid4(),
            school_id=school.id,
            subject_id=subject.id,
            kind="standalone",
            title="QA 复习原题",
            status="published",
            source_system="native",
        )
        db.add(question)
        await db.flush()
        version = QuestionVersion(
            id=uuid4(),
            school_id=school.id,
            question_id=question.id,
            number=1,
            stem="合成题目：2 + 2 = ?",
            answer="4",
            explanation="把两组各两个合并。",
            published_at=datetime.now(timezone.utc),
        )
        db.add(version)
        await db.flush()
        score.question_id, score.question_version_id = question.id, version.id
        await db.commit()
        fixture.update(
            school_code=school.code,
            subject_id=str(subject.id),
            exam_id=str(score.exam_id),
            question_id=str(question.id),
            score_id=str(score.id),
            paper_path=str(scratch / "paper.png"),
            pdf_path=str(scratch / "paper-two-pages.pdf"),
        )
    print(json.dumps(fixture))


asyncio.run(main())
