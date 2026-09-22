"""Negative, empty, rollback and concurrent cases for every new workbench domain."""
from datetime import datetime, timezone
from uuid import uuid4, UUID
from unittest.mock import AsyncMock
import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.api.deps import get_current_user, AuthenticatedUser
from app.core.database import get_db
from app.main import app
from app.db.models import Student, User, QuestionScore
from app.db.models.education import (
    Question,
    PrivateAsset,
    PaperVersion,
    ImportWorkspace,
    SourceRecord,
    ReviewEntry,
    ReportAttachment,
)
from app.data.import_service import CsvImportService
from app.services.import_workbench import execute_import
from test_education_workbench import (
    actors,
    post,
    setup_exam,
    setup_paper,
    setup_question,
    add_scores,
    image_upload,
    csv_batch,
    P,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/imports",
        "/mapping-templates",
        "/sources",
        "/reports",
        "/papers",
        "/questions",
        "/taxonomy",
        "/school/teachers",
    ],
)
async def test_management_lists_reject_student_role(client, actors, path):
    actors["switch"]("student")
    assert (await client.get(P + path)).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/imports",
        "/assets",
        "/papers",
        "/questions",
        "/taxonomy",
        "/legacy-snapshots",
        "/reports",
        "/mapping-templates",
    ],
)
async def test_new_writes_are_not_granted_to_qa_or_teachers(client, actors, path):
    for role in ("qa", "teacher", "student"):
        actors["switch"](role)
        assert (await client.post(P + path, json={})).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/imports",
        "/mapping-templates",
        "/sources",
        "/reports",
        "/papers",
        "/questions",
        "/taxonomy",
        "/school/classes",
        "/school/teachers",
    ],
)
async def test_empty_tenant_lists_have_no_foreign_counts(client, actors, path):
    actors["switch"]("foreign")
    response = await client.get(P + path)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body == [] or (body["items"] == [] and body["total"] == 0)


@pytest.mark.asyncio
async def test_report_cannot_be_repurposed_as_a_student_exam_paper(
    client, test_db, actors
):
    exam, asset, paper = await setup_paper(client, actors)
    await post(
        client,
        "/reports",
        {
            "student_id": str(actors["student"].id),
            "exam_id": exam["id"],
            "version": "bad",
            "summary": "测试",
            "asset_id": asset["id"],
            "generated_at": "2026-09-01T00:00:00Z",
        },
        status=409,
    )
    standalone = await post(client, "/assets", image_upload())
    report = await post(
        client,
        "/reports",
        {
            "student_id": str(actors["student"].id),
            "exam_id": exam["id"],
            "version": "v1",
            "summary": "合成报告",
            "asset_id": standalone["id"],
            "generated_at": "2026-09-01T00:00:00Z",
        },
    )
    await post(
        client,
        f"/papers/{paper['id']}/versions",
        {"asset_id": standalone["id"], "expected_revision": paper["revision"]},
        status=409,
    )
    await post(
        client,
        "/reports",
        {
            "student_id": str(actors["student"].id),
            "exam_id": exam["id"],
            "version": "v2",
            "summary": "复用原件",
            "asset_id": standalone["id"],
            "generated_at": "2026-09-01T00:00:00Z",
        },
        status=409,
    )
    assert await test_db.scalar(select(func.count()).select_from(ReportAttachment)) == 1


@pytest.mark.asyncio
async def test_unpublished_questions_and_wrong_subjects_are_not_readable_by_teacher(
    client, test_db, actors
):
    from app.db.models import ImportedClass, TeachingAssignment

    classroom = ImportedClass(
        id=uuid4(),
        school_id=actors["school"].id,
        external_class_id="scope",
        name="scope",
        source_system="native",
    )
    test_db.add(classroom)
    await test_db.flush()
    test_db.add(
        TeachingAssignment(
            school_id=actors["school"].id,
            teacher_user_id=actors["teacher"].id,
            class_id=classroom.id,
            subject_id=actors["subject"].id,
            starts_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    )
    await test_db.commit()
    q = await post(
        client,
        "/questions",
        {
            "subject_id": str(actors["subject"].id),
            "kind": "standalone",
            "title": "草稿不可泄露",
            "stem": "草稿正文",
        },
    )
    actors["switch"]("teacher")
    assert (await client.get(P + f"/questions/{q['id']}")).status_code == 404
    assert (await client.get(P + "/questions")).json()["total"] == 0


@pytest.mark.asyncio
async def test_import_failure_rolls_back_domain_and_source_records_then_retry_recovers(
    client, test_db, actors, monkeypatch
):
    files = csv_batch(actors["school"].code)
    item = await post(
        client,
        "/imports",
        {"batch_key": "rollback-batch", "source_system": "school_csv", "files": files},
    )
    item = await post(
        client,
        f"/imports/{item['id']}/preflight",
        {"expected_revision": item["revision"], "mapping": item["mapping"]},
    )
    monkeypatch.setattr("app.services.import_workbench.execute_import", AsyncMock())
    await post(
        client,
        f"/imports/{item['id']}/confirm",
        {"expected_revision": item["revision"]},
        status=202,
    )
    original = CsvImportService._upsert_domain

    async def fail_after_writes(self, plan, source):
        await original(self, plan, source)
        raise RuntimeError("synthetic failure after domain writes")

    monkeypatch.setattr(CsvImportService, "_upsert_domain", fail_after_writes)
    factory = async_sessionmaker(test_db.bind, expire_on_commit=False)
    await execute_import(factory, UUID(item["id"]))
    await test_db.rollback()
    assert (
        await test_db.scalar(
            select(func.count())
            .select_from(Student)
            .where(Student.external_student_id == "import-student")
        )
        == 0
    )
    assert await test_db.scalar(select(func.count()).select_from(SourceRecord)) == 0
    current = (await client.get(P + f"/imports/{item['id']}")).json()
    assert (
        current["status"] == "failed"
        and current["report"]["error_code"] == "IMPORT_TRANSACTION_FAILED"
    )
    monkeypatch.setattr(CsvImportService, "_upsert_domain", original)
    await post(
        client,
        f"/imports/{item['id']}/confirm",
        {"expected_revision": item["revision"]},
        status=202,
    )
    await execute_import(factory, UUID(item["id"]))
    await test_db.rollback()
    assert (await client.get(P + f"/imports/{item['id']}")).json()[
        "status"
    ] == "succeeded"


@pytest.mark.asyncio
async def test_source_batch_conflict_rolls_back_earlier_entities(
    client, test_db, actors
):
    body = {
        "source_system": "legacy",
        "source_version": "v1",
        "captured_at": "2026-09-01T00:00:00Z",
        "records": [
            {
                "entity_type": "exam",
                "external_id": "e",
                "name": "不应残留",
                "start_date": "2026-09-01",
            },
            {
                "entity_type": "score",
                "external_id": "s",
                "student_external_id": "missing-student",
                "exam_external_id": "e",
                "score": 80,
                "full_score": 100,
            },
        ],
    }
    await post(client, "/legacy-snapshots", body, status=422)
    assert await test_db.scalar(select(func.count()).select_from(SourceRecord)) == 0
    assert (await client.get(P + "/school/exams")).json()["total"] == 0


@pytest.mark.asyncio
async def test_teacher_account_status_and_name_readback_do_not_expose_credentials(
    client, test_db, actors
):
    response = await client.get(P + "/school/teachers")
    assert response.status_code == 200
    assert set(response.json()["items"][0]) == {"id", "display_name", "status", "name"}
    body = {"display_name": "QA 更新教师", "status": "inactive"}
    changed = await client.put(
        P + f"/school/teachers/{actors['teacher'].id}", json=body
    )
    assert changed.status_code == 200 and changed.json()["status"] == "inactive"
    again = await client.put(P + f"/school/teachers/{actors['teacher'].id}", json=body)
    assert again.json() == changed.json()
    assert (await client.get(P + "/school/teachers")).json()["items"][0][
        "display_name"
    ] == "QA 更新教师"


@pytest.mark.asyncio
async def test_full_mark_questions_are_not_mistakes_and_no_source_review_is_rejected(
    client, test_db, actors
):
    exam = await setup_exam(client, actors)
    _, _, score = await add_scores(test_db, actors, exam)
    actors["switch"]("student")
    await post(client, "/student/reviews", {"score_id": str(score.id)}, status=409)
    current = await test_db.get(QuestionScore, score.id)
    current.score = 5
    current.lost_score = 0
    await test_db.commit()
    assert (await client.get("/api/v1/platform/student/mistakes")).json() == []
    assert (await client.get(P + "/student/reviews")).json() == []


@pytest.mark.asyncio
async def test_asset_validation_never_echoes_uploaded_payload(client, actors):
    response = await client.post(
        P + "/assets", json={"filename": "x.png", "content_base64": 42}
    )
    assert response.status_code == 422
    assert all(
        "input" not in field for field in response.json()["error"]["details"]["fields"]
    )


@pytest.mark.asyncio
async def test_concurrent_import_upload_uses_one_canonical_workspace(
    client, test_db, actors
):
    if test_db.bind.dialect.name != "postgresql":
        pytest.skip("Row locks require PostgreSQL")
    import asyncio
    from httpx import AsyncClient, ASGITransport

    factory = async_sessionmaker(test_db.bind, expire_on_commit=False)

    async def independent_db():
        async with factory() as db:
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    original = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = independent_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as parallel:
            body = {
                "batch_key": "parallel",
                "source_system": "school_csv",
                "files": csv_batch(actors["school"].code),
            }
            one, two = await asyncio.gather(
                parallel.post(P + "/imports", json=body),
                parallel.post(P + "/imports", json=body),
            )
            assert one.status_code == two.status_code == 200
            assert one.json()["id"] == two.json()["id"]
    finally:
        app.dependency_overrides[get_db] = original
    assert await test_db.scalar(select(func.count()).select_from(ImportWorkspace)) == 1
