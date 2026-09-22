"""Controlled export contract. Old integer IDs remain strings, never UUIDs."""
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field, field_validator
from app.schemas.education import Payload


class LegacyBase(Payload):
    external_id: str = Field(min_length=1, max_length=100)


class LegacyExam(LegacyBase):
    entity_type: Literal["exam"]
    name: str = Field(min_length=1, max_length=200)
    exam_type: str = Field(default="legacy", max_length=50)
    start_date: date


class LegacyPaper(LegacyBase):
    entity_type: Literal["paper"]
    exam_external_id: str = Field(min_length=1, max_length=100)
    subject_id: UUID
    title: str = Field(min_length=1, max_length=200)
    asset_id: UUID


class LegacyQuestion(LegacyBase):
    entity_type: Literal["question"]
    subject_id: UUID
    kind: Literal["material", "major", "minor", "standalone"]
    parent_external_id: str | None = None
    title: str = Field(min_length=1, max_length=200)
    stem: str = Field(min_length=1, max_length=50000)
    answer: str = Field(default="", max_length=20000)
    explanation: str = Field(default="", max_length=50000)
    options: list[str] = Field(default_factory=list, max_length=20)
    paper_external_id: str | None = None


class LegacyReport(LegacyBase):
    entity_type: Literal["report"]
    student_external_id: str = Field(min_length=1, max_length=100)
    exam_external_id: str = Field(min_length=1, max_length=100)
    subject_id: UUID | None = None
    report_type: Literal["diagnosis", "score_report", "marked_work"] = "diagnosis"
    raw_content: str = Field(default="", max_length=100000)
    summary: str = Field(min_length=1, max_length=10000)
    asset_id: UUID | None = None
    generated_at: datetime


class LegacyScore(LegacyBase):
    entity_type: Literal["score"]
    student_external_id: str = Field(min_length=1, max_length=100)
    exam_external_id: str = Field(min_length=1, max_length=100)
    subject_id: UUID | None = None
    question_external_id: str | None = None
    question_no: str | None = Field(default=None, max_length=20)
    score: float = Field(ge=0, le=100000)
    full_score: float = Field(gt=0, le=100000)
    class_rank: int | None = Field(default=None, ge=1)
    grade_rank: int | None = Field(default=None, ge=1)


Record = Annotated[
    LegacyExam | LegacyPaper | LegacyQuestion | LegacyReport | LegacyScore,
    Field(discriminator="entity_type"),
]


class Snapshot(Payload):
    source_system: str = Field(min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    source_version: str = Field(min_length=1, max_length=20)
    captured_at: datetime
    records: list[Record] = Field(min_length=1, max_length=500)

    @field_validator("source_system")
    @classmethod
    def external_source(cls, value):
        if value == "native":
            raise ValueError("外部快照不能使用 native 来源")
        return value
