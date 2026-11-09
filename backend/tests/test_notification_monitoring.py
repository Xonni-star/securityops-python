from datetime import UTC, datetime, timedelta
from uuid import uuid4

from conftest import ADMIN_PASSWORD, TestingSessionLocal
from sqlalchemy import func, select

from app.models import NotificationOutbox, NotificationWorkerHeartbeat, Permission, Role
from app.notification_monitoring import WORKER_NAME, write_worker_heartbeat


def login(client, username: str, password: str) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200


def test_notification_monitoring_requires_an_operations_or_admin_permission(client) -> None:
    path = "/api/v1/monitoring/notifications"
    assert client.get(path).status_code == 401

    login(client, "geschaeftsfuehrung", "management-test-passwort-2026")
    assert client.get(path).status_code == 403

    login(client, "operations", "operations-test-passwort-2026")
    assert client.get(path).status_code == 200

    login(client, "admin", ADMIN_PASSWORD)
    assert client.get(path).status_code == 200

    with TestingSessionLocal() as db:
        operations = db.scalar(select(Role).where(Role.code == "operations"))
        permission = db.scalar(
            select(Permission).where(Permission.code == "system.monitoring.read")
        )
        assert operations is not None and permission in operations.permissions


def test_missing_worker_heartbeat_is_unknown_and_response_is_data_minimal(client) -> None:
    login(client, "admin", ADMIN_PASSWORD)

    response = client.get("/api/v1/monitoring/notifications")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    result = response.json()
    assert result["status"] == "unknown"
    assert result["worker"] == {
        "status": "unknown",
        "last_heartbeat_at": None,
        "heartbeat_age_seconds": None,
        "stale_after_seconds": 90,
    }
    assert result["outbox"]["pending"] == 0
    assert result["outbox"]["dead_letter"] == 0
    assert "payload" not in response.text
    assert "recipient" not in response.text

    write_worker_heartbeat(TestingSessionLocal)
    healthy_response = client.get("/api/v1/monitoring/notifications")
    assert healthy_response.json()["status"] == "healthy"
    assert healthy_response.json()["worker"]["status"] == "healthy"


def test_monitoring_uses_real_queue_counts_and_marks_stale_worker(client) -> None:
    login(client, "admin", ADMIN_PASSWORD)
    now = datetime.now(UTC)
    with TestingSessionLocal() as db:
        db.add(
            NotificationWorkerHeartbeat(
                worker_name=WORKER_NAME,
                heartbeat_at=now - timedelta(seconds=91),
            )
        )
        db.add_all(
            [
                NotificationOutbox(
                    id=uuid4(),
                    dedupe_key=f"monitoring:{uuid4()}",
                    event_type="task.assigned",
                    aggregate_type="task",
                    aggregate_id=uuid4(),
                    payload={"recipient_ids": ["private-recipient"], "title": "private title"},
                    status="pending",
                    attempt_count=0,
                    available_at=now,
                    created_at=now - timedelta(minutes=5),
                ),
                NotificationOutbox(
                    id=uuid4(),
                    dedupe_key=f"monitoring:{uuid4()}",
                    event_type="task.assigned",
                    aggregate_type="task",
                    aggregate_id=uuid4(),
                    payload={"recipient_ids": ["private-recipient"]},
                    status="processing",
                    attempt_count=1,
                    available_at=now,
                    locked_at=now - timedelta(minutes=10),
                    created_at=now - timedelta(minutes=10),
                ),
                NotificationOutbox(
                    id=uuid4(),
                    dedupe_key=f"monitoring:{uuid4()}",
                    event_type="task.assigned",
                    aggregate_type="task",
                    aggregate_id=uuid4(),
                    payload={"recipient_ids": ["private-recipient"]},
                    status="dead_letter",
                    attempt_count=8,
                    available_at=now,
                    created_at=now - timedelta(minutes=20),
                ),
                NotificationOutbox(
                    id=uuid4(),
                    dedupe_key=f"monitoring:{uuid4()}",
                    event_type="task.assigned",
                    aggregate_type="task",
                    aggregate_id=uuid4(),
                    payload={},
                    status="completed",
                    attempt_count=1,
                    available_at=now,
                    created_at=now,
                ),
            ]
        )
        db.commit()

    response = client.get("/api/v1/monitoring/notifications")

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "degraded"
    assert result["worker"]["status"] == "stale"
    assert result["worker"]["heartbeat_age_seconds"] >= 91
    assert result["outbox"]["pending"] == 1
    assert result["outbox"]["processing"] == 1
    assert result["outbox"]["completed"] == 1
    assert result["outbox"]["dead_letter"] == 1
    assert result["outbox"]["stale_processing"] == 1
    assert result["outbox"]["oldest_pending_at"] is not None
    assert result["outbox"]["oldest_dead_letter_at"] is not None
    assert "private-recipient" not in response.text
    assert "private title" not in response.text
    assert "recipient_ids" not in response.text


def test_worker_heartbeat_upsert_records_activity_once(client) -> None:
    write_worker_heartbeat(TestingSessionLocal)
    with TestingSessionLocal() as db:
        first_heartbeat = db.scalar(
            select(NotificationWorkerHeartbeat.heartbeat_at).where(
                NotificationWorkerHeartbeat.worker_name == WORKER_NAME
            )
        )
    assert first_heartbeat is not None

    write_worker_heartbeat(TestingSessionLocal)

    with TestingSessionLocal() as db:
        row_count = db.scalar(select(func.count()).select_from(NotificationWorkerHeartbeat))
        latest_heartbeat = db.scalar(
            select(NotificationWorkerHeartbeat.heartbeat_at).where(
                NotificationWorkerHeartbeat.worker_name == WORKER_NAME
            )
        )
    assert row_count == 1
    assert latest_heartbeat is not None
    assert latest_heartbeat >= first_heartbeat
