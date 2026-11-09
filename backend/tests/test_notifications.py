import importlib
from uuid import UUID

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from conftest import ADMIN_PASSWORD, TestingSessionLocal, test_engine
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.identity_api import password_hasher
from app.models import (
    Notification,
    NotificationOutbox,
    ObjectAssignment,
    Permission,
    Role,
    Task,
    User,
)
from app.notification_worker import NotificationOutboxWorker


def sign_in(client: TestClient, username: str = "admin", password: str = ADMIN_PASSWORD):
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


def create_task_recipient() -> str:
    with TestingSessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "employee"))
        assert role is not None
        user = User(
            username="notification_recipient",
            email="notification-recipient@example.com",
            full_name="Test Benachrichtigungsempfang",
            password_hash=password_hasher.hash("notification-test-password"),
            roles=[role],
        )
        db.add(user)
        db.commit()
        return str(user.id)


def test_assignment_status_notifications_are_scoped_and_idempotent(client: TestClient) -> None:
    admin_headers = sign_in(client)
    recipient_id = create_task_recipient()
    manager_headers = sign_in(client, "geschaeftsfuehrung", "management-test-passwort-2026")

    created = client.post(
        "/api/v1/tasks",
        headers=admin_headers,
        json={"title": "Kontrollbericht prüfen", "assigned_to_id": recipient_id},
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]

    NotificationOutboxWorker(TestingSessionLocal).run_once()
    recipient_headers = sign_in(client, "notification_recipient", "notification-test-password")
    received = client.get("/api/v1/notifications", headers=recipient_headers)
    assert received.status_code == 200
    assert received.json()["total"] == 1
    assert received.json()["unread_count"] == 1
    assignment_notification_id = received.json()["items"][0]["id"]
    assert received.json()["items"][0]["event_type"] == "task.assigned"

    outsider_page = client.get("/api/v1/notifications", headers=manager_headers)
    assert outsider_page.status_code == 200
    assert outsider_page.json()["items"] == []
    assert (
        client.patch(
            f"/api/v1/notifications/{assignment_notification_id}/read",
            headers=manager_headers,
        ).status_code
        == 404
    )

    reassigned = client.patch(
        f"/api/v1/tasks/{task_id}",
        headers=manager_headers,
        json={"assigned_to_id": created.json()["created_by_id"]},
    )
    assert reassigned.status_code == 200, reassigned.text
    NotificationOutboxWorker(TestingSessionLocal).run_once()
    assert client.get("/api/v1/notifications", headers=recipient_headers).json()["items"] == []

    admin_page = client.get("/api/v1/notifications", headers=admin_headers)
    assert admin_page.status_code == 200
    assert admin_page.json()["unread_count"] == 1
    assert admin_page.json()["items"][0]["event_type"] == "task.assigned"
    assert admin_page.json()["items"][0]["task_id"] == task_id

    completed = client.patch(
        f"/api/v1/tasks/{task_id}",
        headers=manager_headers,
        json={"status": "completed", "completion_evidence": "Prüfung abgeschlossen."},
    )
    assert completed.status_code == 200, completed.text
    NotificationOutboxWorker(TestingSessionLocal).run_once()
    admin_page = client.get("/api/v1/notifications", headers=admin_headers)
    assert admin_page.json()["total"] == 2
    assert admin_page.json()["unread_count"] == 2
    page_two = client.get(
        "/api/v1/notifications?limit=1&offset=1",
        headers=admin_headers,
    )
    assert page_two.json()["total"] == 2
    assert page_two.json()["offset"] == 1
    assert len(page_two.json()["items"]) == 1
    status_notification = next(
        item for item in admin_page.json()["items"] if item["event_type"] == "task.status_changed"
    )

    unchanged = client.patch(
        f"/api/v1/tasks/{task_id}",
        headers=manager_headers,
        json={"status": "completed", "completion_evidence": "Prüfung abgeschlossen."},
    )
    assert unchanged.status_code == 422
    assert client.get("/api/v1/notifications", headers=admin_headers).json()["total"] == 2

    first_read = client.patch(
        f"/api/v1/notifications/{status_notification['id']}/read",
        headers=admin_headers,
    )
    second_read = client.patch(
        f"/api/v1/notifications/{status_notification['id']}/read",
        headers=admin_headers,
    )
    assert first_read.status_code == second_read.status_code == 200
    assert first_read.json()["read_at"] == second_read.json()["read_at"]
    assert (
        client.get("/api/v1/notifications?unread_only=true", headers=admin_headers).json()["total"]
        == 1
    )

    with TestingSessionLocal() as db:
        assert db.scalar(select(Task).where(Task.id == UUID(task_id))).status == "completed"
        assert db.scalar(select(func.count()).select_from(NotificationOutbox)) == 3
        assert db.scalar(select(func.count()).select_from(Notification)) == 3
        assert (
            db.scalar(
                select(NotificationOutbox).where(NotificationOutbox.event_type == "task.assigned")
            )
            is not None
        )
        assert (
            db.scalar(select(Notification).where(Notification.event_type == "task.status_changed"))
            is not None
        )


def test_notifications_require_permission_and_bound_pagination(client: TestClient) -> None:
    with TestingSessionLocal() as db:
        notification_permission = db.scalar(
            select(Permission).where(Permission.code == "notifications.read_own")
        )
        assert notification_permission is not None
        role = Role(
            code="notification_taskless_test",
            name="Benachrichtigung ohne Aufgabenrecht",
            description="Testrolle ohne Aufgabenleserecht",
            permissions=[notification_permission],
        )
        user = User(
            username="notification_taskless",
            email="notification-taskless@example.com",
            full_name="Test ohne Aufgabenleserecht",
            password_hash=password_hasher.hash("notification-test-password"),
            roles=[role],
        )
        db.add(user)
        db.commit()

    headers = sign_in(client, "notification_taskless", "notification-test-password")
    assert client.get("/api/v1/notifications", headers=headers).status_code == 403
    admin_headers = sign_in(client)
    assert client.get("/api/v1/notifications?limit=101", headers=admin_headers).status_code == 422
    assert client.get("/api/v1/notifications?offset=-1", headers=admin_headers).status_code == 422


def test_object_notification_requires_owks_permission_and_assignment(client: TestClient) -> None:
    admin_headers = sign_in(client)
    customer = client.post(
        "/api/v1/customers",
        headers=admin_headers,
        json={"company_name": "Testkunde Objektbenachrichtigung GmbH"},
    )
    assert customer.status_code == 201
    object_response = client.post(
        "/api/v1/objects",
        headers=admin_headers,
        json={
            "customer_id": customer.json()["id"],
            "name": "Objekt Benachrichtigung",
            "code": "NOTIF-OBJECT-001",
        },
    )
    assert object_response.status_code == 201
    object_id = UUID(object_response.json()["id"])

    with TestingSessionLocal() as db:
        notification_permission = db.scalar(
            select(Permission).where(Permission.code == "notifications.read_own")
        )
        task_permission = db.scalar(select(Permission).where(Permission.code == "tasks.read_own"))
        owks_permission = db.scalar(select(Permission).where(Permission.code == "owks.read"))
        assert notification_permission is not None and task_permission is not None
        assert owks_permission is not None
        role = Role(
            code="notification_task_scope_only",
            name="Benachrichtigung ohne OWKS-Leserecht",
            description="Testrolle ohne OWKS-Leserecht",
            permissions=[notification_permission, task_permission],
        )
        user = User(
            username="notification_task_scope_only",
            email="notification-task-scope-only@example.com",
            full_name="Test ohne OWKS-Leserecht",
            password_hash=password_hasher.hash("notification-test-password"),
            roles=[role],
        )
        unassigned_role = Role(
            code="notification_owks_unassigned",
            name="OWKS-Benachrichtigung ohne Objektzuweisung",
            description="Testrolle ohne Objektzuweisung",
            permissions=[notification_permission, owks_permission],
        )
        unassigned_user = User(
            username="notification_owks_unassigned",
            email="notification-owks-unassigned@example.com",
            full_name="Test ohne Objektzuweisung",
            password_hash=password_hasher.hash("notification-test-password"),
            roles=[unassigned_role],
        )
        db.add(user)
        db.add(unassigned_user)
        db.flush()
        db.add(ObjectAssignment(object_id=object_id, user_id=user.id))
        outbox = NotificationOutbox(
            dedupe_key="test:object-notification-scope",
            event_type="automation.notification",
            aggregate_type="object",
            aggregate_id=object_id,
            payload={},
            status="completed",
        )
        db.add(outbox)
        db.flush()
        db.add(
            Notification(
                outbox_id=outbox.id,
                recipient_id=user.id,
                task_id=None,
                object_id=object_id,
                event_type="automation.notification",
                title="Objektbezogene Nachricht",
                body="Allgemeine Meldung",
            )
        )
        db.add(
            Notification(
                outbox_id=outbox.id,
                recipient_id=unassigned_user.id,
                task_id=None,
                object_id=object_id,
                event_type="automation.notification",
                title="Nicht zugewiesene Objektmeldung",
                body="Allgemeine Meldung",
            )
        )
        db.commit()

    user_headers = sign_in(
        client,
        "notification_task_scope_only",
        "notification-test-password",
    )
    response = client.get("/api/v1/notifications", headers=user_headers)
    assert response.status_code == 200
    assert response.json()["items"] == []

    unassigned_headers = sign_in(
        client,
        "notification_owks_unassigned",
        "notification-test-password",
    )
    unassigned_response = client.get("/api/v1/notifications", headers=unassigned_headers)
    assert unassigned_response.status_code == 200
    assert unassigned_response.json()["items"] == []


def test_notification_migration_is_linear_after_tasks() -> None:
    migration = importlib.import_module("migrations.versions.0020_notifications")
    assert migration.revision == "0020_notifications"
    assert migration.down_revision == "0019_tasks"


@pytest.mark.skipif(
    test_engine.dialect.name != "postgresql",
    reason="PostgreSQL-Migrationspfad wird in PostgreSQL geprüft",
)
def test_postgresql_database_has_the_notification_migration_applied(client: TestClient) -> None:
    from sqlalchemy import inspect

    with test_engine.connect() as connection:
        inspector = inspect(connection)
        assert {"notification_outbox", "notifications"} <= set(inspector.get_table_names())


@pytest.mark.skipif(
    test_engine.dialect.name != "postgresql",
    reason="Benachrichtigungs-Migrationsschutz wird in PostgreSQL geprüft",
)
def test_notification_downgrade_refuses_to_delete_records(client: TestClient) -> None:
    admin_headers = sign_in(client)
    recipient_id = create_task_recipient()
    created = client.post(
        "/api/v1/tasks",
        headers=admin_headers,
        json={"title": "Downgrade-Prüfung", "assigned_to_id": recipient_id},
    )
    assert created.status_code == 201, created.text

    migration = importlib.import_module("migrations.versions.0020_notifications")
    with test_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        with (
            Operations.context(context),
            pytest.raises(RuntimeError, match="Benachrichtigungs-Downgrade"),
        ):
            migration.downgrade()
        connection.rollback()

    with TestingSessionLocal() as db:
        assert db.scalar(select(NotificationOutbox.id)) is not None
