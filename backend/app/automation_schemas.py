from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.automation_events import (
    BILLING_AUTOMATION_EVENT_TYPES,
    OWKS_AUTOMATION_EVENT_TYPES,
    AutomationTrigger,
)

NO_CONDITION_AUTOMATION_EVENT_TYPES = OWKS_AUTOMATION_EVENT_TYPES | BILLING_AUTOMATION_EVENT_TYPES

AutomationAction = Literal["notify_event_recipients"]
TaskStatus = Literal["open", "in_progress", "blocked", "completed", "cancelled"]


class AutomationCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TaskStatus | None = None


class AutomationRuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    trigger_type: AutomationTrigger
    conditions: AutomationCondition = Field(default_factory=AutomationCondition)
    action_type: AutomationAction = "notify_event_recipients"

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Der Regelname darf nicht leer sein.")
        return value

    @field_validator("description")
    @classmethod
    def description_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("Die Beschreibung darf nicht leer sein.")
        return value

    @model_validator(mode="after")
    def validate_trigger_conditions(self) -> "AutomationRuleCreate":
        if (
            self.trigger_type in NO_CONDITION_AUTOMATION_EVENT_TYPES
            and self.conditions.status is not None
        ):
            raise ValueError("Dieser Auslöser unterstützt keine Aufgabenstatus-Bedingung.")
        return self


class AutomationRuleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    trigger_type: AutomationTrigger | None = None
    conditions: AutomationCondition | None = None
    action_type: AutomationAction | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("Der Regelname darf nicht leer sein.")
        return value

    @field_validator("description")
    @classmethod
    def description_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("Die Beschreibung darf nicht leer sein.")
        return value


class AutomationRuleRead(BaseModel):
    id: UUID
    name: str
    description: str | None
    trigger_type: AutomationTrigger
    conditions: AutomationCondition
    action_type: AutomationAction
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AutomationAttemptRead(BaseModel):
    attempt_number: int
    event: str
    error_code: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AutomationRunRead(BaseModel):
    id: UUID
    rule_id: UUID
    rule_name: str
    source_event_id: UUID
    action_event_id: UUID | None
    trigger_type: AutomationTrigger
    status: Literal[
        "condition_not_met",
        "skipped_no_recipients",
        "queued",
        "succeeded",
        "dead_letter",
    ]
    last_error: str | None
    manual_retry_count: int
    created_at: datetime
    updated_at: datetime
    attempt_history: list[AutomationAttemptRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class AutomationRunPage(BaseModel):
    items: list[AutomationRunRead]
    total: int
    limit: int
    offset: int


class AutomationOutboxEventRead(BaseModel):
    id: UUID
    event_type: str
    aggregate_id: UUID
    status: Literal["dead_letter"]
    attempt_count: int
    manual_retry_count: int
    last_error: str | None
    created_at: datetime
    attempt_history: list[AutomationAttemptRead] = Field(default_factory=list)


class AutomationOutboxEventPage(BaseModel):
    items: list[AutomationOutboxEventRead]
    total: int
