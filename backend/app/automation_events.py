from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AutomationTrigger = Literal[
    "task.assigned",
    "task.status_changed",
    "owks.missed_control",
    "owks.deviation_reported",
    "owks.offline_event_synced",
    "billing.invoice_approved",
    "key.issued",
]

TASK_EVENT_TYPES = frozenset({"task.assigned", "task.status_changed"})
BILLING_INVOICE_APPROVED_EVENT = "billing.invoice_approved"
BILLING_AUTOMATION_EVENT_TYPES = frozenset({BILLING_INVOICE_APPROVED_EVENT})
KEY_ISSUED_AUTOMATION_EVENT = "key.issued"
KEY_AUTOMATION_EVENT_TYPES = frozenset({KEY_ISSUED_AUTOMATION_EVENT})
KEY_ISSUED_EVENT_MESSAGE = "An einem zugewiesenen Objekt wurde ein Schlüssel ausgegeben."
OWKS_EVENT_MESSAGES = {
    "owks.missed_control": "An einem zugewiesenen Objekt wurde eine Kontrolle als versäumt protokolliert.",
    "owks.deviation_reported": "An einem zugewiesenen Objekt wurde eine OWKS-Auffälligkeit gemeldet.",
    "owks.offline_event_synced": "Ein Offline-Ereignis wurde an einem zugewiesenen Objekt synchronisiert.",
}
OWKS_AUTOMATION_EVENT_TYPES = frozenset(OWKS_EVENT_MESSAGES)
OWKS_EVENT_TRIGGER_TYPES = {
    "missed": "owks.missed_control",
    "deviation": "owks.deviation_reported",
}
OWKS_OFFLINE_SYNC_TRIGGER = "owks.offline_event_synced"
AUTOMATION_NOTIFICATION_EVENT = "automation.notification"


class EventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("recipient_ids")
    @classmethod
    def recipients_must_be_unique(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("Empfänger dürfen nicht doppelt vorkommen.")
        return value

    recipient_ids: list[UUID] = Field(max_length=1000)


class TaskNotificationEventPayload(EventPayload):
    schema_version: Literal[1] | None = None
    task_id: UUID
    status: Literal["open", "in_progress", "blocked", "completed", "cancelled"] | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, max_length=500)
    previous_assignee_id: UUID | None = None

    @model_validator(mode="after")
    def versioned_payload_is_complete(self) -> "TaskNotificationEventPayload":
        if self.schema_version == 1 and (
            self.status is None or self.title is None or self.body is None
        ):
            raise ValueError("Versionierte Aufgabenereignisse benötigen Status und Nachricht.")
        return self


class OWKSAutomationEventPayload(EventPayload):
    schema_version: Literal[1]
    owks_event_id: UUID
    object_id: UUID


class BillingInvoiceApprovedEventPayload(EventPayload):
    schema_version: Literal[1]
    invoice_id: UUID


class KeyIssuedAutomationEventPayload(EventPayload):
    schema_version: Literal[1]
    movement_id: UUID
    object_id: UUID


class AutomationNotificationPayload(EventPayload):
    schema_version: Literal[1] | None = None
    automation_run_id: UUID
    source_event_type: AutomationTrigger | None = None
    task_id: UUID | None = None
    object_id: UUID | None = None
    invoice_id: UUID | None = None
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(max_length=500)

    @model_validator(mode="after")
    def has_exactly_one_target(self) -> "AutomationNotificationPayload":
        if (
            sum(target is not None for target in (self.task_id, self.object_id, self.invoice_id))
            != 1
        ):
            raise ValueError("Genau ein Benachrichtigungsziel ist erforderlich.")
        return self


EVENT_REGISTRY: dict[str, type[EventPayload]] = {
    "task.assigned": TaskNotificationEventPayload,
    "task.status_changed": TaskNotificationEventPayload,
    **{event_type: OWKSAutomationEventPayload for event_type in OWKS_AUTOMATION_EVENT_TYPES},
    BILLING_INVOICE_APPROVED_EVENT: BillingInvoiceApprovedEventPayload,
    **{event_type: KeyIssuedAutomationEventPayload for event_type in KEY_AUTOMATION_EVENT_TYPES},
    AUTOMATION_NOTIFICATION_EVENT: AutomationNotificationPayload,
}
