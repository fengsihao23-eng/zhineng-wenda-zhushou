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
from app.db.models import School, Student, Subject, ExamSubject, QuestionScore, ImportedClass
from app.services.roster_excel import TEACHER_COLUMNS, STUDENT_COLUMNS, workbook_bytes
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
    suffix = uuid4().hex[:10]
    fixture["roster_accounts"] = {key: f"roster-{key}-{suffix}" for key in ("old", "keep", "skip", "student", "change", "changed")}
    files = {
        "teacher-invalid": (TEACHER_COLUMNS, [{"教师账号": "", "教师姓名": "", "状态": "离职"}]),
        "teacher-old": (TEACHER_COLUMNS, [{"教师账号": fixture["roster_accounts"]["old"], "教师姓名": "QA 流程教师", "状态": "正常", "任课年级班级": "数学:99.1;", "手机号码": "131****7000"}]),
        "teacher-suspects": (TEACHER_COLUMNS, [{"教师账号": fixture["roster_accounts"][key], "教师姓名": "QA 流程教师", "状态": "正常", "任课年级班级": "数学:99.2;"} for key in ("keep", "skip")]),
        "student-roster": (STUDENT_COLUMNS, [{"账号": fixture["roster_accounts"]["student"], "姓名": "QA 流程学生", "年级（1-12）": "高中一年级", "班级号": "1班"}]),
        "teacher-change-before": (TEACHER_COLUMNS, [{"教师账号": fixture["roster_accounts"]["change"], "教师姓名": "QA 变更教师", "状态": "正常", "任课年级班级": "数学:10.1;"}]),
        "teacher-change-after": (TEACHER_COLUMNS, [{"教师账号": fixture["roster_accounts"]["changed"], "教师姓名": "QA 变更教师", "状态": "正常", "任课年级班级": ""}]),
        "student-login-shared": (STUDENT_COLUMNS, [{"账号": fixture["users"]["teacher"], "姓名": "QA 同名学生", "年级（1-12）": "高中一年级", "班级号": "1班"}]),
    }
    fixture["roster_files"] = {}
    for key, (columns, rows) in files.items():
        path = scratch / f"{key}.xlsx"
        path.write_bytes(workbook_bytes(columns, [[row.get(c, "") for c in columns] for row in rows]))
        fixture["roster_files"][key] = str(path)
    async with AsyncSessionLocal() as db:
        school = await db.get(School, UUID(fixture["school_id"]))
        if not school.code.startswith("QA-"):
            raise RuntimeError("Synthetic school required")
        db.add(ImportedClass(id=uuid4(), school_id=school.id, external_class_id="10.1", name="高中一年级1班", source_system="native"))
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
