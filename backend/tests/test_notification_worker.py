import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from conftest import TestingSessionLocal, test_engine
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app import notification_worker
from app.models import (
    Notification,
    NotificationOutbox,
    NotificationOutboxAttempt,
    Task,
    User,
)
from app.notification_worker import (
    CycleResult,
    NotificationOutboxWorker,
    inspect_outbox,
    retry_delay_seconds,
    run_worker,
)


def create_task_event(
    *,
    status: str = "pending",
    locked_at: datetime | None = None,
    attempt_count: int = 0,
) -> tuple[object, object]:
    with TestingSessionLocal() as db:
        recipient = db.scalar(select(User).where(User.username == "admin"))
        assert recipient is not None
        task = Task(
            id=uuid4(),
            title="Test-Aufgabe",
            assigned_to_id=recipient.id,
            created_by_id=recipient.id,
            priority="normal",
            status="open",
        )
        db.add(task)
        db.flush()
        event = NotificationOutbox(
            id=uuid4(),
            dedupe_key=f"test:{uuid4()}",
            event_type="task.assigned",
            aggregate_type="task",
            aggregate_id=task.id,
            payload={
                "task_id": str(task.id),
                "recipient_ids": [str(recipient.id)],
                "title": "Neue Aufgabe zugewiesen",
                "body": "Test-Aufgabe",
            },
            status=status,
            attempt_count=attempt_count,
            available_at=datetime.now(UTC),
            locked_at=locked_at,
            lock_token=uuid4() if status == "processing" else None,
        )
        db.add(event)
        db.commit()
        return event.id, task.id


def test_outbox_delivery_is_idempotent_and_records_attempt_history(client) -> None:
    event_id, _ = create_task_event()
    worker = NotificationOutboxWorker(TestingSessionLocal)

    first = worker.run_once()
    with TestingSessionLocal() as db:
        event = db.get(NotificationOutbox, event_id)
        assert event is not None
        event.status = "pending"
        db.commit()
    second = worker.run_once()

    assert first.delivered == 1
    assert second.delivered == 1
    with TestingSessionLocal() as db:
        event = db.get(NotificationOutbox, event_id)
        notifications = db.scalars(
            select(Notification).where(Notification.outbox_id == event_id)
        ).all()
        attempts = db.scalars(
            select(NotificationOutboxAttempt)
            .where(NotificationOutboxAttempt.outbox_id == event_id)
            .order_by(NotificationOutboxAttempt.event)
        ).all()
    assert event is not None and event.status == "completed"
    assert len(notifications) == 1
    assert sum(attempt.event == "claimed" for attempt in attempts) == 2
    assert sum(attempt.event == "succeeded" for attempt in attempts) == 2


def test_expired_processing_claim_is_recovered(client) -> None:
    event_id, _ = create_task_event(
        status="processing",
        locked_at=datetime.now(UTC) - timedelta(minutes=10),
        attempt_count=1,
    )

    result = NotificationOutboxWorker(TestingSessionLocal).run_once()

    assert result.delivered == 1
    with TestingSessionLocal() as db:
        event = db.get(NotificationOutbox, event_id)
        assert event is not None
        assert event.status == "completed"
        assert event.attempt_count == 2


def test_legacy_outbox_with_existing_notification_is_completed_idempotently(client) -> None:
    event_id, task_id = create_task_event()
    with TestingSessionLocal() as db:
        event = db.get(NotificationOutbox, event_id)
        recipient = db.scalar(select(User).where(User.username == "admin"))
        assert event is not None and recipient is not None
        event.payload.pop("title")
        event.payload.pop("body")
        db.add(
            Notification(
                outbox_id=event.id,
                recipient_id=recipient.id,
                task_id=task_id,
                event_type=event.event_type,
                title="Neue Aufgabe zugewiesen",
                body="Test-Aufgabe",
            )
        )
        db.commit()

    result = NotificationOutboxWorker(TestingSessionLocal).run_once()

    assert result.delivered == 1
    with TestingSessionLocal() as db:
        event = db.get(NotificationOutbox, event_id)
        notifications = db.scalars(
            select(Notification).where(Notification.outbox_id == event_id)
        ).all()
    assert event is not None and event.status == "completed"
    assert len(notifications) == 1


def test_status_event_without_recipients_is_successful_noop(client) -> None:
    event_id, _ = create_task_event()
    with TestingSessionLocal() as db:
        event = db.get(NotificationOutbox, event_id)
        assert event is not None
        event.event_type = "task.status_changed"
        event.payload = {**event.payload, "recipient_ids": []}
        db.commit()

    result = NotificationOutboxWorker(TestingSessionLocal).run_once()

    assert result.delivered == 1
    with TestingSessionLocal() as db:
        event = db.get(NotificationOutbox, event_id)
        notifications = db.scalars(
            select(Notification).where(Notification.outbox_id == event_id)
        ).all()
        succeeded = db.scalar(
            select(NotificationOutboxAttempt).where(
                NotificationOutboxAttempt.outbox_id == event_id,
                NotificationOutboxAttempt.event == "succeeded",
            )
        )
    assert event is not None and event.status == "completed"
    assert notifications == []
    assert succeeded is not None


def test_retry_backoff_is_bounded_and_error_logging_excludes_exception_text(
    client, caplog, monkeypatch
) -> None:
    event_id, _ = create_task_event()
    worker = NotificationOutboxWorker(TestingSessionLocal)

    def fail_with_sensitive_text(_db, _event):
        raise ValueError("personenbezogene Testdaten nicht protokollieren")

    monkeypatch.setattr(worker, "_deliver", fail_with_sensitive_text)
    with caplog.at_level("ERROR", logger="app.notification_worker"):
        result = worker.run_once()

    with TestingSessionLocal() as db:
        event = db.get(NotificationOutbox, event_id)
        attempt = db.scalar(
            select(NotificationOutboxAttempt).where(
                NotificationOutboxAttempt.outbox_id == event_id,
                NotificationOutboxAttempt.event == "retry_scheduled",
            )
        )
    assert result.retried == 1
    assert event is not None and event.status == "pending"
    assert event.last_error == "ValueError"
    retry_delay = event.available_at - event.last_attempt_at
    assert timedelta(seconds=5) <= retry_delay < timedelta(seconds=6)
    assert attempt is not None and attempt.error_code == "ValueError"
    assert "personenbezogene Testdaten" not in caplog.text
    assert retry_delay_seconds(1) == 5
    assert retry_delay_seconds(8) == 640
    assert retry_delay_seconds(20) == 3600


def test_max_attempts_moves_event_to_dead_letter(client, monkeypatch) -> None:
    event_id, _ = create_task_event()
    worker = NotificationOutboxWorker(TestingSessionLocal, max_attempts=1)
    monkeypatch.setattr(worker, "_deliver", lambda _db, _event: (_ for _ in ()).throw(ValueError()))

    result = worker.run_once()

    assert result.dead_lettered == 1
    with TestingSessionLocal() as db:
        event = db.get(NotificationOutbox, event_id)
        attempt = db.scalar(
            select(NotificationOutboxAttempt).where(
                NotificationOutboxAttempt.outbox_id == event_id,
                NotificationOutboxAttempt.event == "dead_lettered",
            )
        )
    assert event is not None and event.status == "dead_letter"
    assert event.attempt_count == 1
    assert event.last_error == "ValueError"
    assert attempt is not None


def test_failed_event_inspection_excludes_payload_and_includes_attempts(
    client, monkeypatch
) -> None:
    event_id, _ = create_task_event()
    worker = NotificationOutboxWorker(TestingSessionLocal, max_attempts=1)
    monkeypatch.setattr(worker, "_deliver", lambda _db, _event: (_ for _ in ()).throw(ValueError()))
    worker.run_once()
    with TestingSessionLocal() as db:
        event = db.get(NotificationOutbox, event_id)
        assert event is not None
        event.last_error = "person testsecret@example.com"
        db.commit()
    monkeypatch.setattr(notification_worker, "SessionLocal", TestingSessionLocal)

    inspection = inspect_outbox(limit=1)
    failed_event = inspection["failed_events"][0]
    serialized = str(inspection)

    assert failed_event["id"] == str(event_id)
    assert failed_event["status"] == "dead_letter"
    assert failed_event["last_error"] == "legacy_or_invalid_error_code"
    assert failed_event["attempt_history"][-1]["error_code"] == "ValueError"
    assert "Test-Aufgabe" not in serialized
    assert "testsecret@example.com" not in serialized
    assert "recipient_ids" not in serialized


@pytest.mark.skipif(test_engine.dialect.name != "postgresql", reason="PostgreSQL SKIP LOCKED nötig")
def test_concurrent_workers_claim_event_once(client) -> None:
    event_id, _ = create_task_event()
    worker = NotificationOutboxWorker(TestingSessionLocal)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: worker.run_once(), range(2)))

    with TestingSessionLocal() as db:
        notifications = db.scalars(
            select(Notification).where(Notification.outbox_id == event_id)
        ).all()
        claims = db.scalars(
            select(NotificationOutboxAttempt).where(
                NotificationOutboxAttempt.outbox_id == event_id,
                NotificationOutboxAttempt.event == "claimed",
            )
        ).all()
    assert sum(result.claimed for result in results) == 1
    assert len(notifications) == 1
    assert len(claims) == 1


@pytest.mark.skipif(test_engine.dialect.name != "postgresql", reason="PostgreSQL-Trigger nötig")
def test_attempt_history_is_append_only(client) -> None:
    event_id, _ = create_task_event()
    NotificationOutboxWorker(TestingSessionLocal).run_once()

    with pytest.raises(DBAPIError), TestingSessionLocal() as db:
        attempt = db.scalar(
            select(NotificationOutboxAttempt).where(NotificationOutboxAttempt.outbox_id == event_id)
        )
        assert attempt is not None
        attempt.error_code = "changed"
        db.commit()


def test_worker_loop_stops_cleanly_after_stop_signal() -> None:
    stop = asyncio.Event()
    cycles = 0
    heartbeats = 0

    def run_cycle():
        nonlocal cycles
        cycles += 1
        stop.set()
        return CycleResult()

    def write_heartbeat():
        nonlocal heartbeats
        heartbeats += 1

    asyncio.run(
        run_worker(
            stop,
            run_cycle=run_cycle,
            poll_interval_seconds=60,
            heartbeat_writer=write_heartbeat,
        )
    )

    assert cycles == 1
    assert heartbeats == 1
