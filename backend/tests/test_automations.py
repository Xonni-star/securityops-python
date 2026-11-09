from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from importlib import import_module
from uuid import UUID, uuid4

import pytest
from conftest import ADMIN_PASSWORD, TestingSessionLocal, test_engine
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import (
    AuditLog,
    AutomationRule,
    AutomationRun,
    Notification,
    NotificationOutbox,
    ObjectAssignment,
    SecurityObject,
    Task,
    User,
)
from app.notification_worker import NotificationOutboxWorker


def sign_in(
    client: TestClient,
    username: str = "admin",
    password: str = ADMIN_PASSWORD,
) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    csrf_token = response.cookies.get("securityops_csrf", "")
    return {
        "Cookie": (
            f"securityops_session={response.cookies['securityops_session']}; "
            f"securityops_csrf={csrf_token}"
        ),
        "X-CSRF-Token": csrf_token,
    }


def create_task_event(
    *,
    event_type: str = "task.assigned",
    task_status: str = "open",
) -> tuple[object, object, object]:
    with TestingSessionLocal() as db:
        recipient = db.scalar(select(User).where(User.username == "admin"))
        assert recipient is not None
        task = Task(
            id=uuid4(),
            title="Kontrollpunkt dokumentieren",
            assigned_to_id=recipient.id,
            created_by_id=recipient.id,
            priority="normal",
            status=task_status,
        )
        db.add(task)
        db.flush()
        event = NotificationOutbox(
            id=uuid4(),
            dedupe_key=f"automation-test:{uuid4()}",
            event_type=event_type,
            aggregate_type="task",
            aggregate_id=task.id,
            payload={
                "task_id": str(task.id),
                "recipient_ids": [str(recipient.id)],
                "status": task_status,
                "title": "Neue Aufgabe zugewiesen",
                "body": task.title,
            },
            available_at=datetime.now(UTC),
        )
        db.add(event)
        db.commit()
        return event.id, task.id, recipient.id


def create_rule(
    *,
    trigger_type: str = "task.assigned",
    conditions: dict[str, object] | None = None,
    is_active: bool = True,
) -> object:
    with TestingSessionLocal() as db:
        rule = AutomationRule(
            id=uuid4(),
            name="Aufgabenregel",
            trigger_type=trigger_type,
            conditions=conditions or {},
            action_type="notify_event_recipients",
            is_active=is_active,
        )
        db.add(rule)
        db.commit()
        return rule.id


def create_owks_object(client: TestClient, headers: dict[str, str], code: str) -> str:
    customer = client.post(
        "/api/v1/customers",
        headers=headers,
        json={"company_name": f"Testkunde {code} Automatisierung GmbH"},
    )
    assert customer.status_code == 201
    response = client.post(
        "/api/v1/objects",
        headers=headers,
        json={"customer_id": customer.json()["id"], "name": f"Objekt {code}", "code": code},
    )
    assert response.status_code == 201
    return response.json()["id"]


def create_deviation_event(
    client: TestClient,
    headers: dict[str, str],
    object_id: str,
    *,
    client_event_id: str | None = None,
) -> dict[str, object]:
    response = client.post(
        "/api/v1/owks/events",
        headers=headers,
        json={
            "object_id": object_id,
            "event_type": "deviation",
            "title": "Vertraulicher Ereignistitel",
            "description": "VERTRAULICHER HERGANG",
            "severity": "warning",
            "client_event_id": client_event_id or str(uuid4()),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_admin_only_typed_rule_crud_and_soft_delete(client: TestClient) -> None:
    client.cookies.clear()
    assert client.get("/api/v1/automations/rules").status_code == 401
    admin_headers = sign_in(client)
    manager_headers = sign_in(client, "geschaeftsfuehrung", "management-test-passwort-2026")

    assert client.get("/api/v1/automations/rules", headers=manager_headers).status_code == 403
    invalid = client.post(
        "/api/v1/automations/rules",
        headers=admin_headers,
        json={
            "name": "Dynamisch",
            "trigger_type": "python.execute",
            "conditions": {"sql": "SELECT 1"},
            "action_type": "execute_code",
        },
    )
    assert invalid.status_code == 422

    created = client.post(
        "/api/v1/automations/rules",
        headers=admin_headers,
        json={
            "name": "Blockierte Aufgaben melden",
            "description": "Nur Aufgabenereignisse",
            "trigger_type": "task.status_changed",
            "conditions": {"status": "blocked"},
            "action_type": "notify_event_recipients",
        },
    )
    assert created.status_code == 201, created.text
    rule = created.json()
    assert rule["is_active"] is False
    assert rule["conditions"] == {"status": "blocked"}

    activated = client.patch(
        f"/api/v1/automations/rules/{rule['id']}",
        headers=admin_headers,
        json={"is_active": True},
    )
    assert activated.status_code == 200
    assert activated.json()["is_active"] is True
    changed = client.patch(
        f"/api/v1/automations/rules/{rule['id']}",
        headers=admin_headers,
        json={"conditions": {"status": "completed"}},
    )
    assert changed.status_code == 200
    assert changed.json()["conditions"] == {"status": "completed"}

    deleted = client.delete(
        f"/api/v1/automations/rules/{rule['id']}",
        headers=admin_headers,
    )
    assert deleted.status_code == 204
    assert client.get("/api/v1/automations/rules", headers=admin_headers).json() == []
    assert (
        client.get(
            f"/api/v1/automations/rules/{uuid4()}",
            headers=admin_headers,
        ).status_code
        == 404
    )
    with TestingSessionLocal() as db:
        audit_actions = set(
            db.scalars(
                select(AuditLog.action).where(AuditLog.entity_type == "automation_rule")
            ).all()
        )
    assert {
        "automation.rule_created",
        "automation.rule_updated",
        "automation.rule_deleted",
    } <= audit_actions


def test_owks_trigger_registration_rejects_task_conditions(client: TestClient) -> None:
    headers = sign_in(client)
    invalid = client.post(
        "/api/v1/automations/rules",
        headers=headers,
        json={
            "name": "OWKS mit Aufgabenbedingung",
            "trigger_type": "owks.missed_control",
            "conditions": {"status": "blocked"},
        },
    )
    assert invalid.status_code == 422

    created = client.post(
        "/api/v1/automations/rules",
        headers=headers,
        json={
            "name": "Versäumte Kontrolle melden",
            "trigger_type": "owks.missed_control",
            "conditions": {},
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["trigger_type"] == "owks.missed_control"

    changed = client.patch(
        f"/api/v1/automations/rules/{created.json()['id']}",
        headers=headers,
        json={"trigger_type": "owks.deviation_reported"},
    )
    assert changed.status_code == 200
    assert changed.json()["trigger_type"] == "owks.deviation_reported"


def test_task_event_conditions_and_rule_execution_are_idempotent(client: TestClient) -> None:
    rule_id = create_rule(conditions={"status": "open"})
    event_id, _, recipient_id = create_task_event()
    worker = NotificationOutboxWorker(TestingSessionLocal)

    first = worker.run_once()
    with TestingSessionLocal() as db:
        run = db.scalar(
            select(AutomationRun).where(
                AutomationRun.rule_id == rule_id,
                AutomationRun.source_event_id == event_id,
            )
        )
        source = db.get(NotificationOutbox, event_id)
        assert run is not None and run.status == "queued" and run.action_event_id is not None
        action_event_id = run.action_event_id
        assert source is not None
        source.status = "pending"
        db.commit()

    second = worker.run_once()

    with TestingSessionLocal() as db:
        runs = db.scalars(select(AutomationRun).where(AutomationRun.rule_id == rule_id)).all()
        action_events = db.scalars(
            select(NotificationOutbox).where(
                NotificationOutbox.dedupe_key == f"automation:{rule_id}:{event_id}"
            )
        ).all()
        action_notifications = db.scalars(
            select(Notification).where(
                Notification.outbox_id == action_event_id,
                Notification.recipient_id == recipient_id,
            )
        ).all()
        final_run = db.get(AutomationRun, runs[0].id)
    assert first.delivered == 1
    assert second.claimed == 2
    assert len(runs) == 1
    assert len(action_events) == 1
    assert len(action_notifications) == 1
    assert final_run is not None and final_run.status == "succeeded"


def test_conditions_and_inactive_rules_record_safe_outcomes(client: TestClient) -> None:
    matching_rule = create_rule(conditions={"status": "blocked"})
    inactive_rule = create_rule(is_active=False)
    event_id, _, _ = create_task_event()

    NotificationOutboxWorker(TestingSessionLocal).run_once()

    with TestingSessionLocal() as db:
        mismatch = db.scalar(
            select(AutomationRun).where(
                AutomationRun.rule_id == matching_rule,
                AutomationRun.source_event_id == event_id,
            )
        )
        inactive = db.scalar(select(AutomationRun).where(AutomationRun.rule_id == inactive_rule))
        action = db.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.dedupe_key == f"automation:{matching_rule}:{event_id}"
            )
        )
    assert mismatch is not None and mismatch.status == "condition_not_met"
    assert inactive is None
    assert action is None


def test_status_change_trigger_matches_registered_status_condition(client: TestClient) -> None:
    rule_id = create_rule(
        trigger_type="task.status_changed",
        conditions={"status": "blocked"},
    )
    event_id, _, _ = create_task_event(
        event_type="task.status_changed",
        task_status="blocked",
    )

    NotificationOutboxWorker(TestingSessionLocal).run_once()

    with TestingSessionLocal() as db:
        run = db.scalar(
            select(AutomationRun).where(
                AutomationRun.rule_id == rule_id,
                AutomationRun.source_event_id == event_id,
            )
        )
    assert run is not None
    assert run.status == "queued"
    assert run.action_event_id is not None


def test_dead_letter_can_be_retried_by_admin_and_history_is_visible(
    client: TestClient,
) -> None:
    admin_headers = sign_in(client)
    rule_id = create_rule()
    create_task_event()
    worker = NotificationOutboxWorker(TestingSessionLocal, max_attempts=1)
    original_deliver = worker._deliver

    def fail_automation_action(db, event):
        if event.event_type == "automation.notification":
            raise ValueError("Keine personenbezogenen Daten speichern")
        original_deliver(db, event)

    worker._deliver = fail_automation_action
    worker.run_once()
    worker.run_once()

    with TestingSessionLocal() as db:
        run = db.scalar(select(AutomationRun).where(AutomationRun.rule_id == rule_id))
        assert run is not None and run.action_event_id is not None
        run_id = run.id
        action_event_id = run.action_event_id
    history = client.get("/api/v1/automations/runs", headers=admin_headers)
    assert history.status_code == 200
    assert history.json()["items"][0]["status"] == "dead_letter"
    assert history.json()["items"][0]["last_error"] == "ValueError"
    assert history.json()["items"][0]["attempt_history"][-1]["event"] == "dead_lettered"

    retried = client.post(
        f"/api/v1/automations/runs/{run_id}/retry",
        headers=admin_headers,
    )
    assert retried.status_code == 202
    with TestingSessionLocal() as db:
        action_event = db.get(NotificationOutbox, action_event_id)
        run = db.get(AutomationRun, run_id)
        assert action_event is not None and action_event.failure_count == 0
        assert action_event.manual_retry_count == 1
        assert run is not None and run.manual_retry_count == 1 and run.status == "queued"

    worker._deliver = original_deliver
    worker.run_once()
    with TestingSessionLocal() as db:
        run = db.get(AutomationRun, run_id)
    assert run is not None and run.status == "succeeded"
    assert (
        client.post(
            f"/api/v1/automations/runs/{run_id}/retry",
            headers=admin_headers,
        ).status_code
        == 409
    )


def test_dead_letter_retry_limit_is_enforced(client: TestClient) -> None:
    admin_headers = sign_in(client)
    event_id, _, _ = create_task_event()
    with TestingSessionLocal() as db:
        event = db.get(NotificationOutbox, event_id)
        assert event is not None
        event.status = "dead_letter"
        event.failure_count = 1
        event.last_error = "ValueError"
        db.commit()
    worker = NotificationOutboxWorker(TestingSessionLocal, max_attempts=1)
    worker._deliver = lambda _db, _event: (_ for _ in ()).throw(ValueError())

    for _ in range(3):
        response = client.post(
            f"/api/v1/automations/outbox-events/{event_id}/retry",
            headers=admin_headers,
        )
        assert response.status_code == 202
        worker.run_once()

    limited = client.post(
        f"/api/v1/automations/outbox-events/{event_id}/retry",
        headers=admin_headers,
    )
    assert limited.status_code == 409
    with TestingSessionLocal() as db:
        event = db.get(NotificationOutbox, event_id)
    assert event is not None
    assert event.status == "dead_letter"
    assert event.manual_retry_count == 3


@pytest.mark.skipif(test_engine.dialect.name != "postgresql", reason="PostgreSQL SKIP LOCKED nötig")
def test_parallel_workers_create_one_automation_run(client: TestClient) -> None:
    rule_id = create_rule()
    event_id, _, _ = create_task_event()
    worker = NotificationOutboxWorker(TestingSessionLocal)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: worker.run_once(), range(2)))

    with TestingSessionLocal() as db:
        runs = db.scalars(
            select(AutomationRun).where(
                AutomationRun.rule_id == rule_id,
                AutomationRun.source_event_id == event_id,
            )
        ).all()
        actions = db.scalars(
            select(NotificationOutbox).where(
                NotificationOutbox.dedupe_key == f"automation:{rule_id}:{event_id}"
            )
        ).all()
    assert sum(result.claimed for result in results) == 1
    assert len(runs) == 1
    assert len(actions) == 1


def test_owks_automation_event_is_minimal_scoped_and_idempotent(client: TestClient) -> None:
    admin_headers = sign_in(client)
    object_id = create_owks_object(client, admin_headers, "AUTO-OWKS-001")
    with TestingSessionLocal() as db:
        admin = db.scalar(select(User).where(User.username == "admin"))
        manager = db.scalar(select(User).where(User.username == "geschaeftsfuehrung"))
        obj = db.get(SecurityObject, UUID(object_id))
        assert admin is not None and manager is not None and obj is not None
        db.add(ObjectAssignment(object_id=obj.id, user_id=admin.id))
        db.commit()
        admin_id = admin.id
        manager_id = manager.id

    created_rule = client.post(
        "/api/v1/automations/rules",
        headers=admin_headers,
        json={
            "name": "OWKS-Ereignis sicher melden",
            "trigger_type": "owks.deviation_reported",
            "conditions": {},
        },
    )
    assert created_rule.status_code == 201, created_rule.text
    rule_id = created_rule.json()["id"]
    assert (
        client.patch(
            f"/api/v1/automations/rules/{rule_id}",
            headers=admin_headers,
            json={"is_active": True},
        ).status_code
        == 200
    )

    client_event_id = str(uuid4())
    event = create_deviation_event(
        client,
        admin_headers,
        object_id,
        client_event_id=client_event_id,
    )
    with TestingSessionLocal() as db:
        source = db.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.dedupe_key == f"owks:owks.deviation_reported:{event['id']}"
            )
        )
        assert source is not None
        assert source.payload == {
            "schema_version": 1,
            "owks_event_id": event["id"],
            "object_id": object_id,
            "recipient_ids": [str(admin_id)],
        }

    duplicate = create_deviation_event(
        client,
        admin_headers,
        object_id,
        client_event_id=client_event_id,
    )
    assert duplicate["id"] == event["id"]

    worker = NotificationOutboxWorker(TestingSessionLocal)
    assert worker.run_once().delivered == 1
    assert worker.run_once().delivered == 1
    with TestingSessionLocal() as db:
        source = db.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.dedupe_key == f"owks:owks.deviation_reported:{event['id']}"
            )
        )
        assert source is not None
        source.status = "pending"
        db.commit()
    assert worker.run_once().delivered == 1

    with TestingSessionLocal() as db:
        notifications = db.scalars(
            select(Notification).where(Notification.object_id == UUID(object_id))
        ).all()
        run = db.scalar(
            select(AutomationRun).where(
                AutomationRun.rule_id == UUID(rule_id),
                AutomationRun.source_event_id == source.id,
            )
        )
        source_events = db.scalars(
            select(NotificationOutbox).where(
                NotificationOutbox.dedupe_key == f"owks:owks.deviation_reported:{event['id']}"
            )
        ).all()
    assert len(source_events) == 1
    assert len(notifications) == 1
    assert notifications[0].recipient_id == admin_id
    assert notifications[0].task_id is None
    assert "VERTRAULICHER HERGANG" not in notifications[0].body
    assert "Vertraulicher Ereignistitel" not in notifications[0].body
    assert run is not None and run.status == "succeeded"

    outsider_headers = sign_in(
        client,
        "geschaeftsfuehrung",
        "management-test-passwort-2026",
    )
    outsider_inbox = client.get("/api/v1/notifications", headers=outsider_headers)
    assert outsider_inbox.status_code == 200
    assert outsider_inbox.json()["items"] == []
    own_inbox = client.get("/api/v1/notifications", headers=admin_headers)
    assert own_inbox.status_code == 200
    assert own_inbox.json()["items"][0]["object_id"] == object_id
    assert own_inbox.json()["items"][0]["task_id"] is None
    assert manager_id != admin_id


def test_owks_outbox_rejects_invalid_payload_and_unassigned_recipients(
    client: TestClient,
) -> None:
    headers = sign_in(client)
    object_id = create_owks_object(client, headers, "AUTO-OWKS-002")
    event = create_deviation_event(client, headers, object_id)
    with TestingSessionLocal() as db:
        source = db.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.aggregate_id == UUID(event["id"]),
                NotificationOutbox.event_type == "owks.deviation_reported",
            )
        )
        manager = db.scalar(select(User).where(User.username == "geschaeftsfuehrung"))
        assert source is not None and manager is not None
        source.payload = {
            **source.payload,
            "schema_version": 2,
            "unexpected": "must be rejected",
            "recipient_ids": [str(manager.id)],
        }
        source_id = source.id
        db.commit()

    result = NotificationOutboxWorker(TestingSessionLocal).run_once()
    assert result.dead_lettered == 1
    with TestingSessionLocal() as db:
        source = db.get(NotificationOutbox, source_id)
        assert source is not None
        assert source.status == "dead_letter"
        assert source.last_error == "invalid_payload"
        assert db.scalar(select(Notification).where(Notification.outbox_id == source_id)) is None


def test_owks_empty_and_revoked_recipients_fail_closed(client: TestClient) -> None:
    headers = sign_in(client)
    empty_object_id = create_owks_object(client, headers, "AUTO-OWKS-003")
    empty_event = create_deviation_event(client, headers, empty_object_id)
    empty_rule_id = create_rule(trigger_type="owks.deviation_reported")
    worker = NotificationOutboxWorker(TestingSessionLocal)
    worker.run_once()
    with TestingSessionLocal() as db:
        empty_source = db.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.aggregate_id == UUID(empty_event["id"]),
                NotificationOutbox.event_type == "owks.deviation_reported",
            )
        )
        assert empty_source is not None
        empty_run = db.scalar(
            select(AutomationRun).where(
                AutomationRun.rule_id == empty_rule_id,
                AutomationRun.source_event_id == empty_source.id,
            )
        )
    assert empty_source.status == "completed"
    assert empty_run is not None and empty_run.status == "skipped_no_recipients"
    assert empty_run.action_event_id is None

    assigned_object_id = create_owks_object(client, headers, "AUTO-OWKS-004")
    with TestingSessionLocal() as db:
        admin = db.scalar(select(User).where(User.username == "admin"))
        obj = db.get(SecurityObject, UUID(assigned_object_id))
        assert admin is not None and obj is not None
        assignment = ObjectAssignment(object_id=obj.id, user_id=admin.id)
        db.add(assignment)
        db.commit()
        assignment_id = assignment.id
    revoked_event = create_deviation_event(client, headers, assigned_object_id)
    with TestingSessionLocal() as db:
        source = db.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.aggregate_id == UUID(revoked_event["id"]),
                NotificationOutbox.event_type == "owks.deviation_reported",
            )
        )
        assert source is not None
        revoked_source_id = source.id
        db.delete(db.get(ObjectAssignment, assignment_id))
        db.commit()

    revoked_result = worker.run_once()
    assert revoked_result.dead_lettered == 1
    with TestingSessionLocal() as db:
        source = db.get(NotificationOutbox, revoked_source_id)
        assert source is not None
        assert source.status == "dead_letter"
        assert source.last_error == "unauthorized_recipient"
        assert (
            db.scalar(select(Notification).where(Notification.outbox_id == revoked_source_id))
            is None
        )


def test_owks_automation_migration_follows_encrypted_document_storage() -> None:
    migration = import_module("migrations.versions.0034_owks_automation_events")
    assert migration.revision == "0034_owks_automation_events"
    assert migration.down_revision == "0033_encrypted_document_storage"
