"""Read-only teaching/student and city/school drill-downs."""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthenticatedUser, require_management
from app.core.access_scope import scoped, scoped_scores, is_teacher_only
from app.core.database import get_db
from app.core.errors import ApiError
from app.db.models.exam import Exam, Subject
from app.db.models.platform import HumanHandoff, PlatformFeedback, RiskEvent
from app.db.models.school import School
from app.db.models.score import QuestionScore, StudentExamScore, StudentSubjectScore
from app.db.models.student import Student
from app.db.models.trace import AuditLog

router = APIRouter(prefix="/platform/management", tags=["platform"])
management = require_management("TEACHER", "SCHOOL_ADMIN", "QA", "CITY_OPERATOR", "SUPER_ADMIN")
city = require_management("CITY_OPERATOR", "SUPER_ADMIN")


@router.get("/students/{student_id}")
async def student_detail(student_id: UUID, current: AuthenticatedUser = Depends(management), db: AsyncSession = Depends(get_db)):
    student = await db.scalar(scoped(select(Student).where(Student.id == student_id, Student.status == "active"), current, Student.school_id))
    if student is None:
        raise ApiError(404, "STUDENT_NOT_FOUND", "学生不存在或不在授权任教范围")
    scores = (await db.execute(scoped_scores(
        select(StudentSubjectScore, Subject, Exam)
        .join(Subject, Subject.id == StudentSubjectScore.subject_id)
        .join(Exam, Exam.id == StudentSubjectScore.exam_id)
        .where(StudentSubjectScore.student_id == student_id, StudentSubjectScore.school_id == student.school_id)
        .order_by(Exam.start_date.desc().nullslast(), Subject.name).limit(200), current, StudentSubjectScore,
    ))).all()
    questions = (await db.execute(scoped_scores(
        select(QuestionScore, Subject, Exam)
        .join(Subject, Subject.id == QuestionScore.subject_id).join(Exam, Exam.id == QuestionScore.exam_id)
        .where(QuestionScore.student_id == student_id, QuestionScore.school_id == student.school_id, QuestionScore.lost_score > 0)
        .order_by(QuestionScore.lost_score.desc()).limit(100), current, QuestionScore,
    ))).all()
    totals = []
    if not is_teacher_only(current):
        totals = (await db.execute(select(StudentExamScore, Exam).join(Exam, Exam.id == StudentExamScore.exam_id)
                  .where(StudentExamScore.school_id == student.school_id, StudentExamScore.student_id == student_id)
                  .order_by(Exam.start_date.desc().nullslast()).limit(20))).all()
    db.add(AuditLog(action="student.learning.read", actor_type="management", actor_id=current.user_id,
                    resource_type="student", resource_id=student_id, allowed=True,
                    extra_data={"school_id": str(student.school_id), "scope": "teaching" if is_teacher_only(current) else "school"}))
    await db.commit()
    return {
        "student": {"id": str(student.id), "name": student.name, "student_no": student.student_no},
        "scope": "teaching_subjects" if is_teacher_only(current) else "all_subjects",
        "subject_scores": [{"exam": exam.name, "subject": subject.name, "score": float(score.score), "full_score": float(score.full_score),
                            "class_rank": score.class_rank, "date": exam.start_date.isoformat() if exam.start_date else None}
                           for score, subject, exam in scores],
        "exam_scores": [{"exam": exam.name, "score": float(score.total_score)} for score, exam in totals],
        "question_losses": [{"exam": exam.name, "subject": subject.name, "question_no": score.question_no,
                             "lost_score": float(score.lost_score)} for score, subject, exam in questions],
    }


@router.get("/schools/{school_id}")
async def school_detail(school_id: UUID, current: AuthenticatedUser = Depends(city), db: AsyncSession = Depends(get_db)):
    school = await db.scalar(select(School).where(School.id == school_id))
    if school is None:
        raise ApiError(404, "SCHOOL_NOT_FOUND", "学校不存在")
    counts = {}
    for key, model, condition in (
        ("students", Student, Student.status == "active"),
        ("open_risks", RiskEvent, RiskEvent.status.in_(["open", "acknowledged"])),
        ("open_feedback", PlatformFeedback, PlatformFeedback.status == "open"),
        ("open_handoffs", HumanHandoff, HumanHandoff.status.in_(["open", "accepted"])),
    ):
        counts[key] = int(await db.scalar(select(func.count(model.id)).where(model.school_id == school_id, condition)) or 0)
    db.add(AuditLog(action="school.operations.read", actor_type="management", actor_id=current.user_id,
                    resource_type="school", resource_id=school_id, allowed=True))
    await db.commit()
    return {"id": str(school.id), "name": school.name, "code": school.code, "status": school.status,
            **counts, "active_7d": None, "activity_note": "尚未建设学校活跃度统计，不能以学生总数代替。"}
