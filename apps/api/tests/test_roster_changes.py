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
async def test_login_automatically_resolves_same_username_by_password(client, test_db, actors):
    await classroom(client)
    s = await confirm(client, await upload(client, [student("13800000027")], "students"))
    t = await confirm(client, await upload(client, [teacher("13800000027")]))
    teacher_user = await test_db.get(User, UUID(t["report"]["imported"][0]["id"]))
    teacher_user.password_hash = get_password_hash("different-teacher-secret")
    teacher_user.must_change_password = False
    # Include another school using the same username to prove tenant resolution.
    foreign = User(id=uuid4(), school_id=actors["other_school"].id, username="13800000027", password_hash=get_password_hash("foreign-secret"), account_type="parent")
    test_db.add(foreign)
    await test_db.commit()
    for password, kind, identifier in [("13800000027", "student", str((await test_db.get(Student, UUID(s["report"]["imported"][0]["id"]))).user_id)), ("different-teacher-secret", "teacher", str(teacher_user.id)), ("foreign-secret", "parent", str(foreign.id))]:
        result = await client.post("/api/v1/auth/login", json={"username": " 13800000027 ", "password": password})
        assert result.status_code == 200
        assert result.json()["user"]["id"] == identifier
        assert result.json()["user"]["account_type"] == kind
    wrong = await client.post("/api/v1/auth/login", json={"username": "13800000027", "password": "wrong"})
    assert wrong.status_code == 401 and "identities" not in wrong.text


@pytest.mark.asyncio
async def test_login_identical_credentials_offer_only_verified_active_identities(client, test_db, actors):
    await classroom(client)
    await confirm(client, await upload(client, [student("13800000017")], "students"))
    await confirm(client, await upload(client, [teacher("13800000017")]))
    foreign = User(id=uuid4(), school_id=actors["other_school"].id, username="13800000017", password_hash=get_password_hash("another-password"))
    test_db.add(foreign)
    await test_db.commit()
    credentials = {"username": "13800000017", "password": "13800000017"}
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
async def test_student_preflight_keeps_batch_atomic_without_class_dictionary_matching(client, test_db, actors):
    batch = await upload(client, [student("valid-row"), student("bad-row", 姓名="")], "students")
    assert batch["status"] == "invalid"
    await confirm(client, batch, status=409)
    assert await test_db.scalar(select(User).where(User.username == "valid-row")) is None
    room = await classroom(client)
    good = await upload(client, [student("valid-row")], "students")
    from app.db.models import ImportedClass
    classroom_record = await test_db.get(ImportedClass, UUID(room["id"]))
    classroom_record.status = "inactive"
    await test_db.commit()
    done = await confirm(client, good)
    assert done["report"]["success_count"] == 1


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
