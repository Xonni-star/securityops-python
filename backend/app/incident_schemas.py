from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

IncidentType = Literal["incident", "accident", "assault", "property_damage", "complaint", "other"]
IncidentSeverity = Literal["low", "medium", "high", "critical"]
IncidentStatus = Literal["reported", "investigating", "action_required", "closed"]


def _trim_required(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Das Feld darf nicht leer sein.")
    return value


class IncidentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    report: str = Field(min_length=1, max_length=4000)
    incident_type: IncidentType
    severity: IncidentSeverity
    object_id: UUID
    due_at: datetime | None = None
    assigned_to_id: UUID | None = None
    owks_event_id: UUID | None = None

    @field_validator("title", "report")
    @classmethod
    def trim_required(cls, value: str) -> str:
        return _trim_required(value)


class IncidentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    report: str | None = Field(default=None, min_length=1, max_length=4000)
    incident_type: IncidentType | None = None
    severity: IncidentSeverity | None = None
    due_at: datetime | None = None
    assigned_to_id: UUID | None = None

    @field_validator("title", "report")
    @classmethod
    def trim_optional(cls, value: str | None) -> str | None:
        return _trim_required(value) if value is not None else None


class IncidentStatusUpdate(BaseModel):
    status: IncidentStatus


class IncidentSensitiveUpdate(BaseModel):
    narrative: str | None = Field(default=None, max_length=20000)
    closure_report: str | None = Field(default=None, max_length=10000)

    @field_validator("narrative", "closure_report")
    @classmethod
    def trim_sensitive(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class IncidentMeasureCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    due_at: datetime | None = None
    assigned_to_id: UUID

    @field_validator("title")
    @classmethod
    def trim_title(cls, value: str) -> str:
        return _trim_required(value)

    @field_validator("description")
    @classmethod
    def trim_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class IncidentMeasureUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    due_at: datetime | None = None
    assigned_to_id: UUID | None = None
    status: Literal["open", "in_progress", "completed"] | None = None

    @field_validator("title")
    @classmethod
    def trim_optional_title(cls, value: str | None) -> str | None:
        return _trim_required(value) if value is not None else None

    @field_validator("description")
    @classmethod
    def trim_optional_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class IncidentPersonCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    role: Literal["involved", "witness"]
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        return _trim_required(value)

    @field_validator("notes")
    @classmethod
    def trim_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class IncidentRead(BaseModel):
    id: UUID
    title: str
    report: str
    incident_type: IncidentType
    severity: IncidentSeverity
    object_id: UUID
    object_name: str
    status: IncidentStatus
    due_at: datetime | None
    assigned_to_id: UUID
    assigned_to_name: str
    owks_event_id: UUID | None
    created_by_id: UUID | None
    created_at: datetime
    updated_at: datetime


class IncidentSensitiveRead(BaseModel):
    narrative: str | None
    closure_report: str | None
    updated_by_id: UUID | None
    updated_at: datetime | None


class ORMRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class IncidentPersonRead(ORMRead):
    id: UUID
    name: str
    role: Literal["involved", "witness"]
    notes: str | None
    created_at: datetime


class IncidentAttachmentRead(ORMRead):
    id: UUID
    file_name: str
    media_type: str
    size_bytes: int
    sha256: str
    created_at: datetime


class IncidentMeasureRead(ORMRead):
    id: UUID
    title: str
    description: str | None
    due_at: datetime | None
    assigned_to_id: UUID
    status: Literal["open", "in_progress", "completed"]
    created_at: datetime
    updated_at: datetime


class IncidentHistoryRead(ORMRead):
    id: UUID
    actor_id: UUID | None
    action: str
    changes: dict[str, object]
    created_at: datetime


class IncidentDetail(IncidentRead):
    sensitive_details: IncidentSensitiveRead | None
    people: list[IncidentPersonRead]
    attachments: list[IncidentAttachmentRead]
    measures: list[IncidentMeasureRead]
    history: list[IncidentHistoryRead]


class IncidentPage(BaseModel):
    items: list[IncidentRead]
    total: int
    limit: int
    offset: int


class IncidentObjectChoice(BaseModel):
    id: UUID
    name: str
    code: str


class IncidentAssigneeChoice(BaseModel):
    id: UUID
    full_name: str


class IncidentChoices(BaseModel):
    objects: list[IncidentObjectChoice]
    assignees: list[IncidentAssigneeChoice]
    linked_owks_event_ids: list[UUID] = Field(default_factory=list)
