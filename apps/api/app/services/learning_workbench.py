"""Student revision, authorized report originals, human messages and evidence."""
from uuid import UUID
from sqlalchemy import select, and_, func, update
from app.core.errors import ApiError
from app.core.access_scope import scoped, is_teacher_only
from app.core.diagnosis_access import require_report, audit_report_access
from app.db.models.education import (
    Question,
    QuestionVersion,
    ReviewEntry,
    ReviewRecord,
    ReportAttachment,
    PrivateAsset,
    SourceRecord,
    HandoffMessage,
    PaperVersion,
    Paper,
)
from app.db.models.score import QuestionScore, StudentExamScore, StudentSubjectScore
from app.db.models.exam import Exam, Subject
from app.db.models.student import Student
from app.db.models.user import User
from app.db.models.diagnosis import DiagnosisReport
from app.db.models.platform import HumanHandoff
from app.db.models.chat import ChatMessage, ChatSession
from app.db.models.trace import AuditLog
from app.services.education_common import owned, claim, audit, now, data


async def student_owned(db, model, identifier, actor):
    item = await owned(db, model, identifier, actor)
    if item.student_id != actor.student_id:
        raise ApiError(404, "RESOURCE_NOT_AVAILABLE", "记录不存在或不属于当前学生。")
    return item


async def question_facts(db, actor, score_id):
    score = await student_owned(db, QuestionScore, score_id, actor)
    question = None
    if score.question_version_id:
        version = await owned(db, QuestionVersion, score.question_version_id, actor)
        item = await owned(db, Question, version.question_id, actor)
        if version.published_at:
            question = {
                **data(
                    version,
                    "id",
                    "number",
                    "stem",
                    "options",
                    "answer",
                    "explanation",
                    "paper_version_id",
                    "regions",
                    "source_id",
                ),
                "title": item.title,
                "kind": item.kind,
                "parents": [],
            }
            parent_id = item.parent_id
            # Parent content is only shown from published versions; source date pins it.
            while parent_id:
                parent = await owned(db, Question, parent_id, actor)
                parent_version = await db.scalar(
                    select(QuestionVersion)
                    .where(
                        QuestionVersion.question_id == parent_id,
                        QuestionVersion.published_at.is_not(None),
                        QuestionVersion.created_at <= version.created_at,
                    )
                    .order_by(QuestionVersion.number.desc())
                    .limit(1)
                )
                if parent_version:
                    question["parents"].insert(
                        0,
                        {
                            "title": parent.title,
                            "stem": parent_version.stem,
                            "version": parent_version.number,
                        },
                    )
                parent_id = parent.parent_id
    exam = await owned(db, Exam, score.exam_id, actor)
    subject = await owned(db, Subject, score.subject_id, actor)
    return {
        "score": {
            **data(score, "id", "question_no", "question_version_id"),
            "score": float(score.score),
            "full_score": float(score.full_score),
            "lost_score": float(score.lost_score),
            "exam": exam.name,
            "subject": subject.name,
        },
        "question": question,
        "missing_reason": None if question else "尚未关联经确认的正式题目版本，请联系学校补全来源；得分事实仍可查看。",
    }


async def add_review(db, actor, body, key):
    score = await owned(db, QuestionScore, body.score_id, actor, lock=True)
    if score.student_id != actor.student_id:
        raise ApiError(404, "RESOURCE_NOT_AVAILABLE", "记录不属于当前学生。")
    if not score.question_version_id:
        raise ApiError(409, "QUESTION_SOURCE_REQUIRED", "该成绩尚未关联原题，暂不能加入复盘。")
    await question_facts(db, actor, score.id)
    existing = await db.scalar(
        select(ReviewEntry).where(
            ReviewEntry.student_id == actor.student_id, ReviewEntry.score_id == score.id
        )
    )
    if existing:
        return await review_detail(db, actor, existing.id)
    identifier, fresh = await claim(
        db, actor, "review.create", key, body.model_dump(mode="json")
    )
    if fresh:
        item = ReviewEntry(
            id=identifier,
            school_id=actor.school_id,
            student_id=actor.student_id,
            score_id=score.id,
            question_version_id=score.question_version_id,
        )
        db.add(item)
        audit(db, actor, "review.create", item)
        await db.commit()
    return await review_detail(db, actor, identifier)


async def review_detail(db, actor, identifier):
    item = await student_owned(db, ReviewEntry, identifier, actor)
    records = (
        await db.scalars(
            select(ReviewRecord)
            .where(
                ReviewRecord.review_id == identifier,
                ReviewRecord.school_id == actor.school_id,
            )
            .order_by(ReviewRecord.created_at.desc(), ReviewRecord.id.desc())
        )
    ).all()
    return {
        **data(item, "id", "score_id", "question_version_id", "created_at"),
        **await question_facts(db, actor, item.score_id),
        "records": [
            data(r, "id", "correction", "mastery", "next_review_at", "created_at")
            for r in records
        ],
        "mastery": records[0].mastery if records else "learning",
        "mastery_source": "student_self_report",
    }


async def add_review_record(db, actor, identifier, body, key):
    await student_owned(db, ReviewEntry, identifier, actor)
    if body.next_review_at and body.next_review_at.tzinfo is None:
        raise ApiError(422, "TIMEZONE_REQUIRED", "复习时间须包含时区。")
    record_id, fresh = await claim(
        db, actor, f"review.record.{identifier}", key, body.model_dump(mode="json")
    )
    if fresh:
        item = ReviewRecord(
            id=record_id,
            school_id=actor.school_id,
            review_id=identifier,
            **body.model_dump(),
        )
        db.add(item)
        audit(db, actor, "review.record", item)
        await db.commit()
    return await review_detail(db, actor, identifier)


async def create_report(db, actor, body, key):
    await owned(db, Student, body.student_id, actor)
    await owned(db, Exam, body.exam_id, actor)
    await owned(db, PrivateAsset, body.asset_id, actor)
    if body.subject_id:
        await owned(db, Subject, body.subject_id, actor)
    identifier, fresh = await claim(
        db, actor, "report.create", key, body.model_dump(mode="json")
    )
    if fresh:
        from app.services.curriculum import assert_asset_purpose

        await assert_asset_purpose(db, actor, body.asset_id, "report")
        collision = await db.scalar(
            select(DiagnosisReport.id).where(
                DiagnosisReport.school_id == actor.school_id,
                DiagnosisReport.student_id == body.student_id,
                DiagnosisReport.exam_id == body.exam_id,
                DiagnosisReport.subject_id == body.subject_id,
                DiagnosisReport.report_type == body.report_type,
                DiagnosisReport.version == body.version,
            )
        )
        if collision:
            raise ApiError(409, "REPORT_VERSION_EXISTS", "该学生、考试、科目和类型的报告版本已存在，请发布新版本。")
        item = DiagnosisReport(
            id=identifier,
            school_id=actor.school_id,
            student_id=body.student_id,
            exam_id=body.exam_id,
            subject_id=body.subject_id,
            report_type=body.report_type,
            version=body.version,
            raw_content=body.raw_content,
            structured_json={"summary": body.summary},
            generated_at=body.generated_at,
            status="generated",
            source_system="native",
        )
        db.add(item)
        await db.flush()
        db.add(
            ReportAttachment(
                school_id=actor.school_id, report_id=identifier, asset_id=body.asset_id
            )
        )
        audit(db, actor, "report.create", item)
        await db.commit()
    return data(
        await owned(db, DiagnosisReport, identifier, actor),
        "id",
        "version",
        "status",
        "source_system",
        "generated_at",
    )


async def report_versions(db, actor, identifier):
    report = await require_report(db, actor, identifier)
    from app.core.diagnosis_access import authorized_reports

    versions = (
        await db.scalars(
            authorized_reports(actor.school_id, actor.student_id)
            .where(
                DiagnosisReport.exam_id == report.exam_id,
                DiagnosisReport.subject_id == report.subject_id,
                DiagnosisReport.report_type == report.report_type,
            )
            .order_by(DiagnosisReport.generated_at.desc())
        )
    ).all()
    result = []
    for version in versions:
        attachment = await db.scalar(
            select(ReportAttachment).where(
                ReportAttachment.school_id == actor.school_id,
                ReportAttachment.report_id == version.id,
            )
        )
        result.append(
            {
                **data(
                    version,
                    "id",
                    "version",
                    "source_system",
                    "generated_at",
                    "report_type",
                ),
                "asset_id": str(attachment.asset_id) if attachment else None,
                "has_text": bool(version.raw_content),
            }
        )
    await audit_report_access(db, actor, True, report.id)
    return result


async def handoff_access(db, actor, identifier, lock=False):
    query = select(HumanHandoff).where(
        HumanHandoff.id == identifier, HumanHandoff.school_id == actor.school_id
    )
    manager = any(
        actor.has_role(r)
        for r in ("TEACHER", "SCHOOL_ADMIN", "QA", "SUPER_ADMIN", "CITY_OPERATOR")
    )
    if manager:
        query = scoped(query, actor, HumanHandoff.school_id)
    elif actor.has_role("STUDENT"):
        query = query.where(
            HumanHandoff.student_id.in_(
                select(Student.id).where(
                    Student.school_id == actor.school_id,
                    Student.user_id == actor.user_id,
                    Student.status == "active",
                )
            )
        )
    else:
        raise ApiError(403, "HANDOFF_PERMISSION_REQUIRED", "没有人工服务访问权限。")
    item = await db.scalar(query.with_for_update() if lock else query)
    if item is None:
        raise ApiError(404, "HANDOFF_NOT_AVAILABLE", "工单不存在或不在授权范围内。")
    return item, manager


async def handoff_detail(db, actor, identifier):
    item, manager = await handoff_access(db, actor, identifier)
    messages = (
        await db.scalars(
            select(HandoffMessage)
            .where(
                HandoffMessage.handoff_id == identifier,
                HandoffMessage.school_id == actor.school_id,
            )
            .order_by(HandoffMessage.created_at, HandoffMessage.id)
            .limit(500)
        )
    ).all()
    events = (
        await db.scalars(
            select(AuditLog)
            .where(
                AuditLog.resource_id == identifier,
                AuditLog.action == "platform.handoff.transition",
                AuditLog.allowed.is_(True),
            )
            .order_by(AuditLog.created_at)
            .limit(100)
        )
    ).all()
    assignee = (
        await db.scalar(
            select(User.display_name).where(
                User.id == item.assigned_to, User.school_id == actor.school_id
            )
        )
        if item.assigned_to
        else None
    )
    return {
        **data(
            item,
            "id",
            "status",
            "state_version",
            "reason",
            "summary",
            "resolution",
            "created_at",
            "accepted_at",
            "resolved_at",
        ),
        "assignee": assignee,
        "can_reply": item.status in {"open", "accepted"}
        and (
            not manager
            or (
                not actor.has_role("QA")
                and (
                    item.assigned_to == actor.user_id
                    or actor.has_role("SCHOOL_ADMIN")
                    or actor.has_role("SUPER_ADMIN")
                )
            )
        ),
        "messages": [
            data(m, "id", "sender_role", "content", "created_at") for m in messages
        ],
        "history": [
            {
                "time": event.created_at.isoformat(),
                "status": (event.extra_data or {}).get("to_status"),
                "note": (event.extra_data or {}).get("note"),
            }
            for event in events
        ],
    }


async def handoff_reply(db, actor, identifier, body, key):
    item, manager = await handoff_access(db, actor, identifier, lock=True)
    # A replay remains readable after closing; new messages require an open case.
    message_id, fresh = await claim(
        db, actor, f"handoff.reply.{identifier}", key, body.model_dump()
    )
    if fresh:
        if item.status not in {"open", "accepted"}:
            raise ApiError(409, "HANDOFF_CLOSED", "工单已结束，请先填写原因重新打开。")
        if manager and (
            actor.has_role("QA")
            or not (
                item.assigned_to == actor.user_id
                or actor.has_role("SCHOOL_ADMIN")
                or actor.has_role("SUPER_ADMIN")
            )
        ):
            raise ApiError(403, "HANDOFF_ASSIGNEE_REQUIRED", "请先接单；仅处理人或学校管理员可以回复。")
        message = HandoffMessage(
            id=message_id,
            school_id=actor.school_id,
            handoff_id=identifier,
            sender_id=actor.user_id,
            sender_role="staff" if manager else "student",
            content=body.content,
        )
        db.add(message)
        audit(db, actor, "handoff.reply", message)
        await db.commit()
    return await handoff_detail(db, actor, identifier)


async def student_handoff_state(db, actor, identifier, body, target):
    item, _ = await handoff_access(db, actor, identifier, lock=True)
    if item.student_id != actor.student_id:
        raise ApiError(404, "HANDOFF_NOT_AVAILABLE", "工单不存在。")
    if item.status == target and item.resolution == body.reason:
        return await handoff_detail(db, actor, identifier)
    if (
        item.state_version != body.expected_version
        or item.status not in {"resolved", "closed"}
        or (target == "closed" and item.status != "resolved")
    ):
        raise ApiError(409, "WORKFLOW_CONFLICT", "只能确认已解决工单，或带原因重新打开已结束工单。")
    previous = item.status
    changed = await db.execute(
        update(HumanHandoff)
        .where(
            HumanHandoff.id == item.id,
            HumanHandoff.state_version == body.expected_version,
        )
        .values(
            status=target,
            resolution=body.reason,
            state_version=body.expected_version + 1,
            assigned_to=None if target == "open" else item.assigned_to,
            resolved_at=None if target == "open" else now(),
            accepted_at=None if target == "open" else item.accepted_at,
        )
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        raise ApiError(409, "WORKFLOW_CONFLICT", "工单已更新，请刷新。")
    db.add(
        AuditLog(
            action="platform.handoff.transition",
            actor_type="student",
            actor_id=actor.user_id,
            resource_type="handoff",
            resource_id=item.id,
            allowed=True,
            extra_data={
                "school_id": str(actor.school_id),
                "from_status": previous,
                "to_status": target,
                "note": body.reason,
            },
        )
    )
    await db.commit()
    await db.refresh(item)
    return await handoff_detail(db, actor, identifier)


SCORE_MODELS = {
    "student_exam_score": StudentExamScore,
    "student_subject_score": StudentSubjectScore,
    "question_score": QuestionScore,
}


async def pin_sources(db, actor, sources):
    result = []
    for source in sources:
        source = dict(source)
        try:
            identifier = UUID(source["resource_id"])
            if source["type"] in SCORE_MODELS:
                item = await student_owned(
                    db, SCORE_MODELS[source["type"]], identifier, actor
                )
                exam = await owned(db, Exam, item.exam_id, actor)
                fields = (
                    ("total_score", "full_score", "class_rank", "grade_rank")
                    if isinstance(item, StudentExamScore)
                    else ("score", "full_score", "lost_score", "question_no")
                    if isinstance(item, QuestionScore)
                    else ("score", "full_score", "class_rank", "grade_rank")
                )
                facts = {
                    field: float(getattr(item, field))
                    if field in {"score", "total_score", "full_score", "lost_score"}
                    and getattr(item, field) is not None
                    else getattr(item, field)
                    for field in fields
                }
                facts["exam"] = exam.name
                facts["exam_id"] = str(exam.id)
                if hasattr(item, "subject_id"):
                    facts["subject"] = (
                        await owned(db, Subject, item.subject_id, actor)
                    ).name
                if isinstance(item, QuestionScore):
                    facts["question_version_id"] = (
                        str(item.question_version_id)
                        if item.question_version_id
                        else None
                    )
            elif source["type"] == "diagnosis_report":
                item = await require_report(db, actor, identifier)
                facts = {
                    "report_version": item.version,
                    "generated_at": item.generated_at.isoformat(),
                    "summary": (item.structured_json or {}).get("summary"),
                }
            else:
                continue
            provenance = await db.scalar(
                select(SourceRecord)
                .where(
                    SourceRecord.school_id == actor.school_id,
                    SourceRecord.native_id == identifier,
                )
                .order_by(SourceRecord.created_at.desc())
                .limit(1)
            )
            source["facts"] = facts
            source["provenance"] = (
                data(
                    provenance,
                    "id",
                    "source_system",
                    "source_version",
                    "content_hash",
                    "captured_at",
                )
                if provenance
                else {"source_system": "native", "as_of": item.updated_at.isoformat()}
            )
            if source.get("as_of") and hasattr(source["as_of"], "isoformat"):
                source["as_of"] = source["as_of"].isoformat()
            result.append(source)
        except (ValueError, KeyError):
            continue
    return result


async def evidence(db, actor, message_id, index):
    message = await db.scalar(
        select(ChatMessage)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(
            ChatMessage.id == message_id,
            ChatSession.school_id == actor.school_id,
            ChatSession.student_id == actor.student_id,
            ChatMessage.role == "assistant",
        )
    )
    if message is None or index < 0 or index >= len(message.sources or []):
        raise ApiError(404, "EVIDENCE_NOT_AVAILABLE", "这条消息没有可访问的依据。")
    source = message.sources[index]
    kind = source.get("type")
    identifier = UUID(source["resource_id"])
    if kind in SCORE_MODELS:
        await student_owned(db, SCORE_MODELS[kind], identifier, actor)
    elif kind == "diagnosis_report":
        await require_report(db, actor, identifier)
    else:
        raise ApiError(404, "EVIDENCE_NOT_AVAILABLE", "该来源类型暂不支持下钻。")
    audit(db, actor, "evidence.read", message, {"source_index": index})
    await db.commit()
    return {"captured_source": source, "note": "显示回答生成时保存的事实与来源版本；访问时重新核验身份和权益。"}
