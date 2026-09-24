"""Education workbench API. All mutations are school-admin capabilities."""
import io
from typing import Literal
from uuid import UUID
from urllib.parse import quote
from fastapi import APIRouter, Depends, Header, Query, BackgroundTasks
from fastapi.responses import Response
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.api.deps import (
    AuthenticatedUser,
    AuthenticatedStudent,
    get_current_user,
    get_current_student,
    require_management,
)
from app.core.database import get_db
from app.core.errors import ApiError
from app.core.access_scope import active_grants, is_teacher_only
from app.core.diagnosis_access import require_report, audit_report_access
from app.db.models.education import *
from app.db.models.school import School
from app.db.models.exam import Exam, Subject
from app.db.models.diagnosis import DiagnosisReport
from app.db.models.score import StudentSubjectScore, QuestionScore
from app.db.models.teaching import TeachingAssignment
from app.schemas.education import *
from app.schemas.legacy_snapshot import Snapshot
from app.services import (
    curriculum as c,
    import_workbench as imports,
    school_workbench as school,
    learning_workbench as learning,
    ocr_jobs,
    legacy_snapshot,
)
from app.services.education_common import owned, data, audit, claim

router = APIRouter(prefix="/platform/education", tags=["education"])
reader = require_management("SCHOOL_ADMIN", "QA", "SUPER_ADMIN", "TEACHER", "SCHOOL_VIEWER")
admin_reader = require_management("SCHOOL_ADMIN", "QA", "SUPER_ADMIN", "SCHOOL_VIEWER")
write_role = require_management("SCHOOL_ADMIN", "SUPER_ADMIN")
exam_read_role = require_management("SCHOOL_ADMIN", "QA", "SUPER_ADMIN", "SCHOOL_VIEWER", "EXAM_ADMIN")
exam_write_role = require_management("SCHOOL_ADMIN", "SUPER_ADMIN", "EXAM_ADMIN")
school_read_role = require_management("SCHOOL_ADMIN", "QA", "SUPER_ADMIN", "TEACHER", "SCHOOL_VIEWER", "EXAM_ADMIN")


async def exam_writer(actor=Depends(exam_write_role), db: AsyncSession = Depends(get_db)):
    await db.scalar(select(School.id).where(School.id == actor.school_id).with_for_update())
    return actor


async def writer(actor=Depends(write_role), db: AsyncSession = Depends(get_db)):
    # Serialize school production mutations, including import workers, so a
    # reference cannot be created concurrently with an authorized soft delete.
    await db.scalar(
        select(School.id).where(School.id == actor.school_id).with_for_update()
    )
    return actor


async def write(db, operation):
    try:
        return await operation
    except IntegrityError:
        await db.rollback()
        raise ApiError(409, "EDUCATION_CONFLICT", "记录已存在、身份关联冲突或被引用，请刷新核对后重试。")
    except Exception:
        await db.rollback()
        raise


@router.get("/school/{kind}")
async def school_list(
    kind: Literal["classes", "students", "subjects", "exams", "teaching", "teachers"],
    search: str = Query("", max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    actor=Depends(school_read_role),
    db: AsyncSession = Depends(get_db),
):
    if actor.has_role("EXAM_ADMIN") and not any(actor.has_role(r) for r in ("SCHOOL_ADMIN", "SUPER_ADMIN", "SCHOOL_VIEWER", "QA")) and kind not in {"exams", "classes", "subjects"}:
        raise ApiError(403, "EXAM_SCOPE_ONLY", "考试管理员仅可维护考试科目，不能维护师生档案或任教授权。")
    return await school.listing(db, actor, kind, search, page, page_size)


@router.get("/accounts")
async def school_accounts(
    actor=Depends(admin_reader), db: AsyncSession = Depends(get_db)
):
    return await school.users(db, actor)


@router.post("/school/classes")
async def class_create(
    body: ClassCreate,
    key: UUID | None = Header(None, alias="Idempotency-Key"),
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    return await write(db, school.create(db, actor, "classes", body, key))


@router.put("/school/classes/{identifier}")
async def class_update(
    identifier: UUID,
    body: ClassUpdate,
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    return await write(db, school.update_record(db, actor, "classes", identifier, body))


@router.post("/school/students")
async def student_create(
    body: StudentCreate,
    key: UUID | None = Header(None, alias="Idempotency-Key"),
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    raise ApiError(409, "ROSTER_EXCEL_REQUIRED", "学生统一通过 30 列 Excel 模板导入，不提供单个新增。")


@router.put("/school/students/{identifier}")
async def student_update(
    identifier: UUID,
    body: StudentUpdate,
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    raise ApiError(409, "ROSTER_REIMPORT_REQUIRED", "学生变更（含调班）须先删除原档案，再修改 Excel 重新导入；毕业请使用毕业归档操作。")


@router.post("/school/students/{identifier}/bind")
async def student_bind(
    identifier: UUID,
    body: BindUser,
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    return await write(db, school.bind_student(db, actor, identifier, body))


@router.post("/school/teaching")
async def teaching_create(
    body: TeachingCreate,
    key: UUID | None = Header(None, alias="Idempotency-Key"),
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    return await write(db, school.create(db, actor, "teaching", body, key))


@router.put("/school/teaching/{identifier}")
async def teaching_update(
    identifier: UUID,
    body: TeachingCreate,
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    return await write(
        db, school.update_record(db, actor, "teaching", identifier, body)
    )


@router.put("/school/teachers/{identifier}")
async def teacher_update(
    identifier: UUID,
    body: TeacherUpdate,
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    raise ApiError(409, "ROSTER_REIMPORT_REQUIRED", "教师变更须先删除原档案，再修改 Excel 重新导入；离职 / 停用请使用列表操作。")


@router.post("/school/subjects")
async def subject_create(
    body: SubjectCreate,
    key: UUID | None = Header(None, alias="Idempotency-Key"),
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    return await write(db, school.create(db, actor, "subjects", body, key))


@router.post("/school/exams")
async def exam_create(
    body: ExamCreate,
    key: UUID | None = Header(None, alias="Idempotency-Key"),
    actor=Depends(exam_writer),
    db: AsyncSession = Depends(get_db),
):
    return await write(db, school.create(db, actor, "exams", body, key))


@router.put("/school/exams/{identifier}")
async def exam_update(
    identifier: UUID,
    body: ExamCreate,
    actor=Depends(exam_writer),
    db: AsyncSession = Depends(get_db),
):
    return await write(db, school.update_record(db, actor, "exams", identifier, body))


@router.get("/exams/{identifier}")
async def exam_get(
    identifier: UUID, actor=Depends(exam_read_role), db: AsyncSession = Depends(get_db)
):
    return await school.exam_detail(db, actor, identifier)


@router.put("/exams/{identifier}/subjects")
async def exam_subject(
    identifier: UUID,
    body: ExamSubjectWrite,
    actor=Depends(exam_writer),
    db: AsyncSession = Depends(get_db),
):
    return await write(db, school.set_exam_subject(db, actor, identifier, body))


@router.get("/class-analysis")
async def class_analysis(
    class_id: UUID,
    subject_id: UUID,
    exam_id: UUID,
    actor=Depends(reader),
    db: AsyncSession = Depends(get_db),
):
    return await school.class_analysis(db, actor, class_id, subject_id, exam_id)


@router.get("/imports")
async def import_list(actor=Depends(admin_reader), db: AsyncSession = Depends(get_db)):
    rows = (
        await db.scalars(
            select(ImportWorkspace)
            .where(ImportWorkspace.school_id == actor.school_id)
            .order_by(ImportWorkspace.created_at.desc())
            .limit(100)
        )
    ).all()
    return [
        data(r, "id", "batch_key", "source_system", "status", "progress", "created_at")
        for r in rows
    ]


@router.post("/imports")
async def import_upload(
    body: ImportUpload,
    key: UUID | None = Header(None, alias="Idempotency-Key"),
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    return await write(db, imports.upload(db, actor, body, key))


@router.get("/imports/{identifier}")
async def import_detail(
    identifier: UUID, actor=Depends(admin_reader), db: AsyncSession = Depends(get_db)
):
    return imports.view(await owned(db, ImportWorkspace, identifier, actor))


@router.post("/imports/{identifier}/preflight")
async def import_preflight(
    identifier: UUID,
    body: ImportMapping,
    key: UUID | None = Header(None, alias="Idempotency-Key"),
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    return await write(db, imports.preflight(db, actor, identifier, body, key))


@router.post("/imports/{identifier}/confirm", status_code=202)
async def import_confirm(
    identifier: UUID,
    body: Revision,
    background: BackgroundTasks,
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    result = await write(db, imports.confirm(db, actor, identifier, body))
    if result["status"] == "running":
        background.add_task(
            imports.execute_import,
            async_sessionmaker(db.bind, expire_on_commit=False),
            identifier,
        )
    return result


@router.get("/mapping-templates")
async def template_list(
    actor=Depends(admin_reader), db: AsyncSession = Depends(get_db)
):
    rows = (
        await db.scalars(
            select(MappingTemplate)
            .where(MappingTemplate.school_id == actor.school_id)
            .order_by(MappingTemplate.created_at.desc())
            .limit(100)
        )
    ).all()
    return [data(r, "id", "name", "version", "mapping") for r in rows]


@router.post("/mapping-templates")
async def template_create(
    body: TemplateCreate,
    key: UUID | None = Header(None, alias="Idempotency-Key"),
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    async def operation():
        identifier, fresh = await claim(
            db, actor, "mapping.template", key, body.model_dump()
        )
        if fresh:
            if set(body.mapping) - set(imports.REQUIRED_COLUMNS):
                raise ApiError(422, "IMPORT_MAPPING_INVALID", "模板包含未知文件。")
            version = (
                await db.scalar(
                    select(func.max(MappingTemplate.version)).where(
                        MappingTemplate.school_id == actor.school_id,
                        MappingTemplate.name == body.name,
                    )
                )
                or 0
            ) + 1
            item = MappingTemplate(
                id=identifier,
                school_id=actor.school_id,
                name=body.name,
                version=version,
                mapping=body.mapping,
            )
            db.add(item)
            audit(db, actor, "mapping.template", item)
            await db.commit()
        return data(
            await owned(db, MappingTemplate, identifier, actor),
            "id",
            "name",
            "version",
            "mapping",
        )

    return await write(db, operation())


@router.post("/legacy-snapshots")
async def snapshot_ingest(
    body: Snapshot, actor=Depends(writer), db: AsyncSession = Depends(get_db)
):
    return await write(db, legacy_snapshot.ingest(db, actor, body))


@router.get("/sources")
async def sources(
    entity_type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    actor=Depends(admin_reader),
    db: AsyncSession = Depends(get_db),
):
    query = select(SourceRecord).where(SourceRecord.school_id == actor.school_id)
    if entity_type:
        query = query.where(SourceRecord.entity_type == entity_type)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await db.scalars(
            query.order_by(SourceRecord.created_at.desc(), SourceRecord.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {
        "items": [
            data(
                r,
                "id",
                "source_system",
                "entity_type",
                "external_id",
                "source_version",
                "content_hash",
                "captured_at",
                "native_id",
            )
            for r in rows
        ],
        "total": total,
    }


@router.get("/sources/{identifier}")
async def source_detail(
    identifier: UUID, actor=Depends(admin_reader), db: AsyncSession = Depends(get_db)
):
    row = await owned(db, SourceRecord, identifier, actor)
    audit(db, actor, "source.read", row)
    await db.commit()
    return data(
        row,
        "id",
        "source_system",
        "entity_type",
        "external_id",
        "source_version",
        "content_hash",
        "captured_at",
        "native_id",
        "payload",
    )


@router.post("/assets")
async def asset_upload(
    body: AssetUpload,
    key: UUID | None = Header(None, alias="Idempotency-Key"),
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    return await write(db, c.upload_asset(db, actor, body, key))


async def asset_access(db, actor, identifier):
    allowed = any(actor.has_role(r) for r in ("SCHOOL_ADMIN", "QA", "SUPER_ADMIN"))
    if is_teacher_only(actor):
        allowed = bool(
            await db.scalar(
                select(PaperVersion.id)
                .join(Paper, Paper.id == PaperVersion.paper_id)
                .where(
                    PaperVersion.school_id == actor.school_id,
                    PaperVersion.asset_id == identifier,
                    Paper.id.in_(c.teacher_paper_ids(actor)),
                )
                .limit(1)
            )
        )
    if not allowed and actor.has_role("STUDENT"):
        student = await get_current_student(actor, db)
        attachments = (
            await db.scalars(
                select(ReportAttachment).where(
                    ReportAttachment.school_id == actor.school_id,
                    ReportAttachment.asset_id == identifier,
                )
            )
        ).all()
        if attachments:
            # One asset may have only one report owner (enforced on attachment writes).
            await require_report(db, student, attachments[0].report_id)
            await audit_report_access(db, student, True, attachments[0].report_id)
            allowed = True
        else:
            allowed = bool(
                await db.scalar(
                    select(PaperVersion.id)
                    .join(Paper, Paper.id == PaperVersion.paper_id)
                    .join(
                        StudentSubjectScore,
                        (StudentSubjectScore.exam_id == Paper.exam_id)
                        & (StudentSubjectScore.subject_id == Paper.subject_id),
                    )
                    .where(
                        PaperVersion.school_id == actor.school_id,
                        PaperVersion.asset_id == identifier,
                        StudentSubjectScore.school_id == actor.school_id,
                        StudentSubjectScore.student_id == student.student_id,
                    )
                    .limit(1)
                )
            )
    if not allowed:
        raise ApiError(404, "ASSET_NOT_AVAILABLE", "原件不存在或不在授权范围内。")
    return await owned(db, PrivateAsset, identifier, actor)


@router.get("/assets/{identifier}")
async def asset_download(
    identifier: UUID,
    page: int | None = Query(None, ge=1, le=100),
    actor=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await asset_access(db, actor, identifier)
    content, media_type = asset.content, asset.media_type
    if page:
        image = c.render_page(asset, page)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        content, media_type = buffer.getvalue(), "image/png"
    audit(db, actor, "asset.read", asset)
    await db.commit()
    return Response(
        content,
        media_type=media_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(asset.filename)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@router.get("/papers")
async def paper_list(
    subject_id: UUID | None = None,
    exam_id: UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    actor=Depends(reader),
    db: AsyncSession = Depends(get_db),
):
    query = select(Paper).where(Paper.school_id == actor.school_id)
    if is_teacher_only(actor):
        query = query.where(Paper.id.in_(c.teacher_paper_ids(actor)))
    if subject_id:
        query = query.where(Paper.subject_id == subject_id)
    if exam_id:
        query = query.where(Paper.exam_id == exam_id)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await db.scalars(
            query.order_by(Paper.created_at.desc(), Paper.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {
        "items": [
            data(
                r,
                "id",
                "title",
                "exam_id",
                "subject_id",
                "source_system",
                "status",
                "revision",
            )
            for r in rows
        ],
        "total": total,
    }


@router.post("/papers")
async def paper_create(
    body: PaperCreate,
    key: UUID | None = Header(None, alias="Idempotency-Key"),
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    return await write(db, c.create_paper(db, actor, body, key))


@router.get("/papers/{identifier}")
async def paper_get(
    identifier: UUID, actor=Depends(reader), db: AsyncSession = Depends(get_db)
):
    return await c.paper_detail(db, actor, identifier)


@router.post("/papers/{identifier}/versions")
async def paper_replace(
    identifier: UUID,
    body: PaperReplace,
    key: UUID | None = Header(None, alias="Idempotency-Key"),
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    return await write(db, c.replace_paper(db, actor, identifier, body, key))


@router.get("/questions")
async def questions(
    subject_id: UUID | None = None,
    kind: Literal["material", "major", "minor", "standalone"] | None = None,
    tag_id: UUID | None = None,
    search: str = Query("", max_length=100),
    deleted: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    actor=Depends(reader),
    db: AsyncSession = Depends(get_db),
):
    query = select(Question).where(
        Question.school_id == actor.school_id,
        Question.deleted_at.is_not(None) if deleted else Question.deleted_at.is_(None),
    )
    if is_teacher_only(actor):
        query = query.where(
            Question.status == "published",
            Question.subject_id.in_(
                select(TeachingAssignment.subject_id).where(*active_grants(actor))
            ),
        )
    if subject_id:
        query = query.where(Question.subject_id == subject_id)
    if kind:
        query = query.where(Question.kind == kind)
    if search:
        query = query.where(Question.title.contains(search, autoescape=True))
    if tag_id:
        query = query.where(
            Question.id.in_(
                select(QuestionVersion.question_id)
                .join(
                    QuestionTag, QuestionTag.question_version_id == QuestionVersion.id
                )
                .where(
                    QuestionTag.node_id == tag_id,
                    QuestionTag.school_id == actor.school_id,
                )
            )
        )
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await db.scalars(
            query.order_by(Question.created_at.desc(), Question.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {
        "items": [
            data(
                r,
                "id",
                "title",
                "kind",
                "parent_id",
                "subject_id",
                "status",
                "revision",
                "source_system",
                "deleted_at",
            )
            for r in rows
        ],
        "total": total,
    }


@router.post("/questions")
async def question_create(
    body: QuestionCreate,
    key: UUID | None = Header(None, alias="Idempotency-Key"),
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    return await write(db, c.create_question(db, actor, body, key))


@router.post("/questions/batch")
async def question_batch(
    body: BatchAction, actor=Depends(writer), db: AsyncSession = Depends(get_db)
):
    results = []
    for identifier in dict.fromkeys(body.ids):
        try:
            async with db.begin_nested():
                await c.lifecycle(db, actor, Question, identifier, body.action)
            results.append({"id": str(identifier), "ok": True})
        except ApiError as error:
            results.append(
                {
                    "id": str(identifier),
                    "ok": False,
                    "code": error.code,
                    "message": error.user_message,
                    "references": error.details,
                }
            )
    await db.commit()
    return {"items": results}


@router.get("/questions/{identifier}")
async def question_get(
    identifier: UUID, actor=Depends(reader), db: AsyncSession = Depends(get_db)
):
    return await c.question_detail(db, actor, identifier)


@router.post("/questions/{identifier}/versions")
async def question_edit(
    identifier: UUID,
    body: QuestionEdit,
    key: UUID | None = Header(None, alias="Idempotency-Key"),
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    return await write(db, c.edit_question(db, actor, identifier, body, key))


@router.post("/questions/{identifier}/publish")
async def question_publish(
    identifier: UUID,
    body: Revision,
    key: UUID | None = Header(None, alias="Idempotency-Key"),
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    return await write(db, c.publish_question(db, actor, identifier, body, key))


@router.get("/questions/{identifier}/references")
async def question_refs(
    identifier: UUID, actor=Depends(admin_reader), db: AsyncSession = Depends(get_db)
):
    return await c.question_references(
        db, actor, await owned(db, Question, identifier, actor)
    )


@router.post("/scores/{identifier}/question")
async def score_link(
    identifier: UUID,
    body: ScoreLink,
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    return await write(db, school.link_score(db, actor, identifier, body))


@router.get("/taxonomy")
async def taxonomy(
    subject_id: UUID | None = None,
    deleted: bool = False,
    actor=Depends(reader),
    db: AsyncSession = Depends(get_db),
):
    query = select(TaxonomyNode).where(
        TaxonomyNode.school_id == actor.school_id,
        TaxonomyNode.deleted_at.is_not(None)
        if deleted
        else TaxonomyNode.deleted_at.is_(None),
    )
    if subject_id:
        query = query.where(TaxonomyNode.subject_id == subject_id)
    if is_teacher_only(actor):
        query = query.where(
            TaxonomyNode.subject_id.in_(
                select(TeachingAssignment.subject_id).where(*active_grants(actor))
            )
        )
    return [
        data(
            r, "id", "name", "kind", "subject_id", "parent_id", "revision", "deleted_at"
        )
        for r in (await db.scalars(query.order_by(TaxonomyNode.name).limit(2000))).all()
    ]


@router.post("/taxonomy")
async def taxonomy_create(
    body: TaxonomyCreate,
    key: UUID | None = Header(None, alias="Idempotency-Key"),
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    return await write(db, c.taxonomy_write(db, actor, body, key))


@router.put("/taxonomy/{identifier}")
async def taxonomy_edit(
    identifier: UUID,
    body: TaxonomyEdit,
    key: UUID | None = Header(None, alias="Idempotency-Key"),
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    return await write(db, c.taxonomy_write(db, actor, body, key, identifier))


@router.post("/taxonomy/{identifier}/{action}")
async def taxonomy_lifecycle(
    identifier: UUID,
    action: Literal["delete", "restore"],
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    item = await write(db, c.lifecycle(db, actor, TaxonomyNode, identifier, action))
    await db.commit()
    return data(item, "id", "deleted_at", "revision")


@router.get("/paper-versions/{identifier}/draft")
async def draft_get(
    identifier: UUID, actor=Depends(admin_reader), db: AsyncSession = Depends(get_db)
):
    _, draft = await c.draft_detail(db, actor, identifier)
    jobs = (
        await db.scalars(
            select(OcrJob)
            .where(OcrJob.draft_id == draft.id)
            .order_by(OcrJob.created_at.desc())
            .limit(20)
        )
    ).all()
    return {
        **data(
            draft,
            "id",
            "revision",
            "entries",
            "published_revision",
            "published_ids",
            "updated_at",
        ),
        "jobs": [
            data(
                j,
                "id",
                "status",
                "attempt",
                "progress",
                "error_code",
                "result",
                "draft_revision",
            )
            for j in jobs
        ],
        "ocr": ocr_jobs.capabilities(),
    }


@router.put("/paper-versions/{identifier}/draft")
async def draft_save(
    identifier: UUID,
    body: DraftSave,
    key: UUID | None = Header(None, alias="Idempotency-Key"),
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    return await write(db, c.save_draft(db, actor, identifier, body, key))


@router.post("/paper-versions/{identifier}/publish")
async def draft_publish(
    identifier: UUID,
    body: DraftPublish,
    key: UUID | None = Header(None, alias="Idempotency-Key"),
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    return await write(db, c.publish_draft(db, actor, identifier, body, key))


@router.post("/paper-versions/{identifier}/ocr", status_code=202)
async def ocr_enqueue(
    identifier: UUID,
    body: OcrRequest,
    background: BackgroundTasks,
    key: UUID | None = Header(None, alias="Idempotency-Key"),
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    result = await write(db, ocr_jobs.enqueue(db, actor, identifier, body, key))
    if result["status"] in {"queued", "running"}:
        background.add_task(
            ocr_jobs.execute_ocr,
            async_sessionmaker(db.bind, expire_on_commit=False),
            UUID(result["id"]),
        )
    return result


@router.get("/reports")
async def report_list(actor=Depends(admin_reader), db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(DiagnosisReport, ReportAttachment.asset_id)
            .outerjoin(
                ReportAttachment, ReportAttachment.report_id == DiagnosisReport.id
            )
            .where(DiagnosisReport.school_id == actor.school_id)
            .order_by(DiagnosisReport.generated_at.desc())
            .limit(100)
        )
    ).all()
    return [
        {
            **data(
                r,
                "id",
                "student_id",
                "exam_id",
                "subject_id",
                "report_type",
                "version",
                "source_system",
                "status",
                "generated_at",
            ),
            "asset_id": str(a) if a else None,
        }
        for r, a in rows
    ]


@router.post("/reports")
async def report_create(
    body: ReportCreate,
    key: UUID | None = Header(None, alias="Idempotency-Key"),
    actor=Depends(writer),
    db: AsyncSession = Depends(get_db),
):
    return await write(db, learning.create_report(db, actor, body, key))


@router.get("/student/mistakes/{identifier}")
async def mistake_detail(
    identifier: UUID,
    actor=Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    return await learning.question_facts(db, actor, identifier)


@router.get("/student/reviews")
async def review_list(
    actor=Depends(get_current_student), db: AsyncSession = Depends(get_db)
):
    rows = (
        await db.scalars(
            select(ReviewEntry)
            .where(
                ReviewEntry.school_id == actor.school_id,
                ReviewEntry.student_id == actor.student_id,
            )
            .order_by(ReviewEntry.created_at.desc())
            .limit(100)
        )
    ).all()
    return [await learning.review_detail(db, actor, row.id) for row in rows]


@router.post("/student/reviews")
async def review_create(
    body: ReviewCreate,
    key: UUID | None = Header(None, alias="Idempotency-Key"),
    actor=Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    return await write(db, learning.add_review(db, actor, body, key))


@router.get("/student/reviews/{identifier}")
async def review_get(
    identifier: UUID,
    actor=Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    return await learning.review_detail(db, actor, identifier)


@router.post("/student/reviews/{identifier}/records")
async def review_record(
    identifier: UUID,
    body: ReviewRecordCreate,
    key: UUID | None = Header(None, alias="Idempotency-Key"),
    actor=Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    return await write(db, learning.add_review_record(db, actor, identifier, body, key))


@router.get("/student/reports/{identifier}/versions")
async def student_report_versions(
    identifier: UUID,
    actor=Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    return await learning.report_versions(db, actor, identifier)


@router.get("/handoffs/{identifier}")
async def handoff_get(
    identifier: UUID,
    actor=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await learning.handoff_detail(db, actor, identifier)


@router.post("/handoffs/{identifier}/messages")
async def handoff_message(
    identifier: UUID,
    body: HandoffReply,
    key: UUID | None = Header(None, alias="Idempotency-Key"),
    actor=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await write(db, learning.handoff_reply(db, actor, identifier, body, key))


@router.post("/student/handoffs/{identifier}/{action}")
async def student_handoff_action(
    identifier: UUID,
    action: Literal["confirm", "reopen"],
    body: HandoffReopen,
    actor=Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    return await write(
        db,
        learning.student_handoff_state(
            db, actor, identifier, body, "closed" if action == "confirm" else "open"
        ),
    )


@router.get("/evidence/{message_id}/{index}")
async def evidence_get(
    message_id: UUID,
    index: int,
    actor=Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    return await learning.evidence(db, actor, message_id, index)
