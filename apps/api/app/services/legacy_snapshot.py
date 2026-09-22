"""Read-only legacy projections from explicitly supplied, validated exports.

No legacy database, filesystem archive or remote URL is ever read by this service.
Each external ID is scoped by school/source/type. Historical payloads stay pinned.
"""
from uuid import uuid4
from datetime import timezone
from sqlalchemy import select, func
from app.core.errors import ApiError
from app.db.models.education import (
    SourceRecord,
    Paper,
    PaperVersion,
    PrivateAsset,
    Question,
    QuestionVersion,
    ReportAttachment,
)
from app.db.models.school import School
from app.db.models.student import Student
from app.db.models.exam import Exam, Subject, ExamSubject
from app.db.models.score import StudentExamScore, StudentSubjectScore, QuestionScore
from app.db.models.diagnosis import DiagnosisReport
from app.schemas.education import QuestionCreate
from app.services.education_common import owned, digest, now, audit, data
from app.services.curriculum import validate_question, add_version, assert_asset_purpose


async def lookup(db, actor, source, kind, external):
    result = await db.scalar(
        select(SourceRecord)
        .where(
            SourceRecord.school_id == actor.school_id,
            SourceRecord.source_system == source,
            SourceRecord.entity_type == kind,
            SourceRecord.external_id == external,
        )
        .order_by(SourceRecord.created_at.desc(), SourceRecord.captured_at.desc())
        .limit(1)
    )
    if result is None:
        raise ApiError(422, "SOURCE_MAPPING_MISSING", f"{kind} 的来源映射不存在，请先提供被引用实体。")
    return result


async def student_lookup(db, actor, external):
    student = await db.scalar(
        select(Student).where(
            Student.school_id == actor.school_id,
            Student.external_student_id == external,
        )
    )
    if student is None:
        raise ApiError(422, "STUDENT_MAPPING_MISSING", "请先建立明确的本校学生外部 ID 映射；不按姓名自动匹配。")
    return student


async def ingest(db, actor, body):
    if body.captured_at.tzinfo is None:
        raise ApiError(422, "SOURCE_TIME_REQUIRED", "来源水位须包含时区。")
    await db.scalar(
        select(School).where(School.id == actor.school_id).with_for_update()
    )
    seen, items = set(), []
    # Dependencies are deliberate: exams, papers, parent-first questions, reports, scores.
    order = {"exam": 0, "paper": 1, "question": 2, "report": 3, "score": 4}
    for entry in sorted(body.records, key=lambda r: order[r.entity_type]):
        pair = (entry.entity_type, entry.external_id)
        if pair in seen:
            raise ApiError(422, "DUPLICATE_SOURCE_ID", "同批次实体来源 ID 重复。")
        seen.add(pair)
        payload = entry.model_dump(mode="json")
        content_hash = digest(payload)
        old = await db.scalar(
            select(SourceRecord).where(
                SourceRecord.school_id == actor.school_id,
                SourceRecord.source_system == body.source_system,
                SourceRecord.entity_type == entry.entity_type,
                SourceRecord.external_id == entry.external_id,
                SourceRecord.source_version == body.source_version,
            )
        )
        if old:
            if old.content_hash != content_hash:
                raise ApiError(
                    409, "SOURCE_VERSION_CONFLICT", "相同来源版本的内容发生变化，请使用新的来源版本。"
                )
            items.append(
                {
                    **data(
                        old,
                        "id",
                        "entity_type",
                        "external_id",
                        "native_id",
                        "source_version",
                        "content_hash",
                    ),
                    "replayed": True,
                }
            )
            continue
        previous = await db.scalar(
            select(SourceRecord)
            .where(
                SourceRecord.school_id == actor.school_id,
                SourceRecord.source_system == body.source_system,
                SourceRecord.entity_type == entry.entity_type,
                SourceRecord.external_id == entry.external_id,
            )
            .order_by(SourceRecord.created_at.desc())
            .limit(1)
        )
        if (
            previous
            and (
                previous.captured_at
                if previous.captured_at.tzinfo
                else previous.captured_at.replace(tzinfo=timezone.utc)
            )
            > body.captured_at
        ):
            raise ApiError(409, "SOURCE_WATERMARK_REGRESSION", "来源水位不能早于已有版本。")
        identifier = (
            previous.native_id
            if previous and entry.entity_type != "report"
            else uuid4()
        )
        source = SourceRecord(
            id=uuid4(),
            school_id=actor.school_id,
            source_system=body.source_system,
            entity_type=entry.entity_type,
            external_id=entry.external_id,
            source_version=body.source_version,
            content_hash=content_hash,
            captured_at=body.captured_at,
            native_id=identifier,
            payload=payload,
        )
        db.add(source)
        await db.flush()
        if entry.entity_type == "exam":
            item = (
                await db.get(Exam, identifier)
                if previous
                else Exam(
                    id=identifier,
                    school_id=actor.school_id,
                    external_exam_id=f"legacy-{digest([body.source_system,entry.external_id])}",
                    source_system=body.source_system,
                )
            )
            item.name, item.exam_type, item.start_date = (
                entry.name,
                entry.exam_type,
                entry.start_date,
            )
            db.add(item)
        elif entry.entity_type == "paper":
            exam_id = (
                await lookup(
                    db, actor, body.source_system, "exam", entry.exam_external_id
                )
            ).native_id
            await owned(db, Subject, entry.subject_id, actor)
            await assert_asset_purpose(db, actor, entry.asset_id, "paper")
            item = (
                await db.get(Paper, identifier)
                if previous
                else Paper(
                    id=identifier,
                    school_id=actor.school_id,
                    exam_id=exam_id,
                    subject_id=entry.subject_id,
                    title=entry.title,
                    source_system=body.source_system,
                )
            )
            if previous and (
                item.exam_id != exam_id or item.subject_id != entry.subject_id
            ):
                raise ApiError(409, "SOURCE_IDENTITY_CHANGED", "同一试卷来源 ID 不能改变考试或学科归属。")
            item.title = entry.title
            db.add(item)
            await db.flush()
            number = (
                await db.scalar(
                    select(func.max(PaperVersion.number)).where(
                        PaperVersion.paper_id == identifier
                    )
                )
                or 0
            ) + 1
            db.add(
                PaperVersion(
                    school_id=actor.school_id,
                    paper_id=identifier,
                    asset_id=entry.asset_id,
                    number=number,
                    source_id=source.id,
                )
            )
        elif entry.entity_type == "question":
            parent_id = (
                (
                    await lookup(
                        db,
                        actor,
                        body.source_system,
                        "question",
                        entry.parent_external_id,
                    )
                ).native_id
                if entry.parent_external_id
                else None
            )
            paper_version = None
            if entry.paper_external_id:
                paper_id = (
                    await lookup(
                        db, actor, body.source_system, "paper", entry.paper_external_id
                    )
                ).native_id
                paper_version = await db.scalar(
                    select(PaperVersion.id)
                    .where(
                        PaperVersion.school_id == actor.school_id,
                        PaperVersion.paper_id == paper_id,
                    )
                    .order_by(PaperVersion.number.desc())
                    .limit(1)
                )
            question_body = QuestionCreate(
                subject_id=entry.subject_id,
                kind=entry.kind,
                parent_id=parent_id,
                title=entry.title,
                stem=entry.stem,
                options=entry.options,
                answer=entry.answer,
                explanation=entry.explanation,
                paper_version_id=paper_version,
            )
            await validate_question(db, actor, question_body)
            item = (
                await db.get(Question, identifier)
                if previous
                else Question(
                    id=identifier,
                    school_id=actor.school_id,
                    subject_id=entry.subject_id,
                    kind=entry.kind,
                    parent_id=parent_id,
                    title=entry.title,
                    source_system=body.source_system,
                    status="published",
                )
            )
            if previous and (
                item.subject_id != entry.subject_id
                or item.parent_id != parent_id
                or item.kind != entry.kind
            ):
                raise ApiError(409, "SOURCE_IDENTITY_CHANGED", "同一题目来源 ID 不能改变学科或层级归属。")
            db.add(item)
            await db.flush()
            number = (
                await db.scalar(
                    select(func.max(QuestionVersion.number)).where(
                        QuestionVersion.question_id == identifier
                    )
                )
                or 0
            ) + 1
            await add_version(
                db,
                actor,
                item,
                question_body,
                number,
                published=True,
                source_id=source.id,
            )
        elif entry.entity_type == "report":
            student = await student_lookup(db, actor, entry.student_external_id)
            exam_id = (
                await lookup(
                    db, actor, body.source_system, "exam", entry.exam_external_id
                )
            ).native_id
            if entry.subject_id:
                await owned(db, Subject, entry.subject_id, actor)
            if previous:
                prior_report = await db.get(DiagnosisReport, previous.native_id)
                if (
                    prior_report.student_id != student.id
                    or prior_report.exam_id != exam_id
                    or prior_report.subject_id != entry.subject_id
                ):
                    raise ApiError(
                        409, "SOURCE_IDENTITY_CHANGED", "同一报告来源 ID 不能改变学生、考试或学科。"
                    )
            item = DiagnosisReport(
                id=identifier,
                school_id=actor.school_id,
                student_id=student.id,
                exam_id=exam_id,
                subject_id=entry.subject_id,
                report_type=entry.report_type,
                status="generated",
                source_system=body.source_system,
                raw_content=entry.raw_content,
                structured_json={"summary": entry.summary},
                version=body.source_version,
                generated_at=entry.generated_at,
            )
            db.add(item)
            await db.flush()
            if entry.asset_id:
                await assert_asset_purpose(db, actor, entry.asset_id, "report")
                db.add(
                    ReportAttachment(
                        school_id=actor.school_id,
                        report_id=identifier,
                        asset_id=entry.asset_id,
                        source_id=source.id,
                    )
                )
        else:
            if entry.score > entry.full_score or (
                entry.question_external_id
                and (not entry.subject_id or not entry.question_no)
            ):
                raise ApiError(422, "INVALID_SCORE", "得分不能超过满分，小题须含学科和题号。")
            student = await student_lookup(db, actor, entry.student_external_id)
            exam_id = (
                await lookup(
                    db, actor, body.source_system, "exam", entry.exam_external_id
                )
            ).native_id
            model = (
                QuestionScore
                if entry.question_external_id
                else StudentSubjectScore
                if entry.subject_id
                else StudentExamScore
            )
            query = select(model).where(
                model.school_id == actor.school_id,
                model.student_id == student.id,
                model.exam_id == exam_id,
            )
            values = {
                "school_id": actor.school_id,
                "student_id": student.id,
                "exam_id": exam_id,
                "full_score": entry.full_score,
            }
            if entry.subject_id:
                await owned(db, Subject, entry.subject_id, actor)
                query = query.where(model.subject_id == entry.subject_id)
                values.update(subject_id=entry.subject_id, score=entry.score)
            else:
                values["total_score"] = entry.score
            if entry.question_external_id:
                question_id = (
                    await lookup(
                        db,
                        actor,
                        body.source_system,
                        "question",
                        entry.question_external_id,
                    )
                ).native_id
                question = await owned(db, Question, question_id, actor)
                if question.subject_id != entry.subject_id:
                    raise ApiError(422, "SUBJECT_MISMATCH", "小题和成绩学科不一致。")
                version = await db.scalar(
                    select(QuestionVersion)
                    .where(
                        QuestionVersion.question_id == question_id,
                        QuestionVersion.published_at.is_not(None),
                    )
                    .order_by(QuestionVersion.number.desc())
                    .limit(1)
                )
                query = query.where(QuestionScore.question_no == entry.question_no)
                values.update(
                    question_id=question_id,
                    question_version_id=version.id,
                    question_no=entry.question_no,
                    lost_score=round(entry.full_score - entry.score, 2),
                )
            else:
                values.update(class_rank=entry.class_rank, grade_rank=entry.grade_rank)
            existing = await db.scalar(query)
            if existing and (not previous or previous.native_id != existing.id):
                raise ApiError(
                    409, "SCORE_MAPPING_CONFLICT", "该成绩业务键已由其他来源 ID 管理，不允许覆盖。"
                )
            if previous and (existing is None or existing.id != identifier):
                raise ApiError(409, "SOURCE_IDENTITY_CHANGED", "同一成绩来源 ID 不能改归学生或考试。")
            item = existing or model(id=identifier, **values)
            # Keep pinned question versions stable once learning records exist.
            if (
                existing
                and isinstance(item, QuestionScore)
                and item.question_version_id != values.get("question_version_id")
            ):
                raise ApiError(409, "SCORE_VERSION_PINNED", "历史小题依据已固定，需单独核查版本更正。")
            for field, value in values.items():
                setattr(item, field, value)
            db.add(item)
        await db.flush()
        audit(db, actor, "source.ingest", source, {"entity_type": entry.entity_type})
        items.append(
            {
                **data(
                    source,
                    "id",
                    "entity_type",
                    "external_id",
                    "native_id",
                    "source_version",
                    "content_hash",
                ),
                "replayed": False,
            }
        )
    await db.commit()
    return {
        "mode": "controlled_snapshot",
        "source_system": body.source_system,
        "source_version": body.source_version,
        "captured_at": body.captured_at.isoformat(),
        "count": len(items),
        "items": items,
        "live_connection": False,
    }
