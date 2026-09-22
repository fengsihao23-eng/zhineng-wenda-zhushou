"""Uploaded CSV -> mapping -> preflight -> durable atomic import -> receipt."""
import csv
import io
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.core.errors import ApiError
from app.data.csv_importer import REQUIRED_COLUMNS, CsvIssue
from app.data.import_service import build_import_plan, CsvImportService
from app.db.models.education import (
    ImportWorkspace,
    MappingTemplate,
    SourceRecord,
    QuestionVersion,
    Question,
)
from app.db.models.school import School
from app.db.models.student import Student
from app.db.models.exam import Exam, Subject
from app.db.models.score import QuestionScore, StudentExamScore, StudentSubjectScore
from app.services.education_common import claim, digest, owned, now, audit, data, cas

OPTIONAL = {
    "schools.csv": set(),
    "classes.csv": set(),
    "students.csv": {"external_class_id"},
    "exams.csv": {"start_date", "end_date", "academic_year", "term"},
    "subjects.csv": set(),
    "student_exam_scores.csv": {
        "full_score",
        "class_rank",
        "grade_rank",
        "class_student_count",
        "grade_student_count",
    },
    "student_subject_scores.csv": {
        "full_score",
        "class_rank",
        "grade_rank",
        "class_avg",
        "grade_avg",
    },
    "question_scores.csv": {
        "question_id",
        "answer_status",
        "knowledge_point_id",
        "question_version_id",
    },
}


def columns():
    return {
        name: {
            "required": sorted(
                required
                | ({"full_score"} if name == "student_subject_scores.csv" else set())
            ),
            "optional": sorted(OPTIONAL[name]),
        }
        for name, required in REQUIRED_COLUMNS.items()
    }


def read_files(files):
    if not files or set(files) - set(REQUIRED_COLUMNS):
        raise ApiError(422, "IMPORT_FILES_INVALID", "请按模板上传 CSV 文件，文件名不允许路径或未知类型。")
    if sum(len(text.encode()) for text in files.values()) > 5_000_000:
        raise ApiError(413, "IMPORT_TOO_LARGE", "首版批次最大 5 MB、5000 行，请拆分批次。")
    result, total = {}, 0
    for filename, text in files.items():
        reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
        headers = reader.fieldnames or []
        if not headers or len(headers) != len(set(headers)) or len(headers) > 60:
            raise ApiError(422, "IMPORT_HEADERS_INVALID", "CSV 表头为空、重复或过多。")
        rows = list(reader)
        total += len(rows)
        if total > 5000 or any(
            None in row
            or any(value is None or len(value) > 5000 for value in row.values())
            for row in rows
        ):
            raise ApiError(422, "IMPORT_ROWS_INVALID", "CSV 行数超限、列数不匹配或单元格过长。")
        result[filename] = (headers, rows)
    return result


async def upload(db, actor, body, key):
    parsed = read_files(body.files)
    content_hash = digest(body.files)
    existing = await db.scalar(
        select(ImportWorkspace).where(
            ImportWorkspace.school_id == actor.school_id,
            ImportWorkspace.batch_key == body.batch_key,
        )
    )
    if existing:
        if (
            existing.content_hash != content_hash
            or existing.source_system != body.source_system
        ):
            raise ApiError(409, "BATCH_CONTENT_CONFLICT", "该批次编号已经用于其他内容，请使用新批次编号。")
        return view(existing)
    identifier, fresh = await claim(db, actor, "import.upload", key, body.model_dump())
    if fresh:
        item = ImportWorkspace(
            id=identifier,
            school_id=actor.school_id,
            created_by=actor.user_id,
            batch_key=body.batch_key,
            source_system=body.source_system,
            files=body.files,
            content_hash=content_hash,
            mapping={
                name: {
                    column: column
                    for column in headers
                    if column in REQUIRED_COLUMNS[name] | OPTIONAL[name]
                }
                for name, (headers, _) in parsed.items()
            },
        )
        db.add(item)
        audit(db, actor, "import.upload", item, {"files": list(parsed)})
        await db.commit()
    return view(await owned(db, ImportWorkspace, identifier, actor))


def view(item):
    parsed = read_files(item.files)
    return {
        **data(
            item,
            "id",
            "batch_key",
            "source_system",
            "content_hash",
            "status",
            "revision",
            "progress",
            "report",
            "mapping",
            "created_at",
            "updated_at",
        ),
        "files": {
            name: {"headers": headers, "row_count": len(rows)}
            for name, (headers, rows) in parsed.items()
        },
        "schema": columns(),
    }


async def make_plan(db, item):
    parsed = read_files(item.files)
    school = await db.get(School, item.school_id)
    scope_issues = []
    with TemporaryDirectory(prefix="education-import-") as directory:
        for filename, (headers, rows) in parsed.items():
            mapping = item.mapping.get(filename, {})
            if set(mapping) - (REQUIRED_COLUMNS[filename] | OPTIONAL[filename]) or any(
                source not in headers for source in mapping.values()
            ):
                raise ApiError(422, "IMPORT_MAPPING_INVALID", "映射包含未知目标字段或不存在的原始列。")
            target_headers = list(mapping)
            with (Path(directory) / filename).open(
                "w", newline="", encoding="utf-8"
            ) as handle:
                writer = csv.DictWriter(handle, fieldnames=target_headers)
                writer.writeheader()
                for row_no, row in enumerate(rows, 2):
                    mapped = {
                        target: row[source].strip()
                        for target, source in mapping.items()
                    }
                    code_key = "code" if filename == "schools.csv" else "school_code"
                    if mapped.get(code_key) != school.code:
                        scope_issues.append(
                            CsvIssue(
                                filename,
                                row_no,
                                "SCHOOL_SCOPE_MISMATCH",
                                "学校代码必须与当前管理学校一致。",
                            )
                        )
                    if filename == "schools.csv":
                        # The importer can synchronize schools, but a school UI cannot rename its tenant.
                        mapped["name"] = school.name
                        mapped["external_school_id"] = (
                            school.external_school_id or school.code
                        )
                    writer.writerow(mapped)
        plan = build_import_plan(directory, f"web-{item.id}")
        plan.issues.extend(scope_issues)
    if len(parsed.get("schools.csv", ([], []))[1]) != 1:
        plan.issues.append(
            CsvIssue(
                "schools.csv", None, "SINGLE_SCHOOL_REQUIRED", "每个工作台批次必须且只能包含当前学校一行。"
            )
        )
    full_scores = {}
    for planned in plan.rows:
        row, filename = planned.raw_data, planned.file_name

        def issue(code, field, message):
            plan.issues.append(
                CsvIssue(filename, planned.row_number, code, f"{field}: {message}")
            )

        for field in (
            "score",
            "total_score",
            "full_score",
            "lost_score",
            "class_rank",
            "grade_rank",
            "class_student_count",
            "grade_student_count",
            "class_avg",
            "grade_avg",
        ):
            value = row.get(field)
            required = (
                field in {"score", "total_score", "full_score", "lost_score"}
                and field in REQUIRED_COLUMNS[filename]
            ) or (filename == "student_subject_scores.csv" and field == "full_score")
            if not value and not required:
                continue
            try:
                number = Decimal(value or "")
                if (
                    not number.is_finite()
                    or number < 0
                    or number > 100000
                    or (field == "full_score" and number <= 0)
                    or (
                        ("rank" in field or "count" in field)
                        and (number < 1 or number != int(number))
                    )
                ):
                    raise ValueError()
            except (InvalidOperation, ValueError):
                issue("INVALID_NUMBER", field, "须为有效非负数，满分/排名/人数须大于零")
        try:
            if row.get("full_score"):
                score = Decimal(row.get("score") or row.get("total_score") or "0")
                full = Decimal(row["full_score"])
                if score.is_finite() and full.is_finite() and score > full:
                    issue("SCORE_EXCEEDS_FULL", "score", "得分不能高于满分")
                if (
                    filename == "question_scores.csv"
                    and Decimal(row["lost_score"]) != full - score
                ):
                    issue("LOSS_MISMATCH", "lost_score", "丢分必须等于满分减得分")
                if filename == "student_subject_scores.csv":
                    pair = (row["external_exam_id"], row["external_subject_id"])
                    if pair in full_scores and full_scores[pair] != full:
                        issue("FULL_SCORE_CONFLICT", "full_score", "同一考试科目满分不一致")
                    full_scores[pair] = full
        except (InvalidOperation, KeyError):
            pass
        for field in (
            "external_student_id",
            "external_exam_id",
            "external_subject_id",
            "external_class_id",
            "name",
            "student_no",
            "code",
            "question_no",
            "exam_type",
        ):
            if len(row.get(field, "")) > {
                "student_no": 50,
                "code": 50,
                "question_no": 20,
                "exam_type": 50,
            }.get(field, 100 if field != "name" or filename != "exams.csv" else 200):
                issue("FIELD_TOO_LONG", field, "字段长度超限")
        if filename == "students.csv":
            collision = await db.scalar(
                select(Student).where(
                    Student.school_id == item.school_id,
                    Student.student_no == row.get("student_no"),
                    Student.external_student_id != row.get("external_student_id"),
                )
            )
            if collision:
                issue("STUDENT_ID_CONFLICT", "student_no", "学号已绑定另一外部身份，不允许按姓名合并")
        if filename == "subjects.csv":
            collision = await db.scalar(
                select(Subject).where(
                    Subject.school_id == item.school_id,
                    or_(
                        Subject.code == row.get("code"),
                        Subject.external_subject_id == row.get("external_subject_id"),
                    ),
                )
            )
            if collision and (
                collision.code != row.get("code")
                or collision.external_subject_id
                not in (None, row.get("external_subject_id"))
            ):
                issue("SUBJECT_ID_CONFLICT", "external_subject_id", "科目来源映射冲突")
        if filename == "question_scores.csv":
            previous_score = await db.scalar(
                select(QuestionScore)
                .join(Student, Student.id == QuestionScore.student_id)
                .join(Exam, Exam.id == QuestionScore.exam_id)
                .join(Subject, Subject.id == QuestionScore.subject_id)
                .where(
                    QuestionScore.school_id == item.school_id,
                    Student.external_student_id == row.get("external_student_id"),
                    Exam.external_exam_id == row.get("external_exam_id"),
                    Subject.external_subject_id == row.get("external_subject_id"),
                    QuestionScore.question_no == row.get("question_no"),
                )
            )
            if (
                previous_score
                and previous_score.question_version_id
                and (
                    (
                        row.get("question_version_id")
                        and row["question_version_id"]
                        != str(previous_score.question_version_id)
                    )
                    or (
                        row.get("question_id")
                        and row["question_id"] != str(previous_score.question_id)
                    )
                )
            ):
                issue(
                    "SCORE_VERSION_PINNED",
                    "question_version_id",
                    "历史得分已关联正式题目，不允许导入覆盖依据版本",
                )
        if row.get("question_version_id"):
            try:
                version = await db.scalar(
                    select(QuestionVersion).where(
                        QuestionVersion.id == UUID(row["question_version_id"]),
                        QuestionVersion.school_id == item.school_id,
                        QuestionVersion.published_at.is_not(None),
                    )
                )
                question = (
                    await db.get(Question, version.question_id) if version else None
                )
                subject = (
                    await db.get(Subject, question.subject_id) if question else None
                )
                if (
                    not question
                    or question.deleted_at
                    or subject.external_subject_id != row.get("external_subject_id")
                ):
                    raise ValueError()
                if row.get("question_id") and row["question_id"] != str(question.id):
                    raise ValueError()
            except (ValueError, TypeError):
                issue("QUESTION_VERSION_INVALID", "question_version_id", "版本须为当前学科正式题目")
    plan.issues = plan.issues[:1000]
    return plan


async def preflight(db, actor, identifier, body, key):
    item = await owned(db, ImportWorkspace, identifier, actor, lock=True)
    _, fresh = await claim(
        db, actor, f"import.preflight.{identifier}", key, body.model_dump()
    )
    if fresh:
        if item.status in {"running", "succeeded"}:
            raise ApiError(409, "IMPORT_FROZEN", "已确认批次不能再改变映射。")
        # Validate a separate plan before changing the stored mapping/revision.
        old_mapping = item.mapping
        item.mapping = body.mapping
        plan = await make_plan(db, item)
        item.mapping = old_mapping
        report = {
            "ok": plan.ok,
            "files": plan.files,
            "total_rows": len(plan.rows),
            "issues": [i.__dict__ for i in plan.issues],
            "account_binding": "separate",
            "validated_hash": plan.content_hash,
        }
        await cas(
            db,
            item,
            body.expected_revision,
            {
                "mapping": body.mapping,
                "report": report,
                "status": "ready" if plan.ok else "invalid",
                "updated_at": now(),
            },
        )
        audit(db, actor, "import.preflight", item, {"error_count": len(plan.issues)})
        await db.commit()
    return view(item)


async def confirm(db, actor, identifier, body):
    item = await owned(db, ImportWorkspace, identifier, actor, lock=True)
    if item.status in {"running", "succeeded"}:
        return view(item)
    if (
        item.status not in {"ready", "failed"}
        or item.revision != body.expected_revision
        or not item.report.get("ok")
    ):
        raise ApiError(409, "IMPORT_NOT_READY", "请先完成最新映射预检并修正逐行错误。")
    item.status = "running"
    item.progress = 0
    item.updated_at = now()
    audit(db, actor, "import.confirm", item)
    await db.commit()
    return view(item)


async def execute_import(factory, identifier):
    """Recoverable worker: row lock + domain/staging/receipt in one transaction."""
    async with factory() as db:
        try:
            async with db.begin():
                school_id = await db.scalar(
                    select(ImportWorkspace.school_id).where(
                        ImportWorkspace.id == identifier
                    )
                )
                if school_id is None:
                    return
                # Match the API lock order: school first, workspace second.
                await db.scalar(
                    select(School).where(School.id == school_id).with_for_update()
                )
                item = await db.scalar(
                    select(ImportWorkspace)
                    .where(
                        ImportWorkspace.id == identifier,
                        ImportWorkspace.status == "running",
                    )
                    .with_for_update(skip_locked=True)
                )
                if item is None:
                    return
                plan = await make_plan(db, item)
                if not plan.ok:
                    item.status = "failed"
                    item.report = {
                        **item.report,
                        "ok": False,
                        "issues": [i.__dict__ for i in plan.issues],
                    }
                    return
                report = await CsvImportService(db).apply_validated_plan(
                    plan, item.source_system, item.created_by
                )
                await db.flush()
                counts = {}
                for entry in plan.rows:
                    row, filename = entry.raw_data, entry.file_name
                    model, external_field = {
                        "students.csv": (Student, "external_student_id"),
                        "exams.csv": (Exam, "external_exam_id"),
                        "subjects.csv": (Subject, "external_subject_id"),
                    }.get(filename, (None, None))
                    if model:
                        native = await db.scalar(
                            select(model).where(
                                model.school_id == item.school_id,
                                getattr(model, external_field) == row[external_field],
                            )
                        )
                        entity, external_id = model.__tablename__, row[external_field]
                    elif filename in {
                        "question_scores.csv",
                        "student_subject_scores.csv",
                        "student_exam_scores.csv",
                    }:
                        student = await db.scalar(
                            select(Student).where(
                                Student.school_id == item.school_id,
                                Student.external_student_id
                                == row["external_student_id"],
                            )
                        )
                        exam = await db.scalar(
                            select(Exam).where(
                                Exam.school_id == item.school_id,
                                Exam.external_exam_id == row["external_exam_id"],
                            )
                        )
                        model = {
                            "question_scores.csv": QuestionScore,
                            "student_subject_scores.csv": StudentSubjectScore,
                            "student_exam_scores.csv": StudentExamScore,
                        }[filename]
                        query = select(model).where(
                            model.school_id == item.school_id,
                            model.student_id == student.id,
                            model.exam_id == exam.id,
                        )
                        if filename != "student_exam_scores.csv":
                            subject = await db.scalar(
                                select(Subject).where(
                                    Subject.school_id == item.school_id,
                                    Subject.external_subject_id
                                    == row["external_subject_id"],
                                )
                            )
                            query = query.where(model.subject_id == subject.id)
                        if filename == "question_scores.csv":
                            query = query.where(model.question_no == row["question_no"])
                        native = await db.scalar(query)
                        entity = model.__tablename__
                        external_id = digest(
                            [
                                row.get(f)
                                for f in (
                                    "external_student_id",
                                    "external_exam_id",
                                    "external_subject_id",
                                    "question_no",
                                )
                            ]
                        )
                        if filename == "question_scores.csv":
                            if row.get("question_version_id"):
                                native.question_version_id = UUID(
                                    row["question_version_id"]
                                )
                            if native.question_version_id:
                                native.question_id = (
                                    await db.get(
                                        QuestionVersion, native.question_version_id
                                    )
                                ).question_id
                    else:
                        continue
                    db.add(
                        SourceRecord(
                            school_id=item.school_id,
                            source_system=item.source_system,
                            entity_type=entity,
                            external_id=external_id,
                            source_version=str(item.id),
                            content_hash=entry.row_hash,
                            captured_at=now(),
                            native_id=native.id,
                            payload=row,
                        )
                    )
                    counts[entity] = counts.get(entity, 0) + 1
                unbound = int(
                    await db.scalar(
                        select(func.count())
                        .select_from(Student)
                        .where(
                            Student.school_id == item.school_id,
                            Student.user_id.is_(None),
                        )
                    )
                    or 0
                )
                item.status, item.progress = "succeeded", 100
                item.report = {
                    **report.as_dict(),
                    "root": None,
                    "counts": counts,
                    "unbound_accounts": unbound,
                    "account_binding": "separate",
                    "batch_content_hash": plan.content_hash,
                }
                item.updated_at = now()
        except Exception:
            await db.rollback()
            async with db.begin():
                item = await db.scalar(
                    select(ImportWorkspace)
                    .where(ImportWorkspace.id == identifier)
                    .with_for_update()
                )
                if item and item.status == "running":
                    item.status = "failed"
                    item.report = {
                        **item.report,
                        "error_code": "IMPORT_TRANSACTION_FAILED",
                        "message": "整批写入失败，业务数据已回滚；可核对后重试。",
                    }
                    item.updated_at = now()
