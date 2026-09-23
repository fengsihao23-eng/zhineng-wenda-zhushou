"""0922 teacher reimport, student import and automatic login acceptance."""
import base64
from pathlib import Path
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, func

from app.api.deps import get_current_user
from app.main import app
from app.core.security import get_password_hash, verify_password
from app.db.models import User, Student, TeacherDeletion, AuditLog
from app.services.roster_excel import STUDENT_COLUMNS, parse_excel
from test_education_workbench import actors, post, P  # noqa: F401
from test_roster_workflows import teacher, student, upload, confirm, lifecycle, classroom


@pytest.mark.asyncio
@pytest.mark.parametrize("changed_account", [False, True])
@pytest.mark.parametrize("initial_password", [False, True])
async def test_teacher_reimport_preserves_password_and_invalidates_old_session(client, test_db, actors, changed_account, initial_password):
    old_account, new_account = "before-change", "after-change" if changed_account else "before-change"
    result = await confirm(client, await upload(client, [teacher(old_account)]))
    original_id = UUID(result["report"]["imported"][0]["id"])
    original = await test_db.get(User, original_id)
    password = old_account if initial_password else "teacher-changed-secret"
    if not initial_password:
        original.password_hash = get_password_hash(password)
        original.must_change_password = False
        await test_db.commit()
    original_hash = original.password_hash
    tokens = (await client.post("/api/v1/auth/login", json={"username": old_account, "password": password})).json()
    deletion = await lifecycle(client, "teachers", str(original_id))
    # Retrying deletion must not overwrite the immutable snapshot or add logs.
    await lifecycle(client, "teachers", str(original_id))
    assert await test_db.scalar(select(func.count()).select_from(TeacherDeletion)) == 1
    assert await test_db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "education.roster.teachers.delete")) == 1
    assert (await client.post("/api/v1/auth/login", json={"username": old_account, "password": password})).status_code == 401
    batch = await upload(client, [teacher(new_account, "更新后的姓名")])
    values = {"teacher_replacements": {2: deletion["deletion_id"]}} if changed_account else {}
    done = await confirm(client, batch, **values)
    assert done["report"]["changed_count"] == 1
    new_id = UUID(done["report"]["imported"][0]["id"])
    assert new_id != original_id
    rebuilt = await test_db.get(User, new_id)
    assert rebuilt.must_change_password is initial_password
    assert verify_password(new_account if initial_password else password, rebuilt.password_hash)
    if not initial_password:
        assert rebuilt.password_hash == original_hash
    app.dependency_overrides.pop(get_current_user)
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + tokens["access_token"]})).status_code == 403
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})).status_code == 401
    login = await client.post("/api/v1/auth/login", json={"username": new_account, "password": new_account if initial_password else password})
    assert login.status_code == 200
    assert login.json()["user"]["account_type"] == "teacher"


@pytest.mark.asyncio
async def test_reimport_snapshot_is_single_use_and_school_scoped(client, test_db, actors):
    result = await confirm(client, await upload(client, [teacher("deleted-one")]))
    deletion = await lifecycle(client, "teachers", result["report"]["imported"][0]["id"])
    identifier = deletion["deletion_id"]
    actors["switch"]("foreign")
    assert (await client.get(P + "/roster/teachers/deletions")).json()["total"] == 0
    assert (await client.get(P + f"/roster/teachers/deletions/{identifier}")).status_code == 404
    foreign = await upload(client, [teacher("foreign-new")])
    await confirm(client, foreign, status=404, teacher_replacements={2: identifier})
    actors["switch"]("admin")
    batch = await upload(client, [teacher("changed-one"), teacher("changed-two")])
    await confirm(client, batch, status=422, teacher_replacements={2: identifier, 3: identifier})
    assert await test_db.scalar(select(User).where(User.username == "changed-one")) is None
    await confirm(client, batch, teacher_replacements={2: identifier})
    again = await upload(client, [teacher("changed-again")])
    await confirm(client, again, status=409, teacher_replacements={2: identifier})
    assert (await client.get(P + "/roster/teachers/deletions?search=deleted-one")).json()["total"] == 1
    assert (await client.get(P + "/roster/teachers/deletions?available=true")).json()["total"] == 0
    actors["switch"]("teacher")
    assert (await client.get(P + "/roster/teachers/deletions")).status_code == 403


@pytest.mark.asyncio
async def test_reimport_failure_keeps_snapshot_available_and_rolls_back_all_rows(client, test_db, actors, monkeypatch):
    from app.services import roster_workbench
    from app.core.errors import ApiError
    done = await confirm(client, await upload(client, [teacher("rollback-original")]))
    deletion = await lifecycle(client, "teachers", done["report"]["imported"][0]["id"])
    batch = await upload(client, [teacher("rollback-original"), teacher("fail-second")])
    original_grants = roster_workbench.grant_roles
    calls = 0
    async def fail_second(db, user, roles):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ApiError(422, "TEST_FAILURE", "合成失败")
        await original_grants(db, user, roles)
    monkeypatch.setattr(roster_workbench, "grant_roles", fail_second)
    await confirm(client, batch, status=422)
    assert await test_db.scalar(select(User).where(User.username == "rollback-original")) is None
    assert (await test_db.get(TeacherDeletion, UUID(deletion["deletion_id"]))).reimported_user_id is None


@pytest.mark.asyncio
async def test_login_automatically_resolves_same_username_by_password(client, test_db, actors):
    await classroom(client)
    s = await confirm(client, await upload(client, [student("same-login")], "students"))
    t = await confirm(client, await upload(client, [teacher("same-login")]))
    teacher_user = await test_db.get(User, UUID(t["report"]["imported"][0]["id"]))
    teacher_user.password_hash = get_password_hash("different-teacher-secret")
    teacher_user.must_change_password = False
    # Include another school using the same username to prove tenant resolution.
    foreign = User(id=uuid4(), school_id=actors["other_school"].id, username="same-login", password_hash=get_password_hash("foreign-secret"), account_type="parent")
    test_db.add(foreign)
    await test_db.commit()
    for password, kind, identifier in [("same-login", "student", str((await test_db.get(Student, UUID(s["report"]["imported"][0]["id"]))).user_id)), ("different-teacher-secret", "teacher", str(teacher_user.id)), ("foreign-secret", "parent", str(foreign.id))]:
        result = await client.post("/api/v1/auth/login", json={"username": " same-login ", "password": password})
        assert result.status_code == 200
        assert result.json()["user"]["id"] == identifier
        assert result.json()["user"]["account_type"] == kind
    wrong = await client.post("/api/v1/auth/login", json={"username": "same-login", "password": "wrong"})
    assert wrong.status_code == 401 and "identities" not in wrong.text


@pytest.mark.asyncio
async def test_login_identical_credentials_offer_only_verified_active_identities(client, test_db, actors):
    await classroom(client)
    await confirm(client, await upload(client, [student("identical")], "students"))
    await confirm(client, await upload(client, [teacher("identical")]))
    foreign = User(id=uuid4(), school_id=actors["other_school"].id, username="identical", password_hash=get_password_hash("another-password"))
    test_db.add(foreign)
    await test_db.commit()
    credentials = {"username": "identical", "password": "identical"}
    response = await client.post("/api/v1/auth/login", json=credentials)
    assert response.status_code == 409 and "access_token" not in response.text
    identities = response.json()["error"]["details"]["identities"]
    assert {i["account_type"] for i in identities} == {"teacher", "student"}
    for identity in identities:
        chosen = await client.post("/api/v1/auth/login", json={**credentials, "identity_id": identity["id"]})
        assert chosen.status_code == 200
        assert chosen.json()["user"]["id"] == identity["id"]
    for bad in ({"identity_id": str(foreign.id)}, {"identity_id": identities[0]["id"], "password": "wrong"}):
        assert (await client.post("/api/v1/auth/login", json={**credentials, **bad})).status_code == 401
    disabled = await test_db.get(User, UUID(identities[0]["id"]))
    disabled.status = "inactive"
    await test_db.commit()
    single = await client.post("/api/v1/auth/login", json=credentials)
    assert single.status_code == 200 and single.json()["user"]["id"] == identities[1]["id"]


@pytest.mark.asyncio
async def test_student_preflight_rejects_entire_batch_and_rechecks_classes(client, test_db, actors):
    room = await classroom(client)
    batch = await upload(client, [student("valid-row"), student("bad-row", 班级号="99班")], "students")
    assert batch["status"] == "invalid"
    await confirm(client, batch, status=409)
    assert await test_db.scalar(select(User).where(User.username == "valid-row")) is None
    good = await upload(client, [student("valid-row")], "students")
    from app.db.models import ImportedClass
    classroom_record = await test_db.get(ImportedClass, UUID(room["id"]))
    classroom_record.status = "inactive"
    await test_db.commit()
    await confirm(client, good, status=409)
    assert await test_db.scalar(select(User).where(User.username == "valid-row")) is None


@pytest.mark.asyncio
async def test_student_xls_uses_same_contract_and_atomic_import(client, test_db, actors):
    await classroom(client)
    content = (Path(__file__).parent / "fixtures/student_roster.xls").read_bytes()
    rows, issues = parse_excel("students", "学生.xls", base64.b64encode(content).decode())
    assert not issues and len(rows) == 2
    assert list(rows[0]["values"]) == STUDENT_COLUMNS
    assert rows[0]["values"]["中/高考号"] == "20250101"
    assert rows[0]["values"]["手机号"] == "131****0000"
    batch = await post(client, "/roster/students/imports", {"filename": "学生.xls", "content_base64": base64.b64encode(content).decode()})
    assert batch["report"]["ok"]
    done = await confirm(client, batch)
    assert done["report"]["success_count"] == 2
    for row in done["report"]["imported"]:
        item = await test_db.get(Student, UUID(row["id"]))
        assert item.student_no is None and len(item.profile_fields) == 30
    repeated = await post(client, "/roster/students/imports", {"filename": "学生.xls", "content_base64": base64.b64encode(content).decode()})
    assert repeated["status"] == "invalid"
    assert len(repeated["report"]["issues"]) == 2


@pytest.mark.asyncio
async def test_two_reimports_cannot_consume_same_deletion_concurrently(client, test_db, test_engine, actors):
    if test_engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row locks required")
    import asyncio
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.api.deps import AuthenticatedUser
    from app.core.errors import ApiError
    from app.schemas.roster import RosterConfirm
    from app.services.roster_workbench import confirm as confirm_service
    done = await confirm(client, await upload(client, [teacher("concurrent-original")]))
    deletion = await lifecycle(client, "teachers", done["report"]["imported"][0]["id"])
    batches = [await upload(client, [teacher("concurrent-a")]), await upload(client, [teacher("concurrent-b")])]
    actor = AuthenticatedUser(actors["admin"].id, actors["school"].id, "qa-admin", ["SCHOOL_ADMIN"])
    async def run(batch):
        async with AsyncSession(test_engine, expire_on_commit=False) as db:
            try:
                await confirm_service(db, actor, UUID(batch["id"]), RosterConfirm(expected_revision=1, teacher_replacements={2: UUID(deletion["deletion_id"])}))
                return 200
            except ApiError as error:
                await db.rollback()
                return error.status_code
    assert sorted(await asyncio.gather(*(run(batch) for batch in batches))) == [200, 409]
