from uuid import UUID, uuid4

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.automation_events import (
    BILLING_INVOICE_APPROVED_EVENT,
    KEY_ISSUED_AUTOMATION_EVENT,
    OWKS_EVENT_TRIGGER_TYPES,
    OWKS_OFFLINE_SYNC_TRIGGER,
    BillingInvoiceApprovedEventPayload,
    KeyIssuedAutomationEventPayload,
    OWKSAutomationEventPayload,
)
from app.models import (
    BillingInvoice,
    KeyMovement,
    NotificationOutbox,
    ObjectAssignment,
    OWKSEvent,
    Permission,
    Role,
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
    if trigger_type is None and event.event_type == "deviation" and event.sync_status != "synced":
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


def billing_notification_recipient_ids(db: Session) -> set[UUID]:
    return set(
        db.scalars(
            select(User.id)
            .join(User.roles)
            .join(Role.permissions)
            .where(
                User.is_active.is_(True),
                Permission.code.in_({"billing.invoices.read", "notifications.read_own"}),
            )
            .group_by(User.id)
            .having(func.count(distinct(Permission.code)) == 2)
        ).all()
    )


def enqueue_invoice_approved_event(db: Session, invoice: BillingInvoice) -> None:
    payload = BillingInvoiceApprovedEventPayload(
        schema_version=1,
        invoice_id=invoice.id,
        recipient_ids=sorted(billing_notification_recipient_ids(db), key=str),
    )
    db.add(
        NotificationOutbox(
            id=uuid4(),
            dedupe_key=f"billing.invoice_approved:{invoice.id}",
            event_type=BILLING_INVOICE_APPROVED_EVENT,
            aggregate_type="billing_invoice",
            aggregate_id=invoice.id,
            payload=payload.model_dump(mode="json"),
        )
    )


def key_notification_recipient_ids(db: Session, object_id: UUID) -> set[UUID]:
    return set(
        db.scalars(
            select(User.id)
            .join(User.roles)
            .join(Role.permissions)
            .join(ObjectAssignment, ObjectAssignment.user_id == User.id)
            .join(SecurityObject, SecurityObject.id == ObjectAssignment.object_id)
            .where(
                ObjectAssignment.object_id == object_id,
                SecurityObject.archived_at.is_(None),
                User.is_active.is_(True),
                Permission.code.in_({"keys.read", "notifications.read_own"}),
            )
            .group_by(User.id)
            .having(func.count(distinct(Permission.code)) == 2)
        ).all()
    )


def enqueue_key_issued_event(db: Session, movement: KeyMovement) -> None:
    if movement.movement_type != "issued":
        return
    payload = KeyIssuedAutomationEventPayload(
        schema_version=1,
        movement_id=movement.id,
        object_id=movement.object_id,
        recipient_ids=sorted(key_notification_recipient_ids(db, movement.object_id), key=str),
    )
    db.add(
        NotificationOutbox(
            id=uuid4(),
            dedupe_key=f"{KEY_ISSUED_AUTOMATION_EVENT}:{movement.id}",
            event_type=KEY_ISSUED_AUTOMATION_EVENT,
            aggregate_type="key_movement",
            aggregate_id=movement.id,
            payload=payload.model_dump(mode="json"),
        )
    )
