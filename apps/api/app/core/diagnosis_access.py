"""Report-level entitlement policy shared by pages, source reads and Tools."""
from datetime import datetime, timezone

from sqlalchemy import and_, exists, or_, select

from app.core.errors import ApiError
from app.db.models.diagnosis import DiagnosisReport, StudentEntitlement
from app.db.models.trace import AuditLog


def active_entitlements(school_id, student_id):
    now = datetime.now(timezone.utc)
    e = StudentEntitlement
    return (
        e.school_id == school_id, e.student_id == student_id,
        e.product_code.in_(["DIAGNOSIS", "DIAGNOSIS_REPORT"]),
        e.status == "active", e.starts_at <= now,
        or_(e.expires_at.is_(None), e.expires_at > now),
        or_(and_(e.resource_type.is_(None), e.resource_id.is_(None)),
            and_(e.resource_type.in_(["all", "student"]), e.resource_id.is_(None)),
            and_(e.resource_type.in_(["exam", "report", "diagnosis_report", "subject"]), e.resource_id.is_not(None))),
    )


async def has_diagnosis_entitlement(db, school_id, student_id):
    return bool(await db.scalar(select(exists().where(*active_entitlements(school_id, student_id)))))


def authorized_reports(school_id, student_id):
    r, e = DiagnosisReport, StudentEntitlement
    grant = exists(select(e.id).where(
        *active_entitlements(school_id, student_id),
        or_(
            and_(e.resource_id.is_(None), or_(e.resource_type.is_(None), e.resource_type.in_(["all", "student"]))),
            and_(e.resource_type == "exam", e.resource_id == r.exam_id),
            and_(e.resource_type.in_(["report", "diagnosis_report"]), e.resource_id == r.id),
            and_(e.resource_type == "subject", e.resource_id == r.subject_id),
        ),
    ))
    return select(r).where(r.school_id == school_id, r.student_id == student_id, r.status == "generated", grant)


async def audit_report_access(db, actor, allowed, resource_id=None, reason=None):
    db.add(AuditLog(action="diagnosis.read", actor_type="student", actor_id=actor.user_id,
                    resource_type="diagnosis_report", resource_id=resource_id,
                    allowed=allowed, reason=reason,
                    extra_data={"school_id": str(actor.school_id)}))
    # These read-only entry points have no pending business writes. Commit the
    # denied audit too; request rollback must not erase evidence of a denial.
    await db.commit()


async def require_diagnosis(db, actor):
    if not await has_diagnosis_entitlement(db, actor.school_id, actor.student_id):
        await audit_report_access(db, actor, False, reason="ENTITLEMENT_REQUIRED")
        raise ApiError(403, "ENTITLEMENT_REQUIRED", "当前没有有效的诊断报告授权，请联系学校确认。")


async def require_report(db, actor, report_id):
    await require_diagnosis(db, actor)
    report = await db.scalar(authorized_reports(actor.school_id, actor.student_id).where(DiagnosisReport.id == report_id))
    if report is None:
        await audit_report_access(db, actor, False, report_id, "REPORT_NOT_AVAILABLE")
        raise ApiError(404, "REPORT_NOT_AVAILABLE", "报告不存在、未正式发布或不在授权范围内。")
    return report
