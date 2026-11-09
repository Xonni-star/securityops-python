from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.automation_events import AutomationTrigger

NotificationEventType = AutomationTrigger | Literal["automation.notification"]


class NotificationRead(BaseModel):
    id: UUID
    task_id: UUID | None
    object_id: UUID | None
    invoice_id: UUID | None
    event_type: NotificationEventType
    title: str
    body: str
    created_at: datetime
    read_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class NotificationPage(BaseModel):
    items: list[NotificationRead]
    total: int
    unread_count: int
    limit: int
    offset: int
