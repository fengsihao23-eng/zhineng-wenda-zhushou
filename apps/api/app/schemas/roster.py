from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.person_id import PersonReference

RosterKind = Literal["teachers", "students"]


class RosterUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=200)
    content_base64: str = Field(max_length=7_000_000)


class RosterConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    duplicate_decisions: dict[int, bool] = Field(default_factory=dict)
    teacher_replacements: dict[int, PersonReference] = Field(default_factory=dict)
    identity_confirmed: bool = False
    changes_confirmed: bool = False


class RosterAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["delete", "disable", "depart", "graduate", "suspend", "withdraw"]
    confirmed: Literal[True]


class TeacherDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    teacher_ids: list[PersonReference] = Field(min_length=1, max_length=5000)
    reason: Literal["depart", "disable", "incorrect", "change", "other"]
    reason_note: str = Field(default="", max_length=500)
    confirmed: Literal[True]
