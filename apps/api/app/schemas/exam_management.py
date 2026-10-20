"""Validated, revision-bound requests for the v17 exam workbench."""
from datetime import date
from typing import Literal
from uuid import UUID
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class DraftSubject(Payload):
    key: str = Field(min_length=1, max_length=100)
    subject_id: UUID | None = None
    name: str = Field(min_length=1, max_length=100)
    full_score: Decimal = Field(gt=0, le=10000, max_digits=10, decimal_places=2)
    student_ids: list[UUID] = Field(min_length=1, max_length=30000)


class ExamDraft(Payload):
    name: str = Field(min_length=1, max_length=200)
    academic_year: str = Field(pattern=r"^20\d{2}-20\d{2}$")
    exam_date: date
    subjects: list[DraftSubject] = Field(min_length=1, max_length=30)
    expected_revision: int | None = Field(default=None, ge=1)
    preview_hash: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def unique_subjects(self):
        start, end = map(int, self.academic_year.split("-"))
        if end != start + 1:
            raise ValueError("考试学年必须为连续两年")
        if len({s.name.casefold() for s in self.subjects}) != len(self.subjects):
            raise ValueError("同次考试科目名称不得重复")
        if len({s.key for s in self.subjects}) != len(self.subjects):
            raise ValueError("科目标识重复")
        ids = [s.subject_id for s in self.subjects if s.subject_id]
        if len(set(ids)) != len(ids):
            raise ValueError("同次考试科目不得重复")
        return self


class Upload(Payload):
    filename: str = Field(min_length=1, max_length=200)
    content_base64: str = Field(min_length=1, max_length=15000000)


class ScoreUpload(Upload):
    subject_id: UUID
    expected_revision: int = Field(ge=1)


class Revision(Payload):
    expected_revision: int = Field(ge=1)


class QuestionMaxima(Revision):
    full_scores: dict[str, Decimal] = Field(min_length=1, max_length=500)


class TeacherPermission(Payload):
    teacher_id: UUID
    score_types: list[Literal["student", "classSubject", "gradeSubject", "classAll", "gradeAll", "school"]] = Field(default_factory=list)
    score_subjects: list[UUID] = Field(default_factory=list)
    diagnosis_types: list[Literal["student", "classSubject", "gradeSubject", "classAll", "gradeAll", "school"]] = Field(default_factory=list)
    diagnosis_subjects: list[UUID] = Field(default_factory=list)
    essay_types: list[Literal["chinese", "english"]] = Field(default_factory=list)
    range_type: Literal["all", "grade", "class"] = "all"
    grades: list[str] = Field(default_factory=list)
    classes: list[str] = Field(default_factory=list)


class TeacherPermissions(Payload):
    expected_revision: int = Field(ge=1)
    teachers: list[TeacherPermission] = Field(min_length=1, max_length=1000)
    preview_hash: str | None = Field(default=None, max_length=64)


class StudentPermissions(Payload):
    expected_revision: int = Field(ge=1)
    student_ids: list[UUID] = Field(min_length=1, max_length=30000)
    subject_ids: list[UUID] = Field(min_length=1, max_length=30)
    mode: Literal["open", "close"]
    preview_hash: str | None = Field(default=None, max_length=64)
