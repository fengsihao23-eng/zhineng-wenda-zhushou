"""Student product APIs and role based operations workbenches."""
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
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

router = APIRouter(prefix="/platform", tags=["platform"])
management_roles = require_management("TEACHER", "SCHOOL_ADMIN", "CITY_OPERATOR", "SUPER_ADMIN", "QA")
school_admin_roles = require_management("SCHOOL_ADMIN", "CITY_OPERATOR", "SUPER_ADMIN", "QA")
city_roles = require_management("CITY_OPERATOR", "SUPER_ADMIN")


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def _scoped(query, user: AuthenticatedUser, column):
    if not (user.has_role("CITY_OPERATOR") or user.has_role("SUPER_ADMIN")):
        return query.where(column == user.school_id)
    return query


def _student_scope(query, current: AuthenticatedStudent, school_column, student_column):
    return query.where(school_column == current.school_id, student_column == current.student_id)


class AuthorizationCreate(BaseModel):
    parent_name: str = Field(..., min_length=1, max_length=100)
    parent_phone: str = Field(..., min_length=6, max_length=40)
    scopes: list[str] = Field(default_factory=lambda: ["dashboard", "diagnosis", "feedback"])


class ParentApprove(BaseModel):
    share_code: str = Field(..., min_length=6, max_length=20)


class PlatformFeedbackCreate(BaseModel):
    rating: str = Field(..., pattern="^(helpful|not_helpful|data_wrong|inappropriate)$")
    category: str = Field(default="回答质量", max_length=50)
    note: str | None = Field(default=None, max_length=1000)
    message_id: UUID | None = None


class WorkflowStatusUpdate(BaseModel):
    status: str = Field(..., min_length=2, max_length=30)
    resolution: str | None = Field(default=None, max_length=1000)


class RiskCreate(BaseModel):
    student_id: UUID | None = None
    event_type: str = Field(default="learning", max_length=50)
    severity: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    title: str = Field(..., min_length=1, max_length=240)
    detail: str = Field(..., min_length=1, max_length=2000)
    source: str = Field(default="manual", max_length=80)


class KnowledgeCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=240)
    subject: str = Field(default="通用", max_length=80)
    doc_type: str = Field(default="教学资料", max_length=40)
    content: str = Field(..., min_length=1)
    source_name: str = Field(..., min_length=1, max_length=200)
    source_url: str | None = Field(default=None, max_length=1000)
    source_reference: str = Field(..., min_length=1, max_length=500)
    tags: list[str] = Field(default_factory=list)


class KnowledgeReview(BaseModel):
    action: str = Field(..., pattern="^(submit|approve|reject|publish|offline|republish)$")
    reason: str | None = Field(default=None, max_length=500)


class HandoffCreate(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")
    summary: str = Field(..., min_length=1, max_length=3000)
    session_id: UUID | None = None


@router.get("/student/dashboard")
async def student_dashboard(
    current: AuthenticatedStudent = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    scores_result = await db.execute(
        select(StudentExamScore, Exam)
        .join(Exam, Exam.id == StudentExamScore.exam_id)
        .where(StudentExamScore.school_id == current.school_id, StudentExamScore.student_id == current.student_id)
        .order_by(Exam.start_date.desc(), Exam.created_at.desc())
        .limit(6)
    )
    scores = scores_result.all()
    latest = scores[0] if scores else None
    previous = scores[1] if len(scores) > 1 else None
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
            .order_by(StudentSubjectScore.score.desc())
        )
        subjects = [
            {
                "name": subject.name,
                "score": float(item.score),
                "full_score": float(item.full_score),
                "percentage": round(float(item.score) / float(item.full_score) * 100, 1),
                "class_rank": item.class_rank,
                "grade_rank": item.grade_rank,
            }
            for item, subject in subjects_result.all()
        ]
    diagnosis_count = await db.scalar(
        select(func.count(DiagnosisReport.id)).where(
            DiagnosisReport.school_id == current.school_id,
            DiagnosisReport.student_id == current.student_id,
            DiagnosisReport.status == "generated",
        )
    )
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
            "full_score": float(latest_score.full_score or 0),
            "class_rank": latest_score.class_rank,
            "grade_rank": latest_score.grade_rank,
            "score_delta": round(float(latest_score.total_score) - float(previous[0].total_score), 1) if previous else None,
        } if latest else None,
        "subjects": subjects,
        "exam_count": len(scores),
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
        .order_by(Exam.start_date.asc(), Exam.created_at.asc())
        .limit(20)
    )
    exam_rows = result.all()
    subject_result = await db.execute(
        select(StudentSubjectScore, Subject, Exam)
        .join(Subject, Subject.id == StudentSubjectScore.subject_id)
        .join(Exam, Exam.id == StudentSubjectScore.exam_id)
        .where(StudentSubjectScore.school_id == current.school_id, StudentSubjectScore.student_id == current.student_id)
        .order_by(Exam.start_date.asc(), Subject.name.asc())
        .limit(200)
    )
    subject_rows = subject_result.all()
    subject_names = list(dict.fromkeys(subject.name for _, subject, _ in subject_rows))
    return {
        "exams": [
            {"id": str(exam.id), "name": exam.name, "date": _iso(exam.start_date), "score": float(score.total_score), "full_score": float(score.full_score or 0), "class_rank": score.class_rank, "grade_rank": score.grade_rank}
            for score, exam in exam_rows
        ],
        "subjects": [
            {"subject": subject.name, "exam": exam.name, "date": _iso(exam.start_date), "score": float(score.score), "full_score": float(score.full_score)}
            for score, subject, exam in subject_rows
        ],
        "subject_names": subject_names,
    }


@router.get("/student/diagnosis")
async def student_diagnosis(
    current: AuthenticatedStudent = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DiagnosisReport, Exam)
        .outerjoin(Exam, Exam.id == DiagnosisReport.exam_id)
        .where(DiagnosisReport.school_id == current.school_id, DiagnosisReport.student_id == current.student_id)
        .order_by(DiagnosisReport.generated_at.desc())
        .limit(20)
    )
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
        }
        for report, exam in result.all()
    ]


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
        .where(QuestionScore.school_id == current.school_id, QuestionScore.student_id == current.student_id)
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
    item = PlatformFeedback(
        school_id=current.school_id, user_id=current.user_id, student_id=current.student_id,
        message_id=data.message_id, rating=data.rating, category=data.category, note=data.note,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return {"id": str(item.id), "status": item.status}


@router.post("/student/handoffs", status_code=status.HTTP_201_CREATED)
async def create_student_handoff(
    data: HandoffCreate,
    current: AuthenticatedStudent = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    item = HumanHandoff(
        school_id=current.school_id, student_id=current.student_id, session_id=data.session_id,
        reason=data.reason, priority=data.priority, summary=data.summary,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
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
        "scope": "city" if current.has_role("CITY_OPERATOR") or current.has_role("SUPER_ADMIN") else "school",
        "schools": int(school_count or 0), "students": int(student_count or 0),
        "open_risks": int(risk_count or 0), "open_feedback": int(feedback_count or 0),
        "open_handoffs": int(handoff_count or 0),
    }


@router.get("/management/students")
async def management_students(
    current: AuthenticatedUser = Depends(management_roles),
    db: AsyncSession = Depends(get_db),
):
    students_query = _scoped(select(Student, School).join(School, School.id == Student.school_id).where(Student.status == "active"), current, Student.school_id).order_by(Student.name.asc())
    students = (await db.execute(students_query)).all()
    scores_query = _scoped(select(StudentExamScore, Exam), current, StudentExamScore.school_id).join(Exam, Exam.id == StudentExamScore.exam_id).order_by(Exam.start_date.desc())
    score_by_student: dict[UUID, tuple[StudentExamScore, Exam]] = {}
    for score, exam in (await db.execute(scores_query)).all():
        score_by_student.setdefault(score.student_id, (score, exam))
    risks_query = _scoped(select(RiskEvent.student_id, func.count(RiskEvent.id)).where(RiskEvent.status.in_(["open", "acknowledged"])), current, RiskEvent.school_id).group_by(RiskEvent.student_id)
    risk_by_student = {student_id: count for student_id, count in (await db.execute(risks_query)).all() if student_id}
    return [
        {
            "id": str(student.id), "name": student.name, "student_no": student.student_no,
            "school": school.name, "school_id": str(student.school_id),
            "latest_score": float(score_by_student[student.id][0].total_score) if student.id in score_by_student else None,
            "latest_exam": score_by_student[student.id][1].name if student.id in score_by_student else None,
            "open_risks": int(risk_by_student.get(student.id, 0)),
        }
        for student, school in students
    ]


@router.get("/management/schools")
async def management_schools(
    current: AuthenticatedUser = Depends(city_roles),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(School).order_by(School.name.asc()))
    rows = []
    for school in result.scalars().all():
        count = await db.scalar(select(func.count(Student.id)).where(Student.school_id == school.id, Student.status == "active"))
        risk_count = await db.scalar(select(func.count(RiskEvent.id)).where(RiskEvent.school_id == school.id, RiskEvent.status.in_(["open", "acknowledged"])))
        rows.append({"id": str(school.id), "name": school.name, "code": school.code, "status": school.status, "students": int(count or 0), "open_risks": int(risk_count or 0)})
    return rows


def _feedback_out(item: PlatformFeedback) -> dict[str, Any]:
    return {"id": str(item.id), "rating": item.rating, "category": item.category, "note": item.note, "status": item.status, "school_id": str(item.school_id), "student_id": str(item.student_id) if item.student_id else None, "created_at": _iso(item.created_at), "resolution": item.resolution}


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
    item.status = data.status
    item.resolution = data.resolution
    item.assignee_id = current.user_id
    if data.status in {"resolved", "closed"}:
        item.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    return _feedback_out(item)


def _risk_out(item: RiskEvent) -> dict[str, Any]:
    return {"id": str(item.id), "student_id": str(item.student_id) if item.student_id else None, "event_type": item.event_type, "severity": item.severity, "title": item.title, "detail": item.detail, "source": item.source, "status": item.status, "created_at": _iso(item.created_at), "resolved_at": _iso(item.resolved_at)}


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
    current: AuthenticatedUser = Depends(management_roles),
    db: AsyncSession = Depends(get_db),
):
    item = RiskEvent(school_id=current.school_id, student_id=data.student_id, event_type=data.event_type, severity=data.severity, title=data.title, detail=data.detail, source=data.source)
    db.add(item)
    await db.commit()
    await db.refresh(item)
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
    item.status = data.status
    item.assigned_to = current.user_id
    if data.status in {"resolved", "closed"}:
        item.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    return _risk_out(item)


def _handoff_out(item: HumanHandoff) -> dict[str, Any]:
    return {"id": str(item.id), "student_id": str(item.student_id), "reason": item.reason, "priority": item.priority, "summary": item.summary, "status": item.status, "assigned_to": str(item.assigned_to) if item.assigned_to else None, "created_at": _iso(item.created_at), "accepted_at": _iso(item.accepted_at), "resolved_at": _iso(item.resolved_at)}


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
    item.status = data.status
    item.assigned_to = current.user_id
    now = datetime.now(timezone.utc)
    if data.status == "accepted" and item.accepted_at is None:
        item.accepted_at = now
    if data.status in {"resolved", "closed"}:
        item.resolved_at = now
    await db.commit()
    return _handoff_out(item)


def _knowledge_out(item: KnowledgeDocument) -> dict[str, Any]:
    return {"id": str(item.id), "title": item.title, "subject": item.subject, "doc_type": item.doc_type, "status": item.status, "version": item.version, "content": item.content, "source_name": item.source_name, "source_url": item.source_url, "source_reference": item.source_reference, "tags": item.tags or [], "rejection_reason": item.rejection_reason, "created_at": _iso(item.created_at), "reviewed_at": _iso(item.reviewed_at), "published_at": _iso(item.published_at), "offlined_at": _iso(item.offlined_at)}


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
    current: AuthenticatedUser = Depends(school_admin_roles),
    db: AsyncSession = Depends(get_db),
):
    item = KnowledgeDocument(
        school_id=current.school_id, title=data.title, subject=data.subject, doc_type=data.doc_type,
        content=data.content, source_name=data.source_name, source_url=data.source_url,
        source_reference=data.source_reference, tags=data.tags, created_by=current.user_id,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
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
    now = datetime.now(timezone.utc)
    transitions = {"submit": "pending_review", "approve": "published", "publish": "published", "reject": "rejected", "offline": "offline", "republish": "published"}
    item.status = transitions[data.action]
    item.rejection_reason = data.reason if data.action == "reject" else None
    item.reviewed_by = current.user_id
    item.reviewed_at = now
    if item.status == "published":
        item.published_at = now
        item.offlined_at = None
    if item.status == "offline":
        item.offlined_at = now
    await db.commit()
    return _knowledge_out(item)
