"""Short IDs are stable platform identities, never login/student/exam numbers."""
import asyncio
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.db.models import PlatformPersonId, Student, User, School
from app.services.person_ids import resolve
from test_education_workbench import actors, post, P  # noqa: F401
from test_roster_workflows import teacher, upload, confirm
from test_student_r79 import seed_student, existing_fields, task_create, task_prepare, task_confirm
from test_teacher_r79 import delete_teachers, task_rows, upload_task, confirm_task


@pytest.mark.asyncio
async def test_short_ids_unique_across_types_schools_and_independent_of_business_fields(client, test_db, actors):
    sid = await seed_student(client, "90909090", "短号学生", **{"学号": "2026123456", "准考证号": "88776655", "中/高考号": "66554433"})
    student = await test_db.get(Student, sid)
    fields = await existing_fields(client, sid)
    number = fields["学生ID"]
    assert number == str(student.platform_id) and number.isascii() and number.isdigit() and 8 <= len(number) <= 10
    assert {fields["账号"], fields["学号"], fields["准考证号"], fields["中/高考号"], number} == {"90909090", "2026123456", "88776655", "66554433", number}
    assert len({fields["账号"], fields["学号"], fields["准考证号"], fields["中/高考号"], number}) == 5
    assert (await client.get(P + "/roster/students/records", params={"search": number})).json()["items"][0]["id"] == str(sid)
    assert (await client.get(P + f"/roster/students/records/{number}")).json()["id"] == str(sid)
    assert await resolve(test_db, student.school_id, "student", ["90909090", "2026123456", "88776655", "66554433"]) == {}
    teacher_batch = await confirm(client, await upload(client, [teacher("13900000001")]))
    teacher_row = teacher_batch["report"]["imported"][0]
    assert teacher_row["platform_id"] != number and teacher_row["platform_id"] != "13900000001"
    assert (await client.get(P + "/roster/teachers/records", params={"search": teacher_row["platform_id"]})).json()["items"][0]["id"] == teacher_row["id"]
    other_school = School(id=uuid4(), name="合成另一校", code=str(uuid4()))
    other = Student(id=uuid4(), school_id=other_school.id, name="合成同名", student_no=student.student_no)
    test_db.add_all([other_school, other])
    await test_db.commit()
    assert other.platform_id not in {student.platform_id, int(teacher_row["platform_id"])}
    assert await resolve(test_db, student.school_id, "student", [str(other.platform_id), teacher_row["platform_id"]]) == {}
    assert (await client.get(P + f"/roster/students/records/{other.platform_id}")).status_code == 404


@pytest.mark.asyncio
async def test_short_student_id_survives_archive_identity_promotion_and_status(client, test_db, actors):
    sid = await seed_student(client, "stable-account", "稳定身份", **{"学号": "20260001", "准考证号": "20269999"})
    student = await test_db.get(Student, sid)
    original_user_id, number = student.user_id, str(student.platform_id)
    fields = await existing_fields(client, number)
    fields["宿舍号"] = "改为201"
    archive = await task_prepare(client, await task_create(client, "archive", values=[fields]), identity_confirmed_ids=[number])
    await task_confirm(client, archive)
    for field, value in [("姓名", "更正姓名"), ("账号", "changed-account")]:
        task = await task_create(client, "identity", [number], field=field, new_value=value, reason="合成身份核验通过")
        await task_confirm(client, await task_prepare(client, task, identity_confirmed_ids=[number]))
    fields = await existing_fields(client, number)
    promotion = await task_create(client, "promotion", mode="current", values=[{"学生ID": number, "姓名": fields["姓名"], "账号": fields["账号"], "目标年级": "高中一年级", "目标班级号": "2班"}])
    await task_confirm(client, await task_prepare(client, promotion, identity_confirmed_ids=[number]))
    departed = await task_create(client, "status", [number], action="depart")
    await task_confirm(client, await task_prepare(client, departed, identity_confirmed_ids=[number]))
    restore = await task_create(client, "status", [number], action="restore", placements={number: {"grade": "高中一年级", "class_number": "2班"}})
    await task_confirm(client, await task_prepare(client, restore, identity_confirmed_ids=[number]))
    fields = await existing_fields(client, number)
    assert (fields["学生ID"], fields["姓名"], fields["账号"], fields["学号"], fields["准考证号"], fields["宿舍号"]) == (number, "更正姓名", "changed-account", "20260001", "20269999", "改为201")
    assert student.user_id == original_user_id and student.id == sid and str(student.platform_id) == number


@pytest.mark.asyncio
async def test_short_and_legacy_ids_cannot_duplicate_or_cross_person_types(client, test_db, actors):
    sid = await seed_student(client)
    fields = await existing_fields(client, sid)
    duplicated = await task_create(client, "archive", values=[fields, {**fields, "学生ID": str(sid)}])
    assert duplicated["status"] == "invalid" and len([row for row in duplicated["report"]["issues"] if row["error_type"] == "ID重复"]) == 2
    legacy = await task_create(client, "archive", values=[{**fields, "学生ID": str(sid), "宿舍号": "旧模板仍可办理"}])
    await task_confirm(client, await task_prepare(client, legacy))
    batch = await confirm(client, await upload(client, [teacher("13900000001")]))
    for number in (batch["report"]["imported"][0]["platform_id"], "0" + fields["学生ID"], "10000000000", "90909090"):
        invalid = await task_create(client, "archive", values=[{**(await existing_fields(client, sid)), "学生ID": number}])
        assert invalid["status"] == "invalid" and "ID缺失或不存在" in str(invalid["report"]["issues"])


@pytest.mark.asyncio
async def test_teacher_change_keeps_short_id_and_pure_delete_new_import_gets_new_id(client, test_db, actors):
    original = (await confirm(client, await upload(client, [teacher("13900000001")])))["report"]["imported"][0]
    deletion = await delete_teachers(client, [original["platform_id"]])
    assert deletion["snapshots"][0]["platform_id"] == original["platform_id"]
    rows = await task_rows(client, deletion["task_id"])
    rows[0]["教师姓名"] = "更新后的合成教师"
    updated = await confirm_task(client, await upload_task(client, deletion["task_id"], rows), teacher_replacements={2: original["platform_id"]})
    assert updated["report"]["imported"][0]["platform_id"] == original["platform_id"]
    assert updated["report"]["imported"][0]["id"] == original["id"]
    await delete_teachers(client, [original["platform_id"]], reason="depart")
    fresh = (await confirm(client, await upload(client, [teacher("13900000001")])))["report"]["imported"][0]
    assert fresh["platform_id"] != original["platform_id"]
    old_user = await test_db.get(User, UUID(original["id"]))
    assert str(old_user.platform_id) == original["platform_id"] and old_user.status == "deleted"


@pytest.mark.asyncio
async def test_deleted_student_number_reserved_and_reference_not_reassigned(client, test_db, actors):
    sid = await seed_student(client)
    number = (await existing_fields(client, sid))["学生ID"]
    task = await task_create(client, "deletion", [number], reason="合成误导入已核实")
    done = await task_confirm(client, await task_prepare(client, task, records_verified_ids=[number]))
    assert done["snapshots"][0]["platform_id"] == number and done["snapshots"][0]["fields"]["学生ID"] == number
    assert await test_db.get(Student, sid) is None
    mapping = await test_db.get(PlatformPersonId, int(number))
    assert mapping.entity_id == sid
    new_id = await seed_student(client)
    assert str((await test_db.get(Student, new_id)).platform_id) != number
    assert (await client.get(P + f"/roster/students/records/{number}")).status_code == 404


@pytest.mark.asyncio
async def test_parallel_allocations_are_unique_and_within_ten_digits(test_db, test_engine, actors):
    if test_engine.dialect.name != "postgresql":
        pytest.skip("Independent PostgreSQL identity sequence sessions required")
    school_id = (await test_db.get(Student, actors["student"].id)).school_id
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async def create(index):
        async with factory() as session:
            item = Student(id=uuid4(), school_id=school_id, name=f"合成并发{index}")
            session.add(item)
            await session.commit()
            return item.platform_id
    numbers = await asyncio.gather(*(create(index) for index in range(16)))
    assert len(set(numbers)) == 16 and all(10000001 <= value <= 9999999999 for value in numbers)
    assert await test_db.scalar(select(func.count()).select_from(PlatformPersonId).where(PlatformPersonId.id.in_(numbers))) == 16
