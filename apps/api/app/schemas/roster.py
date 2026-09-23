from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

RosterKind = Literal["teachers", "students"]


class RosterUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=200)
    content_base64: str = Field(max_length=7_000_000)


class RosterConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    duplicate_decisions: dict[int, bool] = Field(default_factory=dict)
    teacher_replacements: dict[int, UUID] = Field(default_factory=dict)


class RosterAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["delete", "disable", "depart", "graduate"]
    confirmed: Literal[True]
