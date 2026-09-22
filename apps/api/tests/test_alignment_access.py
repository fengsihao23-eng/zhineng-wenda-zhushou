"""P0 alignment contracts. Every identity and learning record is synthetic."""
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.api.deps import AuthenticatedStudent, AuthenticatedUser, get_current_student, get_current_user
from app.main import app
from app.db.models import (School, User, Student, ImportedClass, Subject, Exam, TeachingAssignment,
                           StudentSubjectScore, StudentExamScore, QuestionScore, DiagnosisReport,
                           StudentEntitlement, RiskEvent, HumanHandoff, PlatformFeedback, ChatSession, AuditLog)
from app.tools.analysis_tools import GetDiagnosisTool
from app.tools.base import ToolContext

P = "/api/v1/platform"


@pytest_asyncio.fixture
async def scope_data(test_db, sample_school_id, sample_student_id):
    db, school = test_db, sample_school_id
    current = await db.get(Student, sample_student_id)
    other_school = School(id=uuid4(), name="Synthetic B", code=f"Q-{uuid4()}")
    db.add(other_school)
    await db.flush()
    classes = [ImportedClass(id=uuid4(), school_id=school, external_class_id=str(i), name=f"Class {i}", source_system="QA") for i in range(3)]
    subjects = [Subject(id=uuid4(), school_id=school, code=str(i), name=f"Subject {i}") for i in range(2)]
    teacher_user = User(id=uuid4(), school_id=school, username=f"qa-{uuid4()}", password_hash="unused")
    db.add_all([*classes, *subjects, teacher_user])
    await db.flush()
    current.class_id = classes[0].id
    others = [Student(id=uuid4(), school_id=school, class_id=c.id, name=f"Synthetic {i}", student_no=f"Q-{uuid4()}") for i, c in enumerate(classes[1:])]
    foreign = Student(id=uuid4(), school_id=other_school.id, name="Synthetic foreign", student_no=f"Q-{uuid4()}")
    exam = Exam(id=uuid4(), school_id=school, name="QA exam", exam_type="test", start_date=date(2026, 9, 1))
    db.add_all([*others, foreign, exam])
    await db.flush()
    now = datetime.now(timezone.utc)
    grants = [TeachingAssignment(school_id=school, teacher_user_id=teacher_user.id, class_id=classes[i].id,
                                subject_id=subjects[i].id, starts_at=now-timedelta(days=1)) for i in range(2)]
    db.add_all(grants)
    for student in [current, *others]:
        db.add(StudentExamScore(school_id=school, student_id=student.id, exam_id=exam.id, total_score=155))
        for i, subject in enumerate(subjects):
            db.add(StudentSubjectScore(school_id=school, student_id=student.id, exam_id=exam.id, subject_id=subject.id, score=70+i*15, full_score=100))
            db.add(QuestionScore(school_id=school, student_id=student.id, exam_id=exam.id, subject_id=subject.id, question_no="1", score=3, full_score=5, lost_score=2))
        db.add(RiskEvent(school_id=school, student_id=student.id, event_type="learning", title="QA risk", detail="Synthetic event"))
        db.add(HumanHandoff(school_id=school, student_id=student.id, reason="QA help", summary="Synthetic help"))
    await db.commit()
    return dict(school=school, current=current, others=others, foreign=foreign, other_school=other_school,
                teacher=AuthenticatedUser(teacher_user.id, school, teacher_user.username, ["TEACHER"]),
                student=AuthenticatedStudent(current.user_id, school, current.id, current.name, ["STUDENT"]),
                classes=classes, subjects=subjects, grants=grants, exam=exam)


def authenticate(actor, student=False):
    app.dependency_overrides[get_current_student if student else get_current_user] = lambda: actor


@pytest.mark.asyncio
async def test_teacher_scope_is_class_subject_correlated_and_audited(client, test_db, scope_data):
    d = scope_data
    authenticate(d["teacher"])
    rows = (await client.get(P + "/management/students")).json()
    assert {row["id"] for row in rows} == {str(d["current"].id), str(d["others"][0].id)}
    assert all(row["latest_score"] is None for row in rows)
    assert all(len(row["subject_scores"]) == 1 for row in rows)
    for student, subject in zip([d["current"], d["others"][0]], d["subjects"]):
        response = await client.get(f"{P}/management/students/{student.id}")
        assert response.status_code == 200
        detail = response.json()
        assert {row["subject"] for row in detail["subject_scores"]} == {subject.name}
        assert {row["subject"] for row in detail["question_losses"]} == {subject.name}
        assert detail["exam_scores"] == []
    assert await test_db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "student.learning.read")) == 2
    for student in [d["others"][1], d["foreign"]]:
        assert (await client.get(f"{P}/management/students/{student.id}")).status_code == 404
    overview = (await client.get(P + "/management/overview")).json()
    assert overview["students"] == 2
    assert overview["open_risks"] == 2
    assert overview["open_handoffs"] == 2
    assert len((await client.get(P + "/management/risks")).json()) == 2
    assert len((await client.get(P + "/management/handoffs")).json()) == 2


@pytest.mark.asyncio
async def test_teacher_grant_expiry_and_empty_scope(client, test_db, scope_data):
    d = scope_data
    authenticate(d["teacher"])
    d["grants"][0].expires_at = datetime.now(timezone.utc)-timedelta(seconds=1)
    d["grants"][1].status = "revoked"
    await test_db.commit()
    assert (await client.get(P + "/management/students")).json() == []
    overview = (await client.get(P + "/management/overview")).json()
    assert overview["students"] == overview["open_risks"] == overview["open_handoffs"] == 0


@pytest.mark.asyncio
async def test_teacher_scope_honors_existing_csv_class_mapping(client, test_db, scope_data):
    d = scope_data
    authenticate(d["teacher"])
    d["current"].class_id = None
    d["current"].external_class_id = d["classes"][0].external_class_id
    await test_db.commit()
    detail = await client.get(f"{P}/management/students/{d['current'].id}")
    assert detail.status_code == 200
    assert {r["subject"] for r in detail.json()["subject_scores"]} == {d["subjects"][0].name}


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["STUDENT", "TEACHER", "SCHOOL_ADMIN", "QA", "CITY_OPERATOR"])
async def test_global_prompt_writes_require_super_admin(client, scope_data, role):
    d = scope_data
    authenticate(AuthenticatedUser(d["teacher"].user_id, d["school"], "qa", [role]))
    for path, body in [("/", {"name": "qa", "scene": "qa", "content": "synthetic"}), ("/qa/v1/publish", {}), ("/qa/v1/deprecate", {})]:
        response = await client.post("/api/v1/admin/prompts"+path, json=body)
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_super_admin_prompt_publish_readback(client, scope_data):
    d = scope_data
    authenticate(AuthenticatedUser(d["teacher"].user_id, d["school"], "qa", ["SUPER_ADMIN"]))
    created = await client.post("/api/v1/admin/prompts/", json={"name": "qa", "scene": "qa", "content": "Synthetic facts only"})
    assert created.status_code == 200
    version = created.json()["version"]
    for _ in range(2):
        assert (await client.post(f"/api/v1/admin/prompts/qa/{version}/publish")).status_code == 200
    assert (await client.get(f"/api/v1/admin/prompts/qa/{version}")).json()["status"] == "published"


@pytest.mark.asyncio
async def test_cross_tenant_related_creates_and_retries(client, test_db, scope_data):
    d = scope_data
    authenticate(d["student"], student=True)
    other_session = ChatSession(id=uuid4(), school_id=d["school"], student_id=d["others"][0].id)
    own_session = ChatSession(id=uuid4(), school_id=d["school"], student_id=d["current"].id)
    foreign_session = ChatSession(id=uuid4(), school_id=d["other_school"].id, student_id=d["foreign"].id)
    test_db.add_all([other_session, own_session, foreign_session])
    await test_db.commit()
    body = {"reason": "QA request", "summary": "Synthetic support", "session_id": str(own_session.id)}
    for session in [other_session, foreign_session]:
        assert (await client.post(P + "/student/handoffs", json={**body, "session_id": str(session.id)})).status_code == 404
    key = {"Idempotency-Key": str(uuid4())}
    created = await client.post(P + "/student/handoffs", json=body, headers=key)
    assert created.status_code == 201
    again = await client.post(P + "/student/handoffs", json=body, headers=key)
    assert again.json()["id"] == created.json()["id"]
    assert (await client.post(P + "/student/handoffs", json={**body, "summary": "changed"}, headers=key)).status_code == 409
    assert created.json()["id"] in [r["id"] for r in (await client.get(P + "/student/handoffs")).json()]
    authenticate(d["teacher"])
    risk = {"title": "QA risk", "detail": "Synthetic risk"}
    for student in [d["foreign"], d["others"][1]]:
        assert (await client.post(P + "/management/risks", json={**risk, "student_id": str(student.id)})).status_code == 404
    assert (await client.post(P + "/management/risks", json=risk)).status_code == 403
    allowed = {**risk, "student_id": str(d["current"].id)}
    first = await client.post(P + "/management/risks", json=allowed)
    duplicate = await client.post(P + "/management/risks", json=allowed)
    assert first.status_code == 201 and duplicate.json()["id"] == first.json()["id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("resource_type", ["report", "exam", "subject"])
async def test_diagnosis_shared_resource_scope_and_revoke(client, test_db, scope_data, resource_type):
    d = scope_data
    authenticate(d["student"], student=True)
    now = datetime.now(timezone.utc)
    report = DiagnosisReport(id=uuid4(), school_id=d["school"], student_id=d["current"].id,
                             exam_id=d["exam"].id, subject_id=d["subjects"][0].id, report_type="subject", generated_at=now,
                             status="generated", version="v1", raw_content="Synthetic original", structured_json={"summary": "Synthetic"})
    draft = DiagnosisReport(id=uuid4(), school_id=d["school"], student_id=d["current"].id,
                            exam_id=d["exam"].id, subject_id=d["subjects"][0].id, report_type="subject", generated_at=now,
                            status="draft", structured_json={"summary": "MUST NOT LEAK"})
    test_db.add_all([report, draft])
    await test_db.commit()
    ctx = ToolContext(request_id="qa", agent_run_id="qa", user_id=d["current"].user_id,
                      school_id=d["school"], student_id=d["current"].id, entitlement_level="DIAGNOSIS")
    tool = GetDiagnosisTool(test_db)
    assert (await client.get(P + "/student/diagnosis")).status_code == 403
    assert (await client.get(f"{P}/student/diagnosis/{report.id}/source")).status_code == 403
    assert (await tool.execute(ctx, {})).error_code == "ENTITLEMENT_REQUIRED"
    resource_id = {"report": report.id, "exam": d["exam"].id, "subject": d["subjects"][0].id}[resource_type]
    grant = StudentEntitlement(school_id=d["school"], student_id=d["current"].id, product_code="DIAGNOSIS_REPORT",
                               resource_type=resource_type, resource_id=resource_id, starts_at=now-timedelta(days=1))
    test_db.add(grant)
    await test_db.commit()
    rows = (await client.get(P + "/student/diagnosis")).json()
    assert [r["id"] for r in rows] == [str(report.id)]
    source = await client.get(f"{P}/student/diagnosis/{report.id}/source")
    assert source.status_code == 200 and source.json()["version"] == "v1"
    assert (await tool.execute(ctx, {})).data["report_id"] == str(report.id)
    assert (await client.get(f"{P}/student/diagnosis/{draft.id}/source")).status_code == 404
    report.raw_content = None
    await test_db.commit()
    assert (await client.get(f"{P}/student/diagnosis/{report.id}/source")).json()["error"]["code"] == "REPORT_SOURCE_MISSING"
    grant.status = "revoked"
    await test_db.commit()
    assert (await client.get(P + "/student/diagnosis")).status_code == 403
    assert (await tool.execute(ctx, {})).error_code == "ENTITLEMENT_REQUIRED"


@pytest.mark.asyncio
async def test_diagnosis_empty_expired_future_and_unrelated_grant(client, test_db, scope_data):
    d = scope_data
    authenticate(d["student"], student=True)
    now = datetime.now(timezone.utc)
    grant = StudentEntitlement(school_id=d["school"], student_id=d["current"].id, product_code="OTHER",
                               starts_at=now-timedelta(days=1))
    test_db.add(grant)
    await test_db.commit()
    assert (await client.get(P + "/student/diagnosis")).status_code == 403
    grant.product_code = "DIAGNOSIS"
    grant.starts_at = now+timedelta(days=1)
    await test_db.commit()
    assert (await client.get(P + "/student/diagnosis")).status_code == 403
    grant.starts_at = now-timedelta(days=2)
    grant.expires_at = now-timedelta(days=1)
    await test_db.commit()
    assert (await client.get(P + "/student/diagnosis")).status_code == 403
    grant.expires_at = None
    await test_db.commit()
    assert (await client.get(P + "/student/diagnosis")).json() == []


@pytest.mark.asyncio
async def test_backend_role_routes_and_school_detail(client, scope_data):
    d = scope_data
    authenticate(AuthenticatedUser(d["current"].user_id, d["school"], "student", ["STUDENT"]))
    for path in ["overview", "students", "schools", "knowledge", "feedback", "risks", "handoffs"]:
        assert (await client.get(P + "/management/"+path)).status_code == 403
    authenticate(d["teacher"])
    assert (await client.get(P + "/student/dashboard")).status_code == 403
    assert (await client.get(f"{P}/management/schools/{d['school']}")).status_code == 403
    authenticate(AuthenticatedUser(d["teacher"].user_id, d["school"], "city", ["CITY_OPERATOR"]))
    detail = await client.get(f"{P}/management/schools/{d['school']}")
    assert detail.status_code == 200 and detail.json()["students"] == 3
    assert "student_no" not in detail.text
    assert (await client.get(f"{P}/management/schools/{uuid4()}")).status_code == 404


@pytest.mark.asyncio
async def test_postgresql_rejects_cross_tenant_workflow_links(test_db, scope_data):
    from sqlalchemy.exc import IntegrityError
    if test_db.get_bind().dialect.name != "postgresql":
        pytest.skip("Production database FK test")
    d = scope_data
    foreign_session = ChatSession(id=uuid4(), school_id=d["other_school"].id, student_id=d["foreign"].id)
    test_db.add(foreign_session)
    await test_db.commit()
    for invalid in [
        RiskEvent(school_id=d["school"], student_id=d["foreign"].id, event_type="QA", title="QA", detail="QA"),
        HumanHandoff(school_id=d["school"], student_id=d["current"].id, session_id=foreign_session.id, reason="QA", summary="QA"),
        TeachingAssignment(school_id=d["other_school"].id, teacher_user_id=d["teacher"].user_id,
                           class_id=d["classes"][0].id, subject_id=d["subjects"][0].id),
    ]:
        with pytest.raises(IntegrityError):
            async with test_db.begin_nested():
                test_db.add(invalid)
                await test_db.flush()


@pytest.mark.asyncio
async def test_postgresql_parallel_create_is_atomic(test_engine, test_db, scope_data):
    import asyncio
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.core.idempotency import create_once
    if test_db.get_bind().dialect.name != "postgresql":
        pytest.skip("Independent PostgreSQL transaction concurrency")
    d = scope_data
    key = uuid4()
    payload = {"reason": "Parallel QA", "summary": "Synthetic"}
    async def create():
        async with AsyncSession(test_engine, expire_on_commit=False) as db:
            item = await create_once(db, d["student"], "handoff", payload, key, HumanHandoff,
                                     dict(school_id=d["school"], student_id=d["current"].id, **payload))
            return item.id
    first, second = await asyncio.gather(create(), create())
    assert first == second
    assert await test_db.scalar(select(func.count(HumanHandoff.id)).where(HumanHandoff.id == first)) == 1
