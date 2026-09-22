"""Atomic, actor/tenant-scoped creation with read-back on retries."""
import hashlib
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.core.errors import ApiError
from app.db.models.operation_receipt import OperationReceipt
from app.db.models.trace import AuditLog


async def create_once(db, actor, kind, payload, key, model, values):
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    # Old clients without an idempotency key get content-based deduplication.
    # A deliberately new identical operation must provide a fresh UUID key.
    request_hash = hashlib.sha256(f"{actor.school_id}:{actor.user_id}:{kind}:{key or digest}".encode()).hexdigest()
    resource_id = uuid4()
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    claimed = await db.scalar(insert(OperationReceipt).values(
        request_hash=request_hash, payload_hash=digest, resource_id=resource_id,
    ).on_conflict_do_nothing(index_elements=["request_hash"]).returning(OperationReceipt.resource_id))
    if claimed is None:
        receipt = await db.scalar(select(OperationReceipt).where(OperationReceipt.request_hash == request_hash))
        if receipt.payload_hash != digest:
            raise ApiError(409, "IDEMPOTENCY_KEY_CONFLICT", "同一提交标识不能用于不同内容，请重新发起操作。")
        item = await db.scalar(select(model).where(model.id == receipt.resource_id, model.school_id == actor.school_id))
        if item is None:
            raise ApiError(409, "IDEMPOTENCY_RESOURCE_UNAVAILABLE", "原提交记录不可用，请联系管理员核查。")
        return item
    item = model(id=resource_id, **values)
    db.add(item)
    db.add(AuditLog(action=f"platform.{kind}.create", actor_type="user", actor_id=actor.user_id,
                    resource_type=kind, resource_id=resource_id, allowed=True,
                    extra_data={"school_id": str(actor.school_id)}))
    await db.commit()
    await db.refresh(item)
    return item
