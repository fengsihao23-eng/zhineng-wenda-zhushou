"""Synthetic-only business journeys for the education alignment workbench."""
import base64
import csv
import io
from types import SimpleNamespace
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4, UUID
import pytest
from sqlalchemy import select, func
from app.main import app
from app.api.deps import get_current_user, AuthenticatedUser
from app.db.models import (
    School,
    User,
    Role,
    UserRole,
    Student,
    Subject,
    Exam,
    StudentExamScore,
    StudentSubjectScore,
    QuestionScore,
    StudentEntitlement,
)
from app.db.models.education import (
    SourceRecord,
    QuestionVersion,
    ImportWorkspace,
    ReviewEntry,
    ReviewRecord,
    HandoffMessage,
)

P = "/api/v1/platform/education"


@pytest.fixture
async def actors(test_db, sample_school_id, sample_student_id):
    student = await test_db.get(Student, sample_student_id)
    admin = User(
        id=uuid4(),
        school_id=sample_school_id,
        username=f"qa-admin-{uuid4()}",
        password_hash="unused",
        display_name="合成管理员",
    )
    teacher = User(
        id=uuid4(),
        school_id=sample_school_id,
        username=f"qa-teacher-{uuid4()}",
        password_hash="unused",
        display_name="合成教师",
    )
    subject = Subject(
        id=uuid4(),
        school_id=sample_school_id,
        code="MATH",
        name="数学",
        external_subject_id="math",
        source_system="native",
    )
    other_school = School(id=uuid4(), code=f"OTHER-{uuid4()}", name="隔离学校")
    test_db.add_all([admin, teacher, subject, other_school])
    await test_db.flush()
    role = Role(id=uuid4(), code="TEACHER", name="教师")
    srole = Role(id=uuid4(), code="STUDENT", name="学生")
    test_db.add_all([role, srole])
    await test_db.flush()
    test_db.add_all(
        [
            UserRole(user_id=teacher.id, role_id=role.id, school_id=sample_school_id),
            UserRole(
                user_id=student.user_id, role_id=srole.id, school_id=sample_school_id
            ),
        ]
    )
    student.external_student_id = "student-a"
    student.student_no = "A001"
    await test_db.commit()
    school = await test_db.get(School, sample_school_id)
    admin = SimpleNamespace(id=admin.id)
    teacher = SimpleNamespace(id=teacher.id)
    student = SimpleNamespace(id=student.id, user_id=student.user_id)
    subject = SimpleNamespace(id=subject.id)
    other_school = SimpleNamespace(id=other_school.id)
    school = SimpleNamespace(id=school.id, code=school.code)
    current = {
        "actor": AuthenticatedUser(
            admin.id, sample_school_id, "qa-admin", ["SCHOOL_ADMIN"]
        )
    }
    app.dependency_overrides[get_current_user] = lambda: current["actor"]

    def switch(role="admin"):
        current["actor"] = {
            "admin": AuthenticatedUser(
                admin.id, sample_school_id, "qa-admin", ["SCHOOL_ADMIN"]
            ),
            "student": AuthenticatedUser(
                student.user_id, sample_school_id, "qa-student", ["STUDENT"]
            ),
            "teacher": AuthenticatedUser(
                teacher.id, sample_school_id, "qa-teacher", ["TEACHER"]
            ),
            "qa": AuthenticatedUser(admin.id, sample_school_id, "qa-admin", ["QA"]),
            "foreign": AuthenticatedUser(
                admin.id, other_school.id, "qa-foreign", ["SCHOOL_ADMIN"]
            ),
        }[role]

    return {
        "switch": switch,
        "student": student,
        "admin": admin,
        "teacher": teacher,
        "subject": subject,
        "school": school,
        "other_school": other_school,
    }


async def post(client, path, body, key=None, status=200):
    r = await client.post(
        P + path, json=body, headers={"Idempotency-Key": str(key or uuid4())}
    )
    assert r.status_code == status, r.text
    return r.json()


def image_upload():
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (400, 500), "white")
    ImageDraw.Draw(image).text((40, 60), "QA: 2 + 2 = ?", fill="black")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return {
        "filename": "synthetic-paper.png",
        "content_base64": base64.b64encode(output.getvalue()).decode(),
    }


async def setup_exam(client, actors):
    exam = await post(
        client,
        "/school/exams",
        {
            "external_exam_id": str(uuid4()),
            "name": "合成测试考试",
            "exam_type": "test",
            "start_date": "2026-09-01",
        },
    )
    r = await client.put(
        P + f"/exams/{exam['id']}/subjects",
        json={"subject_id": str(actors["subject"].id), "full_score": 100},
    )
    assert r.status_code == 200, r.text
    return exam


async def setup_paper(client, actors):
    exam = await setup_exam(client, actors)
    asset = await post(client, "/assets", image_upload())
    body = {
        "title": "合成数学试卷",
        "exam_id": exam["id"],
        "subject_id": str(actors["subject"].id),
        "asset_id": asset["id"],
    }
    paper = await post(client, "/papers", body)
    return exam, asset, paper


async def setup_question(
    client, actors, kind="standalone", parent_id=None, tag_ids=None
):
    body = {
        "subject_id": str(actors["subject"].id),
        "kind": kind,
        "parent_id": parent_id,
        "title": f"合成{kind}",
        "stem": "2 + 2 = ?",
        "answer": "4",
        "explanation": "将两组各两个合并。",
        "tag_ids": tag_ids or [],
    }
    q = await post(client, "/questions", body)
    return await post(
        client, f"/questions/{q['id']}/publish", {"expected_revision": q["revision"]}
    )


async def add_scores(test_db, actors, exam, question=None):
    school = actors["school"].id
    student = actors["student"].id
    subject = actors["subject"].id
    exam_id = UUID(exam["id"])
    total = StudentExamScore(
        id=uuid4(),
        school_id=school,
        student_id=student,
        exam_id=exam_id,
        total_score=80,
        full_score=100,
    )
    sub = StudentSubjectScore(
        id=uuid4(),
        school_id=school,
        student_id=student,
        exam_id=exam_id,
        subject_id=subject,
        score=80,
        full_score=100,
    )
    score = QuestionScore(
        id=uuid4(),
        school_id=school,
        student_id=student,
        exam_id=exam_id,
        subject_id=subject,
        question_no="1",
        score=2,
        full_score=5,
        lost_score=3,
        question_id=UUID(question["id"]) if question else None,
        question_version_id=UUID(question["versions"][0]["id"]) if question else None,
    )
    test_db.add_all([total, sub, score])
    await test_db.commit()
    return tuple(SimpleNamespace(id=row.id) for row in (total, sub, score))


@pytest.mark.asyncio
async def test_roster_permissions_binding_and_class_aggregation(
    client, test_db, actors
):
    key = uuid4()
    body = {"external_class_id": "class-a", "name": "合成一班"}
    classroom = await post(client, "/school/classes", body, key)
    assert (await post(client, "/school/classes", body, key))["id"] == classroom["id"]
    await post(client, "/school/classes", {**body, "name": "冲突"}, key, status=409)
    student_row = await test_db.get(Student, actors["student"].id)
    student_row.class_id = UUID(classroom["id"])
    await test_db.commit()
    assignment = {
        "teacher_user_id": str(actors["teacher"].id),
        "class_id": classroom["id"],
        "subject_id": str(actors["subject"].id),
        "starts_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
    }
    grant = await post(client, "/school/teaching", assignment)
    exam = await setup_exam(client, actors)
    await add_scores(test_db, actors, exam)
    actors["switch"]("teacher")
    assert (await client.get(P + "/school/classes")).json()["total"] == 1
    report = await client.get(
        P
        + f"/class-analysis?class_id={classroom['id']}&subject_id={actors['subject'].id}&exam_id={exam['id']}"
    )
    assert report.status_code == 200, report.text
    assert report.json()["sample_size"] == 1 and report.json()["average"] == 80
    assert "name" not in report.json()["students"][0]
    assert (await client.post(P + "/school/classes", json=body)).status_code == 403
    actors["switch"]("admin")
    r = await client.put(
        P + f"/school/classes/{classroom['id']}",
        json={"name": body["name"], "status": "inactive"},
    )
    assert r.status_code == 409
    await test_db.rollback()
    r = await client.put(
        P + f"/school/teaching/{grant['id']}", json={**assignment, "status": "inactive"}
    )
    assert r.status_code == 200, r.text
    actors["switch"]("teacher")
    assert (await client.get(P + "/school/classes")).json()["total"] == 0
    assert (
        await client.get(
            P
            + f"/class-analysis?class_id={classroom['id']}&subject_id={actors['subject'].id}&exam_id={exam['id']}"
        )
    ).status_code == 404
    actors["switch"]("qa")
    assert (await client.post(P + "/school/classes", json=body)).status_code == 403
    actors["switch"]("student")
    assert (await client.get(P + "/school/classes")).status_code == 403


@pytest.mark.asyncio
async def test_private_original_versions_and_asset_permissions(client, test_db, actors):
    exam, asset, paper = await setup_paper(client, actors)
    old_version = paper["versions"][0]
    r = await client.get(P + f"/assets/{asset['id']}?page=1")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"] == "no-store"
    key = uuid4()
    body = {"asset_id": asset["id"], "expected_revision": paper["revision"]}
    new = await post(client, f"/papers/{paper['id']}/versions", body, key)
    assert len(new["versions"]) == 2 and new["versions"][1]["id"] == old_version["id"]
    assert (
        len(
            (await post(client, f"/papers/{paper['id']}/versions", body, key))[
                "versions"
            ]
        )
        == 2
    )
    await post(
        client,
        "/assets",
        {"filename": "../bad.png", "content_base64": image_upload()["content_base64"]},
        status=422,
    )
    await post(
        client,
        "/assets",
        {"filename": "bad.pdf", "content_base64": image_upload()["content_base64"]},
        status=422,
    )
    actors["switch"]("student")
    assert (await client.get(P + f"/assets/{asset['id']}")).status_code == 404
    actors["switch"]("admin")
    await add_scores(test_db, actors, exam)
    actors["switch"]("student")
    assert (await client.get(P + f"/assets/{asset['id']}")).status_code == 200
    actors["switch"]("foreign")
    assert (await client.get(P + f"/papers/{paper['id']}")).status_code == 404
    assert (await client.get(P + f"/assets/{asset['id']}")).status_code == 404


@pytest.mark.asyncio
async def test_question_hierarchy_tags_reference_guard_review_readback(
    client, test_db, actors
):
    tag = await post(
        client,
        "/taxonomy",
        {"subject_id": str(actors["subject"].id), "name": "合成加法", "kind": "knowledge"},
    )
    material = await setup_question(client, actors, "material")
    major = await setup_question(client, actors, "major", material["id"])
    minor = await setup_question(client, actors, "minor", major["id"], [tag["id"]])
    assert (await client.get(P + f"/questions/{major['id']}")).json()["children"][0][
        "id"
    ] == minor["id"]
    await post(
        client,
        "/questions",
        {
            "subject_id": str(actors["subject"].id),
            "kind": "minor",
            "title": "非法层级",
            "stem": "x",
        },
        status=422,
    )
    child = await post(
        client,
        "/taxonomy",
        {
            "subject_id": str(actors["subject"].id),
            "name": "子节点",
            "parent_id": tag["id"],
        },
    )
    r = await client.put(
        P + f"/taxonomy/{tag['id']}",
        json={
            "subject_id": str(actors["subject"].id),
            "name": "循环",
            "kind": "knowledge",
            "parent_id": child["id"],
            "expected_revision": tag["revision"],
        },
    )
    assert r.status_code == 422
    exam = await setup_exam(client, actors)
    _, _, score = await add_scores(test_db, actors, exam, minor)
    result = await post(
        client, "/questions/batch", {"ids": [minor["id"]], "action": "delete"}
    )
    assert result["items"][0]["code"] == "RESOURCE_REFERENCED"
    await post(client, f"/taxonomy/{tag['id']}/delete", {}, status=409)
    actors["switch"]("student")
    detail = (await client.get(P + f"/student/mistakes/{score.id}")).json()
    assert (
        detail["question"]["stem"] == "2 + 2 = ?"
        and len(detail["question"]["parents"]) == 2
    )
    review = await post(client, "/student/reviews", {"score_id": str(score.id)})
    assert (await post(client, "/student/reviews", {"score_id": str(score.id)}))[
        "id"
    ] == review["id"]
    record_key = uuid4()
    body = {"correction": "我重新合并两组，结果为四。", "mastery": "reviewing"}
    saved = await post(
        client, f"/student/reviews/{review['id']}/records", body, record_key
    )
    assert saved["records"][0]["correction"] == body["correction"]
    assert (
        len(
            (
                await post(
                    client, f"/student/reviews/{review['id']}/records", body, record_key
                )
            )["records"]
        )
        == 1
    )
    assert (await client.get(P + f"/student/reviews/{review['id']}")).json()[
        "mastery"
    ] == "reviewing"
    actors["switch"]("admin")
    replacement = await post(
        client,
        f"/questions/{minor['id']}/versions",
        {"expected_revision": minor["revision"], "stem": "改版后的题干", "answer": "x"},
    )
    assert replacement["versions"][0]["stem"] == "改版后的题干"
    actors["switch"]("student")
    assert (await client.get(P + f"/student/mistakes/{score.id}")).json()["question"][
        "stem"
    ] == "2 + 2 = ?"
    actors["switch"]("admin")
    unreferenced = await setup_question(client, actors)
    assert (
        await post(
            client,
            "/questions/batch",
            {"ids": [unreferenced["id"], minor["id"]], "action": "delete"},
        )
    )["items"][0]["ok"]
    assert (
        await post(
            client,
            "/questions/batch",
            {"ids": [unreferenced["id"]], "action": "restore"},
        )
    )["items"][0]["ok"]


@pytest.mark.asyncio
async def test_draft_save_conflict_ocr_failure_retry_manual_publish(
    client, test_db, actors, monkeypatch
):
    _, _, paper = await setup_paper(client, actors)
    version_id = paper["versions"][0]["id"]
    draft = (await client.get(P + f"/paper-versions/{version_id}/draft")).json()
    await post(
        client,
        f"/paper-versions/{version_id}/publish",
        {"expected_revision": draft["revision"], "reviewed": True},
        status=422,
    )
    entry = {
        "key": "q1",
        "kind": "standalone",
        "title": "合成框选题",
        "stem": "2 + 2 = ?",
        "answer": "4",
        "regions": [{"page": 1, "x": 0.1, "y": 0.1, "width": 0.7, "height": 0.3}],
    }
    key = uuid4()
    body = {"expected_revision": draft["revision"], "entries": [entry]}
    saved = await client.put(
        P + f"/paper-versions/{version_id}/draft",
        json=body,
        headers={"Idempotency-Key": str(key)},
    )
    assert saved.status_code == 200, saved.text
    revision = saved.json()["revision"]
    assert (
        await client.put(
            P + f"/paper-versions/{version_id}/draft",
            json=body,
            headers={"Idempotency-Key": str(key)},
        )
    ).json()["revision"] == revision
    assert (
        await client.put(P + f"/paper-versions/{version_id}/draft", json=body)
    ).status_code == 409
    await test_db.rollback()
    monkeypatch.setattr("app.services.ocr_jobs.shutil.which", lambda _: None)
    await post(
        client,
        f"/paper-versions/{version_id}/ocr",
        {"expected_revision": revision},
        status=202,
    )
    current = (await client.get(P + f"/paper-versions/{version_id}/draft")).json()
    assert (
        current["jobs"][0]["status"] == "failed"
        and current["jobs"][0]["error_code"] == "OCR_ENGINE_UNAVAILABLE"
    )
    await post(
        client,
        f"/paper-versions/{version_id}/ocr",
        {"expected_revision": revision},
        status=202,
    )
    latest = (await client.get(P + f"/paper-versions/{version_id}/draft")).json()
    assert max(j["attempt"] for j in latest["jobs"]) == 2
    published = await post(
        client,
        f"/paper-versions/{version_id}/publish",
        {"expected_revision": revision, "reviewed": True},
    )
    again = await post(
        client,
        f"/paper-versions/{version_id}/publish",
        {"expected_revision": revision, "reviewed": True},
    )
    assert (
        published["published_ids"] == again["published_ids"]
        and len(published["published_ids"]) == 1
    )
    assert (
        await client.put(
            P + f"/paper-versions/{version_id}/draft",
            json={"expected_revision": revision, "entries": []},
        )
    ).status_code == 409


def csv_batch(school_code):
    rows = {
        "schools.csv": [
            ["external_school_id", "name", "code"],
            ["school-a", "合成学校", school_code],
        ],
        "classes.csv": [
            ["external_class_id", "school_code", "name"],
            ["import-class", school_code, "导入班"],
        ],
        "students.csv": [
            [
                "external_student_id",
                "school_code",
                "student_no",
                "name",
                "external_class_id",
            ],
            ["import-student", school_code, "I001", "合成导入学生", "import-class"],
        ],
        "exams.csv": [
            ["external_exam_id", "school_code", "name", "exam_type", "start_date"],
            ["import-exam", school_code, "导入考试", "test", "2026-09-01"],
        ],
        "subjects.csv": [
            ["external_subject_id", "school_code", "code", "name"],
            ["math", school_code, "MATH", "数学"],
        ],
        "student_exam_scores.csv": [
            [
                "external_student_id",
                "external_exam_id",
                "school_code",
                "total_score",
                "full_score",
            ],
            ["import-student", "import-exam", school_code, "80", "100"],
        ],
        "student_subject_scores.csv": [
            [
                "external_student_id",
                "external_exam_id",
                "external_subject_id",
                "school_code",
                "score",
                "full_score",
            ],
            ["import-student", "import-exam", "math", school_code, "80", "100"],
        ],
        "question_scores.csv": [
            [
                "external_student_id",
                "external_exam_id",
                "external_subject_id",
                "school_code",
                "question_no",
                "score",
                "full_score",
                "lost_score",
            ],
            ["import-student", "import-exam", "math", school_code, "1", "2", "5", "3"],
        ],
    }
    result = {}
    for filename, items in rows.items():
        output = io.StringIO()
        csv.writer(output).writerows(items)
        result[filename] = output.getvalue()
    return result


@pytest.mark.asyncio
async def test_import_mapping_preflight_transaction_receipt_idempotency(
    client, test_db, actors
):
    files = csv_batch(actors["school"].code)
    upload = await post(
        client,
        "/imports",
        {"batch_key": "qa-batch", "source_system": "school_csv", "files": files},
    )
    ready = await post(
        client,
        f"/imports/{upload['id']}/preflight",
        {"expected_revision": upload["revision"], "mapping": upload["mapping"]},
    )
    assert ready["status"] == "ready", ready["report"]
    await post(
        client,
        f"/imports/{upload['id']}/confirm",
        {"expected_revision": ready["revision"]},
        status=202,
    )
    receipt = (await client.get(P + f"/imports/{upload['id']}")).json()
    assert receipt["status"] == "succeeded", receipt
    assert receipt["report"]["counts"]["question_scores"] == 1
    assert (
        await post(
            client,
            f"/imports/{upload['id']}/confirm",
            {"expected_revision": ready["revision"]},
            status=202,
        )
    )["status"] == "succeeded"
    assert await test_db.scalar(select(func.count()).select_from(SourceRecord)) == 6
    await post(
        client,
        "/imports",
        {
            "batch_key": "qa-batch",
            "source_system": "school_csv",
            "files": {
                **files,
                "schools.csv": files["schools.csv"].replace("合成学校", "合成学校改名"),
            },
        },
        status=409,
    )
    invalid_files = {
        **files,
        "question_scores.csv": files["question_scores.csv"].replace(",2,5,3", ",9,5,3"),
    }
    invalid = await post(
        client,
        "/imports",
        {
            "batch_key": "bad-batch",
            "source_system": "school_csv",
            "files": invalid_files,
        },
    )
    invalid = await post(
        client,
        f"/imports/{invalid['id']}/preflight",
        {"expected_revision": invalid["revision"], "mapping": invalid["mapping"]},
    )
    assert invalid["status"] == "invalid" and invalid["report"]["issues"][0]["row"] == 2
    await post(
        client,
        f"/imports/{invalid['id']}/confirm",
        {"expected_revision": invalid["revision"]},
        status=409,
    )
    assert await test_db.scalar(select(func.count()).select_from(QuestionScore)) == 1
    foreign = await post(
        client,
        "/imports",
        {
            "batch_key": "foreign-batch",
            "source_system": "school_csv",
            "files": csv_batch("OTHER"),
        },
    )
    invalid = await post(
        client,
        f"/imports/{foreign['id']}/preflight",
        {"expected_revision": foreign["revision"], "mapping": foreign["mapping"]},
    )
    assert any(
        i["code"] == "SCHOOL_SCOPE_MISMATCH" for i in invalid["report"]["issues"]
    )
    actors["switch"]("foreign")
    assert (await client.get(P + f"/imports/{upload['id']}")).status_code == 404


@pytest.mark.asyncio
async def test_controlled_snapshot_all_domains_and_source_version_conflict(
    client, test_db, actors
):
    asset = await post(client, "/assets", image_upload())
    subject = str(actors["subject"].id)
    records = [
        {
            "entity_type": "exam",
            "external_id": "old-exam-1",
            "name": "旧合成考试",
            "start_date": "2026-08-01",
        },
        {
            "entity_type": "paper",
            "external_id": "old-paper-1",
            "exam_external_id": "old-exam-1",
            "subject_id": subject,
            "title": "旧试卷",
            "asset_id": asset["id"],
        },
        {
            "entity_type": "question",
            "external_id": "old-question-1",
            "subject_id": subject,
            "kind": "standalone",
            "title": "旧题目",
            "stem": "合成旧题干",
            "paper_external_id": "old-paper-1",
        },
        {
            "entity_type": "report",
            "external_id": "old-report-1",
            "student_external_id": "student-a",
            "exam_external_id": "old-exam-1",
            "summary": "正式合成摘要",
            "generated_at": "2026-08-02T00:00:00Z",
        },
        {
            "entity_type": "score",
            "external_id": "old-score-1",
            "student_external_id": "student-a",
            "exam_external_id": "old-exam-1",
            "score": 80,
            "full_score": 100,
        },
        {
            "entity_type": "score",
            "external_id": "old-question-score",
            "student_external_id": "student-a",
            "exam_external_id": "old-exam-1",
            "subject_id": subject,
            "question_external_id": "old-question-1",
            "question_no": "1",
            "score": 2,
            "full_score": 5,
        },
    ]
    body = {
        "source_system": "legacy_export",
        "source_version": "v1",
        "captured_at": "2026-09-01T00:00:00Z",
        "records": records,
    }
    result = await post(client, "/legacy-snapshots", body)
    assert result["count"] == 6 and result["live_connection"] is False
    again = await post(client, "/legacy-snapshots", body)
    assert all(row["replayed"] for row in again["items"])
    bad = {**body, "records": [{**records[0], "name": "冲突内容"}]}
    await post(client, "/legacy-snapshots", bad, status=409)
    question_id = result["items"][2]["native_id"]
    await post(
        client,
        f"/questions/{question_id}/versions",
        {"expected_revision": 1, "stem": "试图编辑外部只读题"},
        status=409,
    )
    assert await test_db.scalar(select(func.count()).select_from(SourceRecord)) == 6
    actors["switch"]("student")
    score = await test_db.scalar(
        select(QuestionScore).where(QuestionScore.question_no == "1")
    )
    assert (await client.get(P + f"/student/mistakes/{score.id}")).json()["question"][
        "stem"
    ] == "合成旧题干"
    assert (await client.get(P + "/sources")).status_code == 403


@pytest.mark.asyncio
async def test_report_original_uses_same_entitlement_and_version(
    client, test_db, actors
):
    exam = await setup_exam(client, actors)
    asset = await post(client, "/assets", image_upload())
    report = await post(
        client,
        "/reports",
        {
            "student_id": str(actors["student"].id),
            "exam_id": exam["id"],
            "version": "v1",
            "summary": "正式合成结论",
            "asset_id": asset["id"],
            "generated_at": "2026-09-01T00:00:00Z",
        },
    )
    actors["switch"]("student")
    assert (await client.get(P + f"/assets/{asset['id']}")).status_code == 403
    grant = StudentEntitlement(
        school_id=actors["school"].id,
        student_id=actors["student"].id,
        product_code="DIAGNOSIS",
        resource_type="report",
        resource_id=UUID(report["id"]),
        status="active",
        starts_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    test_db.add(grant)
    await test_db.commit()
    versions = await client.get(P + f"/student/reports/{report['id']}/versions")
    assert versions.status_code == 200 and versions.json()[0]["asset_id"] == asset["id"]
    assert (await client.get(P + f"/assets/{asset['id']}")).status_code == 200
    grant.status = "revoked"
    await test_db.commit()
    assert (await client.get(P + f"/assets/{asset['id']}")).status_code == 403


@pytest.mark.asyncio
async def test_handoff_bidirectional_messages_receipts_close_reopen(
    client, test_db, actors
):
    actors["switch"]("student")
    response = await client.post(
        "/api/v1/platform/student/handoffs",
        json={"reason": "合成求助", "summary": "测试人工服务", "priority": "normal"},
    )
    assert response.status_code in {200, 201}, response.text
    identifier = response.json()["id"]
    await post(client, f"/handoffs/{identifier}/messages", {"content": "学生补充问题"})
    actors["switch"]("admin")
    r = await client.patch(
        f"/api/v1/platform/management/handoffs/{identifier}",
        json={"status": "accepted", "expected_version": 1},
    )
    assert r.status_code == 200, r.text
    key = uuid4()
    await post(client, f"/handoffs/{identifier}/messages", {"content": "老师已核对并回复"}, key)
    await post(client, f"/handoffs/{identifier}/messages", {"content": "老师已核对并回复"}, key)
    assert await test_db.scalar(select(func.count()).select_from(HandoffMessage)) == 2
    r = await client.patch(
        f"/api/v1/platform/management/handoffs/{identifier}",
        json={"status": "resolved", "expected_version": 2, "resolution": "已解释数据来源"},
    )
    assert r.status_code == 200, r.text
    actors["switch"]("student")
    detail = (await client.get(P + f"/handoffs/{identifier}")).json()
    assert (
        detail["messages"][-1]["content"] == "老师已核对并回复"
        and detail["assignee"] == "合成管理员"
    )
    await post(
        client, f"/handoffs/{identifier}/messages", {"content": "关闭后新消息"}, status=409
    )
    await post(
        client,
        f"/student/handoffs/{identifier}/reopen",
        {"expected_version": 3, "reason": "仍需要帮助"},
    )
    assert (await client.get(P + f"/handoffs/{identifier}")).json()["status"] == "open"
    actors["switch"]("foreign")
    assert (await client.get(P + f"/handoffs/{identifier}")).status_code == 404


@pytest.mark.asyncio
async def test_chat_selected_exam_subject_source_history_and_evidence(
    client, test_db, actors
):
    exam = await setup_exam(client, actors)
    total, _, _ = await add_scores(test_db, actors, exam)
    newer = Exam(
        id=uuid4(),
        school_id=actors["school"].id,
        name="合成新考试",
        exam_type="test",
        start_date=date(2026, 9, 10),
    )
    test_db.add(newer)
    await test_db.flush()
    test_db.add(
        StudentExamScore(
            id=uuid4(),
            school_id=actors["school"].id,
            student_id=actors["student"].id,
            exam_id=newer.id,
            total_score=90,
            full_score=100,
        )
    )
    await test_db.commit()
    actors["switch"]("student")
    session = (await client.post("/api/v1/chat/sessions", json={})).json()["id"]
    r = await client.put(
        f"/api/v1/chat/sessions/{session}/context",
        json={
            "exam_id": exam["id"],
            "subject_id": str(actors["subject"].id),
            "expected_version": 1,
        },
    )
    assert r.status_code == 200, r.text
    message_id = str(uuid4())
    payload = {"content": "数学多少分", "client_message_id": message_id}
    r = await client.post(f"/api/v1/chat/sessions/{session}/messages", json=payload)
    assert r.status_code == 200, r.text
    sources = r.json()["sources"]
    assert sources and sources[0]["facts"]["score"] == 80
    messages = (await client.get(f"/api/v1/chat/sessions/{session}/messages")).json()
    assistant = messages[-1]
    assert assistant["sources"] == sources
    evidence = (await client.get(P + f"/evidence/{assistant['id']}/0")).json()
    assert evidence["captured_source"]["facts"]["exam"] == exam["name"]
    assert (
        await client.post(f"/api/v1/chat/sessions/{session}/messages", json=payload)
    ).json()["sources"] == sources
    bad = await client.put(
        f"/api/v1/chat/sessions/{session}/context",
        json={"exam_id": str(uuid4()), "expected_version": 2},
    )
    assert bad.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("resource", ["papers", "questions", "sources"])
async def test_list_page_size_boundaries_and_school_isolation(client, test_db, actors, resource):
    from app.db.models.education import Paper, Question

    exam = await setup_exam(client, actors)
    for index in range(35):
        common = {"id": uuid4(), "school_id": actors["school"].id}
        if resource == "papers":
            row = Paper(**common, exam_id=UUID(exam["id"]), subject_id=actors["subject"].id, title=f"试卷 {index}")
        elif resource == "questions":
            row = Question(**common, subject_id=actors["subject"].id, title=f"题目 {index}", kind="standalone")
        else:
            row = SourceRecord(**common, source_system="test", entity_type="exam", external_id=str(index), source_version="v1", content_hash="a" * 64, captured_at=datetime.now(timezone.utc), native_id=UUID(exam["id"]), payload={})
        test_db.add(row)
    await test_db.commit()
    default = (await client.get(f"{P}/{resource}")).json()
    assert default["total"] == 35
    assert len(default["items"]) == 30
    all_rows = (await client.get(f"{P}/{resource}?page_size=100")).json()["items"]
    collected = []
    for page, count in [(1, 10), (2, 10), (3, 10), (4, 5), (5, 0)]:
        response = await client.get(f"{P}/{resource}?page={page}&page_size=10")
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["total"] == 35
        assert len(result["items"]) == count
        collected.extend(result["items"])
    assert [row["id"] for row in collected] == [row["id"] for row in all_rows]
    assert len((await client.get(f"{P}/{resource}?page=2&page_size=20")).json()["items"]) == 15
    assert len((await client.get(f"{P}/{resource}?page_size=50")).json()["items"]) == 35
    for invalid in [0, 101]:
        assert (await client.get(f"{P}/{resource}?page_size={invalid}")).status_code == 422
    actors["switch"]("foreign")
    isolated = (await client.get(f"{P}/{resource}?page_size=100")).json()
    assert isolated["items"] == []
    assert isolated["total"] == 0
