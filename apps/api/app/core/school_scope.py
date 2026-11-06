"""School labels for business data; each business identity stays in its own school."""
from uuid import UUID

from sqlalchemy import select

from app.core.errors import ApiError
from app.db.models.school import School

def reject_school_override(request):
    if request.headers.get("X-School-ID"):
        raise ApiError(403, "SCHOOL_SCOPE_FORBIDDEN", "学校业务仅限当前账号所属学校，不支持跨校切换。")


async def school_fields(db, actor):
    school = await db.get(School, actor.school_id)
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
