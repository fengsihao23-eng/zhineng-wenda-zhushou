"""Synthetic browser fixture for an explicitly disposable, migrated QA database."""
import asyncio
from datetime import date, datetime, timedelta, timezone
import json
import sys
from uuid import uuid4

from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.db.models import (School, User, Role, UserRole, Student, ImportedClass, TeachingAssignment,
                           Exam, Subject, StudentExamScore, StudentSubjectScore, QuestionScore,
                           DiagnosisReport, StudentEntitlement, RiskEvent, KnowledgeDocument)
from sqlalchemy import select


async def main():
    # The caller supplies a one-run random credential through stdin, never a
    # repository default, command argument, log, or persisted fixture file.
    credential = sys.stdin.read().strip()
    if len(credential) < 24:
        raise RuntimeError("Synthetic credential required")
    async with AsyncSessionLocal() as db:
        school = School(id=uuid4(), name="QA 合成学校", code=f"QA-{uuid4()}")
        db.add(school)
        await db.flush()
        actors = {}
        roles = {}
        for code in ("STUDENT", "TEACHER", "SCHOOL_ADMIN", "CITY_OPERATOR"):
            role = await db.scalar(select(Role).where(Role.code == code))
            if not role:
                role = Role(id=uuid4(), code=code, name=code)
                db.add(role)
                await db.flush()
            roles[code] = role
        for key, code in (("student", "STUDENT"), ("basic", "STUDENT"), ("teacher", "TEACHER"), ("admin", "SCHOOL_ADMIN"), ("city", "CITY_OPERATOR"), ("unbound", "STUDENT")):
            user = User(id=uuid4(), school_id=school.id, username=f"qa-{key}-{uuid4()}", display_name=f"QA {key}", password_hash=get_password_hash(credential))
            db.add(user)
            await db.flush()
            db.add(UserRole(user_id=user.id, role_id=roles[code].id, school_id=school.id))
            actors[key] = user
        classroom = ImportedClass(id=uuid4(), school_id=school.id, external_class_id=str(uuid4()), name="QA 合成班级", source_system="QA")
        subject = Subject(id=uuid4(), school_id=school.id, code="QA_MATH", name="数学")
        exam = Exam(id=uuid4(), school_id=school.id, name="QA 合成考试", exam_type="QA", start_date=date(2026, 9, 17))
        db.add_all([classroom, subject, exam])
        await db.flush()
        student = Student(id=uuid4(), school_id=school.id, user_id=actors["student"].id, name="QA 合成学生", student_no="QA001", class_id=classroom.id)
        basic = Student(id=uuid4(), school_id=school.id, user_id=actors["basic"].id, name="QA 空数据学生", student_no="QA002")
        db.add_all([student, basic])
        await db.flush()
        now = datetime.now(timezone.utc)
        db.add(TeachingAssignment(school_id=school.id, teacher_user_id=actors["teacher"].id, class_id=classroom.id, subject_id=subject.id, starts_at=now-timedelta(days=1)))
        db.add(StudentExamScore(school_id=school.id, student_id=student.id, exam_id=exam.id, total_score=70, full_score=100))
        db.add(StudentSubjectScore(school_id=school.id, student_id=student.id, exam_id=exam.id, subject_id=subject.id, score=70, full_score=100))
        db.add(QuestionScore(school_id=school.id, student_id=student.id, exam_id=exam.id, subject_id=subject.id, question_no="1", score=3, full_score=5, lost_score=2))
        report = DiagnosisReport(id=uuid4(), school_id=school.id, student_id=student.id, exam_id=exam.id, subject_id=subject.id, report_type="QA", version="v1", generated_at=now, raw_content="QA 原始依据，仅为合成验收数据。", structured_json={"summary": "QA 正式报告合成摘要"})
        db.add(report)
        db.add(StudentEntitlement(school_id=school.id, student_id=student.id, product_code="DIAGNOSIS_REPORT", resource_type="report", resource_id=report.id, starts_at=now-timedelta(days=1)))
        risk = RiskEvent(id=uuid4(), school_id=school.id, student_id=student.id, event_type="learning", title="QA 待确认事件", detail="仅为合成测试，不代表真实风险")
        db.add(risk)
        await db.commit()
        print(json.dumps({"users": {key: value.username for key, value in actors.items()}, "school_id": str(school.id), "student_id": str(student.id), "report_id": str(report.id), "risk_id": str(risk.id)}))


asyncio.run(main())
