"""Explicit school selection for super-admin workbenches, independent of identity."""
from uuid import UUID

from sqlalchemy import select

from app.core.errors import ApiError
from app.db.models.school import School

SCOPED_PREFIXES = ("/api/v1/platform/education/", "/api/v1/platform/management/", "/api/v1/answer-workbench/admin/",
                   "/api/v1/answer-workbench/tickets", "/api/v1/answer-workbench/sources/", "/api/v1/answer-workbench/reports/")


async def apply_school_selection(request, actor, db):
    value = request.headers.get("X-School-ID")
    if not value:
        return actor
    if not actor.has_role("SUPER_ADMIN"):
        raise ApiError(403, "SCHOOL_SCOPE_FORBIDDEN", "只有超级管理员可以切换管理学校。")
    if not request.url.path.startswith(SCOPED_PREFIXES):
        raise ApiError(400, "SCHOOL_SCOPE_NOT_SUPPORTED", "该接口不支持切换学校。")
    try:
        identifier = UUID(value)
    except ValueError:
        raise ApiError(422, "INVALID_SCHOOL_SCOPE", "学校标识无效，请重新选择学校。")
    school = await db.scalar(select(School).where(School.id == identifier))
    if school is None:
        raise ApiError(404, "SCHOOL_NOT_FOUND", "学校不存在，请重新选择。")
    if school.status != "active" and request.method not in {"GET", "HEAD", "OPTIONS"}:
        raise ApiError(403, "SCHOOL_INACTIVE", "该学校已停用，仅可查看历史数据。")
    actor.identity_school_id = actor.school_id
    actor.school_id = school.id
    actor.selected_school_id = school.id
    actor.selected_school = school
    context = getattr(request.state, "administrator_audit", None)
    if context:
        context["school_id"] = str(school.id)
    return actor


async def school_fields(db, actor):
    school = getattr(actor, "selected_school", None) or await db.get(School, actor.school_id)
    return {"school_id": str(school.id), "school_name": school.name, "school_code": school.code} if school else {}


async def label_school_rows(db, actor, payload):
    """Annotate rows already limited to one school by the domain service."""
    fields = await school_fields(db, actor)
    if isinstance(payload, list):
        return [{**item, **fields} for item in payload]
    return {**payload, **fields, "items": [{**item, **fields} for item in payload.get("items", [])]}


async def label_management_rows(db, items):
    """Use each record's actual school for management lists that can span schools."""
    identifiers = {UUID(str(item["school_id"])) for item in items if item.get("school_id")}
    schools = {str(s.id): s for s in (await db.scalars(select(School).where(School.id.in_(identifiers)))).all()}
    return [{**item, "school_name": schools[str(item["school_id"])].name,
             "school_code": schools[str(item["school_id"])].code} if str(item.get("school_id")) in schools else item for item in items]
