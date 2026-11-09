from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class ControlRoomObject(BaseModel):
    id: UUID
    code: str
    name: str


class ControlRoomShift(BaseModel):
    id: UUID
    employee_id: UUID
    employee_name: str
    object_id: UUID
    object_name: str
    starts_at: datetime
    ends_at: datetime
    status: Literal["published"]


class ControlRoomOWKSEvent(BaseModel):
    id: UUID
    object_id: UUID
    object_name: str
    event_type: str
    severity: str
    title: str
    occurred_at: datetime
    status: Literal["open", "in_progress"]


class ControlRoomIncident(BaseModel):
    id: UUID
    title: str
    object_id: UUID
    object_name: str
    severity: str
    status: Literal["reported", "investigating", "action_required"]
    due_at: datetime | None
    assigned_to_name: str
    created_at: datetime


class ControlRoomTask(BaseModel):
    id: UUID
    title: str
    object_id: UUID | None
    object_name: str | None
    status: Literal["open", "in_progress", "blocked"]
    priority: Literal["low", "normal", "high", "urgent"]
    due_at: datetime | None
    assigned_to_name: str
    created_at: datetime


class ControlRoomAbsence(BaseModel):
    employee_id: UUID
    employee_name: str
    absence_type: Literal["vacation", "sick_leave", "other"]
    status: Literal["pending", "approved"]
    starts_on: date
    ends_on: date


class ControlRoomQualification(BaseModel):
    employee_id: UUID
    employee_name: str
    category: str
    name: str
    expires_on: date


class ControlRoomBillingApproval(BaseModel):
    id: UUID
    invoice_number: str
    object_name: str
    issued_on: date
    created_at: datetime


class ControlRoomRead(BaseModel):
    generated_at: datetime
    range_start: date
    range_end: date
    counts: dict[str, int]
    objects: list[ControlRoomObject] | None = None
    shifts: list[ControlRoomShift] | None = None
    owks_events: list[ControlRoomOWKSEvent] | None = None
    incidents: list[ControlRoomIncident] | None = None
    tasks: list[ControlRoomTask] | None = None
    absences: list[ControlRoomAbsence] | None = None
    qualifications: list[ControlRoomQualification] | None = None
    billing_approvals: list[ControlRoomBillingApproval] | None = None


class ObjectOperationsReportItem(BaseModel):
    object_id: UUID
    object_code: str
    object_name: str
    published_assigned_shifts: int
    incidents_created: int
    control_events: int
    missed_controls: int
    task_status_counts: dict[str, int]


class ObjectOperationsReportRead(BaseModel):
    range_start: date
    range_end: date
    total: int
    limit: int
    offset: int
    has_more: bool
    items: list[ObjectOperationsReportItem]
