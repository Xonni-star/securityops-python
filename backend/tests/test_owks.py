import asyncio
import importlib
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from conftest import ADMIN_PASSWORD, TestingSessionLocal, test_engine
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from app import owks_scheduler
from app.config import get_settings
from app.identity_api import password_hasher
from app.malware_scanner import MalwareDetected
from app.models import (
    Employee,
    NotificationOutbox,
    ObjectAssignment,
    OWKSAttachment,
    OWKSEvent,
    OWKSRoute,
    Permission,
    Role,
    SecurityObject,
    User,
)
from app.owks_api import (
    MONITOR_ADVISORY_LOCK_KEY,
    as_utc,
    create_event,
    monitor_due_routes,
)


def sign_in(client: TestClient, username: str = "admin", password: str = ADMIN_PASSWORD) -> str:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return client.cookies.get("securityops_csrf", "")


def create_object(client: TestClient, headers: dict[str, str], code: str) -> str:
    customer = client.post(
        "/api/v1/customers",
        headers=headers,
        json={"company_name": f"Testkunde {code} Wachschutz GmbH"},
    )
    assert customer.status_code == 201
    response = client.post(
        "/api/v1/objects",
        headers=headers,
        json={"customer_id": customer.json()["id"], "name": f"Objekt {code}", "code": code},
    )
    assert response.status_code == 201
    return response.json()["id"]


def create_assigned_employee(object_id: str, username: str = "wachkraft") -> None:
    with TestingSessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "employee"))
        assert role is not None
        user = User(
            username=username,
            email=f"{username}@example.com",
            full_name="Test Wachkraft",
            password_hash=password_hasher.hash("wachkraft-test-passwort-2026"),
            roles=[role],
        )
        db.add(user)
        db.flush()
        employee = Employee(
            employee_number=f"TEST-{username}",
            user_id=user.id,
            full_name=user.full_name,
            employment_status="active",
            hired_on=date(2026, 1, 1),
        )
        db.add(employee)
        obj = db.get(SecurityObject, UUID(object_id))
        assert obj is not None
        db.add(ObjectAssignment(object_id=obj.id, user_id=user.id))
        db.commit()


def create_object_manager(object_id: str, username: str) -> None:
    with TestingSessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "object_manager"))
        manage_permission = db.scalar(select(Permission).where(Permission.code == "owks.manage"))
        read_permission = db.scalar(select(Permission).where(Permission.code == "owks.read"))
        obj = db.get(SecurityObject, UUID(object_id))
        assert (
            role is not None
            and manage_permission is not None
            and read_permission is not None
            and obj is not None
        )
        role.permissions = [*role.permissions, manage_permission, read_permission]
        user = User(
            username=username,
            email=f"{username}@example.com",
            full_name="Test Objektleitung",
            password_hash=password_hasher.hash("objektleitung-test-passwort-2026"),
            roles=[role],
        )
        db.add(user)
        db.flush()
        db.add(ObjectAssignment(object_id=obj.id, user_id=user.id))
        db.commit()


def test_object_scoping_scan_replay_route_monitor_and_timestamp(client: TestClient) -> None:
    admin_headers = {"X-CSRF-Token": sign_in(client)}
    object_id = create_object(client, admin_headers, "OWKS-001")
    other_object_id = create_object(client, admin_headers, "OWKS-002")
    create_assigned_employee(object_id)

    point_response = client.post(
        f"/api/v1/owks/objects/{object_id}/control-points",
        headers=admin_headers,
        json={"name": "Haupteingang", "identifier_type": "qr"},
    )
    assert point_response.status_code == 201
    point = point_response.json()
    credential = point["credential"]
    assert credential
    foreign_point = client.post(
        f"/api/v1/owks/objects/{other_object_id}/control-points",
        headers=admin_headers,
        json={"name": "Fremder Kontrollpunkt", "identifier_type": "nfc"},
    )
    assert foreign_point.status_code == 201
    listed_point = client.get(f"/api/v1/owks/objects/{object_id}/control-points")
    assert listed_point.status_code == 200
    assert "credential" not in listed_point.json()[0]

    route_response = client.post(
        f"/api/v1/owks/objects/{object_id}/routes",
        headers=admin_headers,
        json={
            "name": "Außenrunde",
            "interval_minutes": 1,
            "control_point_ids": [point["id"]],
        },
    )
    assert route_response.status_code == 201
    route_id = route_response.json()["id"]
    with TestingSessionLocal() as db:
        route = db.scalar(select(OWKSRoute))
        assert route is not None
        route.created_at = datetime.now(UTC) - timedelta(hours=2)
        db.commit()
    missed = client.post(f"/api/v1/owks/routes/{route_id}/monitor", headers=admin_headers)
    assert missed.status_code == 200
    assert len(missed.json()) == 1
    assert missed.json()[0]["event_type"] == "missed"
    with TestingSessionLocal() as db:
        missed_outbox = db.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.aggregate_id == UUID(missed.json()[0]["id"]),
                NotificationOutbox.event_type == "owks.missed_control",
            )
        )
    assert missed_outbox is not None
    assert missed_outbox.payload["schema_version"] == 1
    with TestingSessionLocal() as db:
        assigned_ids = sorted(
            str(user_id)
            for user_id in db.scalars(
                select(ObjectAssignment.user_id).where(
                    ObjectAssignment.object_id == UUID(object_id)
                )
            ).all()
        )
    assert missed_outbox.payload["recipient_ids"] == assigned_ids
    catch_up = client.post(f"/api/v1/owks/routes/{route_id}/monitor", headers=admin_headers)
    assert catch_up.status_code == 200
    assert len(catch_up.json()) == 1
    assert catch_up.json()[0]["id"] != missed.json()[0]["id"]

    user_headers = {"X-CSRF-Token": sign_in(client, "wachkraft", "wachkraft-test-passwort-2026")}
    visible_objects = client.get("/api/v1/owks/objects")
    assert visible_objects.status_code == 200
    assert [item["id"] for item in visible_objects.json()] == [object_id]
    assert client.get(f"/api/v1/owks/objects/{other_object_id}/events").status_code == 404
    assert (
        client.post(
            f"/api/v1/owks/objects/{other_object_id}/challenges",
            headers=user_headers,
        ).status_code
        == 404
    )

    challenge = client.post(
        f"/api/v1/owks/objects/{object_id}/challenges",
        headers=user_headers,
    )
    assert challenge.status_code == 200
    foreign_scan = client.post(
        "/api/v1/owks/scans",
        headers=user_headers,
        json={
            "challenge_id": challenge.json()["id"],
            "credential": foreign_point.json()["credential"],
            "client_event_id": str(uuid4()),
        },
    )
    assert foreign_scan.status_code == 409
    scan_id = str(uuid4())
    scan = client.post(
        "/api/v1/owks/scans",
        headers=user_headers,
        json={
            "challenge_id": challenge.json()["id"],
            "credential": credential,
            "client_event_id": scan_id,
            "route_id": route_id,
        },
    )
    assert scan.status_code == 201
    assert scan.json()["event_type"] == "control"
    assert scan.json()["presence_verified"] is False
    assert scan.json()["status"] == "open"
    assert "physische Anwesenheit ist nicht bestätigt" in scan.json()["description"]
    assert scan.json()["employee_id"]
    with TestingSessionLocal() as db:
        still_missed = monitor_due_routes(db, current_time=datetime.now(UTC))
        db.commit()
    assert any(
        event.route_id == UUID(route_id) and event.event_type == "missed" for event in still_missed
    )
    repeated_scan = client.post(
        "/api/v1/owks/scans",
        headers=user_headers,
        json={
            "challenge_id": challenge.json()["id"],
            "credential": credential,
            "client_event_id": scan_id,
            "route_id": route_id,
        },
    )
    assert repeated_scan.status_code == 201
    assert repeated_scan.json()["id"] == scan.json()["id"]
    conflicting_scan = client.post(
        "/api/v1/owks/scans",
        headers=user_headers,
        json={
            "challenge_id": challenge.json()["id"],
            "credential": foreign_point.json()["credential"],
            "client_event_id": scan_id,
            "route_id": route_id,
        },
    )
    assert conflicting_scan.status_code == 409
    replay = client.post(
        "/api/v1/owks/scans",
        headers=user_headers,
        json={
            "challenge_id": challenge.json()["id"],
            "credential": credential,
            "client_event_id": str(uuid4()),
            "route_id": route_id,
        },
    )
    assert replay.status_code == 409
    replay_events = client.get(f"/api/v1/owks/objects/{object_id}/events").json()
    assert any(event["event_type"] == "manipulation" for event in replay_events)


def test_offline_sync_conflicts_status_corrections_and_secure_attachments(
    client: TestClient,
) -> None:
    admin_headers = {"X-CSRF-Token": sign_in(client)}
    object_id = create_object(client, admin_headers, "OWKS-003")
    create_assigned_employee(object_id, "syncwache")
    employee_headers = {
        "X-CSRF-Token": sign_in(client, "syncwache", "wachkraft-test-passwort-2026")
    }
    offline_id = str(uuid4())
    timestamp = "2026-11-08T19:00:00Z"
    sync = client.post(
        "/api/v1/owks/events/sync",
        headers=employee_headers,
        json=[
            {
                "object_id": object_id,
                "event_type": "handover",
                "title": "Übergabe Nachtschicht",
                "description": "Schlüssel übergeben.",
                "severity": "info",
                "occurred_at": timestamp,
                "client_event_id": offline_id,
            },
            {
                "object_id": object_id,
                "event_type": "control",
                "title": "Offline-Rundgang",
                "description": "Vor Ort notiert.",
                "severity": "info",
                "occurred_at": timestamp,
                "client_event_id": str(uuid4()),
            },
        ],
    )
    assert sync.status_code == 200
    assert [item["status"] for item in sync.json()] == ["synced", "conflict"]
    synced_event_id = sync.json()[0]["event"]["id"]
    conflict_event = sync.json()[1]["event"]
    assert conflict_event["sync_status"] == "conflict"
    with TestingSessionLocal() as db:
        synced_outbox = db.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.aggregate_id == UUID(synced_event_id),
                NotificationOutbox.event_type == "owks.offline_event_synced",
            )
        )
        conflict_sync_outbox = db.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.aggregate_id == UUID(conflict_event["id"]),
                NotificationOutbox.event_type == "owks.offline_event_synced",
            )
        )
        conflict_deviation_outbox = db.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.aggregate_id == UUID(conflict_event["id"]),
                NotificationOutbox.event_type == "owks.deviation_reported",
            )
        )
    assert synced_outbox is not None
    assert synced_outbox.payload["schema_version"] == 1
    assert conflict_sync_outbox is None
    assert conflict_deviation_outbox is None
    repeated = client.post(
        "/api/v1/owks/events/sync",
        headers=employee_headers,
        json=[
            {
                "object_id": object_id,
                "event_type": "handover",
                "title": "Übergabe Nachtschicht",
                "description": "Schlüssel übergeben.",
                "severity": "info",
                "occurred_at": timestamp,
                "client_event_id": offline_id,
            }
        ],
    )
    assert repeated.json()[0]["status"] == "duplicate"
    changed_replay = client.post(
        "/api/v1/owks/events/sync",
        headers=employee_headers,
        json=[
            {
                "object_id": object_id,
                "event_type": "handover",
                "title": "Manipulierter Wiederholungsversuch",
                "description": "",
                "severity": "info",
                "occurred_at": timestamp,
                "client_event_id": offline_id,
            }
        ],
    )
    assert changed_replay.json()[0]["status"] == "conflict"

    critical = client.post(
        "/api/v1/owks/events",
        headers=employee_headers,
        json={
            "object_id": object_id,
            "event_type": "deviation",
            "title": "Kritische Abweichung",
            "description": "Ursprünglicher Eintrag",
            "severity": "critical",
            "client_event_id": str(uuid4()),
        },
    )
    assert critical.status_code == 201
    critical_id = critical.json()["id"]
    admin_headers = {"X-CSRF-Token": sign_in(client)}
    status_update = client.post(
        f"/api/v1/owks/events/{critical_id}/status",
        headers=admin_headers,
        json={"status": "in_progress", "note": "In Prüfung"},
    )
    assert status_update.status_code == 200
    status_update = client.post(
        f"/api/v1/owks/events/{critical_id}/status",
        headers=admin_headers,
        json={"status": "resolved", "note": "Geprüft"},
    )
    assert status_update.status_code == 200
    correction = client.post(
        f"/api/v1/owks/events/{critical_id}/corrections",
        headers=admin_headers,
        json={"reason": "Ergänzung nach Prüfung", "client_event_id": str(uuid4())},
    )
    assert correction.status_code == 201
    assert correction.json()["corrects_event_id"] == critical_id
    original = client.get(f"/api/v1/owks/objects/{object_id}/events").json()
    original_event = next(item for item in original if item["id"] == critical_id)
    assert original_event["description"] == "Ursprünglicher Eintrag"
    assert original_event["severity"] == "critical"
    assert original_event["status"] == "resolved"

    valid_pdf = b"%PDF-1.4\nTestdokument\n%%EOF"
    uploaded = client.post(
        f"/api/v1/owks/events/{critical_id}/attachments",
        headers=admin_headers,
        files={"document": ("../../bericht.pdf", valid_pdf, "application/pdf")},
    )
    assert uploaded.status_code == 201
    assert uploaded.json()["file_name"] == "bericht.pdf"
    attachment_id = uploaded.json()["id"]
    with TestingSessionLocal() as db:
        attachment = db.get(OWKSAttachment, UUID(attachment_id))
        assert attachment is not None
        assert attachment.storage_key is not None and attachment.content is None
        encoded_file = (get_settings().document_storage_path / attachment.storage_key).read_bytes()
        assert encoded_file.startswith(b"SECOPS-DOC\x00")
        assert valid_pdf not in encoded_file
    downloaded = client.get(
        f"/api/v1/owks/events/{critical_id}/attachments/{attachment_id}",
        params={"download": "true"},
    )
    assert downloaded.status_code == 200
    assert downloaded.content == valid_pdf
    assert downloaded.headers["cache-control"] == "private, no-store"
    assert "sandbox" in downloaded.headers["content-security-policy"]
    invalid = client.post(
        f"/api/v1/owks/events/{critical_id}/attachments",
        headers=admin_headers,
        files={"document": ("fake.pdf", b"not a PDF", "application/pdf")},
    )
    assert invalid.status_code == 415
    oversized = client.post(
        f"/api/v1/owks/events/{critical_id}/attachments",
        headers=admin_headers,
        files={
            "document": (
                "zu-gross.pdf",
                b"%PDF-1.4\n" + b"x" * (10 * 1024 * 1024),
                "application/pdf",
            )
        },
    )
    assert oversized.status_code == 413


def test_owks_permission_and_foreign_object_attachment_are_denied(client: TestClient) -> None:
    admin_headers = {"X-CSRF-Token": sign_in(client)}
    object_id = create_object(client, admin_headers, "OWKS-004")
    other_object_id = create_object(client, admin_headers, "OWKS-005")
    create_assigned_employee(object_id, "isolatedwache")
    create_assigned_employee(other_object_id, "fremdewache")
    event = client.post(
        "/api/v1/owks/events",
        headers={"X-CSRF-Token": sign_in(client, "isolatedwache", "wachkraft-test-passwort-2026")},
        json={
            "object_id": object_id,
            "event_type": "entry",
            "title": "Wachbuchzugriff",
            "description": "",
            "severity": "info",
            "client_event_id": str(uuid4()),
        },
    )
    assert event.status_code == 201
    assert client.get(f"/api/v1/owks/objects/{object_id}/events").status_code == 200
    assert client.get("/api/v1/owks/objects").status_code == 200
    admin_headers = {"X-CSRF-Token": sign_in(client)}
    uploaded = client.post(
        f"/api/v1/owks/events/{event.json()['id']}/attachments",
        headers=admin_headers,
        files={"document": ("bericht.pdf", b"%PDF-1.4\nprivat\n", "application/pdf")},
    )
    assert uploaded.status_code == 201
    foreign_headers = {
        "X-CSRF-Token": sign_in(client, "fremdewache", "wachkraft-test-passwort-2026")
    }
    foreign_download = client.get(
        f"/api/v1/owks/events/{event.json()['id']}/attachments/{uploaded.json()['id']}"
    )
    assert foreign_download.status_code == 404
    assert client.get(f"/api/v1/owks/events/{event.json()['id']}/attachments").status_code == 404
    assert (
        client.post(
            f"/api/v1/owks/events/{event.json()['id']}/attachments",
            headers=foreign_headers,
            files={"document": ("bericht.pdf", b"%PDF-1.4\nprivat\n", "application/pdf")},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/owks/objects/{object_id}/challenges",
            headers=foreign_headers,
        ).status_code
        == 404
    )

    create_object_manager(object_id, "leitung-ohne-owks")
    manager_headers = {
        "X-CSRF-Token": sign_in(client, "leitung-ohne-owks", "objektleitung-test-passwort-2026")
    }
    assert client.get(f"/api/v1/owks/objects/{object_id}/events").status_code == 200
    managed_event = client.post(
        "/api/v1/owks/events",
        headers=manager_headers,
        json={
            "object_id": object_id,
            "event_type": "entry",
            "title": "Eintrag durch Objektleitung",
            "description": "",
            "severity": "info",
            "client_event_id": str(uuid4()),
        },
    )
    assert managed_event.status_code == 201


def test_owks_attachment_is_not_created_when_scanner_detects_malware(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin_headers = {"X-CSRF-Token": sign_in(client)}
    object_id = create_object(client, admin_headers, "OWKS-SCAN")
    event = client.post(
        "/api/v1/owks/events",
        headers=admin_headers,
        json={
            "object_id": object_id,
            "event_type": "entry",
            "title": "Scanprüfung",
            "description": "",
            "severity": "info",
            "client_event_id": str(uuid4()),
        },
    )
    assert event.status_code == 201

    def infected(_content: bytes) -> None:
        raise MalwareDetected

    monkeypatch.setattr("app.upload_scanning.scan_upload", infected)
    rejected = client.post(
        f"/api/v1/owks/events/{event.json()['id']}/attachments",
        headers=admin_headers,
        files={"document": ("bericht.pdf", b"%PDF-1.4\nprivate", "application/pdf")},
    )
    assert rejected.status_code == 422
    with TestingSessionLocal() as db:
        assert db.scalar(select(OWKSAttachment)) is None


def test_missed_monitor_is_idempotent_and_uses_elapsed_utc_intervals(client: TestClient) -> None:
    headers = {"X-CSRF-Token": sign_in(client)}
    object_id = create_object(client, headers, "OWKS-DST-001")
    point = client.post(
        f"/api/v1/owks/objects/{object_id}/control-points",
        headers=headers,
        json={"name": "Eingang", "identifier_type": "qr"},
    ).json()
    route = client.post(
        f"/api/v1/owks/objects/{object_id}/routes",
        headers=headers,
        json={
            "name": "DST-Prüfroute",
            "interval_minutes": 60,
            "control_point_ids": [point["id"]],
        },
    ).json()
    created_at = datetime(2026, 3, 29, 0, 30, tzinfo=UTC)
    due_at = datetime(2026, 3, 29, 1, 30, tzinfo=UTC)
    with TestingSessionLocal() as db:
        stored_route = db.get(OWKSRoute, UUID(route["id"]))
        assert stored_route is not None
        stored_route.created_at = created_at
        db.commit()
        generated = monitor_due_routes(db, current_time=due_at)
        db.commit()
        assert len(generated) == 1
        assert as_utc(generated[0].occurred_at) == due_at
        assert generated[0].client_event_id is not None
        client_event_id = generated[0].client_event_id

    local_due = due_at.astimezone(ZoneInfo("Europe/Berlin"))
    assert local_due.hour == 3
    with TestingSessionLocal() as db:
        assert monitor_due_routes(db, current_time=due_at) == []
        duplicate = OWKSEvent(
            object_id=UUID(object_id),
            route_id=UUID(route["id"]),
            control_point_id=UUID(point["id"]),
            event_type="missed",
            severity="warning",
            title="Doppeltes Versäumnis",
            description="",
            occurred_at=due_at,
            client_event_id=client_event_id,
            actor_id=None,
        )
        db.add(duplicate)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


@pytest.mark.skipif(
    test_engine.dialect.name != "postgresql",
    reason="Der laufende Hintergrundzyklus wird in PostgreSQL geprüft",
)
def test_postgresql_scheduler_cycle_persists_system_monitor_event(client: TestClient) -> None:
    if owks_scheduler.engine.url.database != test_engine.url.database:
        pytest.skip("Anwendungs- und Testdatenbank sind nicht identisch")
    headers = {"X-CSRF-Token": sign_in(client)}
    object_id = create_object(client, headers, "OWKS-SCHEDULER-001")
    point = client.post(
        f"/api/v1/owks/objects/{object_id}/control-points",
        headers=headers,
        json={"name": "Seiteneingang", "identifier_type": "nfc"},
    ).json()
    route = client.post(
        f"/api/v1/owks/objects/{object_id}/routes",
        headers=headers,
        json={
            "name": "Hintergrundprüfung",
            "interval_minutes": 1,
            "control_point_ids": [point["id"]],
        },
    ).json()
    with TestingSessionLocal() as db:
        stored_route = db.get(OWKSRoute, UUID(route["id"]))
        assert stored_route is not None
        stored_route.created_at = datetime.now(UTC) - timedelta(hours=2)
        db.commit()

    assert owks_scheduler.run_monitoring_cycle() == 1
    with TestingSessionLocal() as db:
        generated = db.scalar(
            select(OWKSEvent).where(
                OWKSEvent.route_id == UUID(route["id"]),
                OWKSEvent.event_type == "missed",
            )
        )
        assert generated is not None
        assert generated.actor_id is None
        assert generated.control_point_id == UUID(point["id"])


@pytest.mark.skipif(
    test_engine.dialect.name != "postgresql",
    reason="Advisory Locks werden gegen PostgreSQL geprüft",
)
def test_missed_monitor_lock_serializes_database_processes() -> None:
    first = TestingSessionLocal()
    second = TestingSessionLocal()
    try:
        assert (
            first.scalar(
                text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
                {"lock_key": MONITOR_ADVISORY_LOCK_KEY},
            )
            is True
        )
        assert (
            second.scalar(
                text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
                {"lock_key": MONITOR_ADVISORY_LOCK_KEY},
            )
            is False
        )
        first.rollback()
        assert (
            second.scalar(
                text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
                {"lock_key": MONITOR_ADVISORY_LOCK_KEY},
            )
            is True
        )
    finally:
        first.close()
        second.rollback()
        second.close()


def test_monitoring_scheduler_retries_each_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    class PostgresDialect:
        name = "postgresql"

    class PostgresEngine:
        dialect = PostgresDialect()

    monkeypatch.setattr(owks_scheduler, "engine", PostgresEngine())
    stop = asyncio.Event()
    calls = 0

    def run_cycle() -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporärer Testfehler")
        stop.set()
        return 0

    asyncio.run(
        owks_scheduler.run_monitoring_scheduler(
            stop,
            run_cycle=run_cycle,
            interval_seconds=0.001,
        )
    )
    assert calls == 2


def test_owks_event_and_outbox_share_the_transaction(client: TestClient) -> None:
    headers = {"X-CSRF-Token": sign_in(client)}
    object_id = create_object(client, headers, "OWKS-TX-001")
    with TestingSessionLocal() as db:
        event = create_event(
            db,
            object_id=UUID(object_id),
            employee_id=None,
            actor_id=None,
            event_type="deviation",
            title="Transaktionstest",
            description="Nicht persistieren",
            severity="warning",
            occurred_at=datetime.now(UTC),
        )
        event_id = event.id
        db.flush()
        outbox = db.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.aggregate_id == event_id,
                NotificationOutbox.event_type == "owks.deviation_reported",
            )
        )
        assert outbox is not None
        db.rollback()

    with TestingSessionLocal() as db:
        assert db.get(OWKSEvent, event_id) is None
        assert (
            db.scalar(
                select(NotificationOutbox).where(
                    NotificationOutbox.aggregate_id == event_id,
                    NotificationOutbox.event_type == "owks.deviation_reported",
                )
            )
            is None
        )


@pytest.mark.skipif(
    test_engine.dialect.name != "postgresql",
    reason="Append-only-Trigger wird in PostgreSQL geprüft",
)
def test_owks_events_are_database_append_only(client: TestClient) -> None:
    admin_headers = {"X-CSRF-Token": sign_in(client)}
    object_id = create_object(client, admin_headers, "OWKS-006")
    create_assigned_employee(object_id, "triggerwache")
    employee_headers = {
        "X-CSRF-Token": sign_in(client, "triggerwache", "wachkraft-test-passwort-2026")
    }
    created = client.post(
        "/api/v1/owks/events",
        headers=employee_headers,
        json={
            "object_id": object_id,
            "event_type": "entry",
            "title": "Unveränderlicher Eintrag",
            "description": "Original",
            "severity": "critical",
            "client_event_id": str(uuid4()),
        },
    )
    assert created.status_code == 201
    with TestingSessionLocal() as db:
        with pytest.raises(DBAPIError):
            db.execute(
                update(OWKSEvent)
                .where(OWKSEvent.id == created.json()["id"])
                .values(description="unzulässig")
            )
        db.rollback()


@pytest.mark.skipif(
    test_engine.dialect.name != "postgresql",
    reason="OWKS-Migrationsschutz wird in PostgreSQL geprüft",
)
def test_owks_downgrade_refuses_to_delete_operational_data(client: TestClient) -> None:
    admin_headers = {"X-CSRF-Token": sign_in(client)}
    object_id = create_object(client, admin_headers, "OWKS-DOWNGRADE")
    created = client.post(
        f"/api/v1/owks/objects/{object_id}/control-points",
        headers=admin_headers,
        json={"name": "Downgrade-Prüfpunkt", "identifier_type": "qr"},
    )
    assert created.status_code == 201

    migration = importlib.import_module("migrations.versions.0014_owks_wachbuch")
    with test_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context), pytest.raises(DBAPIError, match="OWKS-Downgrade"):
            migration.downgrade()
        connection.rollback()

    retained = client.get(f"/api/v1/owks/objects/{object_id}/control-points")
    assert retained.status_code == 200
    assert retained.json()[0]["id"] == created.json()["id"]
