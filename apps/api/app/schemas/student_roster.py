from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class Placement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    grade: str = Field(max_length=100)
    class_number: str = Field(max_length=100)
    source_segment: Literal["小学", "初中", "高中"] | None = None


class StudentTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["archive", "promotion", "status", "deletion", "identity"]
    student_ids: list[UUID] = Field(default_factory=list, max_length=5000)
    filename: str | None = Field(default=None, max_length=200)
    content_base64: str | None = Field(default=None, max_length=7_000_000)
    mode: Literal["current", "next"] = "current"
    target_year: str | None = Field(default=None, max_length=20)
    action: Literal["depart", "graduate", "restore"] | None = None
    placements: dict[UUID, Placement] = Field(default_factory=dict)
    field: Literal["姓名", "账号"] | None = None
    new_value: str = Field(default="", max_length=100)
    reason: str = Field(default="", max_length=500)
    deletion_type: Literal["incorrect", "duplicate"] = "incorrect"
    retained_students: dict[UUID, UUID] = Field(default_factory=dict)


class StudentTaskPrepare(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    identity_confirmed_ids: list[UUID] = Field(default_factory=list, max_length=5000)
    identity_uncertain_ids: list[UUID] = Field(default_factory=list, max_length=5000)
    anomaly_approvals: dict[UUID, str] = Field(default_factory=dict)
    graduation_confirmed: bool = False
    graduation_student_ids: list[UUID] = Field(default_factory=list, max_length=5000)
    graduation_exclusions: dict[UUID, str] = Field(default_factory=dict)
    duplicate_name_confirmed: bool = False
    records_verified_ids: list[UUID] = Field(default_factory=list, max_length=5000)


class StudentTaskConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    confirmed: Literal[True]
    identity_confirmed: Literal[True]
    changes_confirmed: Literal[True]


class StudentTaskReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    student_ids: list[UUID] = Field(min_length=1, max_length=5000)
    decision: Literal["approved", "rejected"]
    note: str = Field(min_length=1, max_length=500)


class StudentTaskCancel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
