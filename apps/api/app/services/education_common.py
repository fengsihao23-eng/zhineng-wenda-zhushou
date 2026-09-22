"""Shared authorization, optimistic writes and receipts for education domains."""
import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.core.errors import ApiError
from app.core.access_scope import active_grants, is_teacher_only
from app.db.models.operation_receipt import OperationReceipt
from app.db.models.teaching import TeachingAssignment
from app.db.models.trace import AuditLog


def now():
    return datetime.now(timezone.utc)


def digest(payload):
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def data(row, *fields):
    result = {}
    for name in fields:
        value = getattr(row, name)
        result[name] = (
            value.isoformat()
            if hasattr(value, "isoformat")
            else str(value)
            if hasattr(value, "hex")
            else value
        )
    return result


async def owned(db, model, identifier, actor, *, lock=False):
    query = select(model).where(
        model.id == identifier, model.school_id == actor.school_id
    )
    if lock:
        query = query.with_for_update()
    item = await db.scalar(query.execution_options(populate_existing=True))
    if item is None:
        raise ApiError(404, "RESOURCE_NOT_AVAILABLE", "记录不存在或不在授权范围内。")
    return item


async def subject_access(db, actor, subject_id):
    if is_teacher_only(actor) and not await db.scalar(
        select(TeachingAssignment.id)
        .where(*active_grants(actor), TeachingAssignment.subject_id == subject_id)
        .limit(1)
    ):
        raise ApiError(404, "RESOURCE_NOT_AVAILABLE", "记录不存在或不在任教学科范围内。")


def native_only(item):
    if getattr(item, "source_system", "native") != "native":
        raise ApiError(409, "EXTERNAL_READ_ONLY", "该记录由外部系统维护，只能接收新来源版本。")


def audit(db, actor, action, item, extra=None):
    db.add(
        AuditLog(
            action=f"education.{action}",
            actor_type="user",
            actor_id=actor.user_id,
            resource_type=item.__tablename__,
            resource_id=item.id,
            allowed=True,
            extra_data={"school_id": str(actor.school_id), **(extra or {})},
        )
    )


async def claim(db, actor, operation, key, payload):
    """Reserve a receipt in the caller's transaction; never commit partial work."""
    content_hash = digest(payload)
    request_hash = digest(
        [str(actor.school_id), str(actor.user_id), operation, str(key or content_hash)]
    )
    identifier = uuid4()
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    result = await db.scalar(
        insert(OperationReceipt)
        .values(
            request_hash=request_hash, payload_hash=content_hash, resource_id=identifier
        )
        .on_conflict_do_nothing(index_elements=["request_hash"])
        .returning(OperationReceipt.resource_id)
    )
    if result is not None:
        return identifier, True
    receipt = await db.scalar(
        select(OperationReceipt).where(OperationReceipt.request_hash == request_hash)
    )
    if receipt.payload_hash != content_hash:
        raise ApiError(409, "IDEMPOTENCY_KEY_CONFLICT", "同一提交标识对应的内容已变化，请刷新后重新提交。")
    return receipt.resource_id, False


async def cas(db, item, expected, values):
    model = type(item)
    changed = await db.execute(
        update(model)
        .where(
            model.id == item.id,
            model.school_id == item.school_id,
            model.revision == expected,
        )
        .values(**values, revision=expected + 1)
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        raise ApiError(409, "VERSION_CONFLICT", "记录已更新，请刷新核对后重试，当前编辑未覆盖。")
    await db.refresh(item)
    return item
