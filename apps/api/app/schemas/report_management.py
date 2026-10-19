"""Only PDF content and explicit report attribution are accepted."""
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

Category = Literal["diagnostic", "essay"]
ReportType = Literal["student", "classAll", "classSubject", "gradeAll", "gradeSubject", "school", "essay"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PdfUpload(StrictModel):
    filename: str = Field(min_length=1, max_length=500)
    content_base64: str = Field(min_length=1, max_length=22_000_000)


class Classification(StrictModel):
    category: Category
    report_type: ReportType
    subject_ids: list[UUID] = Field(min_length=1, max_length=30)


class ReportUpload(Classification):
    target_key: str = Field(min_length=1, max_length=250)
    file: PdfUpload
    naming: Classification
    previewed: bool = False


class Batch(StrictModel):
    exam_id: UUID
    expected_exam_revision: int = Field(ge=1)
    reports: list[ReportUpload] = Field(min_length=1, max_length=30)
    preview_hash: str | None = Field(None, max_length=64)


class Replacement(StrictModel):
    expected_version: int = Field(ge=1)
    file: PdfUpload
    reason: str = Field(min_length=1, max_length=1000)
    previewed: bool
    confirmed: bool


class DeleteItem(StrictModel):
    id: UUID
    expected_version: int = Field(ge=1)


class ReportDelete(StrictModel):
    reports: list[DeleteItem] = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)
    confirmed: bool
