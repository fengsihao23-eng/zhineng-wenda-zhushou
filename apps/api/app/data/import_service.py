"""Transactional CSV import service.

The importer deliberately separates pure batch planning from database writes:
all files are read and cross-referenced before a transaction can touch any
domain table.  A failed plan is still retained in the staging tables so an
operator can inspect the exact input row and retry it safely.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.csv_importer import (
    REQUIRED_COLUMNS,
    CsvBatchReport,
    CsvImportError,
    CsvIssue,
    _read_rows,
    validate_csv_directory,
)
from app.db.models.exam import Exam, ExamSubject, Subject
from app.db.models.import_batch import ImportBatch, ImportRow, ImportedClass
from app.db.models.school import School
from app.db.models.score import QuestionScore, StudentExamScore, StudentSubjectScore
from app.db.models.student import Student

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlannedRow:
    file_name: str
    row_number: int
    raw_data: dict[str, str]
    row_hash: str


@dataclass
class ImportPlan:
    root: Path
    batch_id: str
    files: dict[str, int] = field(default_factory=dict)
    rows: list[PlannedRow] = field(default_factory=list)
    issues: list[CsvIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def content_hash(self) -> str:
        digest = hashlib.sha256()
        for row in self.rows:
            digest.update(row.file_name.encode("utf-8"))
            digest.update(str(row.row_number).encode("ascii"))
            digest.update(row.row_hash.encode("ascii"))
        return digest.hexdigest()


def _clean(row: dict[str, str]) -> dict[str, str]:
    return {str(k): (v or "").strip() for k, v in row.items()}


def _row_hash(row: dict[str, str]) -> str:
    payload = json.dumps(_clean(row), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _issue(plan: ImportPlan, file_name: str, row_number: int, code: str, message: str) -> None:
    if len(plan.issues) < 1000:
        plan.issues.append(CsvIssue(file_name, row_number, code, message))


def build_import_plan(root: str | Path, batch_id: str) -> ImportPlan:
    """Read every CSV and validate cross-file references without writing DB state."""
    directory = Path(root)
    plan = ImportPlan(root=directory, batch_id=batch_id)
    basic_report = validate_csv_directory(directory, batch_id)
    plan.files.update(basic_report.files)
    plan.issues.extend(basic_report.issues[:1000])
    if not directory.is_dir():
        return plan

    rows_by_file: dict[str, list[tuple[int, dict[str, str]]]] = {}
    for filename in REQUIRED_COLUMNS:
        path = directory / filename
        if not path.exists():
            continue
        try:
            headers, rows = _read_rows(path)
        except (OSError, UnicodeDecodeError):
            continue
        if not set(REQUIRED_COLUMNS[filename]).issubset(headers):
            continue
        cleaned = [(number, _clean(row)) for number, row in enumerate(rows, start=2)]
        rows_by_file[filename] = cleaned
        plan.rows.extend(
            PlannedRow(filename, number, row, _row_hash(row)) for number, row in cleaned
        )

    schools: dict[str, dict[str, str]] = {}
    students: set[tuple[str, str]] = set()
    exams: set[tuple[str, str]] = set()
    subjects: set[tuple[str, str]] = set()
    subject_codes: set[tuple[str, str]] = set()
    classes: set[tuple[str, str]] = set()

    for number, row in rows_by_file.get("schools.csv", []):
        code = row.get("code", "")
        if code in schools:
            _issue(plan, "schools.csv", number, "DUPLICATE_SCHOOL", "学校 code 重复")
        schools[code] = row

    for number, row in rows_by_file.get("classes.csv", []):
        key = (row.get("school_code", ""), row.get("external_class_id", ""))
        if key in classes:
            _issue(plan, "classes.csv", number, "DUPLICATE_CLASS", "同一学校内 external_class_id 重复")
        classes.add(key)

    for number, row in rows_by_file.get("students.csv", []):
        key = (row.get("school_code", ""), row.get("external_student_id", ""))
        students.add(key)
        if row.get("school_code") not in schools:
            _issue(plan, "students.csv", number, "SCHOOL_NOT_FOUND", "学生所属学校不存在")
        external_class_id = row.get("external_class_id")
        if external_class_id and (row.get("school_code", ""), external_class_id) not in classes:
            _issue(plan, "students.csv", number, "CLASS_NOT_FOUND", "学生所属班级不存在")

    for number, row in rows_by_file.get("exams.csv", []):
        key = (row.get("school_code", ""), row.get("external_exam_id", ""))
        exams.add(key)
        if row.get("school_code") not in schools:
            _issue(plan, "exams.csv", number, "SCHOOL_NOT_FOUND", "考试所属学校不存在")

    for number, row in rows_by_file.get("subjects.csv", []):
        key = (row.get("school_code", ""), row.get("external_subject_id", ""))
        code_key = (row.get("school_code", ""), row.get("code", ""))
        if key in subjects:
            _issue(plan, "subjects.csv", number, "DUPLICATE_SUBJECT", "同一学校内 external_subject_id 重复")
        if code_key in subject_codes:
            _issue(plan, "subjects.csv", number, "DUPLICATE_SUBJECT_CODE", "同一学校内科目 code 重复")
        subjects.add(key)
        subject_codes.add(code_key)
        if row.get("school_code") not in schools:
            _issue(plan, "subjects.csv", number, "SCHOOL_NOT_FOUND", "科目所属学校不存在")

    for filename in ("student_exam_scores.csv", "student_subject_scores.csv", "question_scores.csv"):
        seen: set[tuple[str, ...]] = set()
        for number, row in rows_by_file.get(filename, []):
            student_key = (row.get("school_code", ""), row.get("external_student_id", ""))
            exam_key = (row.get("school_code", ""), row.get("external_exam_id", ""))
            subject_key = (
                row.get("school_code", ""),
                row.get("external_subject_id", ""),
            )
            if row.get("school_code") not in schools:
                _issue(plan, filename, number, "SCHOOL_NOT_FOUND", "成绩所属学校不存在")
            if student_key not in students:
                _issue(plan, filename, number, "STUDENT_NOT_FOUND", "成绩引用的学生不存在")
            if exam_key not in exams:
                _issue(plan, filename, number, "EXAM_NOT_FOUND", "成绩引用的考试不存在")
            if filename != "student_exam_scores.csv" and subject_key not in subjects:
                _issue(plan, filename, number, "SUBJECT_NOT_FOUND", "成绩引用的科目不存在")
            key_fields = {
                "student_exam_scores.csv": ("school_code", "external_student_id", "external_exam_id"),
                "student_subject_scores.csv": (
                    "school_code", "external_student_id", "external_exam_id", "external_subject_id"
                ),
                "question_scores.csv": (
                    "school_code", "external_student_id", "external_exam_id", "external_subject_id", "question_no"
                ),
            }[filename]
            duplicate_key = tuple(row.get(field, "") for field in key_fields)
            if duplicate_key in seen:
                _issue(plan, filename, number, "DUPLICATE_SCORE", "同一业务键的成绩行重复")
            seen.add(duplicate_key)

    numeric_fields = {
        "student_exam_scores.csv": (
            "full_score", "class_rank", "grade_rank", "class_student_count", "grade_student_count"
        ),
        "student_subject_scores.csv": ("class_rank", "grade_rank", "class_avg", "grade_avg"),
        "question_scores.csv": (),
    }
    for filename, fields in numeric_fields.items():
        for number, row in rows_by_file.get(filename, []):
            for field_name in fields:
                value = row.get(field_name, "")
                if not value:
                    continue
                try:
                    (_integer(value) if field_name.endswith("rank") or "count" in field_name else _decimal(value))
                except ValueError as exc:
                    _issue(plan, filename, number, "INVALID_NUMBER", f"{field_name}{exc}")

    for number, row in rows_by_file.get("exams.csv", []):
        for field_name in ("start_date", "end_date"):
            if row.get(field_name):
                try:
                    _date(row[field_name])
                except ValueError as exc:
                    _issue(plan, "exams.csv", number, "INVALID_DATE", f"{field_name}{exc}")
    for filename in ("question_scores.csv",):
        for number, row in rows_by_file.get(filename, []):
            for field_name in ("question_id", "knowledge_point_id"):
                if row.get(field_name):
                    try:
                        _uuid(row[field_name])
                    except ValueError as exc:
                        _issue(plan, filename, number, "INVALID_UUID", f"{field_name}{exc}")

    return plan


def _decimal(value: str | None, *, required: bool = False) -> Decimal | None:
    value = (value or "").strip()
    if not value:
        if required:
            raise ValueError("必须是数字")
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("必须是数字") from exc


def _integer(value: str | None) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError("必须是整数") from exc


def _date(value: str | None) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError("日期格式必须是 YYYY-MM-DD")


def _uuid(value: str | None) -> UUID | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValueError("必须是 UUID") from exc


async def _one(db: AsyncSession, model: Any, *conditions: Any) -> Any | None:
    return (await db.execute(select(model).where(*conditions))).scalar_one_or_none()


class CsvImportService:
    """Validate and persist one complete CSV batch atomically."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def import_directory(
        self,
        root: str | Path,
        batch_id: str,
        source_system: str = "csv",
        created_by: UUID | None = None,
    ) -> CsvBatchReport:
        plan = build_import_plan(root, batch_id)
        report = CsvBatchReport(
            batch_id=batch_id,
            root=str(plan.root.resolve()),
            files=plan.files,
            issues=list(plan.issues),
        )
        content_hash = plan.content_hash
        try:
            async with self.db.begin():
                existing = await _one(self.db, ImportBatch, ImportBatch.batch_id == batch_id)
                if existing is not None:
                    if existing.status == "succeeded" and existing.content_hash == content_hash:
                        report.status = "succeeded"
                        report.imported_rows = existing.success_rows
                        report.idempotent = True
                        report.failed_rows = existing.failed_rows
                        return report
                    if existing.status == "failed":
                        await self.db.delete(existing)
                        await self.db.flush()
                    else:
                        raise CsvImportError("批次正在执行或已完成，不能复用 batch_id")

                batch = ImportBatch(
                    batch_id=batch_id,
                    source_system=source_system,
                    root_path=str(plan.root.resolve()),
                    content_hash=content_hash,
                    status="validated" if plan.ok else "failed",
                    total_rows=len(plan.rows),
                    success_rows=0,
                    failed_rows=len(plan.rows) if not plan.ok else 0,
                    error_count=len(plan.issues),
                    report_json=report.as_dict(),
                    created_by=created_by,
                )
                self.db.add(batch)
                await self.db.flush()
                if not plan.ok:
                    self._stage_rows(batch.id, plan.rows, plan.issues, status="failed")
                    report.status = "failed"
                    report.failed_rows = len(plan.rows)
                    batch.report_json = report.as_dict()
                    return report

                self._stage_rows(batch.id, plan.rows, [], status="pending")
                await self.db.flush()
                imported = await self._upsert_domain(plan, source_system)
                await self.db.execute(
                    update(ImportRow)
                    .where(ImportRow.batch_id == batch.id)
                    .values(status="imported")
                )
                batch.status = "succeeded"
                batch.success_rows = imported
                batch.failed_rows = 0
                batch.finished_at = datetime.now(timezone.utc)
                report.status = "succeeded"
                report.imported_rows = imported
                batch.report_json = report.as_dict()
                return report
        except CsvImportError:
            raise
        except Exception:
            logger.exception("CSV batch %s failed", batch_id)
            await self.db.rollback()
            report.status = "failed"
            report.failed_rows = len(plan.rows)
            report.issues.append(CsvIssue("*", None, "IMPORT_FAILED", "批次写入失败"))
            async with self.db.begin():
                failed_batch = ImportBatch(
                    batch_id=batch_id,
                    source_system=source_system,
                    root_path=str(plan.root.resolve()),
                    content_hash=content_hash,
                    status="failed",
                    total_rows=len(plan.rows),
                    failed_rows=len(plan.rows),
                    error_count=len(report.issues),
                    report_json=report.as_dict(),
                    created_by=created_by,
                    finished_at=datetime.now(timezone.utc),
                )
                self.db.add(failed_batch)
                await self.db.flush()
                self._stage_rows(failed_batch.id, plan.rows, report.issues, status="failed")
            return report

    async def apply_validated_plan(self, plan: ImportPlan, source_system: str, created_by: UUID) -> CsvBatchReport:
        """Compose the existing importer inside an authenticated workspace transaction.

        The caller owns commit/rollback and holds its school/import lock. No
        partial domain or staging writes can survive a failure.
        """
        if not plan.ok:
            raise CsvImportError("批次预检未通过")
        existing = await _one(self.db, ImportBatch, ImportBatch.batch_id == plan.batch_id)
        report = CsvBatchReport(batch_id=plan.batch_id, root="", files=plan.files, status="succeeded")
        if existing is not None:
            if existing.status != "succeeded" or existing.content_hash != plan.content_hash:
                raise CsvImportError("批次内容冲突")
            report.imported_rows = existing.success_rows
            report.idempotent = True
            return report
        batch = ImportBatch(batch_id=plan.batch_id, source_system=source_system, root_path=None,
                            content_hash=plan.content_hash, status="running", total_rows=len(plan.rows),
                            created_by=created_by)
        self.db.add(batch)
        await self.db.flush()
        self._stage_rows(batch.id, plan.rows, [], status="pending")
        report.imported_rows = await self._upsert_domain(plan, source_system)
        await self.db.execute(update(ImportRow).where(ImportRow.batch_id == batch.id).values(status="imported"))
        batch.status = "succeeded"
        batch.success_rows = report.imported_rows
        batch.finished_at = datetime.now(timezone.utc)
        batch.report_json = report.as_dict()
        return report

    def _stage_rows(
        self,
        batch_id: UUID,
        rows: list[PlannedRow],
        issues: list[CsvIssue],
        status: str,
    ) -> None:
        issue_by_position = {(i.file, i.row): i for i in issues if i.row is not None}
        for row in rows:
            issue = issue_by_position.get((row.file_name, row.row_number))
            self.db.add(
                ImportRow(
                    batch_id=batch_id,
                    file_name=row.file_name,
                    row_number=row.row_number,
                    row_hash=row.row_hash,
                    raw_data=row.raw_data,
                    status=status,
                    error_code=issue.code if issue else None,
                    error_message=issue.message if issue else None,
                )
            )

    async def _upsert_domain(self, plan: ImportPlan, source_system: str) -> int:
        rows = {filename: [row for row in plan.rows if row.file_name == filename] for filename in REQUIRED_COLUMNS}
        school_by_code: dict[str, School] = {}
        for item in rows["schools.csv"]:
            data = item.raw_data
            school = await _one(self.db, School, School.code == data["code"])
            if school is None:
                school = School(code=data["code"], name=data["name"])
                self.db.add(school)
                await self.db.flush()
            school.name = data["name"]
            school.external_school_id = data.get("external_school_id")
            school.source_system = source_system
            school_by_code[school.code] = school

        for item in rows["classes.csv"]:
            data = item.raw_data
            school = school_by_code[data["school_code"]]
            imported_class = await _one(
                self.db,
                ImportedClass,
                ImportedClass.school_id == school.id,
                ImportedClass.external_class_id == data["external_class_id"],
            )
            if imported_class is None:
                imported_class = ImportedClass(
                    school_id=school.id,
                    external_class_id=data["external_class_id"],
                    name=data["name"],
                    source_system=source_system,
                )
                self.db.add(imported_class)
            else:
                imported_class.name = data["name"]
                imported_class.source_system = source_system

        student_by_key: dict[tuple[str, str], Student] = {}
        for item in rows["students.csv"]:
            data = item.raw_data
            school = school_by_code[data["school_code"]]
            key = (data["school_code"], data["external_student_id"])
            student = await _one(
                self.db,
                Student,
                Student.school_id == school.id,
                Student.external_student_id == data["external_student_id"],
            )
            if student is None:
                student = Student(
                    school_id=school.id,
                    external_student_id=data["external_student_id"],
                    student_no=data.get("student_no"),
                    name=data["name"],
                )
                self.db.add(student)
            student.student_no = data.get("student_no")
            student.name = data["name"]
            student.external_class_id = data.get("external_class_id") or None
            student.source_system = source_system
            student_by_key[key] = student

        exam_by_key: dict[tuple[str, str], Exam] = {}
        for item in rows["exams.csv"]:
            data = item.raw_data
            school = school_by_code[data["school_code"]]
            key = (data["school_code"], data["external_exam_id"])
            exam = await _one(
                self.db,
                Exam,
                Exam.school_id == school.id,
                Exam.external_exam_id == data["external_exam_id"],
            )
            if exam is None:
                exam = Exam(
                    school_id=school.id,
                    external_exam_id=data["external_exam_id"],
                    name=data["name"],
                    exam_type=data["exam_type"],
                )
                self.db.add(exam)
            exam.name = data["name"]
            exam.exam_type = data["exam_type"]
            exam.academic_year = data.get("academic_year") or None
            exam.term = data.get("term") or None
            exam.start_date = _date(data.get("start_date"))
            exam.end_date = _date(data.get("end_date"))
            exam.source_system = source_system
            exam_by_key[key] = exam

        subject_by_key: dict[tuple[str, str], Subject] = {}
        for item in rows["subjects.csv"]:
            data = item.raw_data
            school = school_by_code[data["school_code"]]
            key = (data["school_code"], data["external_subject_id"])
            subject = await _one(
                self.db,
                Subject,
                Subject.school_id == school.id,
                Subject.code == data["code"],
            )
            if subject is None:
                subject = Subject(
                    school_id=school.id,
                    code=data["code"],
                    name=data["name"],
                )
                self.db.add(subject)
            subject.name = data["name"]
            subject.external_subject_id = data["external_subject_id"]
            subject.source_system = source_system
            subject_by_key[key] = subject

        await self.db.flush()
        for item in rows["student_exam_scores.csv"]:
            data = item.raw_data
            school = school_by_code[data["school_code"]]
            student = student_by_key[(data["school_code"], data["external_student_id"])]
            exam = exam_by_key[(data["school_code"], data["external_exam_id"])]
            score = await _one(
                self.db,
                StudentExamScore,
                StudentExamScore.student_id == student.id,
                StudentExamScore.exam_id == exam.id,
            )
            if score is None:
                score = StudentExamScore(school_id=school.id, student_id=student.id, exam_id=exam.id)
                self.db.add(score)
            score.total_score = _decimal(data.get("total_score"), required=True)
            score.full_score = _decimal(data.get("full_score"))
            score.class_rank = _integer(data.get("class_rank"))
            score.grade_rank = _integer(data.get("grade_rank"))
            score.class_student_count = _integer(data.get("class_student_count"))
            score.grade_student_count = _integer(data.get("grade_student_count"))

        for item in rows["student_subject_scores.csv"]:
            data = item.raw_data
            school = school_by_code[data["school_code"]]
            student = student_by_key[(data["school_code"], data["external_student_id"])]
            exam = exam_by_key[(data["school_code"], data["external_exam_id"])]
            subject = subject_by_key[(data["school_code"], data["external_subject_id"])]
            full_score = _decimal(data.get("full_score"), required=True)
            exam_subject = await _one(
                self.db,
                ExamSubject,
                ExamSubject.exam_id == exam.id,
                ExamSubject.subject_id == subject.id,
            )
            if exam_subject is None:
                self.db.add(ExamSubject(exam_id=exam.id, subject_id=subject.id, full_score=full_score))
            else:
                exam_subject.full_score = full_score
            score = await _one(
                self.db,
                StudentSubjectScore,
                StudentSubjectScore.student_id == student.id,
                StudentSubjectScore.exam_id == exam.id,
                StudentSubjectScore.subject_id == subject.id,
            )
            if score is None:
                score = StudentSubjectScore(
                    school_id=school.id,
                    student_id=student.id,
                    exam_id=exam.id,
                    subject_id=subject.id,
                )
                self.db.add(score)
            score.score = _decimal(data.get("score"), required=True)
            score.full_score = full_score
            score.class_rank = _integer(data.get("class_rank"))
            score.grade_rank = _integer(data.get("grade_rank"))
            score.class_avg = _decimal(data.get("class_avg"))
            score.grade_avg = _decimal(data.get("grade_avg"))

        for item in rows["question_scores.csv"]:
            data = item.raw_data
            school = school_by_code[data["school_code"]]
            student = student_by_key[(data["school_code"], data["external_student_id"])]
            exam = exam_by_key[(data["school_code"], data["external_exam_id"])]
            subject = subject_by_key[(data["school_code"], data["external_subject_id"])]
            score = await _one(
                self.db,
                QuestionScore,
                QuestionScore.student_id == student.id,
                QuestionScore.exam_id == exam.id,
                QuestionScore.subject_id == subject.id,
                QuestionScore.question_no == data["question_no"],
            )
            if score is None:
                score = QuestionScore(
                    school_id=school.id,
                    student_id=student.id,
                    exam_id=exam.id,
                    subject_id=subject.id,
                    question_no=data["question_no"],
                )
                self.db.add(score)
            score.question_id = _uuid(data.get("question_id"))
            score.score = _decimal(data.get("score"), required=True)
            score.full_score = _decimal(data.get("full_score"), required=True)
            score.lost_score = _decimal(data.get("lost_score"), required=True)
            score.answer_status = data.get("answer_status") or None
            score.knowledge_point_id = _uuid(data.get("knowledge_point_id"))

        await self.db.flush()
        return len(plan.rows)
