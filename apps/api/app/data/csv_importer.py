"""CSV/Excel 导出后的批次校验。

第一阶段把学校导出的文件当作事实源。这里先完成可审计的批次校验，
只有全部文件通过校验后，后续写入器才允许进入正式表。
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


REQUIRED_COLUMNS: dict[str, set[str]] = {
    "schools.csv": {"external_school_id", "name", "code"},
    "students.csv": {"external_student_id", "school_code", "student_no", "name"},
    "classes.csv": {"external_class_id", "school_code", "name"},
    "exams.csv": {"external_exam_id", "school_code", "name", "exam_type"},
    "subjects.csv": {"external_subject_id", "school_code", "code", "name"},
    "student_exam_scores.csv": {
        "external_student_id", "external_exam_id", "school_code", "total_score"
    },
    "student_subject_scores.csv": {
        "external_student_id", "external_exam_id", "external_subject_id", "school_code", "score"
    },
    "question_scores.csv": {
        "external_student_id", "external_exam_id", "external_subject_id", "school_code",
        "question_no", "score", "full_score", "lost_score",
    },
}


@dataclass
class CsvIssue:
    file: str
    row: int | None
    code: str
    message: str


@dataclass
class CsvBatchReport:
    batch_id: str
    root: str
    files: dict[str, int] = field(default_factory=dict)
    issues: list[CsvIssue] = field(default_factory=list)
    validated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "validated"
    imported_rows: int = 0
    failed_rows: int = 0
    idempotent: bool = False

    @property
    def ok(self) -> bool:
        return not self.issues

    def as_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "root": self.root,
            "files": self.files,
            "issues": [issue.__dict__ for issue in self.issues],
            "validated_at": self.validated_at,
            "status": self.status,
            "imported_rows": self.imported_rows,
            "failed_rows": self.failed_rows,
            "idempotent": self.idempotent,
            "ok": self.ok,
        }


class CsvImportError(ValueError):
    pass


def _read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _check_numeric(report: CsvBatchReport, file: str, row_no: int, row: dict[str, str], columns: Iterable[str]) -> None:
    for column in columns:
        value = row.get(column, "").strip()
        if not value:
            continue
        try:
            float(value)
        except ValueError:
            report.issues.append(CsvIssue(file, row_no, "INVALID_NUMBER", f"{column} 必须是数字"))


def validate_csv_directory(root: str | Path, batch_id: str) -> CsvBatchReport:
    directory = Path(root)
    report = CsvBatchReport(batch_id=batch_id, root=str(directory.resolve()))
    if not directory.is_dir():
        report.issues.append(CsvIssue(str(directory), None, "DIRECTORY_NOT_FOUND", "导入目录不存在"))
        return report

    seen_students: set[tuple[str, str]] = set()
    seen_exams: set[tuple[str, str]] = set()
    seen_subjects: set[tuple[str, str]] = set()

    for filename, required in REQUIRED_COLUMNS.items():
        path = directory / filename
        if not path.exists():
            report.issues.append(CsvIssue(filename, None, "FILE_MISSING", "缺少必需文件"))
            continue
        try:
            headers, rows = _read_rows(path)
        except UnicodeDecodeError:
            report.issues.append(CsvIssue(filename, None, "ENCODING", "文件必须使用 UTF-8 或 UTF-8 BOM"))
            continue
        missing = sorted(required - set(headers))
        if missing:
            report.issues.append(CsvIssue(filename, 1, "COLUMN_MISSING", f"缺少字段: {', '.join(missing)}"))
            continue
        report.files[filename] = len(rows)

        for row_no, row in enumerate(rows, start=2):
            empty = [column for column in required if not row.get(column, "").strip()]
            if empty:
                report.issues.append(CsvIssue(filename, row_no, "REQUIRED_EMPTY", f"字段为空: {', '.join(sorted(empty))}"))
                continue
            school_code = row.get("school_code", "").strip()
            if filename == "students.csv":
                key = (school_code, row["external_student_id"].strip())
                if key in seen_students:
                    report.issues.append(CsvIssue(filename, row_no, "DUPLICATE_STUDENT", "同一学校内 external_student_id 重复"))
                seen_students.add(key)
            elif filename == "exams.csv":
                key = (school_code, row["external_exam_id"].strip())
                if key in seen_exams:
                    report.issues.append(CsvIssue(filename, row_no, "DUPLICATE_EXAM", "同一学校内 external_exam_id 重复"))
                seen_exams.add(key)
            elif filename == "subjects.csv":
                key = (school_code, row["external_subject_id"].strip())
                if key in seen_subjects:
                    report.issues.append(CsvIssue(filename, row_no, "DUPLICATE_SUBJECT", "同一学校内 external_subject_id 重复"))
                seen_subjects.add(key)

            numeric_columns = {
                "student_exam_scores.csv": ("total_score",),
                "student_subject_scores.csv": ("score", "full_score"),
                "question_scores.csv": ("score", "full_score", "lost_score"),
            }.get(filename, ())
            _check_numeric(report, filename, row_no, row, numeric_columns)

    if len(report.issues) > 1000:
        report.issues = report.issues[:1000]
        report.issues.append(CsvIssue("*", None, "TOO_MANY_ERRORS", "错误超过1000条，已截断"))
    return report
