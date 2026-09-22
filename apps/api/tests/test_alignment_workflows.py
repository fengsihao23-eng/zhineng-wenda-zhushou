"""State-machine, read-back, duplicate and denied workflow contracts."""
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.api.deps import AuthenticatedStudent, AuthenticatedUser, get_current_student, get_current_user
from app.core.platform_workflows import WORKFLOW_TRANSITIONS
from app.db.models import Student, User, RiskEvent, PlatformFeedback, HumanHandoff, KnowledgeDocument, AuditLog, School
from app.main import app

P = "/api/v1/platform"


@pytest.fixture
def admin(sample_school_id):
    actor = AuthenticatedUser(uuid4(), sample_school_id, "synthetic-admin", ["SCHOOL_ADMIN"])
    app.dependency_overrides[get_current_user] = lambda: actor
    yield actor
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,table,route,first", [
    ("risk", RiskEvent, "risks", "acknowledged"),
    ("handoff", HumanHandoff, "handoffs", "accepted"),
    ("feedback", PlatformFeedback, "feedback", "acknowledged"),
])
async def test_workflow_lifecycle_illegal_repeat_reopen_and_readback(client, test_db, sample_school_id, sample_student_id, admin, kind, table, route, first):
    # Use a real synthetic FK target even with dependency override.
    test_db.add(User(id=admin.user_id, school_id=sample_school_id, username=admin.username, password_hash="unused"))
    student = await test_db.get(Student, sample_student_id)
    values = {"school_id": sample_school_id, "student_id": sample_student_id}
    if kind == "risk": values.update(event_type="learning", title="QA risk", detail="Synthetic detail")
    elif kind == "handoff": values.update(reason="QA help", summary="Synthetic help")
    else: values.update(user_id=student.user_id, rating="not_helpful", note="Synthetic feedback")
    item = table(**values)
    test_db.add(item)
    await test_db.commit()
    url = f"{P}/management/{route}/{item.id}"
    assert (await client.patch(url, json={"status": "anything"})).status_code == 422
    if kind != "feedback":
        assert (await client.patch(url, json={"status": "resolved", "resolution": "QA result"})).status_code == 409
    moved = await client.patch(url, json={"status": first, "expected_version": 1})
    assert moved.status_code == 200
    assert moved.json()["state_version"] == 2
    retry = await client.patch(url, json={"status": first, "expected_version": 1})
    assert retry.status_code == 200 and retry.json()["state_version"] == 2
    assert (await client.patch(url, json={"status": "resolved"})).status_code == 422
    assert (await client.patch(url, json={"status": "resolved", "resolution": "QA", "expected_version": 1})).status_code == 409
    resolved = await client.patch(url, json={"status": "resolved", "resolution": "Synthetic verified result", "expected_version": 2})
    assert resolved.status_code == 200 and resolved.json()["resolved_at"]
    readback = (await client.get(f"{P}/management/{route}")).json()
    assert next(r for r in readback if r["id"] == str(item.id))["resolution"] == "Synthetic verified result"
    target = "acknowledged" if kind == "risk" else "open"
    assert (await client.patch(url, json={"status": target})).status_code == 422
    reopened = await client.patch(url, json={"status": target, "resolution": "Synthetic follow-up required"})
    assert reopened.status_code == 200 and reopened.json()["resolved_at"] is None
    assert await test_db.scalar(select(func.count(AuditLog.id)).where(AuditLog.resource_id == item.id, AuditLog.allowed.is_(True))) == 3
    # Another tenant cannot see or mutate it, including a same-state replay.
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(uuid4(), uuid4(), "other", ["SCHOOL_ADMIN"])
    assert (await client.patch(url, json={"status": target})).status_code == 404


@pytest.mark.asyncio
async def test_knowledge_reject_requires_changed_draft_then_review(client, test_db, admin, sample_school_id):
    test_db.add(User(id=admin.user_id, school_id=sample_school_id, username=admin.username, password_hash="unused"))
    await test_db.commit()
    body = {"title": "Synthetic doc", "subject": "QA", "content": "Synthetic facts", "source_name": "QA", "source_reference": "QA page 1"}
    first = await client.post(P + "/management/knowledge", json=body)
    assert first.status_code == 201
    key = first.json()["id"]
    duplicate = await client.post(P + "/management/knowledge", json=body)
    assert duplicate.json()["id"] == key
    url = f"{P}/management/knowledge/{key}"
    assert (await client.post(url + "/review", json={"action": "approve"})).status_code == 409
    assert (await client.post(url + "/review", json={"action": "submit"})).json()["status"] == "pending_review"
    assert (await client.post(url + "/review", json={"action": "reject"})).status_code == 422
    rejected = await client.post(url + "/review", json={"action": "reject", "reason": "Needs source correction"})
    assert rejected.json()["status"] == "rejected"
    assert (await client.post(url + "/review", json={"action": "submit"})).status_code == 409
    assert (await client.patch(url, json=body)).status_code == 422
    assert (await client.patch(url, json={**body, "source_url": "  "})).status_code == 422
    changed = {**body, "content": "Synthetic corrected facts"}
    edited = await client.patch(url, json={**changed, "expected_version": rejected.json()["state_version"]})
    assert edited.status_code == 200 and edited.json()["status"] == "draft"
    assert edited.json()["version"] == "v2"
    assert (await client.patch(url, json=changed)).json()["version"] == "v2"
    assert (await client.post(url + "/review", json={"action": "submit"})).status_code == 200
    published = await client.post(url + "/review", json={"action": "approve"})
    assert published.json()["status"] == "published"
    assert (await client.patch(url, json=body)).status_code == 409
    assert (await client.post(url + "/review", json={"action": "offline"})).status_code == 422
    assert (await client.post(url + "/review", json={"action": "offline", "reason": "Synthetic update"})).status_code == 200
    assert (await client.post(url + "/review", json={"action": "republish"})).json()["status"] == "published"
    readback = (await client.get(P + "/management/knowledge")).json()
    assert readback[0]["content"] == changed["content"]


@pytest.mark.asyncio
async def test_student_feedback_and_handoff_progress_readback(client, test_db, sample_school_id, sample_student_id, admin):
    student = await test_db.get(Student, sample_student_id)
    test_db.add(User(id=admin.user_id, school_id=sample_school_id, username=admin.username, password_hash="unused"))
    await test_db.commit()
    current = AuthenticatedStudent(student.user_id, sample_school_id, sample_student_id, "Synthetic", ["STUDENT"])
    app.dependency_overrides[get_current_student] = lambda: current
    assert (await client.get(P + "/student/feedback")).json() == []
    assert (await client.get(P + "/student/handoffs")).json() == []
    feedback = await client.post(P + "/student/feedback", json={"rating": "data_wrong", "note": "Synthetic mismatch"})
    handoff = await client.post(P + "/student/handoffs", json={"reason": "Synthetic help", "summary": "Synthetic context"})
    f_id, h_id = feedback.json()["id"], handoff.json()["id"]
    assert (await client.post(P + "/student/feedback", json={"rating": "data_wrong", "note": "Synthetic mismatch"})).json()["id"] == f_id
    assert (await client.patch(f"{P}/management/feedback/{f_id}", json={"status": "resolved", "resolution": "Data checked"})).status_code == 200
    assert (await client.patch(f"{P}/management/handoffs/{h_id}", json={"status": "accepted"})).status_code == 200
    assert (await client.patch(f"{P}/management/handoffs/{h_id}", json={"status": "resolved", "resolution": "Help delivered"})).status_code == 200
    assert (await client.get(P + "/student/feedback")).json()[0]["resolution"] == "Data checked"
    assert (await client.get(P + "/student/handoffs")).json()[0]["resolution"] == "Help delivered"


@pytest.mark.asyncio
async def test_workflow_empty_invalid_input_and_no_role(client, test_db, sample_school_id, sample_student_id, admin):
    for path in ["feedback", "handoffs", "risks", "knowledge"]:
        assert (await client.get(f"{P}/management/{path}")).json() == []
    assert (await client.post(P + "/management/risks", json={"title": "  ", "detail": "  "})).status_code == 422
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(uuid4(), sample_school_id, "student", ["STUDENT"])
    for path in ["feedback", "handoffs", "risks"]:
        assert (await client.patch(f"{P}/management/{path}/{uuid4()}", json={"status": "open"})).status_code == 403
    assert (await client.post(P + f"/management/knowledge/{uuid4()}/review", json={"action": "approve"})).status_code == 403


@pytest.mark.asyncio
async def test_postgresql_concurrent_state_updates_have_one_winner(test_engine, test_db, sample_school_id, sample_student_id, admin):
    import asyncio
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.core.platform_workflows import transition_workflow
    from app.core.errors import ApiError
    if test_db.get_bind().dialect.name != "postgresql":
        pytest.skip("Independent PostgreSQL transaction concurrency")
    test_db.add(User(id=admin.user_id, school_id=sample_school_id, username=admin.username, password_hash="unused"))
    risk = RiskEvent(school_id=sample_school_id, student_id=sample_student_id, event_type="QA", title="QA", detail="QA", status="acknowledged")
    test_db.add(risk)
    await test_db.commit()
    barrier = asyncio.Barrier(2)
    async def change(target):
        async with AsyncSession(test_engine, expire_on_commit=False) as db:
            item = await db.get(RiskEvent, risk.id)
            await barrier.wait()
            try:
                await transition_workflow(db, item, admin, "risk", target, "Synthetic result", 1)
                return 200
            except ApiError as error:
                return error.status_code
    assert sorted(await asyncio.gather(change("resolved"), change("closed"))) == [200, 409]
