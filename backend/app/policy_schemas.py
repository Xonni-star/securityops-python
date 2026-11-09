from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PolicyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["instruction", "training"]
    title: str = Field(min_length=1, max_length=200)
    object_id: UUID | None = None
    repeat_interval_days: int | None = Field(default=None, ge=1, le=3650)
    reminder_days: int | None = Field(default=None, ge=1, le=3650)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Der Titel darf nicht leer sein")
        return value

    @model_validator(mode="after")
    def validate_repeat_settings(self):
        if self.kind == "instruction" and self.repeat_interval_days is not None:
            raise ValueError("Wiederholungsintervalle gelten nur für Unterweisungen")
        return self


class PolicyVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=100_000)
    valid_from: datetime
    valid_until: datetime | None = None

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Der Inhalt darf nicht leer sein")
        return value

    @field_validator("valid_from", "valid_until")
    @classmethod
    def require_aware_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Zeitpunkte müssen eine Zeitzone enthalten")
            return value.astimezone(UTC)
        return value

    @model_validator(mode="after")
    def validate_validity(self):
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError("Das Gültigkeitsende muss nach dem Gültigkeitsbeginn liegen")
        return self


class PolicyAssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: UUID
    due_at: datetime | None = None

    @field_validator("due_at")
    @classmethod
    def require_aware_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Fälligkeitspunkte müssen eine Zeitzone enthalten")
            return value.astimezone(UTC)
        return value


class PolicyVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version_number: int
    content: str
    valid_from: datetime
    valid_until: datetime | None
    created_by_id: UUID | None
    created_at: datetime


class PolicyRead(BaseModel):
    id: UUID
    kind: str
    title: str
    object_id: UUID | None
    object_name: str | None
    repeat_interval_days: int | None
    reminder_days: int | None
    versions: list[PolicyVersionRead]


class PolicyAssignmentRead(BaseModel):
    id: UUID
    policy_id: UUID
    kind: str
    title: str
    object_id: UUID | None
    object_name: str | None
    version_id: UUID
    version_number: int
    content: str
    valid_from: datetime
    valid_until: datetime | None
    cycle_number: int
    due_at: datetime | None
    read_at: datetime | None
    confirmed_at: datetime | None
    overdue: bool
    reminder_due: bool


class PolicyHistoryRead(BaseModel):
    policy: PolicyRead
    assignments: list[dict[str, object]]


class PolicyEmployeeOption(BaseModel):
    id: UUID
    full_name: str
    employee_number: str


class PolicyObjectOption(BaseModel):
    id: UUID
    name: str
    code: str
