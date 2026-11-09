import importlib
from uuid import UUID, uuid4

import pytest
from conftest import ADMIN_PASSWORD, TestingSessionLocal, test_engine
from fastapi.testclient import TestClient
from sqlalchemy import delete, inspect, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.config import get_settings
from app.identity_api import password_hasher
from app.models import (
    Incident,
    IncidentAttachment,
    IncidentHistory,
    ObjectAssignment,
    OWKSEvent,
    OWKSEventStatus,
    Permission,
    Role,
    SecurityObject,
    User,
)


def sign_in(client: TestClient, username: str = "admin", password: str = ADMIN_PASSWORD):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"X-CSRF-Token": client.cookies.get("securityops_csrf", "")}


def restore_admin_session(
    client: TestClient, session_cookie: str, csrf_cookie: str
) -> dict[str, str]:
    client.cookies.clear()
    client.cookies.set("securityops_session", session_cookie, domain="testserver.local", path="/")
    client.cookies.set("securityops_csrf", csrf_cookie, domain="testserver.local", path="/")
    return {"X-CSRF-Token": csrf_cookie}


def create_object(client: TestClient, headers: dict[str, str], code: str) -> str:
    customer = client.post(
        "/api/v1/customers", headers=headers, json={"company_name": f"Testkunde {code}"}
    )
    assert customer.status_code == 201, customer.text
    created = client.post(
        "/api/v1/objects",
        headers=headers,
        json={"customer_id": customer.json()["id"], "name": f"Testobjekt {code}", "code": code},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def create_user_with_object(username: str, role_code: str, object_id: str) -> str:
    with TestingSessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == role_code))
        obj = db.get(SecurityObject, UUID(object_id))
        assert role is not None and obj is not None
        user = User(
            username=username,
            email=f"{username}@example.com",
            full_name="Testkonto",
            password_hash=password_hasher.hash("vorfall-test-passwort-2026"),
            roles=[role],
        )
        db.add(user)
        db.flush()
        db.add(ObjectAssignment(object_id=obj.id, user_id=user.id))
        db.commit()
        return str(user.id)


def create_user_with_permissions(
    username: str, object_id: str, permission_codes: tuple[str, ...]
) -> str:
    with TestingSessionLocal() as db:
        permissions = db.scalars(
            select(Permission).where(Permission.code.in_(permission_codes))
        ).all()
        assert len(permissions) == len(permission_codes)
        obj = db.get(SecurityObject, UUID(object_id))
        assert obj is not None
        role = Role(
            code=f"{username}_role",
            name="Testrolle",
            description="Synthetische Testrolle",
            permissions=permissions,
        )
        user = User(
            username=username,
            email=f"{username}@example.com",
            full_name="Testkonto",
            password_hash=password_hasher.hash("vorfall-test-passwort-2026"),
            roles=[role],
        )
        db.add(user)
        db.flush()
        db.add(ObjectAssignment(object_id=obj.id, user_id=user.id))
        db.commit()
        return str(user.id)


def create_incident(client: TestClient, headers: dict[str, str], object_id: str, title: str):
    return client.post(
        "/api/v1/incidents",
        headers=headers,
        json={
            "title": title,
            "report": "Synthetische Kurzmeldung ohne Personendaten.",
            "incident_type": "complaint",
            "severity": "medium",
            "object_id": object_id,
        },
    )


def create_owks_event(
    client: TestClient, headers: dict[str, str], object_id: str, title: str
) -> dict[str, str]:
    response = client.post(
        "/api/v1/owks/events",
        headers=headers,
        json={
            "object_id": object_id,
            "event_type": "deviation",
            "title": title,
            "description": "Synthetische OWKS-Beschreibung mit vertraulichem Inhalt.",
            "severity": "critical",
            "client_event_id": str(uuid4()),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_incident_scoping_sensitive_data_measures_and_closure(client: TestClient) -> None:
    admin_headers = sign_in(client)
    admin_session_cookie = client.cookies.get("securityops_session")
    admin_csrf_cookie = client.cookies.get("securityops_csrf")
    object_a = create_object(client, admin_headers, "INC-TEST-A")
    object_b = create_object(client, admin_headers, "INC-TEST-B")
    employee_id = create_user_with_object("incident_employee", "employee", object_a)
    employee_headers = sign_in(client, "incident_employee", "vorfall-test-passwort-2026")

    created = create_incident(client, employee_headers, object_a, "Testbeschwerde")
    assert created.status_code == 201, created.text
    incident_id = created.json()["id"]
    assert created.json()["status"] == "reported"

    detail = client.get(f"/api/v1/incidents/{incident_id}", headers=employee_headers)
    assert detail.status_code == 200
    assert detail.json()["sensitive_details"] is None
    assert detail.json()["people"] == []
    assert detail.json()["attachments"] == []
    assert client.get("/api/v1/incidents", headers=employee_headers).json()["total"] == 1

    admin_headers = restore_admin_session(client, admin_session_cookie, admin_csrf_cookie)
    foreign = create_incident(client, admin_headers, object_b, "Fremder Testvorgang")
    assert foreign.status_code == 201, foreign.text
    foreign_id = foreign.json()["id"]
    employee_headers = sign_in(client, "incident_employee", "vorfall-test-passwort-2026")
    create_user_with_object("incident_manager", "object_manager", object_a)
    manager_headers = sign_in(client, "incident_manager", "vorfall-test-passwort-2026")
    assert (
        client.get(f"/api/v1/incidents/{foreign_id}", headers=employee_headers).status_code == 404
    )
    assert (
        client.patch(
            f"/api/v1/incidents/{foreign_id}",
            headers=manager_headers,
            json={"title": "Unberechtigte Änderung"},
        ).status_code
        == 404
    )
    assert create_incident(client, employee_headers, object_b, "Fremdes Objekt").status_code == 403
    assert (
        client.patch(
            f"/api/v1/incidents/{incident_id}/sensitive",
            headers=employee_headers,
            json={"narrative": "Synthetische vertrauliche Angabe"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/incidents/{incident_id}/people",
            headers=employee_headers,
            json={"name": "Testperson", "role": "witness"},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/v1/incidents/{incident_id}/sensitive",
            headers=manager_headers,
            json={"narrative": "Nicht erlaubte Änderung"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/incidents/{incident_id}/attachments",
            headers=manager_headers,
            files={"file": ("test.pdf", b"%PDF-test", "application/pdf")},
        ).status_code
        == 403
    )
    assert employee_id

    admin_headers = restore_admin_session(client, admin_session_cookie, admin_csrf_cookie)
    admin_detail = client.get(f"/api/v1/incidents/{incident_id}", headers=admin_headers)
    assert admin_detail.status_code == 200
    sensitive = client.patch(
        f"/api/v1/incidents/{incident_id}/sensitive",
        headers=admin_headers,
        json={
            "narrative": "Nur synthetische sensible Testangabe",
            "closure_report": "Synthetischer Abschlussbericht",
        },
    )
    assert sensitive.status_code == 200, sensitive.text
    person = client.post(
        f"/api/v1/incidents/{incident_id}/people",
        headers=admin_headers,
        json={"name": "Synthetische Testperson", "role": "witness", "notes": "Testnotiz"},
    )
    assert person.status_code == 201, person.text

    measure = client.post(
        f"/api/v1/incidents/{incident_id}/measures",
        headers=admin_headers,
        json={
            "title": "Testmaßnahme",
            "description": "Nur Testdaten",
            "assigned_to_id": employee_id,
        },
    )
    assert measure.status_code == 201, measure.text
    assert (
        client.post(
            f"/api/v1/incidents/{incident_id}/status",
            headers=admin_headers,
            json={"status": "closed"},
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"/api/v1/incidents/{incident_id}/measures/{measure.json()['id']}",
            headers=admin_headers,
            json={"status": "completed"},
        ).status_code
        == 200
    )

    assert (
        client.post(
            f"/api/v1/incidents/{incident_id}/status",
            headers=admin_headers,
            json={"status": "investigating"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/incidents/{incident_id}/status",
            headers=admin_headers,
            json={"status": "action_required"},
        ).status_code
        == 200
    )
    closed = client.post(
        f"/api/v1/incidents/{incident_id}/status",
        headers=admin_headers,
        json={"status": "closed"},
    )
    assert closed.status_code == 200, closed.text
    final_detail = client.get(f"/api/v1/incidents/{incident_id}", headers=admin_headers)
    assert final_detail.status_code == 200
    assert (
        final_detail.json()["sensitive_details"]["closure_report"]
        == "Synthetischer Abschlussbericht"
    )
    assert "Nur synthetische sensible Testangabe" not in str(final_detail.json()["history"])
    assert final_detail.json()["measures"][0]["status"] == "completed"
    history = final_detail.json()["history"]
    status_events = [entry for entry in history if entry["action"] in {"status_changed", "closed"}]
    assert [entry["changes"] for entry in status_events] == [
        {"from": "reported", "to": "investigating"},
        {"from": "investigating", "to": "action_required"},
        {"from": "action_required", "to": "closed"},
    ]
    measure_event = next(entry for entry in history if entry["action"] == "measure_updated")
    assert measure_event["changes"]["status_transition"] == {"from": "open", "to": "completed"}
    assert (
        client.patch(
            f"/api/v1/incidents/{incident_id}",
            headers=admin_headers,
            json={"title": "Nachträgliche Änderung"},
        ).status_code
        == 409
    )


def test_incident_attachment_uses_private_scanned_storage_and_checks_scope(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin_headers = sign_in(client)
    object_id = create_object(client, admin_headers, "INC-ATT-1")
    incident = create_incident(client, admin_headers, object_id, "Test mit Dateianhang")
    assert incident.status_code == 201, incident.text
    incident_id = incident.json()["id"]

    upload = client.post(
        f"/api/v1/incidents/{incident_id}/attachments",
        headers=admin_headers,
        files={"file": ("test.pdf", b"%PDF-synthetischer-test", "application/pdf")},
    )
    assert upload.status_code == 201, upload.text
    attachment_id = upload.json()["id"]
    with TestingSessionLocal() as db:
        attachment = db.get(IncidentAttachment, UUID(attachment_id))
        assert attachment is not None
        encoded_file = (get_settings().document_storage_path / attachment.storage_key).read_bytes()
        assert encoded_file.startswith(b"SECOPS-DOC\x00")
        assert b"%PDF-synthetischer-test" not in encoded_file

    downloaded = client.get(
        f"/api/v1/incidents/{incident_id}/attachments/{attachment_id}/download",
        headers=admin_headers,
    )
    assert downloaded.status_code == 200
    assert downloaded.content == b"%PDF-synthetischer-test"
    assert downloaded.headers["cache-control"] == "private, no-store"
    client.cookies.clear()
    assert (
        client.get(
            f"/api/v1/incidents/{incident_id}/attachments/{attachment_id}/download",
            headers={"X-CSRF-Token": admin_headers["X-CSRF-Token"]},
        ).status_code
        == 401
    )
    admin_headers = sign_in(client)

    def reject_scan(_content: bytes) -> None:
        from app.malware_scanner import MalwareDetected

        raise MalwareDetected("synthetic test result")

    monkeypatch.setattr("app.upload_scanning.scan_upload", reject_scan)
    rejected = client.post(
        f"/api/v1/incidents/{incident_id}/attachments",
        headers=admin_headers,
        files={"file": ("bad.pdf", b"%PDF-test", "application/pdf")},
    )
    assert rejected.status_code == 422
    with TestingSessionLocal() as db:
        assert (
            db.scalar(
                select(IncidentAttachment.id).where(
                    IncidentAttachment.incident_id == UUID(incident_id)
                )
            )
            is not None
        )
        assert (
            db.scalar(
                select(IncidentAttachment.id).where(IncidentAttachment.file_name == "bad.pdf")
            )
            is None
        )


def test_incident_model_and_migration_are_linear_and_constrained() -> None:
    migration = importlib.import_module("migrations.versions.0022_incident_management")
    assert migration.revision == "0022_incident_management"
    assert migration.down_revision == "0021_key_management"
    unique_link_migration = importlib.import_module(
        "migrations.versions.0025_unique_incident_owks_event"
    )
    assert unique_link_migration.revision == "0025_unique_incident_owks_event"
    assert unique_link_migration.down_revision == "0024_notification_outbox_worker"
    constraints = {constraint.name for constraint in Incident.__table__.constraints}
    assert {
        "ck_incidents_type",
        "ck_incidents_severity",
        "ck_incidents_status",
        "ck_incidents_title",
        "ck_incidents_report",
    } <= constraints
    assert {
        "ix_incidents_object_status_due",
        "ix_incidents_assignee_status",
        "uq_incidents_owks_event_id",
    } <= {index.name for index in Incident.__table__.indexes}


def test_owks_event_incident_reference_is_scoped_and_non_mutating(client: TestClient) -> None:
    admin_headers = sign_in(client)
    object_a = create_object(client, admin_headers, "INC-OWKS-A")
    object_b = create_object(client, admin_headers, "INC-OWKS-B")
    event_a = create_owks_event(client, admin_headers, object_a, "Synthetisches OWKS-Ereignis A")
    event_b = create_owks_event(client, admin_headers, object_b, "Synthetisches OWKS-Ereignis B")

    create_user_with_object("owks_incident_creator", "employee", object_a)
    creator_headers = sign_in(client, "owks_incident_creator", "vorfall-test-passwort-2026")
    choices = client.get(f"/api/v1/incidents/choices?object_id={object_a}", headers=creator_headers)
    assert choices.status_code == 200, choices.text
    assert [item["id"] for item in choices.json()["objects"]] == [object_a]
    assert any(item["id"] for item in choices.json()["assignees"])

    linked = client.post(
        "/api/v1/incidents",
        headers=creator_headers,
        json={
            "title": "Synthetische Vorfallmeldung",
            "report": "Synthetischer eigener Kurzbericht.",
            "incident_type": "incident",
            "severity": "high",
            "object_id": object_a,
            "assigned_to_id": choices.json()["assignees"][0]["id"],
            "owks_event_id": event_a["id"],
        },
    )
    assert linked.status_code == 201, linked.text
    assert linked.json()["owks_event_id"] == event_a["id"]
    repeated = client.post(
        "/api/v1/incidents",
        headers=creator_headers,
        json={
            "title": "Erneuter synthetischer Versuch",
            "report": "Synthetischer erneuter Kurzbericht.",
            "incident_type": "incident",
            "severity": "medium",
            "object_id": object_a,
            "assigned_to_id": choices.json()["assignees"][0]["id"],
            "owks_event_id": event_a["id"],
        },
    )
    assert repeated.status_code == 409
    assert repeated.json()["detail"] == (
        "Dieses OWKS-Ereignis ist bereits mit einem Vorgang verknüpft."
    )
    with TestingSessionLocal() as db:
        db.add(
            Incident(
                id=uuid4(),
                title="Paralleler Datenbankversuch",
                report="Synthetischer Constraint-Test.",
                incident_type="incident",
                severity="medium",
                object_id=UUID(object_a),
                assigned_to_id=UUID(choices.json()["assignees"][0]["id"]),
                owks_event_id=UUID(event_a["id"]),
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    refreshed_choices = client.get(
        f"/api/v1/incidents/choices?object_id={object_a}", headers=creator_headers
    )
    assert refreshed_choices.status_code == 200
    assert refreshed_choices.json()["linked_owks_event_ids"] == [event_a["id"]]

    foreign_object = client.post(
        "/api/v1/incidents",
        headers=creator_headers,
        json={
            "title": "Synthetischer Fremdobjektvorgang",
            "report": "Synthetischer Kurzbericht.",
            "incident_type": "incident",
            "severity": "medium",
            "object_id": object_b,
            "owks_event_id": event_b["id"],
        },
    )
    assert foreign_object.status_code == 403
    mismatched_event = client.post(
        "/api/v1/incidents",
        headers=creator_headers,
        json={
            "title": "Synthetischer Fehlbezug",
            "report": "Synthetischer Kurzbericht.",
            "incident_type": "complaint",
            "severity": "low",
            "object_id": object_a,
            "owks_event_id": event_b["id"],
        },
    )
    assert mismatched_event.status_code == 422

    with TestingSessionLocal() as db:
        stored_incident = db.get(Incident, UUID(linked.json()["id"]))
        original_event = db.get(OWKSEvent, UUID(event_a["id"]))
        assert stored_incident is not None and original_event is not None
        assert stored_incident.owks_event_id == original_event.id
        assert original_event.title == event_a["title"]
        assert original_event.description == event_a["description"]
        assert original_event.severity == event_a["severity"]
        original_status = db.scalar(
            select(OWKSEventStatus)
            .where(OWKSEventStatus.event_id == original_event.id)
            .order_by(OWKSEventStatus.sequence_no.desc())
        )
        assert original_status is not None
        assert original_status.status == event_a["status"]

    create_user_with_permissions(
        "owks_incident_without_create",
        object_a,
        ("owks.read", "owks.write", "incidents.read"),
    )
    reader_headers = sign_in(client, "owks_incident_without_create", "vorfall-test-passwort-2026")
    denied = client.post(
        "/api/v1/incidents",
        headers=reader_headers,
        json={
            "title": "Nicht autorisiert",
            "report": "Synthetischer Kurzbericht.",
            "incident_type": "incident",
            "severity": "medium",
            "object_id": object_a,
            "owks_event_id": event_a["id"],
        },
    )
    assert denied.status_code == 403
    read_only_choices = client.get(
        f"/api/v1/incidents/choices?object_id={object_a}", headers=reader_headers
    )
    assert read_only_choices.status_code == 200
    assert read_only_choices.json()["linked_owks_event_ids"] == []


def test_incident_input_validation_uses_german_error_message(client: TestClient) -> None:
    headers = sign_in(client)
    object_id = create_object(client, headers, "INC-VALIDATION")
    response = client.post(
        "/api/v1/incidents",
        headers=headers,
        json={
            "title": "Ungültiger Typ",
            "report": "Synthetische Kurzmeldung",
            "incident_type": "unbekannt",
            "severity": "medium",
            "object_id": object_id,
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Eingaben für den Vorfall sind ungültig."
    overdue = client.post(
        "/api/v1/incidents",
        headers=headers,
        json={
            "title": "Fristprüfung",
            "report": "Synthetische Fristmeldung",
            "incident_type": "incident",
            "severity": "low",
            "object_id": object_id,
            "due_at": "2020-01-01T00:00:00Z",
        },
    )
    assert overdue.status_code == 201, overdue.text
    page = client.get("/api/v1/incidents?overdue=true", headers=headers)
    assert page.status_code == 200
    assert page.json()["total"] == 1


@pytest.mark.skipif(
    test_engine.dialect.name != "postgresql",
    reason="PostgreSQL-Migration, Append-only-Trigger und Downgrade werden in PostgreSQL geprüft",
)
def test_postgresql_incident_history_is_append_only_and_downgrade_preserves_data(
    client: TestClient,
) -> None:
    headers = sign_in(client)
    object_id = create_object(client, headers, "INC-PG-1")
    incident = create_incident(client, headers, object_id, "PostgreSQL Testvorfall")
    assert incident.status_code == 201, incident.text
    with TestingSessionLocal() as db:
        entry = db.scalar(
            select(IncidentHistory).where(
                IncidentHistory.incident_id == UUID(incident.json()["id"])
            )
        )
        assert entry is not None
        with pytest.raises(DBAPIError):
            db.execute(
                update(IncidentHistory)
                .where(IncidentHistory.id == entry.id)
                .values(action="changed")
            )
        db.rollback()
        with pytest.raises(DBAPIError):
            db.execute(delete(IncidentHistory).where(IncidentHistory.id == entry.id))
        db.rollback()

    migration = importlib.import_module("migrations.versions.0022_incident_management")
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with test_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        with (
            Operations.context(context),
            pytest.raises(RuntimeError, match="Vorfallmanagement-Downgrade"),
        ):
            migration.downgrade()
        connection.rollback()
        assert inspect(connection).has_table("incidents")
