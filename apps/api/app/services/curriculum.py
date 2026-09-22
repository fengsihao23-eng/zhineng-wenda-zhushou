"""Versioned papers/questions, private files, taxonomy and manual publishing."""
import base64
import binascii
import hashlib
import io
from pathlib import PurePath
from uuid import uuid4
from sqlalchemy import select, func, or_, delete
from app.core.errors import ApiError
from app.core.access_scope import is_teacher_only, scoped_scores
from app.db.models.education import (
    PrivateAsset,
    Paper,
    PaperVersion,
    Question,
    QuestionVersion,
    TaxonomyNode,
    QuestionTag,
    PaperDraft,
    OcrJob,
    ReviewEntry,
    ReportAttachment,
)
from app.db.models.exam import Exam, Subject, ExamSubject
from app.db.models.score import QuestionScore, StudentSubjectScore
from app.schemas.education import QuestionCreate
from app.services.education_common import (
    owned,
    native_only,
    claim,
    audit,
    now,
    cas,
    data,
    subject_access,
)

MAX_FILE_BYTES = 15 * 1024 * 1024
PARENTS = {
    "material": {None},
    "major": {None, "material"},
    "minor": {"major"},
    "standalone": {None},
}


def inspect_file(upload):
    if (
        "/" in upload.filename
        or "\\" in upload.filename
        or any(ord(c) < 32 for c in upload.filename)
    ):
        raise ApiError(422, "INVALID_FILENAME", "文件名不能包含路径或控制字符。")
    try:
        content = base64.b64decode(upload.content_base64, validate=True)
    except (ValueError, binascii.Error):
        raise ApiError(422, "INVALID_FILE", "文件编码无效。")
    if not content or len(content) > MAX_FILE_BYTES:
        raise ApiError(413, "FILE_TOO_LARGE", "原件大小须在 1 字节至 15 MB 之间。")
    suffix = PurePath(upload.filename).suffix.lower()
    pages = []
    try:
        if content.startswith(b"%PDF-") and suffix == ".pdf":
            import pypdfium2 as pdfium

            document = pdfium.PdfDocument(content)
            if not 1 <= len(document) <= 100:
                raise ValueError("page limit")
            for index in range(len(document)):
                page = document[index]
                width, height = page.get_size()
                if not (0 < width <= 20000 and 0 < height <= 20000):
                    raise ValueError("page size")
                pages.append({"page": index + 1, "width": width, "height": height})
                page.close()
            document.close()
            media_type = "application/pdf"
        elif (content.startswith(b"\x89PNG\r\n\x1a\n") and suffix == ".png") or (
            content.startswith(b"\xff\xd8\xff") and suffix in {".jpg", ".jpeg"}
        ):
            from PIL import Image

            image = Image.open(io.BytesIO(content))
            if (
                image.width * image.height > 30_000_000
                or image.width <= 0
                or image.height <= 0
            ):
                raise ValueError("image size")
            image.verify()
            pages = [{"page": 1, "width": image.width, "height": image.height}]
            media_type = "image/png" if suffix == ".png" else "image/jpeg"
        else:
            raise ValueError("unsupported type")
    except ImportError:
        raise ApiError(503, "FILE_PARSER_UNAVAILABLE", "原件校验组件未安装，请联系管理员配置。")
    except Exception:
        raise ApiError(422, "INVALID_FILE", "仅支持有效的 PDF、PNG、JPEG，最多 100 页；文件类型须与扩展名一致。")
    return content, media_type, pages


async def upload_asset(db, actor, upload, key):
    content, media_type, pages = inspect_file(upload)
    content_hash = hashlib.sha256(content).hexdigest()
    identifier, fresh = await claim(
        db,
        actor,
        "asset.upload",
        key,
        {"filename": upload.filename, "hash": content_hash},
    )
    if fresh:
        item = PrivateAsset(
            id=identifier,
            school_id=actor.school_id,
            filename=upload.filename,
            media_type=media_type,
            byte_size=len(content),
            content_hash=content_hash,
            content=content,
            pages=pages,
            storage_key=f"{actor.school_id}/{identifier}/{content_hash}",
            created_by=actor.user_id,
        )
        db.add(item)
        audit(
            db,
            actor,
            "asset.upload",
            item,
            {"bytes": len(content), "hash": content_hash},
        )
        await db.commit()
    item = await owned(db, PrivateAsset, identifier, actor)
    return data(
        item,
        "id",
        "filename",
        "media_type",
        "byte_size",
        "content_hash",
        "pages",
        "created_at",
    )


def render_page(asset, page_number):
    if page_number < 1 or page_number > len(asset.pages):
        raise ApiError(404, "PAGE_NOT_FOUND", "原件中没有该页。")
    from PIL import Image

    if asset.media_type == "application/pdf":
        import pypdfium2 as pdfium

        document = pdfium.PdfDocument(asset.content)
        page = document[page_number - 1]
        width, height = page.get_size()
        scale = min(2, 2200 / max(width, height))
        bitmap = page.render(scale=scale)
        image = bitmap.to_pil().copy()
        bitmap.close()
        page.close()
        document.close()
        return image
    return Image.open(io.BytesIO(asset.content)).convert("RGB")


async def assert_asset_purpose(db, actor, asset_id, purpose):
    await owned(db, PrivateAsset, asset_id, actor, lock=True)
    report = await db.scalar(
        select(ReportAttachment.id)
        .where(
            ReportAttachment.school_id == actor.school_id,
            ReportAttachment.asset_id == asset_id,
        )
        .limit(1)
    )
    paper = await db.scalar(
        select(PaperVersion.id)
        .where(
            PaperVersion.school_id == actor.school_id, PaperVersion.asset_id == asset_id
        )
        .limit(1)
    )
    if report or (purpose == "report" and paper):
        raise ApiError(
            409, "ASSET_PURPOSE_CONFLICT", "报告原件不能复用于试卷或其他报告，请上传独立原件以保持权限边界。"
        )


async def create_paper(db, actor, body, key):
    await owned(db, Exam, body.exam_id, actor)
    await owned(db, Subject, body.subject_id, actor)
    await assert_asset_purpose(db, actor, body.asset_id, "paper")
    if not await db.scalar(
        select(ExamSubject.id).where(
            ExamSubject.exam_id == body.exam_id,
            ExamSubject.subject_id == body.subject_id,
        )
    ):
        raise ApiError(422, "EXAM_SUBJECT_REQUIRED", "请先为考试配置该科目和满分。")
    identifier, fresh = await claim(
        db, actor, "paper.create", key, body.model_dump(mode="json")
    )
    if fresh:
        item = Paper(
            id=identifier,
            school_id=actor.school_id,
            exam_id=body.exam_id,
            subject_id=body.subject_id,
            title=body.title,
        )
        db.add(item)
        await db.flush()
        version = PaperVersion(
            id=uuid4(),
            school_id=actor.school_id,
            paper_id=item.id,
            asset_id=body.asset_id,
            number=1,
        )
        db.add(version)
        await db.flush()
        db.add(PaperDraft(school_id=actor.school_id, paper_version_id=version.id))
        audit(db, actor, "paper.create", item)
        await db.commit()
    return await paper_detail(db, actor, identifier)


def teacher_paper_ids(actor):
    return scoped_scores(
        select(Paper.id)
        .join(
            StudentSubjectScore,
            (StudentSubjectScore.exam_id == Paper.exam_id)
            & (StudentSubjectScore.subject_id == Paper.subject_id),
        )
        .where(Paper.school_id == actor.school_id),
        actor,
        StudentSubjectScore,
    )


async def paper_detail(db, actor, identifier):
    item = await owned(db, Paper, identifier, actor)
    await subject_access(db, actor, item.subject_id)
    if is_teacher_only(actor) and not await db.scalar(
        teacher_paper_ids(actor).where(Paper.id == identifier).limit(1)
    ):
        raise ApiError(404, "PAPER_NOT_AVAILABLE", "试卷不在授权班级考试范围内。")
    versions = (
        await db.execute(
            select(
                PaperVersion,
                PrivateAsset.filename,
                PrivateAsset.pages,
                PrivateAsset.content_hash,
            )
            .join(PrivateAsset, PrivateAsset.id == PaperVersion.asset_id)
            .where(
                PaperVersion.paper_id == item.id,
                PaperVersion.school_id == actor.school_id,
            )
            .order_by(PaperVersion.number.desc())
        )
    ).all()
    return {
        **data(
            item,
            "id",
            "title",
            "exam_id",
            "subject_id",
            "revision",
            "source_system",
            "status",
        ),
        "versions": [
            {
                **data(v, "id", "number", "asset_id", "source_id", "created_at"),
                "filename": filename,
                "pages": pages,
                "content_hash": content_hash,
            }
            for v, filename, pages, content_hash in versions
        ],
    }


async def replace_paper(db, actor, identifier, body, key):
    item = await owned(db, Paper, identifier, actor, lock=True)
    native_only(item)
    _, fresh = await claim(
        db, actor, f"paper.replace.{identifier}", key, body.model_dump(mode="json")
    )
    if not fresh:
        return await paper_detail(db, actor, identifier)
    await assert_asset_purpose(db, actor, body.asset_id, "paper")
    await cas(db, item, body.expected_revision, {})
    version = PaperVersion(
        id=uuid4(),
        school_id=actor.school_id,
        paper_id=item.id,
        asset_id=body.asset_id,
        number=item.revision,
    )
    db.add(version)
    await db.flush()
    db.add(PaperDraft(school_id=actor.school_id, paper_version_id=version.id))
    audit(db, actor, "paper.version", item, {"version": item.revision})
    await db.commit()
    return await paper_detail(db, actor, identifier)


async def validate_tags(db, actor, subject_id, ids):
    for node_id in set(ids):
        node = await owned(db, TaxonomyNode, node_id, actor)
        if node.subject_id != subject_id or node.deleted_at:
            raise ApiError(422, "TAG_NOT_AVAILABLE", "标签必须属于当前学科且未删除。")


async def validate_question(db, actor, body):
    await owned(db, Subject, body.subject_id, actor)
    parent = (
        await owned(db, Question, body.parent_id, actor) if body.parent_id else None
    )
    if (parent.kind if parent else None) not in PARENTS[body.kind] or (
        parent and (parent.deleted_at or parent.subject_id != body.subject_id)
    ):
        raise ApiError(
            422, "INVALID_QUESTION_PARENT", "层级须为材料→大题→小题；独立题和材料不设父题，父子须同学科。"
        )
    await validate_body(db, actor, body.subject_id, body)


async def validate_body(db, actor, subject_id, body):
    if any(len(option) > 5000 for option in body.options):
        raise ApiError(422, "OPTION_TOO_LONG", "单个选项不能超过 5000 字。")
    await validate_tags(db, actor, subject_id, body.tag_ids)
    if body.paper_version_id:
        version = await owned(db, PaperVersion, body.paper_version_id, actor)
        paper = await owned(db, Paper, version.paper_id, actor)
        asset = await owned(db, PrivateAsset, version.asset_id, actor)
        if paper.subject_id != subject_id or any(
            region.page > len(asset.pages) for region in body.regions
        ):
            raise ApiError(422, "INVALID_PAPER_REGION", "原件学科或页码不匹配。")
    elif body.regions:
        raise ApiError(422, "PAPER_VERSION_REQUIRED", "框选区域须绑定原件版本。")


async def add_version(
    db, actor, question, body, number=1, published=False, source_id=None
):
    version = QuestionVersion(
        id=uuid4(),
        school_id=actor.school_id,
        question_id=question.id,
        number=number,
        stem=body.stem,
        options=body.options,
        answer=body.answer,
        explanation=body.explanation,
        paper_version_id=body.paper_version_id,
        regions=[r.model_dump() for r in body.regions],
        published_at=now() if published else None,
        source_id=source_id,
    )
    db.add(version)
    await db.flush()
    db.add_all(
        [
            QuestionTag(
                school_id=actor.school_id,
                question_version_id=version.id,
                node_id=node_id,
            )
            for node_id in set(body.tag_ids)
        ]
    )
    return version


async def create_question(db, actor, body, key):
    await validate_question(db, actor, body)
    identifier, fresh = await claim(
        db, actor, "question.create", key, body.model_dump(mode="json")
    )
    if fresh:
        item = Question(
            id=identifier,
            school_id=actor.school_id,
            subject_id=body.subject_id,
            kind=body.kind,
            parent_id=body.parent_id,
            title=body.title,
        )
        db.add(item)
        await db.flush()
        await add_version(db, actor, item, body)
        audit(db, actor, "question.create", item)
        await db.commit()
    return await question_detail(db, actor, identifier)


async def question_detail(db, actor, identifier):
    item = await owned(db, Question, identifier, actor)
    await subject_access(db, actor, item.subject_id)
    if is_teacher_only(actor) and (item.deleted_at or item.status != "published"):
        raise ApiError(404, "QUESTION_NOT_AVAILABLE", "题目未正式发布或已删除。")
    versions_query = select(QuestionVersion).where(
        QuestionVersion.question_id == item.id,
        QuestionVersion.school_id == actor.school_id,
    )
    if is_teacher_only(actor):
        versions_query = versions_query.where(QuestionVersion.published_at.is_not(None))
    versions = (
        await db.scalars(versions_query.order_by(QuestionVersion.number.desc()))
    ).all()
    result = data(
        item,
        "id",
        "subject_id",
        "kind",
        "parent_id",
        "title",
        "status",
        "source_system",
        "revision",
        "deleted_at",
    )
    children = (
        await db.scalars(
            select(Question)
            .where(
                Question.school_id == actor.school_id,
                Question.parent_id == item.id,
                Question.deleted_at.is_(None),
            )
            .order_by(Question.created_at)
        )
    ).all()
    result["children"] = [
        data(child, "id", "title", "kind", "status")
        for child in children
        if not is_teacher_only(actor) or child.status == "published"
    ]
    result["versions"] = []
    for v in versions:
        tags = (
            await db.scalars(
                select(TaxonomyNode)
                .join(QuestionTag, QuestionTag.node_id == TaxonomyNode.id)
                .where(
                    QuestionTag.question_version_id == v.id,
                    TaxonomyNode.school_id == actor.school_id,
                )
            )
        ).all()
        result["versions"].append(
            {
                **data(
                    v,
                    "id",
                    "number",
                    "stem",
                    "options",
                    "answer",
                    "explanation",
                    "paper_version_id",
                    "regions",
                    "source_id",
                    "published_at",
                    "created_at",
                ),
                "tags": [data(t, "id", "name", "kind") for t in tags],
            }
        )
    return result


async def edit_question(db, actor, identifier, body, key):
    item = await owned(db, Question, identifier, actor, lock=True)
    native_only(item)
    _, fresh = await claim(
        db, actor, f"question.edit.{identifier}", key, body.model_dump(mode="json")
    )
    if fresh:
        if item.deleted_at:
            raise ApiError(409, "QUESTION_DELETED", "请先恢复该题目。")
        await validate_body(db, actor, item.subject_id, body)
        await cas(db, item, body.expected_revision, {"status": "draft"})
        number = await db.scalar(
            select(func.max(QuestionVersion.number)).where(
                QuestionVersion.question_id == item.id
            )
        )
        await add_version(db, actor, item, body, number + 1)
        audit(db, actor, "question.version", item)
        await db.commit()
    return await question_detail(db, actor, identifier)


async def publish_question(db, actor, identifier, body, key):
    item = await owned(db, Question, identifier, actor, lock=True)
    native_only(item)
    _, fresh = await claim(
        db, actor, f"question.publish.{identifier}", key, body.model_dump()
    )
    if fresh:
        if item.deleted_at:
            raise ApiError(409, "QUESTION_DELETED", "已删除题目不可发布。")
        if item.parent_id:
            parent = await owned(db, Question, item.parent_id, actor)
            if parent.deleted_at or parent.status != "published":
                raise ApiError(409, "PARENT_NOT_PUBLISHED", "请先发布父级材料或大题。")
        await cas(db, item, body.expected_revision, {"status": "published"})
        version = await db.scalar(
            select(QuestionVersion)
            .where(QuestionVersion.question_id == item.id)
            .order_by(QuestionVersion.number.desc())
            .limit(1)
        )
        version.published_at = version.published_at or now()
        audit(db, actor, "question.publish", item)
        await db.commit()
    return await question_detail(db, actor, identifier)


async def question_references(db, actor, item):
    versions = select(QuestionVersion.id).where(
        QuestionVersion.question_id == item.id,
        QuestionVersion.school_id == actor.school_id,
    )
    counts = {
        "scores": int(
            await db.scalar(
                select(func.count())
                .select_from(QuestionScore)
                .where(
                    QuestionScore.school_id == actor.school_id,
                    or_(
                        QuestionScore.question_id == item.id,
                        QuestionScore.question_version_id.in_(versions),
                    ),
                )
            )
            or 0
        ),
        "reviews": int(
            await db.scalar(
                select(func.count())
                .select_from(ReviewEntry)
                .where(
                    ReviewEntry.school_id == actor.school_id,
                    ReviewEntry.question_version_id.in_(versions),
                )
            )
            or 0
        ),
        "children": int(
            await db.scalar(
                select(func.count())
                .select_from(Question)
                .where(Question.parent_id == item.id, Question.deleted_at.is_(None))
            )
            or 0
        ),
    }
    return counts


async def lifecycle(db, actor, model, identifier, action):
    item = await owned(db, model, identifier, actor, lock=True)
    native_only(item)
    if action == "delete" and not item.deleted_at:
        if model is Question:
            refs = await question_references(db, actor, item)
        else:
            refs = {
                "questions": int(
                    await db.scalar(
                        select(func.count())
                        .select_from(QuestionTag)
                        .where(QuestionTag.node_id == item.id)
                    )
                    or 0
                ),
                "children": int(
                    await db.scalar(
                        select(func.count())
                        .select_from(TaxonomyNode)
                        .where(
                            TaxonomyNode.parent_id == item.id,
                            TaxonomyNode.deleted_at.is_(None),
                        )
                    )
                    or 0
                ),
                "scores": int(
                    await db.scalar(
                        select(func.count())
                        .select_from(QuestionScore)
                        .where(
                            QuestionScore.school_id == actor.school_id,
                            QuestionScore.knowledge_point_id == item.id,
                        )
                    )
                    or 0
                ),
            }
        if any(refs.values()):
            raise ApiError(409, "RESOURCE_REFERENCED", "记录仍被引用，不能删除。", details=refs)
        item.deleted_at = now()
    elif action == "restore" and item.deleted_at:
        if item.parent_id:
            parent = await owned(db, model, item.parent_id, actor)
            if parent.deleted_at:
                raise ApiError(409, "PARENT_DELETED", "请先恢复父级记录。")
        item.deleted_at = None
    else:
        return item
    item.revision += 1
    audit(db, actor, f"{model.__tablename__}.{action}", item)
    await db.flush()
    return item


async def taxonomy_write(db, actor, body, key, identifier=None):
    await owned(db, Subject, body.subject_id, actor)
    if body.parent_id:
        parent = await owned(db, TaxonomyNode, body.parent_id, actor)
        if (
            parent.deleted_at
            or parent.subject_id != body.subject_id
            or parent.kind != body.kind
        ):
            raise ApiError(422, "INVALID_TAXONOMY_PARENT", "父节点须有效且属于同一学科、同一字典类型。")
        seen = {identifier} if identifier else set()
        while parent:
            if parent.id in seen:
                raise ApiError(422, "TAXONOMY_CYCLE", "知识点父子关系不能形成环。")
            seen.add(parent.id)
            parent = (
                await owned(db, TaxonomyNode, parent.parent_id, actor)
                if parent.parent_id
                else None
            )
    receipt_id, fresh = await claim(
        db, actor, f"taxonomy.write.{identifier}", key, body.model_dump(mode="json")
    )
    if fresh:
        if identifier:
            item = await owned(db, TaxonomyNode, identifier, actor, lock=True)
            referenced = await db.scalar(
                select(QuestionTag.id).where(QuestionTag.node_id == item.id).limit(1)
            )
            children = await db.scalar(
                select(TaxonomyNode.id)
                .where(TaxonomyNode.parent_id == item.id)
                .limit(1)
            )
            if item.deleted_at or (
                (referenced or children)
                and (item.subject_id != body.subject_id or item.kind != body.kind)
            ):
                raise ApiError(409, "TAXONOMY_REFERENCED", "已删除或被引用节点不可改变学科与类型。")
            await cas(
                db,
                item,
                body.expected_revision,
                body.model_dump(exclude={"expected_revision"}),
            )
        else:
            item = TaxonomyNode(
                id=receipt_id, school_id=actor.school_id, **body.model_dump()
            )
            db.add(item)
        audit(db, actor, "taxonomy.save", item)
        await db.commit()
    return data(
        await owned(db, TaxonomyNode, identifier or receipt_id, actor),
        "id",
        "name",
        "kind",
        "subject_id",
        "parent_id",
        "revision",
        "deleted_at",
    )


async def draft_detail(db, actor, version_id, lock=False):
    version = await owned(db, PaperVersion, version_id, actor)
    paper = await owned(db, Paper, version.paper_id, actor)
    await subject_access(db, actor, paper.subject_id)
    query = select(PaperDraft).where(
        PaperDraft.paper_version_id == version_id,
        PaperDraft.school_id == actor.school_id,
    )
    draft = await db.scalar(query.with_for_update() if lock else query)
    if draft is None:
        raise ApiError(404, "DRAFT_NOT_AVAILABLE", "该外部版本没有原生拆题草稿。")
    return paper, draft


async def save_draft(db, actor, version_id, body, key):
    paper, draft = await draft_detail(db, actor, version_id, lock=True)
    native_only(paper)
    _, fresh = await claim(
        db, actor, f"draft.save.{draft.id}", key, body.model_dump(mode="json")
    )
    if fresh:
        if draft.published_revision is not None:
            raise ApiError(409, "DRAFT_PUBLISHED", "已发布草稿已冻结，请新增原件版本或编辑题目新版本。")
        keys = set()
        kinds = {}
        asset = await owned(
            db,
            PrivateAsset,
            (await owned(db, PaperVersion, version_id, actor)).asset_id,
            actor,
        )
        for entry in body.entries:
            if (
                entry.key in keys
                or (entry.parent_key and entry.parent_key not in keys)
                or kinds.get(entry.parent_key) not in PARENTS[entry.kind]
            ):
                raise ApiError(
                    422, "INVALID_DRAFT_TREE", "草稿标识须唯一，父题排在子题前，且材料/大题/小题层级有效。"
                )
            if any(r.page > len(asset.pages) for r in entry.regions):
                raise ApiError(422, "INVALID_PAGE", "草稿页码超出原件。")
            await validate_tags(db, actor, paper.subject_id, entry.tag_ids)
            keys.add(entry.key)
            kinds[entry.key] = entry.kind
        await cas(
            db,
            draft,
            body.expected_revision,
            {
                "entries": [e.model_dump(mode="json") for e in body.entries],
                "updated_at": now(),
            },
        )
        audit(db, actor, "draft.save", draft)
        await db.commit()
    return data(
        draft,
        "id",
        "revision",
        "entries",
        "published_revision",
        "published_ids",
        "updated_at",
    )


async def publish_draft(db, actor, version_id, body, key):
    paper, draft = await draft_detail(db, actor, version_id, lock=True)
    native_only(paper)
    if draft.published_revision == body.expected_revision:
        return data(draft, "id", "revision", "published_revision", "published_ids")
    if draft.revision != body.expected_revision or draft.published_revision is not None:
        raise ApiError(409, "VERSION_CONFLICT", "草稿已更新或发布，请刷新核对。")
    if not draft.entries or any(not entry["stem"].strip() for entry in draft.entries):
        raise ApiError(422, "DRAFT_INCOMPLETE", "每道题必须有人工确认的题干，空草稿不能发布。")
    _, fresh = await claim(
        db, actor, f"draft.publish.{draft.id}", key, body.model_dump()
    )
    if fresh:
        created = {}
        for entry in draft.entries:
            identifier = uuid4()
            body_question = QuestionCreate(
                subject_id=paper.subject_id,
                kind=entry["kind"],
                title=entry["title"],
                parent_id=created.get(entry.get("parent_key")),
                stem=entry["stem"],
                options=entry.get("options", []),
                answer=entry["answer"],
                explanation=entry["explanation"],
                paper_version_id=version_id,
                regions=entry["regions"],
                tag_ids=entry.get("tag_ids", []),
            )
            await validate_question(db, actor, body_question)
            question = Question(
                id=identifier,
                school_id=actor.school_id,
                subject_id=paper.subject_id,
                kind=entry["kind"],
                parent_id=body_question.parent_id,
                title=entry["title"],
                status="published",
            )
            db.add(question)
            await db.flush()
            await add_version(db, actor, question, body_question, published=True)
            created[entry["key"]] = identifier
        draft.published_revision = draft.revision
        draft.published_ids = [str(v) for v in created.values()]
        audit(db, actor, "draft.publish", draft, {"count": len(created)})
        await db.commit()
    return data(draft, "id", "revision", "published_revision", "published_ids")
