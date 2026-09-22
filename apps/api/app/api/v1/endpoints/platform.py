"""Student product APIs and role based operations workbenches."""
from datetime import datetime, timedelta, timezone
from math import isfinite
from secrets import token_urlsafe
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    AuthenticatedStudent,
    AuthenticatedUser,
    get_current_student,
    get_current_user,
    require_management,
)
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.access_scope import scoped as scope_query, scoped_scores, is_teacher_only
from app.core.diagnosis_access import authorized_reports, require_diagnosis, require_report, audit_report_access
from app.core.errors import ApiError
from app.core.idempotency import create_once
from app.core.platform_workflows import (
    edit_knowledge, knowledge_actions, transition_knowledge,
    transition_workflow, workflow_next_states,
)
from app.db.models.chat import ChatMessage, ChatSession
from app.db.models.diagnosis import DiagnosisReport
from app.db.models.exam import Exam, Subject
from app.db.models.platform import (
    HumanHandoff,
    KnowledgeDocument,
    ParentAuthorization,
    PlatformFeedback,
    RiskEvent,
)
from app.db.models.school import School
from app.db.models.score import QuestionScore, StudentExamScore, StudentSubjectScore
from app.db.models.student import Student

logger = get_logger(__name__)
router = APIRouter(prefix="/platform", tags=["platform"])
management_roles = require_management("TEACHER", "SCHOOL_ADMIN", "CITY_OPERATOR", "SUPER_ADMIN", "QA")
school_admin_roles = require_management("SCHOOL_ADMIN", "CITY_OPERATOR", "SUPER_ADMIN", "QA")
city_roles = require_management("CITY_OPERATOR", "SUPER_ADMIN")


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def _full_score(value: Any) -> float | None:
    """Unknown or invalid full scores must not become zero denominators."""
    try:
        full = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return full if isfinite(full) and full > 0 else None


def _percentage(score: Any, full_score: Any) -> float | None:
    """Return a finite percentage, or None when it cannot be calculated."""
    full = _full_score(full_score)
    if full is None:
        return None
    try:
        percentage = float(score) / full * 100
    except (TypeError, ValueError, OverflowError):
        return None
    return round(percentage, 1) if isfinite(percentage) else None


def _scoped(query, user: AuthenticatedUser, column):
    return scope_query(query, user, column)


def _student_scope(query, current: AuthenticatedStudent, school_column, student_column):
    return query.where(school_column == current.school_id, student_column == current.student_id)


class AuthorizationCreate(BaseModel):
    parent_name: str = Field(..., min_length=1, max_length=100)
    parent_phone: str = Field(..., min_length=6, max_length=40)
    scopes: list[str] = Field(default_factory=lambda: ["dashboard", "diagnosis", "feedback"])


class ParentApprove(BaseModel):
    share_code: str = Field(..., min_length=6, max_length=20)


class CreatePayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class PlatformFeedbackCreate(CreatePayload):
    rating: str = Field(..., pattern="^(helpful|not_helpful|data_wrong|inappropriate)$")
    category: str = Field(default="回答质量", max_length=50)
    note: str | None = Field(default=None, max_length=1000)
    message_id: UUID | None = None


class WorkflowStatusUpdate(BaseModel):
    status: str = Field(..., min_length=2, max_length=30)
    resolution: str | None = Field(default=None, max_length=1000)
    expected_version: int | None = Field(default=None, ge=1)


class RiskCreate(CreatePayload):
    student_id: UUID | None = None
    event_type: str = Field(default="learning", max_length=50)
    severity: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    title: str = Field(..., min_length=1, max_length=240)
    detail: str = Field(..., min_length=1, max_length=2000)
    source: str = Field(default="manual", max_length=80)


class KnowledgeCreate(CreatePayload):
    title: str = Field(..., min_length=1, max_length=240)
    subject: str = Field(default="通用", max_length=80)
    doc_type: str = Field(default="教学资料", max_length=40)
    content: str = Field(..., min_length=1)
    source_name: str = Field(..., min_length=1, max_length=200)
    source_url: str | None = Field(default=None, max_length=1000)
    source_reference: str = Field(..., min_length=1, max_length=500)
    tags: list[str] = Field(default_factory=list)

    @field_validator("source_url", mode="before")
    @classmethod
    def normalize_optional_source(cls, value):
        return value.strip() or None if isinstance(value, str) else value


class KnowledgeReview(BaseModel):
    action: str = Field(..., pattern="^(submit|approve|reject|publish|offline|republish)$")
    reason: str | None = Field(default=None, max_length=500)
    expected_version: int | None = Field(default=None, ge=1)


class KnowledgeEdit(KnowledgeCreate):
    expected_version: int | None = Field(default=None, ge=1)


class HandoffCreate(CreatePayload):
    reason: str = Field(..., min_length=1, max_length=500)
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")
    summary: str = Field(..., min_length=1, max_length=3000)
    session_id: UUID | None = None


@router.get("/student/dashboard")
async def student_dashboard(
    current: AuthenticatedStudent = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    logger.info(
        "student_dashboard_request",
        student_id=str(current.student_id),
        school_id=str(current.school_id),
    )
    scores_result = await db.execute(
        select(StudentExamScore, Exam)
        .join(Exam, Exam.id == StudentExamScore.exam_id)
        .where(StudentExamScore.school_id == current.school_id, StudentExamScore.student_id == current.student_id)
        .order_by(Exam.start_date.desc().nullslast(), Exam.created_at.desc(), Exam.id.desc())
        .limit(2)
    )
    scores = scores_result.all()
    latest = scores[0] if scores else None
    previous = scores[1] if len(scores) > 1 else None
    # The query above only fetches the latest two scores for the delta, not the total
    # number of exams. Count the full history separately.
    exam_total = await db.scalar(
        select(func.count(StudentExamScore.id)).where(
            StudentExamScore.school_id == current.school_id,
            StudentExamScore.student_id == current.student_id,
        )
    )
    subjects: list[dict[str, Any]] = []
    if latest:
        subjects_result = await db.execute(
            select(StudentSubjectScore, Subject)
            .join(Subject, Subject.id == StudentSubjectScore.subject_id)
            .where(
                StudentSubjectScore.school_id == current.school_id,
                StudentSubjectScore.student_id == current.student_id,
                StudentSubjectScore.exam_id == latest[0].exam_id,
            )
        )
        subjects = [
            {
                "name": subject.name,
                "score": float(item.score),
                "full_score": _full_score(item.full_score),
                "percentage": _percentage(item.score, item.full_score),
                "class_rank": item.class_rank,
                "grade_rank": item.grade_rank,
            }
            for item, subject in subjects_result.all()
        ]
        # 首页文案承诺按得分率排序；未知得分率排在最后。
        subjects.sort(key=lambda subject: (subject["percentage"] is None, -(subject["percentage"] or 0)))
    diagnosis_count = await db.scalar(select(func.count()).select_from(authorized_reports(current.school_id, current.student_id).subquery()))
    open_risks = await db.scalar(
        select(func.count(RiskEvent.id)).where(
            RiskEvent.school_id == current.school_id,
            RiskEvent.student_id == current.student_id,
            RiskEvent.status.in_(["open", "acknowledged"]),
        )
    )
    open_handoffs = await db.scalar(
        select(func.count(HumanHandoff.id)).where(
            HumanHandoff.school_id == current.school_id,
            HumanHandoff.student_id == current.student_id,
            HumanHandoff.status.in_(["open", "accepted"]),
        )
    )
    authorization = await db.scalar(
        select(ParentAuthorization)
        .where(
            ParentAuthorization.school_id == current.school_id,
            ParentAuthorization.student_id == current.student_id,
            ParentAuthorization.status.in_(["pending", "active"]),
        )
        .order_by(ParentAuthorization.created_at.desc())
        .limit(1)
    )
    latest_score = latest[0] if latest else None
    return {
        "student": {"id": str(current.student_id), "name": current.student_name},
        "latest_exam": {
            "id": str(latest[1].id),
            "name": latest[1].name,
            "date": _iso(latest[1].start_date),
            "total_score": float(latest_score.total_score),
            "full_score": _full_score(latest_score.full_score),
            "class_rank": latest_score.class_rank,
            "grade_rank": latest_score.grade_rank,
            "score_delta": round(float(latest_score.total_score) - float(previous[0].total_score), 1) if previous else None,
        } if latest else None,
        "subjects": subjects,
        "exam_count": int(exam_total or 0),
        "diagnosis_count": int(diagnosis_count or 0),
        "open_risks": int(open_risks or 0),
        "open_handoffs": int(open_handoffs or 0),
        "parent_authorization": _authorization_out(authorization) if authorization else None,
    }


@router.get("/student/trends")
async def student_trends(
    current: AuthenticatedStudent = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StudentExamScore, Exam)
        .join(Exam, Exam.id == StudentExamScore.exam_id)
        .where(StudentExamScore.school_id == current.school_id, StudentExamScore.student_id == current.student_id)
        .order_by(Exam.start_date.desc().nullslast(), Exam.created_at.desc(), Exam.id.desc())
        .limit(20)
    )
    # 先取最近 20 次，再恢复为时间升序，避免第 21 次之后的最新考试被排除。
    exam_rows = list(reversed(result.all()))
    subject_result = await db.execute(
        select(StudentSubjectScore, Subject, Exam)
        .join(Subject, Subject.id == StudentSubjectScore.subject_id)
        .join(Exam, Exam.id == StudentSubjectScore.exam_id)
        .where(
            StudentSubjectScore.school_id == current.school_id,
            StudentSubjectScore.student_id == current.student_id,
            StudentSubjectScore.exam_id.in_([exam.id for _, exam in exam_rows]),
        )
        .order_by(Exam.start_date.asc().nullsfirst(), Exam.created_at.asc(), Exam.id.asc(), Subject.name.asc())
    )
    subject_rows = subject_result.all()
    subject_names = list(dict.fromkeys(subject.name for _, subject, _ in subject_rows))
    return {
        "exams": [
            {"id": str(exam.id), "name": exam.name, "date": _iso(exam.start_date), "score": float(score.total_score), "full_score": _full_score(score.full_score), "class_rank": score.class_rank, "grade_rank": score.grade_rank}
            for score, exam in exam_rows
        ],
        "subjects": [
            {"subject": subject.name, "exam": exam.name, "date": _iso(exam.start_date), "score": float(score.score), "full_score": _full_score(score.full_score)}
            for score, subject, exam in subject_rows
        ],
        "subject_names": subject_names,
    }


@router.get("/student/diagnosis")
async def student_diagnosis(
    current: AuthenticatedStudent = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    await require_diagnosis(db, current)
    result = await db.execute(
        authorized_reports(current.school_id, current.student_id).add_columns(Exam)
        .outerjoin(Exam, (Exam.id == DiagnosisReport.exam_id) & (Exam.school_id == current.school_id))
        .order_by(DiagnosisReport.generated_at.desc())
        .limit(20)
    )
    rows = result.all()
    await audit_report_access(db, current, True)
    return [
        {
            "id": str(report.id),
            "type": report.report_type,
            "status": report.status,
            "version": report.version,
            "generated_at": _iso(report.generated_at),
            "exam_name": exam.name if exam else None,
            "content": report.structured_json or {},
            "source": report.source_system or "校内成绩系统",
            "has_source": bool(report.raw_content and report.raw_content.strip()),
        }
        for report, exam in rows
    ]


@router.get("/student/diagnosis/{report_id}/source")
async def student_diagnosis_source(
    report_id: UUID,
    current: AuthenticatedStudent = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    report = await require_report(db, current, report_id)
    if not report.raw_content or not report.raw_content.strip():
        raise ApiError(404, "REPORT_SOURCE_MISSING", "该版本尚未接入报告原始内容，不能以摘要代替原件。")
    exam = await db.scalar(select(Exam).where(Exam.id == report.exam_id, Exam.school_id == current.school_id)) if report.exam_id else None
    await audit_report_access(db, current, True, report.id)
    return {"id": str(report.id), "version": report.version, "raw_content": report.raw_content,
            "source": report.source_system, "generated_at": _iso(report.generated_at),
            "exam_name": exam.name if exam else None, "source_kind": "stored_text"}


@router.get("/student/mistakes")
async def student_mistakes(
    subject: str | None = None,
    current: AuthenticatedStudent = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(QuestionScore, Exam, Subject)
        .join(Exam, Exam.id == QuestionScore.exam_id)
        .join(Subject, Subject.id == QuestionScore.subject_id)
        .where(QuestionScore.school_id == current.school_id, QuestionScore.student_id == current.student_id, QuestionScore.lost_score > 0)
        .order_by(QuestionScore.lost_score.desc(), Exam.start_date.desc())
        .limit(100)
    )
    if subject:
        query = query.where(Subject.name == subject)
    result = await db.execute(query)
    return [
        {
            "id": str(item.id),
            "exam": exam.name,
            "subject": subject.name,
            "question_no": item.question_no,
            "score": float(item.score),
            "full_score": float(item.full_score),
            "lost_score": float(item.lost_score),
            "answer_status": item.answer_status,
            "knowledge_point_id": str(item.knowledge_point_id) if item.knowledge_point_id else None,
            "date": _iso(exam.start_date),
        }
        for item, exam, subject in result.all()
    ]


def _authorization_out(item: ParentAuthorization) -> dict[str, Any]:
    return {
        "id": str(item.id), "parent_name": item.parent_name, "parent_phone": item.parent_phone,
        "share_code": item.share_code, "scopes": item.scopes or [], "status": item.status,
        "expires_at": _iso(item.expires_at), "granted_at": _iso(item.granted_at),
    }


@router.get("/student/authorization")
async def get_student_authorization(
    current: AuthenticatedStudent = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ParentAuthorization)
        .where(ParentAuthorization.school_id == current.school_id, ParentAuthorization.student_id == current.student_id)
        .order_by(ParentAuthorization.created_at.desc())
        .limit(10)
    )
    return [_authorization_out(item) for item in result.scalars().all()]


@router.post("/student/authorization", status_code=status.HTTP_201_CREATED)
async def create_student_authorization(
    data: AuthorizationCreate,
    current: AuthenticatedStudent = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    item = ParentAuthorization(
        school_id=current.school_id,
        student_id=current.student_id,
        parent_name=data.parent_name,
        parent_phone=data.parent_phone,
        share_code=token_urlsafe(8).replace("-", "").replace("_", "")[:12].upper(),
        scopes=data.scopes,
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _authorization_out(item)


@router.delete("/student/authorization/{authorization_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_student_authorization(
    authorization_id: UUID,
    current: AuthenticatedStudent = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    item = await db.scalar(
        select(ParentAuthorization).where(
            ParentAuthorization.id == authorization_id,
            ParentAuthorization.school_id == current.school_id,
            ParentAuthorization.student_id == current.student_id,
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="授权记录不存在")
    item.status = "revoked"
    item.revoked_at = datetime.now(timezone.utc)
    await db.commit()


@router.post("/parent/authorizations/{authorization_id}/approve")
async def approve_parent_authorization(
    authorization_id: UUID,
    data: ParentApprove,
    db: AsyncSession = Depends(get_db),
):
    item = await db.scalar(select(ParentAuthorization).where(ParentAuthorization.id == authorization_id, ParentAuthorization.share_code == data.share_code))
    expires_at = item.expires_at.replace(tzinfo=timezone.utc) if item and item.expires_at and item.expires_at.tzinfo is None else (item.expires_at if item else None)
    if not item or item.status != "pending" or (expires_at and expires_at < datetime.now(timezone.utc)):
        raise HTTPException(status_code=400, detail="授权链接无效或已过期")
    item.status = "active"
    item.granted_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "active", "authorization_id": str(item.id), "scopes": item.scopes or []}


@router.post("/student/feedback", status_code=status.HTTP_201_CREATED)
async def create_student_feedback(
    data: PlatformFeedbackCreate,
    idempotency_key: UUID | None = Header(default=None),
    current: AuthenticatedStudent = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    if data.message_id:
        message = await db.scalar(
            select(ChatMessage)
            .join(ChatSession, ChatSession.id == ChatMessage.session_id)
            .where(ChatMessage.id == data.message_id, ChatSession.school_id == current.school_id, ChatSession.student_id == current.student_id)
        )
        if not message:
            raise HTTPException(status_code=404, detail="消息不存在")
    item = await create_once(db, current, "feedback", data.model_dump(), idempotency_key, PlatformFeedback,
                            dict(school_id=current.school_id, user_id=current.user_id, student_id=current.student_id, **data.model_dump()))
    return {"id": str(item.id), "status": item.status}


@router.post("/student/handoffs", status_code=status.HTTP_201_CREATED)
async def create_student_handoff(
    data: HandoffCreate,
    idempotency_key: UUID | None = Header(default=None),
    current: AuthenticatedStudent = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    if data.session_id:
        session = await db.scalar(select(ChatSession).where(
            ChatSession.id == data.session_id, ChatSession.school_id == current.school_id,
            ChatSession.student_id == current.student_id, ChatSession.status == "active",
        ))
        if session is None:
            raise ApiError(404, "SESSION_NOT_FOUND", "会话不存在或无权关联")
    item = await create_once(db, current, "handoff", data.model_dump(), idempotency_key, HumanHandoff,
                            dict(school_id=current.school_id, student_id=current.student_id, **data.model_dump()))
    return _handoff_out(item)


@router.get("/management/overview")
async def management_overview(
    current: AuthenticatedUser = Depends(management_roles),
    db: AsyncSession = Depends(get_db),
):
    student_query = _scoped(select(func.count(Student.id)), current, Student.school_id)
    school_query = _scoped(select(func.count(School.id)), current, School.id)
    risk_query = _scoped(select(func.count(RiskEvent.id)).where(RiskEvent.status.in_(["open", "acknowledged"])), current, RiskEvent.school_id)
    feedback_query = _scoped(select(func.count(PlatformFeedback.id)).where(PlatformFeedback.status == "open"), current, PlatformFeedback.school_id)
    handoff_query = _scoped(select(func.count(HumanHandoff.id)).where(HumanHandoff.status.in_(["open", "accepted"])), current, HumanHandoff.school_id)
    student_count = await db.scalar(student_query)
    school_count = await db.scalar(school_query)
    risk_count = await db.scalar(risk_query)
    feedback_count = await db.scalar(feedback_query)
    handoff_count = await db.scalar(handoff_query)
    return {
        "scope": "city" if current.has_role("CITY_OPERATOR") or current.has_role("SUPER_ADMIN") else "teaching" if is_teacher_only(current) else "school",
        "schools": int(school_count or 0), "students": int(student_count or 0),
        "open_risks": int(risk_count or 0), "open_feedback": int(feedback_count or 0),
        "open_handoffs": int(handoff_count or 0),
    }


@router.get("/management/students")
async def management_students(
    current: AuthenticatedUser = Depends(management_roles),
    db: AsyncSession = Depends(get_db),
):
    # 优化：使用单次查询 + 聚合避免 N+1
    # 1. JOIN 一次获取学生及学校信息。
    students_query = _scoped(
        select(Student, School)
        .join(School, School.id == Student.school_id)
        .where(Student.status == "active"),
        current,
        Student.school_id,
    ).order_by(Student.name.asc())
    students = (await db.execute(students_query)).all()

    if not students:
        return []

    student_ids = [student.id for student, _ in students]

    # 2. 批量获取最新成绩（使用窗口函数或子查询，避免 N+1）
    latest_scores_subquery = (
        select(
            StudentExamScore.student_id,
            StudentExamScore.exam_id,
            StudentExamScore.total_score,
            func.row_number()
            .over(
                partition_by=StudentExamScore.student_id,
                order_by=(Exam.start_date.desc().nullslast(), Exam.created_at.desc(), Exam.id.desc()),
            )
            .label("rn"),
        )
        .join(Exam, Exam.id == StudentExamScore.exam_id)
        .where(StudentExamScore.student_id.in_(student_ids), not is_teacher_only(current))
        .subquery()
    )

    scores_query = (
        select(latest_scores_subquery.c.student_id, latest_scores_subquery.c.total_score, Exam.name)
        .join(Exam, Exam.id == latest_scores_subquery.c.exam_id)
        .where(latest_scores_subquery.c.rn == 1)
    )
    score_by_student = {
        student_id: (float(total_score), exam_name)
        for student_id, total_score, exam_name in (await db.execute(scores_query)).all()
    }
    # Total scores include non-taught subjects. A subject teacher gets only
    # explicitly granted subject rows, never a recomputed pseudo-total.
    subject_by_student: dict[UUID, list[dict]] = {}
    if is_teacher_only(current):
        score_by_student = {}
        subject_rows = await db.execute(scoped_scores(
            select(StudentSubjectScore, Subject, Exam)
            .join(Subject, Subject.id == StudentSubjectScore.subject_id)
            .join(Exam, Exam.id == StudentSubjectScore.exam_id)
            .where(StudentSubjectScore.student_id.in_(student_ids))
            .order_by(Exam.start_date.desc().nullslast(), Exam.created_at.desc()),
            current, StudentSubjectScore,
        ))
        seen = set()
        for score, subject, exam in subject_rows:
            key = (score.student_id, score.subject_id)
            if key in seen:
                continue
            seen.add(key)
            subject_by_student.setdefault(score.student_id, []).append({"subject": subject.name, "score": float(score.score), "exam": exam.name})

    # 3. 批量获取风险计数（单次聚合查询）
    risks_query = (
        select(RiskEvent.student_id, func.count(RiskEvent.id))
        .where(
            RiskEvent.student_id.in_(student_ids),
            RiskEvent.status.in_(["open", "acknowledged"]),
        )
        .group_by(RiskEvent.student_id)
    )
    risk_by_student = {
        student_id: count for student_id, count in (await db.execute(risks_query)).all() if student_id
    }

    # 4. 组装结果（无额外查询）
    return [
        {
            "id": str(student.id),
            "name": student.name,
            "student_no": student.student_no,
            "school": school.name,
            "school_id": str(student.school_id),
            "latest_score": score_by_student[student.id][0] if student.id in score_by_student else None,
            "latest_exam": score_by_student[student.id][1] if student.id in score_by_student else None,
            "subject_scores": subject_by_student.get(student.id, []),
            "score_scope": "teaching_subjects" if is_teacher_only(current) else "all_subjects",
            "open_risks": int(risk_by_student.get(student.id, 0)),
        }
        for student, school in students
    ]


@router.get("/management/schools")
async def management_schools(
    current: AuthenticatedUser = Depends(city_roles),
    db: AsyncSession = Depends(get_db),
):
    # 优化：使用批量聚合避免 N+1 查询
    schools_result = await db.execute(select(School).order_by(School.name.asc()))
    schools = schools_result.scalars().all()

    if not schools:
        return []

    school_ids = [school.id for school in schools]

    # 批量获取学生数
    student_counts_query = (
        select(Student.school_id, func.count(Student.id))
        .where(Student.school_id.in_(school_ids), Student.status == "active")
        .group_by(Student.school_id)
    )
    student_counts = {
        school_id: count for school_id, count in (await db.execute(student_counts_query)).all()
    }

    # 批量获取风险数
    risk_counts_query = (
        select(RiskEvent.school_id, func.count(RiskEvent.id))
        .where(RiskEvent.school_id.in_(school_ids), RiskEvent.status.in_(["open", "acknowledged"]))
        .group_by(RiskEvent.school_id)
    )
    risk_counts = {
        school_id: count for school_id, count in (await db.execute(risk_counts_query)).all()
    }

    return [
        {
            "id": str(school.id),
            "name": school.name,
            "code": school.code,
            "status": school.status,
            "students": int(student_counts.get(school.id, 0)),
            "open_risks": int(risk_counts.get(school.id, 0)),
        }
        for school in schools
    ]


def _feedback_out(item: PlatformFeedback) -> dict[str, Any]:
    return {"id": str(item.id), "rating": item.rating, "category": item.category, "note": item.note, "status": item.status, "school_id": str(item.school_id), "student_id": str(item.student_id) if item.student_id else None, "created_at": _iso(item.created_at), "resolution": item.resolution, "resolved_at": _iso(item.resolved_at), "state_version": item.state_version, "allowed_transitions": workflow_next_states("feedback", item.status)}


@router.get("/student/feedback")
async def student_feedback(current: AuthenticatedStudent = Depends(get_current_student), db: AsyncSession = Depends(get_db)):
    items = (await db.execute(select(PlatformFeedback).where(
        PlatformFeedback.school_id == current.school_id, PlatformFeedback.student_id == current.student_id,
        PlatformFeedback.user_id == current.user_id,
    ).order_by(PlatformFeedback.created_at.desc()).limit(100))).scalars().all()
    return [{"id": str(item.id), "status": item.status, "category": item.category, "note": item.note,
             "resolution": item.resolution, "created_at": _iso(item.created_at)} for item in items]


@router.get("/student/handoffs")
async def student_handoffs(current: AuthenticatedStudent = Depends(get_current_student), db: AsyncSession = Depends(get_db)):
    items = (await db.execute(select(HumanHandoff).where(
        HumanHandoff.school_id == current.school_id, HumanHandoff.student_id == current.student_id,
    ).order_by(HumanHandoff.created_at.desc()).limit(100))).scalars().all()
    return [{"id": str(item.id), "status": item.status, "reason": item.reason, "resolution": item.resolution,
             "assigned": item.assigned_to is not None, "created_at": _iso(item.created_at)} for item in items]


@router.get("/management/feedback")
async def management_feedback(
    state: str | None = Query(default=None, alias="status"),
    current: AuthenticatedUser = Depends(management_roles),
    db: AsyncSession = Depends(get_db),
):
    query = _scoped(select(PlatformFeedback), current, PlatformFeedback.school_id).order_by(PlatformFeedback.created_at.desc()).limit(200)
    if state:
        query = query.where(PlatformFeedback.status == state)
    return [_feedback_out(item) for item in (await db.execute(query)).scalars().all()]


@router.patch("/management/feedback/{feedback_id}")
async def update_management_feedback(
    feedback_id: UUID,
    data: WorkflowStatusUpdate,
    current: AuthenticatedUser = Depends(management_roles),
    db: AsyncSession = Depends(get_db),
):
    item = await db.scalar(_scoped(select(PlatformFeedback).where(PlatformFeedback.id == feedback_id), current, PlatformFeedback.school_id))
    if not item:
        raise HTTPException(status_code=404, detail="反馈不存在")
    await transition_workflow(db, item, current, "feedback", data.status, data.resolution, data.expected_version)
    return _feedback_out(item)


def _risk_out(item: RiskEvent) -> dict[str, Any]:
    return {"id": str(item.id), "student_id": str(item.student_id) if item.student_id else None, "event_type": item.event_type, "severity": item.severity, "title": item.title, "detail": item.detail, "source": item.source, "status": item.status, "created_at": _iso(item.created_at), "resolved_at": _iso(item.resolved_at), "resolution": item.resolution, "state_version": item.state_version, "allowed_transitions": workflow_next_states("risk", item.status)}


@router.get("/management/risks")
async def management_risks(
    state: str | None = Query(default=None, alias="status"),
    current: AuthenticatedUser = Depends(management_roles),
    db: AsyncSession = Depends(get_db),
):
    query = _scoped(select(RiskEvent), current, RiskEvent.school_id).order_by(RiskEvent.created_at.desc()).limit(300)
    if state:
        query = query.where(RiskEvent.status == state)
    return [_risk_out(item) for item in (await db.execute(query)).scalars().all()]


@router.post("/management/risks", status_code=status.HTTP_201_CREATED)
async def create_management_risk(
    data: RiskCreate,
    idempotency_key: UUID | None = Header(default=None),
    current: AuthenticatedUser = Depends(management_roles),
    db: AsyncSession = Depends(get_db),
):
    if data.student_id:
        student = await db.scalar(_scoped(select(Student).where(
            Student.id == data.student_id, Student.school_id == current.school_id, Student.status == "active",
        ), current, Student.school_id))
        if student is None:
            raise ApiError(404, "STUDENT_NOT_FOUND", "学生不存在或无权关联")
    elif is_teacher_only(current):
        raise ApiError(403, "STUDENT_SCOPE_REQUIRED", "教师须选择任教班级内的学生，不能创建全校事件")
    item = await create_once(db, current, "risk", data.model_dump(), idempotency_key, RiskEvent,
                            dict(school_id=current.school_id, **data.model_dump()))
    return _risk_out(item)


@router.patch("/management/risks/{risk_id}")
async def update_management_risk(
    risk_id: UUID,
    data: WorkflowStatusUpdate,
    current: AuthenticatedUser = Depends(management_roles),
    db: AsyncSession = Depends(get_db),
):
    item = await db.scalar(_scoped(select(RiskEvent).where(RiskEvent.id == risk_id), current, RiskEvent.school_id))
    if not item:
        raise HTTPException(status_code=404, detail="风险事件不存在")
    await transition_workflow(db, item, current, "risk", data.status, data.resolution, data.expected_version)
    return _risk_out(item)


def _handoff_out(item: HumanHandoff) -> dict[str, Any]:
    return {"id": str(item.id), "student_id": str(item.student_id), "reason": item.reason, "priority": item.priority, "summary": item.summary, "status": item.status, "assigned_to": str(item.assigned_to) if item.assigned_to else None, "created_at": _iso(item.created_at), "accepted_at": _iso(item.accepted_at), "resolved_at": _iso(item.resolved_at), "resolution": item.resolution, "state_version": item.state_version, "allowed_transitions": workflow_next_states("handoff", item.status)}


@router.get("/management/handoffs")
async def management_handoffs(
    state: str | None = Query(default=None, alias="status"),
    current: AuthenticatedUser = Depends(management_roles),
    db: AsyncSession = Depends(get_db),
):
    query = _scoped(select(HumanHandoff), current, HumanHandoff.school_id).order_by(HumanHandoff.created_at.desc()).limit(200)
    if state:
        query = query.where(HumanHandoff.status == state)
    return [_handoff_out(item) for item in (await db.execute(query)).scalars().all()]


@router.patch("/management/handoffs/{handoff_id}")
async def update_management_handoff(
    handoff_id: UUID,
    data: WorkflowStatusUpdate,
    current: AuthenticatedUser = Depends(management_roles),
    db: AsyncSession = Depends(get_db),
):
    item = await db.scalar(_scoped(select(HumanHandoff).where(HumanHandoff.id == handoff_id), current, HumanHandoff.school_id))
    if not item:
        raise HTTPException(status_code=404, detail="转接工单不存在")
    await transition_workflow(db, item, current, "handoff", data.status, data.resolution, data.expected_version)
    return _handoff_out(item)


def _knowledge_out(item: KnowledgeDocument) -> dict[str, Any]:
    return {"id": str(item.id), "title": item.title, "subject": item.subject, "doc_type": item.doc_type, "status": item.status, "version": item.version, "content": item.content, "source_name": item.source_name, "source_url": item.source_url, "source_reference": item.source_reference, "tags": item.tags or [], "rejection_reason": item.rejection_reason, "created_at": _iso(item.created_at), "reviewed_at": _iso(item.reviewed_at), "published_at": _iso(item.published_at), "offlined_at": _iso(item.offlined_at), "state_version": item.state_version, "allowed_actions": knowledge_actions(item.status)}


@router.get("/management/knowledge")
async def management_knowledge(
    state: str | None = Query(default=None, alias="status"),
    current: AuthenticatedUser = Depends(management_roles),
    db: AsyncSession = Depends(get_db),
):
    query = _scoped(select(KnowledgeDocument), current, KnowledgeDocument.school_id).order_by(KnowledgeDocument.updated_at.desc()).limit(300)
    if state:
        query = query.where(KnowledgeDocument.status == state)
    return [_knowledge_out(item) for item in (await db.execute(query)).scalars().all()]


@router.post("/management/knowledge", status_code=status.HTTP_201_CREATED)
async def create_knowledge(
    data: KnowledgeCreate,
    idempotency_key: UUID | None = Header(default=None),
    current: AuthenticatedUser = Depends(school_admin_roles),
    db: AsyncSession = Depends(get_db),
):
    item = await create_once(db, current, "knowledge", data.model_dump(), idempotency_key, KnowledgeDocument,
                            dict(school_id=current.school_id, created_by=current.user_id, **data.model_dump()))
    return _knowledge_out(item)


@router.post("/management/knowledge/{document_id}/review")
async def review_knowledge(
    document_id: UUID,
    data: KnowledgeReview,
    current: AuthenticatedUser = Depends(school_admin_roles),
    db: AsyncSession = Depends(get_db),
):
    item = await db.scalar(_scoped(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id), current, KnowledgeDocument.school_id))
    if not item:
        raise HTTPException(status_code=404, detail="知识文档不存在")
    await transition_knowledge(db, item, current, data.action, data.reason, data.expected_version)
    return _knowledge_out(item)


@router.patch("/management/knowledge/{document_id}")
async def update_knowledge(
    document_id: UUID,
    data: KnowledgeEdit,
    current: AuthenticatedUser = Depends(school_admin_roles),
    db: AsyncSession = Depends(get_db),
):
    item = await db.scalar(_scoped(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id), current, KnowledgeDocument.school_id))
    if not item:
        raise HTTPException(status_code=404, detail="知识文档不存在")
    await edit_knowledge(db, item, current, data.model_dump(exclude={"expected_version"}), data.expected_version)
    return _knowledge_out(item)
