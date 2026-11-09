from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.automation_events import (
    OWKS_EVENT_TRIGGER_TYPES,
    OWKS_OFFLINE_SYNC_TRIGGER,
    OWKSAutomationEventPayload,
)
from app.models import (
    NotificationOutbox,
    ObjectAssignment,
    OWKSEvent,
    SecurityObject,
    Task,
    TaskHistory,
    User,
)

STATUS_NAMES = {
    "open": "Offen",
    "in_progress": "In Bearbeitung",
    "blocked": "Blockiert",
    "completed": "Erledigt",
    "cancelled": "Abgebrochen",
}


def enqueue_task_event(
    db: Session,
    task: Task,
    history: TaskHistory,
    *,
    event_type: str,
    recipient_ids: set[UUID],
    previous_assignee_id: UUID | None = None,
) -> None:
    outbox_event = NotificationOutbox(
        id=uuid4(),
        dedupe_key=f"task-history:{history.id}",
        event_type=event_type,
        aggregate_type="task",
        aggregate_id=task.id,
        payload={
            "schema_version": 1,
            "task_id": str(task.id),
            "recipient_ids": sorted(str(recipient_id) for recipient_id in recipient_ids),
            "status": task.status,
            "title": (
                "Neue Aufgabe zugewiesen"
                if event_type == "task.assigned"
                else "Aufgabenstatus geändert"
            ),
            "body": (
                task.title
                if event_type == "task.assigned"
                else f"{task.title}: {STATUS_NAMES[task.status]}"
            ),
            "previous_assignee_id": (
                str(previous_assignee_id) if previous_assignee_id is not None else None
            ),
        },
    )
    db.add(outbox_event)


def enqueue_owks_automation_event(
    db: Session,
    event: OWKSEvent,
    *,
    trigger_type: str | None = None,
) -> None:
    if (
        trigger_type is None
        and event.event_type == "deviation"
        and event.sync_status != "synced"
    ):
        return
    trigger_type = trigger_type or OWKS_EVENT_TRIGGER_TYPES.get(event.event_type)
    if trigger_type is None:
        return
    if trigger_type not in set(OWKS_EVENT_TRIGGER_TYPES.values()) | {OWKS_OFFLINE_SYNC_TRIGGER}:
        raise ValueError("Unregistrierter OWKS-Automatisierungsauslöser")

    recipient_ids = set(
        db.scalars(
            select(ObjectAssignment.user_id)
            .join(User, User.id == ObjectAssignment.user_id)
            .join(SecurityObject, SecurityObject.id == ObjectAssignment.object_id)
            .where(
                ObjectAssignment.object_id == event.object_id,
                User.is_active.is_(True),
                SecurityObject.archived_at.is_(None),
            )
        ).all()
    )
    payload = OWKSAutomationEventPayload(
        schema_version=1,
        owks_event_id=event.id,
        object_id=event.object_id,
        recipient_ids=sorted(recipient_ids, key=str),
    )
    db.add(
        NotificationOutbox(
            id=uuid4(),
            dedupe_key=f"owks:{trigger_type}:{event.id}",
            event_type=trigger_type,
            aggregate_type="owks_event",
            aggregate_id=event.id,
            payload=payload.model_dump(mode="json"),
        )
    )
