"""Translate platform IDs to existing FK identities with school/type boundaries."""
import re
from uuid import UUID
from sqlalchemy import select, or_
from app.db.models.person_id import PlatformPersonId
from app.core.errors import ApiError


async def resolve(db, school_id, kind, values):
    values = {str(value) for value in values}
    numbers, uuids = set(), set()
    for value in values:
        if re.fullmatch(r"[1-9][0-9]{7,9}", value) and 10000001 <= int(value) <= 9999999999:
            numbers.add(int(value))
        else:
            try:
                uuids.add(UUID(value))
            except (ValueError, TypeError):
                pass
    if not numbers and not uuids:
        return {}
    identities = (await db.scalars(select(PlatformPersonId).where(
        PlatformPersonId.school_id == school_id, PlatformPersonId.kind == kind,
        or_(PlatformPersonId.id.in_(numbers), PlatformPersonId.entity_id.in_(uuids))))).all()
    lookup = {key: item.entity_id for item in identities for key in (str(item.id), str(item.entity_id))}
    # Legacy UUID templates remain usable; no account/student/exam number lookup.
    return {value: lookup[value] for value in values if value in lookup}


async def normalize_body(db, school_id, kind, body):
    """Accept short person IDs in association requests without changing FK data."""
    lists = {name: getattr(body, name) for name in (
        "student_ids", "teacher_ids", "identity_confirmed_ids", "identity_uncertain_ids",
        "graduation_student_ids", "records_verified_ids") if hasattr(body, name)}
    maps = {name: getattr(body, name) for name in (
        "placements", "anomaly_approvals", "graduation_exclusions", "retained_students", "teacher_replacements") if hasattr(body, name)}
    values = [str(value) for entries in lists.values() for value in entries]
    for name, entries in maps.items():
        values.extend(str(value) for value in (entries.values() if name == "teacher_replacements" else entries.keys()))
        if name == "retained_students":
            values.extend(str(value) for value in entries.values())
    lookup = await resolve(db, school_id, kind, values)
    if any(value not in lookup for value in values):
        raise ApiError(404, "RESOURCE_NOT_AVAILABLE", "名单包含不存在、类型不符或不在授权范围内的平台ID。")
    updates = {name: [lookup[str(value)] for value in entries] for name, entries in lists.items()}
    for name, entries in maps.items():
        if name == "teacher_replacements":
            updates[name] = {key: lookup[str(value)] for key, value in entries.items()}
        else:
            updates[name] = {lookup[str(key)]: lookup[str(value)] if name == "retained_students" else value for key, value in entries.items()}
    if any(len(updates[name]) != len(entries) for name, entries in maps.items()):
        raise ApiError(422, "PERSON_SELECTION_DUPLICATE", "同一平台身份被重复指定，请检查短ID与旧ID是否指向同一人。")
    return body.model_copy(update=updates)
