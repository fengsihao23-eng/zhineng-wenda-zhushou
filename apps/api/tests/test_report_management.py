"""Real HTTP/SQL acceptance for the r86 report prototype. Synthetic PDFs only."""
import base64
import copy
import io
from uuid import UUID, uuid4
import pytest
from PIL import Image, ImageDraw
from sqlalchemy import select, func
from app.db.models import User, Student, StudentSubjectScore
from app.db.models.report_management import ManagedReport, ReportFile, ReportOperation
from app.db.models.exam_management import ExamAdministration, ExamQueryGrant
from app.services import report_management as service
from app.schemas.report_management import Classification
from test_education_workbench import actors  # noqa: F401
from test_exam_management import exam_people, create, switch, permission, import_score, ROOT as EXAMS  # noqa: F401

ROOT = "/api/v1/platform/education/report-management"


def pdf_bytes(text="SYNTHETIC REPORT v1", pages=2):
    images = []
    for number in range(pages):
        image = Image.new("RGB", (595, 842), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((20, 20, 575, 120), fill="#efedfd")
        draw.text((40, 60), text + " / page " + str(number + 1), fill="#202736")
        images.append(image)
    output = io.BytesIO()
    images[0].save(output, format="PDF", save_all=True, append_images=images[1:])
    return output.getvalue()


def upload(filename, content=None):
    return {"filename": filename, "content_base64": base64.b64encode(content or pdf_bytes()).decode()}


async def post(client, path, body, status=200, key=None):
    response = await client.post(ROOT + path, json=body, headers={"Idempotency-Key": str(key or uuid4())})
    assert response.status_code == status, response.text
    return response.json()


async def report_row(client, exam, report_type="student", student_index=0, subject_index=0, category="diagnostic"):
    config = (await client.get(ROOT + "/exams/" + exam["id"])).json()
    subject = config["subjects"][subject_index]
    sid = subject["student_ids"][student_index]
    person = config["snapshots"][sid]
    kind = service.KINDS[report_type]
    target = sid if kind == "student" else service.class_key(person) if kind == "class" else person["grade"] if kind == "grade" else "school"
    naming = {"category": category, "report_type": report_type, "subject_ids": [subject["subject_id"]]}
    filename = service.filename_for(config["exam_code"], config, Classification(**naming), target)
    return {**naming, "target_key": target, "file": upload(filename), "naming": naming, "previewed": True}


async def save(client, exam, rows, key=None):
    body = {"exam_id": exam["id"], "expected_exam_revision": exam["revision"], "reports": rows}
    preview = await post(client, "/batches/preview", body)
    return await post(client, "/batches", {**body, "preview_hash": preview["preview_hash"]}, key=key)


@pytest.mark.asyncio
async def test_all_report_types_naming_real_pdf_preview_and_no_implicit_grants(client, test_db, actors, exam_people):
    exam = await create(client, exam_people)
    opts = (await client.get(ROOT + "/options")).json()
    assert opts["upload_rule"] == "single_subject" and opts["exams"][0]["exam_code"] == exam["exam_id"]
    for report_type in ["student", "classAll", "classSubject", "gradeAll", "gradeSubject", "school", "essay"]:
        row = await report_row(client, exam, report_type, subject_index=1 if report_type == "essay" else 0,
                               category="essay" if report_type == "essay" else "diagnostic")
        names = await client.post(ROOT + "/exams/" + exam["id"] + "/naming-list", json=row["naming"])
        assert names.status_code == 200 and row["file"]["filename"] in names.content.decode("utf-8-sig")
        inspected = await post(client, "/inspect-pdf", row["file"])
        assert inspected["page_count"] == 2
        png = await client.post(ROOT + "/pdf-preview?page=2", json=row["file"])
        assert png.status_code == 200 and png.content.startswith(b"\x89PNG")
        result = await save(client, exam, [row])
        report = result["reports"][0]
        assert report["version"] == 1 and report["type_name"] == service.TYPES[report_type]
        original = await client.get(ROOT + "/" + report["id"] + "/file")
        assert original.content == base64.b64decode(row["file"]["content_base64"])
    assert await test_db.scalar(select(func.count()).select_from(ManagedReport)) == 7
    assert await test_db.scalar(select(func.count()).select_from(ExamQueryGrant)) == 0
    assert (await client.get(ROOT)).json()["counts"] == {"all": 7, "diagnostic": 6, "essay": 1}


@pytest.mark.asyncio
async def test_batch_preview_cancel_naming_invalid_pdf_and_atomic_duplicates(client, test_db, actors, exam_people):
    exam = await create(client, exam_people)
    row = await report_row(client, exam)
    body = {"exam_id": exam["id"], "expected_exam_revision": exam["revision"], "reports": [row]}
    checked = await post(client, "/batches/preview", body)
    assert await test_db.scalar(select(func.count()).select_from(ReportFile)) == 0
    for invalid in [
        {**row, "file": upload("随便命名.pdf")},
        {**row, "file": upload(row["file"]["filename"], b"%PDF-1.7\ninvalid")},
        {**row, "previewed": False},
        {**row, "target_key": str(uuid4())},
        {**row, "subject_ids": [str(uuid4())]},
        {**row, "subject_ids": [s["subject_id"] for s in exam["subjects"]]},
        {**row, "category": "essay", "report_type": "essay"},
    ]:
        response = await post(client, "/batches", {**body, "reports": [row, invalid], "preview_hash": checked["preview_hash"]}, 422)
        assert response["error"]["code"] == "REPORT_INVALID"
        assert await test_db.scalar(select(func.count()).select_from(ManagedReport)) == 0
        assert await test_db.scalar(select(func.count()).select_from(ReportOperation)) == 0
    await post(client, "/batches", {**body, "preview_hash": "stale"}, 409)
    await save(client, exam, [row])
    second = await report_row(client, exam, student_index=1)
    await post(client, "/batches/preview", {**body, "reports": [second, row]}, 422)
    assert await test_db.scalar(select(func.count()).select_from(ManagedReport)) == 1
    assert await test_db.scalar(select(func.count()).select_from(ReportOperation)) == 1


@pytest.mark.asyncio
async def test_same_batch_mixed_categories_manual_attribution_and_idempotency(client, test_db, actors, exam_people):
    exam = await create(client, exam_people)
    diagnostic = await report_row(client, exam, subject_index=1)
    essay = await report_row(client, exam, report_type="essay", category="essay", subject_index=1)
    # The filename is validated against its original classification. The reviewer
    # may correct the saved target without renaming or overwriting a report.
    diagnostic["target_key"] = exam["subjects"][1]["student_ids"][1]
    body = {"exam_id": exam["id"], "expected_exam_revision": exam["revision"], "reports": [diagnostic, essay]}
    preview = await post(client, "/batches/preview", body)
    key = uuid4()
    first = await post(client, "/batches", {**body, "preview_hash": preview["preview_hash"]}, key=key)
    again = await post(client, "/batches", {**body, "preview_hash": preview["preview_hash"]}, key=key)
    assert again == first and first["count"] == 2
    assert first["reports"][0]["target_key"] == diagnostic["target_key"]
    assert await test_db.scalar(select(func.count()).select_from(ReportFile)) == 2
    assert await test_db.scalar(select(func.count()).select_from(ReportOperation)) == 1
    await post(client, "/batches", {**body, "preview_hash": "changed"}, 409, key=key)


@pytest.mark.asyncio
async def test_frozen_roster_same_names_filename_account_and_invalid_scope(client, test_db, actors, exam_people):
    exam = await create(client, exam_people)
    row = await report_row(client, exam)
    config = (await client.get(ROOT + "/exams/" + exam["id"])).json()
    sid = row["target_key"]
    person = config["snapshots"][sid]
    by_account = row["file"]["filename"].replace("_" + person["platform_id"] + "_", "_" + person["account"] + "_")
    row["file"]["filename"] = by_account
    student = await test_db.get(Student, UUID(sid))
    student.name = "后续改名"
    student.status = "graduated"
    await test_db.commit()
    result = await save(client, exam, [row])
    record = result["reports"][0]
    assert "同名学生" in record["target_label"] and "后续改名" not in record["target_label"]
    assert person["grade"] in record["grades"]
    # Historical report access follows account login and the saved exam grant,
    # rather than reusing the rule for choosing NEW exam participants.
    test_db.add(ExamQueryGrant(school_id=actors["school"].id, exam_id=UUID(exam["id"]), recipient_kind="student",
        recipient_id=actors["student"].id, student_id=actors["student"].id,
        subject_id=UUID(row["subject_ids"][0]), content_type="student"))
    await test_db.commit()
    switch(actors, test_db, "student")
    history = await client.get(EXAMS + "/my-exams/" + exam["id"])
    assert history.status_code == 200, history.text
    assert [r["id"] for r in history.json()["reports"]] == [record["id"]]
    switch(actors, test_db, "admin")
    admin = await test_db.get(ExamAdministration, UUID(exam["id"]))
    configuration = copy.deepcopy(admin.configuration)
    configuration["subjects"][0]["student_ids"] = configuration["subjects"][0]["student_ids"][:1]
    admin.configuration = configuration; admin.revision += 1
    await test_db.commit()
    body = {"exam_id": exam["id"], "expected_exam_revision": exam["revision"], "reports": [row]}
    await post(client, "/batches/preview", body, 409)


@pytest.mark.asyncio
async def test_replace_preserves_identity_history_failure_conflict_and_retry(client, test_db, actors, exam_people):
    exam = await create(client, exam_people)
    row = await report_row(client, exam)
    original = (await save(client, exam, [row]))["reports"][0]
    path = "/" + original["id"] + "/replace"
    body = {"expected_version": 1, "file": upload("新版无需原命名.pdf", pdf_bytes("SYNTHETIC REPORT v2")), "reason": "修正诊断内容", "previewed": True, "confirmed": True}
    for bad in [{**body, "previewed": False}, {**body, "confirmed": False}, {**body, "file": upload("bad.pdf", b"broken")}]:
        await post(client, path, bad, 422)
        assert (await client.get(ROOT + "/" + original["id"])).json()["version"] == 1
    key = uuid4()
    updated = await post(client, path, body, key=key)
    repeated = await post(client, path, body, key=key)
    assert updated == repeated
    await post(client, path, body, 409)
    detail = (await client.get(ROOT + "/" + original["id"])).json()
    assert detail["version"] == 2 and [v["version"] for v in detail["versions"]] == [2, 1]
    for field in ["id", "exam_id", "report_code", "category", "report_type", "subject_ids", "target_key", "people", "coverage"]:
        assert detail[field] == original[field]
    old = await client.get(ROOT + "/" + original["id"] + "/file?version=1")
    assert old.content == base64.b64decode(row["file"]["content_base64"])
    assert await test_db.scalar(select(func.count()).select_from(ReportOperation)) == 2


@pytest.mark.asyncio
async def test_bulk_delete_cancel_stale_and_rollback_remove_all_versions_keep_other_data(client, test_db, actors, exam_people):
    exam = await create(client, exam_people)
    rows = [await report_row(client, exam, student_index=i) for i in [0, 1]]
    reports = (await save(client, exam, rows))["reports"]
    body = {"reports": [{"id": r["id"], "expected_version": 1} for r in reports], "reason": "清理误传", "confirmed": False}
    await post(client, "/delete", body, 422)
    assert (await client.get(ROOT)).json()["total"] == 2
    stale = {**body, "confirmed": True, "reports": [body["reports"][0], {**body["reports"][1], "expected_version": 9}]}
    await post(client, "/delete", stale, 409)
    assert (await client.get(ROOT)).json()["total"] == 2
    key = uuid4()
    deleted = await post(client, "/delete", {**body, "confirmed": True}, key=key)
    assert deleted == await post(client, "/delete", {**body, "confirmed": True}, key=key)
    assert (await client.get(ROOT)).json()["total"] == 0
    for report in reports:
        assert (await client.get(ROOT + "/" + report["id"] + "/file")).status_code == 409
    assert await test_db.scalar(select(func.count()).select_from(ReportFile)) == 0
    assert await test_db.scalar(select(func.count()).select_from(ExamAdministration)) == 1
    assert await test_db.scalar(select(func.count()).select_from(Student)) == 3
    assert await test_db.scalar(select(func.count()).select_from(ReportOperation)) == 2
    # A deleted identity may be uploaded again with a new report ID.
    again = await save(client, exam, [rows[0]])
    assert again["reports"][0]["id"] != reports[0]["id"]


@pytest.mark.asyncio
async def test_student_and_teacher_queries_full_scope_only_latest_no_cross_person_or_school(client, test_db, actors, exam_people):
    exam = await create(client, exam_people)
    personal = await report_row(client, exam)
    another = await report_row(client, exam, student_index=1)
    group = await report_row(client, exam, "classAll")
    reports = (await save(client, exam, [personal, another, group]))["reports"]
    personal_id, other_id, group_id = [r["id"] for r in reports]
    switch(actors, test_db, "student")
    assert (await client.get(EXAMS + "/my-exams/" + exam["id"])).status_code == 404
    assert (await client.get(ROOT)).status_code == 403
    switch(actors, test_db, "admin")
    # Grant the personal report and only one of the two students covered by the
    # class report. A partial class grant must never expose the class PDF.
    for content in ["diagnosis:student", "diagnosis:classAll"]:
        test_db.add(ExamQueryGrant(school_id=actors["school"].id, exam_id=UUID(exam["id"]), recipient_kind="teacher", recipient_id=actors["teacher"].id,
            student_id=UUID(personal["target_key"]), subject_id=UUID(personal["subject_ids"][0]), content_type=content))
    test_db.add(ExamQueryGrant(school_id=actors["school"].id, exam_id=UUID(exam["id"]), recipient_kind="student", recipient_id=actors["student"].id,
        student_id=actors["student"].id, subject_id=UUID(personal["subject_ids"][0]), content_type="student"))
    await test_db.commit()
    check = await client.get(ROOT + f"/access-check?exam_id={exam['id']}&kind=teacher&recipient_id={actors['teacher'].id}")
    decisions = {r["id"]: r for r in check.json()["reports"]}
    assert decisions[personal_id]["allowed"] and not decisions[group_id]["allowed"]
    switch(actors, test_db, "teacher")
    result = (await client.get(EXAMS + "/my-exams/" + exam["id"])).json()
    assert [r["id"] for r in result["reports"]] == [personal_id]
    assert (await client.get(EXAMS + f"/my-exams/{exam['id']}/reports/{group_id}/original?view_type=classAll")).status_code == 404
    assert (await client.get(ROOT + "/" + personal_id + "/file?version=1")).status_code == 403
    switch(actors, test_db, "student")
    result = (await client.get(EXAMS + "/my-exams/" + exam["id"])).json()
    assert [r["id"] for r in result["reports"]] == [personal_id]
    source = EXAMS + f"/my-exams/{exam['id']}/reports/{personal_id}/original"
    assert (await client.get(source)).content == base64.b64decode(personal["file"]["content_base64"])
    assert (await client.get(source + "?page=2")).content.startswith(b"\x89PNG")
    assert (await client.get(EXAMS + f"/my-exams/{exam['id']}/reports/{other_id}/original")).status_code == 404
    switch(actors, test_db, "admin")
    newer = upload("new.pdf", pdf_bytes("ONLY CURRENT v2"))
    await post(client, "/" + personal_id + "/replace", {"expected_version": 1, "file": newer, "reason": "新版", "previewed": True, "confirmed": True})
    switch(actors, test_db, "student")
    # A guessed historical version parameter cannot select a past file.
    assert (await client.get(source + "?version=1")).content == base64.b64decode(newer["content_base64"])
    switch(actors, test_db, "admin")
    await post(client, "/delete", {"reports": [{"id": personal_id, "expected_version": 2}], "reason": "误传", "confirmed": True})
    switch(actors, test_db, "student")
    assert (await client.get(source)).status_code == 404
    switch(actors, test_db, "foreign")
    assert (await client.get(ROOT)).json()["total"] == 0
    assert (await client.get(ROOT + "/" + other_id)).status_code == 404


@pytest.mark.asyncio
async def test_complete_group_authorization_revocation_and_disabled_login(client, test_db, actors, exam_people):
    exam = await create(client, exam_people)
    group = await report_row(client, exam, "school")
    report = (await save(client, exam, [group]))["reports"][0]
    for sid in exam["subjects"][0]["student_ids"]:
        test_db.add(ExamQueryGrant(school_id=actors["school"].id, exam_id=UUID(exam["id"]), recipient_kind="teacher", recipient_id=actors["teacher"].id,
            student_id=UUID(sid), subject_id=UUID(group["subject_ids"][0]), content_type="diagnosis:school"))
    await test_db.commit()
    path = ROOT + f"/access-check?exam_id={exam['id']}&kind=teacher&recipient_id={actors['teacher'].id}"
    assert (await client.get(path)).json()["reports"][0]["allowed"]
    assert not (await client.get(path + "&login=false")).json()["reports"][0]["allowed"]
    user = await test_db.get(User, actors["teacher"].id); user.status = "inactive"; await test_db.commit()
    assert not (await client.get(path)).json()["reports"][0]["allowed"]
    user.status = "active"; await test_db.commit()
    switch(actors, test_db, "teacher")
    result = await client.get(EXAMS + "/my-exams/" + exam["id"] + "?view_type=school")
    assert [r["id"] for r in result.json()["reports"]] == [report["id"]]
    switch(actors, test_db, "admin")
    from sqlalchemy import delete
    await test_db.execute(delete(ExamQueryGrant).where(ExamQueryGrant.recipient_id == actors["teacher"].id)); await test_db.commit()
    switch(actors, test_db, "teacher")
    assert (await client.get(EXAMS + f"/my-exams/{exam['id']}/reports/{report['id']}/original?view_type=school")).status_code == 404


@pytest.mark.asyncio
async def test_school_viewer_and_exam_admin_cannot_maintain_reports(client, test_db, actors, exam_people):
    from app.main import app
    from app.api.deps import get_current_user, AuthenticatedUser
    exam = await create(client, exam_people)
    row = await report_row(client, exam)
    for role in ["TEACHER", "STUDENT", "EXAM_ADMIN", "QA", "SCHOOL_VIEWER"]:
        app.dependency_overrides[get_current_user] = lambda role=role: AuthenticatedUser(actors["admin"].id, actors["school"].id, "readonly", [role])
        await post(client, "/batches", {"exam_id": exam["id"], "expected_exam_revision": exam["revision"], "reports": [row]}, 403)
    assert await test_db.scalar(select(func.count()).select_from(ManagedReport)) == 0
