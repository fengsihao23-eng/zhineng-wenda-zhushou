"""Bounded, explicit contracts for the education workbench."""
from datetime import date, datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Payload(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, allow_inf_nan=False
    )


class Revision(Payload):
    expected_revision: int = Field(ge=1)


class AssetUpload(Payload):
    filename: str = Field(min_length=1, max_length=200)
    content_base64: str = Field(min_length=1, max_length=21_000_000)


class PaperCreate(Payload):
    title: str = Field(min_length=1, max_length=200)
    exam_id: UUID
    subject_id: UUID
    asset_id: UUID


class PaperReplace(Revision):
    asset_id: UUID


class Region(Payload):
    page: int = Field(ge=1, le=100)
    x: float = Field(ge=0, lt=1)
    y: float = Field(ge=0, lt=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def bounds(self):
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("框选区域不能超出原图")
        return self


class QuestionBody(Payload):
    stem: str = Field(min_length=1, max_length=50000)
    options: list[str] = Field(default_factory=list, max_length=20)
    answer: str = Field(default="", max_length=20000)
    explanation: str = Field(default="", max_length=50000)
    paper_version_id: UUID | None = None
    regions: list[Region] = Field(default_factory=list, max_length=30)
    tag_ids: list[UUID] = Field(default_factory=list, max_length=40)


class QuestionCreate(QuestionBody):
    subject_id: UUID
    kind: Literal["material", "major", "minor", "standalone"]
    parent_id: UUID | None = None
    title: str = Field(min_length=1, max_length=200)


class QuestionEdit(QuestionBody, Revision):
    pass


class BatchAction(Payload):
    ids: list[UUID] = Field(min_length=1, max_length=100)
    action: Literal["delete", "restore"]


class TaxonomyCreate(Payload):
    subject_id: UUID
    parent_id: UUID | None = None
    kind: Literal[
        "knowledge", "stage", "grade", "type", "difficulty", "ability", "tag"
    ] = "knowledge"
    name: str = Field(min_length=1, max_length=100)


class TaxonomyEdit(TaxonomyCreate, Revision):
    pass


class DraftEntry(Payload):
    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    parent_key: str | None = Field(default=None, max_length=80)
    kind: Literal["material", "major", "minor", "standalone"] = "standalone"
    title: str = Field(min_length=1, max_length=200)
    stem: str = Field(default="", max_length=50000)
    answer: str = Field(default="", max_length=20000)
    explanation: str = Field(default="", max_length=50000)
    options: list[str] = Field(default_factory=list, max_length=20)
    regions: list[Region] = Field(min_length=1, max_length=30)
    tag_ids: list[UUID] = Field(default_factory=list, max_length=40)


class DraftSave(Revision):
    entries: list[DraftEntry] = Field(max_length=100)


class DraftPublish(Revision):
    reviewed: Literal[True]


class OcrRequest(Revision):
    pass


class ReviewCreate(Payload):
    score_id: UUID


class ReviewRecordCreate(Payload):
    correction: str = Field(min_length=1, max_length=10000)
    mastery: Literal["learning", "reviewing", "mastered"]
    next_review_at: datetime | None = None


class HandoffReply(Payload):
    content: str = Field(min_length=1, max_length=6000)


class HandoffReopen(Payload):
    reason: str = Field(min_length=1, max_length=1000)
    expected_version: int = Field(ge=1)


class ClassCreate(Payload):
    external_class_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)


class ClassUpdate(Payload):
    name: str = Field(min_length=1, max_length=100)
    status: Literal["active", "inactive"]


class StudentCreate(Payload):
    external_student_id: str = Field(min_length=1, max_length=100)
    student_no: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    class_id: UUID


class StudentUpdate(Payload):
    class_id: UUID
    status: Literal["active", "inactive"]


class BindUser(Payload):
    user_id: UUID


class TeachingCreate(Payload):
    teacher_user_id: UUID
    class_id: UUID
    subject_id: UUID
    starts_at: datetime
    expires_at: datetime | None = None
    status: Literal["active", "inactive"] = "active"

    @model_validator(mode="after")
    def dates(self):
        if self.starts_at.tzinfo is None or (
            self.expires_at and self.expires_at.tzinfo is None
        ):
            raise ValueError("生效时间须包含时区")
        if self.expires_at and self.expires_at <= self.starts_at:
            raise ValueError("结束时间须晚于开始时间")
        return self


class TeacherUpdate(Payload):
    display_name: str = Field(min_length=1, max_length=100)
    status: Literal["active", "inactive"]


class SubjectCreate(Payload):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    external_subject_id: str = Field(min_length=1, max_length=100)


class ExamCreate(Payload):
    external_exam_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    exam_type: str = Field(min_length=1, max_length=50)
    start_date: date
    end_date: date | None = None
    status: Literal["active", "inactive"] = "active"

    @model_validator(mode="after")
    def dates(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("结束日期须晚于或等于开始日期")
        return self


class ExamSubjectWrite(Payload):
    subject_id: UUID
    full_score: float = Field(gt=0, le=10000)


class ScoreLink(Payload):
    question_version_id: UUID


class ReportCreate(Payload):
    student_id: UUID
    exam_id: UUID
    subject_id: UUID | None = None
    report_type: Literal["diagnosis", "score_report", "marked_work"] = "diagnosis"
    version: str = Field(min_length=1, max_length=20)
    raw_content: str = Field(default="", max_length=100000)
    summary: str = Field(min_length=1, max_length=10000)
    asset_id: UUID
    generated_at: datetime


class ImportUpload(Payload):
    batch_key: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    source_system: str = Field(min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    files: dict[str, str]


class ImportMapping(Revision):
    mapping: dict[str, dict[str, str]]


class TemplateCreate(Payload):
    name: str = Field(min_length=1, max_length=100)
    mapping: dict[str, dict[str, str]]
