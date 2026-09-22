"""Explicit, audited workflow transitions; never accept arbitrary state writes.

Scope/role checks stay at the calling service boundary. State updates use a
compare-and-swap so two workers cannot silently overwrite one another.
"""
from datetime import datetime, timezone
import re
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.contextvars import get_contextvars

from app.core.errors import ApiError
from app.db.models.platform import HumanHandoff, KnowledgeDocument, PlatformFeedback, RiskEvent
from app.db.models.trace import AuditLog


WORKFLOW_TRANSITIONS = {
    "risk": {
        "open": {"acknowledged"},
        "acknowledged": {"resolved", "closed"},
        "resolved": {"acknowledged", "closed"},
        "closed": {"acknowledged"},
    },
    "feedback": {
        "open": {"acknowledged", "resolved", "closed"},
        "acknowledged": {"resolved", "closed"},
        "resolved": {"open", "closed"},
        "closed": {"open"},
    },
    "handoff": {
        "open": {"accepted", "closed"},
        "accepted": {"resolved", "closed"},
        "resolved": {"open", "closed"},
        "closed": {"open"},
    },
}

# Published content can be taken offline, but drafts/rejected documents cannot
# bypass review. A rejected document must be changed and saved as a new draft.
KNOWLEDGE_ACTIONS = {
    "submit": ({"draft"}, "pending_review"),
    "approve": ({"pending_review"}, "published"),
    "publish": ({"pending_review"}, "published"),
    "reject": ({"pending_review"}, "rejected"),
    "offline": ({"published"}, "offline"),
    "republish": ({"offline"}, "published"),
}


def workflow_next_states(kind: str, state: str) -> list[str]:
    return sorted(WORKFLOW_TRANSITIONS[kind].get(state, set()))


def knowledge_actions(state: str) -> list[str]:
    return [action for action, (sources, _) in KNOWLEDGE_ACTIONS.items() if state in sources and action != "publish"]


def _audit(db, item, current, kind, action, *, allowed, target=None, note=None, code=None):
    db.add(AuditLog(
        action=f"platform.{kind}.{action}", actor_type="user", actor_id=current.user_id,
        resource_type=kind, resource_id=item.id, allowed=allowed, reason=code or action,
        request_id=get_contextvars().get("request_id"),
        extra_data={
            "school_id": str(item.school_id), "from_status": item.status,
            "to_status": target or item.status, "state_version": item.state_version,
            # Kept in the access-controlled audit store, never ordinary logs.
            **({"note": note} if note else {}),
        },
    ))


async def _reject(db, item, current, kind, action, code, message, *, target=None, status_code=409):
    _audit(db, item, current, kind, action, allowed=False, target=target, code=code)
    await db.commit()
    raise ApiError(status_code, code, message)


async def _persist(db, item, current, kind, action, values, note=None):
    model = type(item)
    values = {**values, "state_version": item.state_version + 1}
    result = await db.execute(
        update(model).where(
            model.id == item.id, model.school_id == item.school_id,
            model.state_version == item.state_version, model.status == item.status,
        ).values(**values).execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        await db.rollback()
        # The rollback expires the ORM row; refresh before using it in audit.
        await db.refresh(item)
        await _reject(db, item, current, kind, action, "WORKFLOW_CONFLICT", "记录已被其他人更新，请刷新后重试")
    _audit(db, item, current, kind, action, allowed=True, target=values.get("status"), note=note)
    await db.commit()
    await db.refresh(item)
    return item


async def transition_workflow(
    db: AsyncSession, item: RiskEvent | PlatformFeedback | HumanHandoff,
    current, kind: str, target: str, resolution: str | None = None,
    expected_version: int | None = None,
):
    transitions = WORKFLOW_TRANSITIONS[kind]
    note = resolution.strip() if resolution else None
    if target not in transitions:
        await _reject(db, item, current, kind, "transition", "WORKFLOW_STATUS_INVALID", "不支持的工作流状态", target=target, status_code=422)
    # Retried requests do not change assignee/timestamps or duplicate audit.
    if target == item.status:
        if note is None or note == item.resolution:
            return item
        await _reject(db, item, current, kind, "transition", "WORKFLOW_CONFLICT", "状态已完成，不能用重复提交覆盖处理说明", target=target)
    if expected_version is not None and expected_version != item.state_version:
        await _reject(db, item, current, kind, "transition", "WORKFLOW_CONFLICT", "记录已更新，请刷新后重试", target=target)
    if target not in transitions.get(item.status, set()):
        await _reject(db, item, current, kind, "transition", "WORKFLOW_TRANSITION_NOT_ALLOWED", "当前状态不允许此操作，请刷新后按流程处理", target=target)
    if (target in {"resolved", "closed"} or item.status in {"resolved", "closed"}) and not note:
        await _reject(db, item, current, kind, "transition", "WORKFLOW_REASON_REQUIRED", "解决、关闭或重新打开必须填写真实处理说明", target=target, status_code=422)
    now = datetime.now(timezone.utc)
    values: dict[str, Any] = {
        "status": target,
        "resolution": note,
        "resolved_at": now if target in {"resolved", "closed"} else None,
        "assignee_id" if kind == "feedback" else "assigned_to": current.user_id,
    }
    if kind == "handoff":
        if target == "accepted":
            values["accepted_at"] = now
        elif target == "open":
            values["accepted_at"] = None
            values["assigned_to"] = None
    return await _persist(db, item, current, kind, "transition", values, note)


async def transition_knowledge(db, item, current, action, reason=None, expected_version=None):
    sources, target = KNOWLEDGE_ACTIONS[action]
    note = reason.strip() if reason else None
    if item.status == target:
        if action != "reject" or note is None or note == item.rejection_reason:
            return item
        await _reject(db, item, current, "knowledge", action, "WORKFLOW_CONFLICT", "请勿用重复提交覆盖审核意见", target=target)
    if expected_version is not None and expected_version != item.state_version:
        await _reject(db, item, current, "knowledge", action, "WORKFLOW_CONFLICT", "文档已更新，请刷新后重试", target=target)
    if item.status not in sources:
        await _reject(db, item, current, "knowledge", action, "WORKFLOW_TRANSITION_NOT_ALLOWED", "当前文档状态不允许此操作；驳回后需修改并保存草稿再提交", target=target)
    if action in {"reject", "offline"} and not note:
        await _reject(db, item, current, "knowledge", action, "WORKFLOW_REASON_REQUIRED", "驳回或下线必须填写原因", target=target, status_code=422)
    now = datetime.now(timezone.utc)
    values = {"status": target, "rejection_reason": note if action == "reject" else None, "updated_at": now}
    if action != "submit":
        values.update(reviewed_by=current.user_id, reviewed_at=now)
    if target == "published":
        values.update(published_at=now, offlined_at=None)
    elif target == "offline":
        values["offlined_at"] = now
    return await _persist(db, item, current, "knowledge", action, values, note)


async def edit_knowledge(db, item, current, content: dict, expected_version=None):
    if item.status not in {"draft", "rejected"}:
        await _reject(db, item, current, "knowledge", "edit", "KNOWLEDGE_NOT_EDITABLE", "只有草稿或已驳回文档可以编辑")
    fields = {key: value for key, value in content.items() if key in {"title", "subject", "doc_type", "content", "source_name", "source_url", "source_reference", "tags"}}
    changed = any(getattr(item, key) != value for key, value in fields.items())
    if not changed:
        if item.status == "rejected":
            await _reject(db, item, current, "knowledge", "edit", "KNOWLEDGE_REWORK_REQUIRED", "请根据驳回意见修改内容后再保存", status_code=422)
        return item
    if expected_version is not None and expected_version != item.state_version:
        await _reject(db, item, current, "knowledge", "edit", "WORKFLOW_CONFLICT", "文档已更新，请刷新后重试")
    old_version = re.fullmatch(r"v?(\d+)", item.version or "v1")
    next_version = f"v{int(old_version.group(1)) + 1}" if old_version else f"r{item.state_version + 1}"
    fields.update(status="draft", version=next_version, rejection_reason=None, reviewed_at=None, reviewed_by=None, updated_at=datetime.now(timezone.utc))
    return await _persist(db, item, current, "knowledge", "edit", fields)
