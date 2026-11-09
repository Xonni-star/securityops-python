from collections.abc import Generator
from datetime import date, datetime, timedelta
from time import sleep
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.identity_api import password_hasher
from app.main import app
from app.models import Base, BillingInvoice, Permission, Role, ScheduleSettings, User
from app.rate_limit import limiter

ADMIN_PASSWORD = "synthetisches-workflow-test-passwort"
EMPLOYEE_PASSWORD = "synthetisches-mitarbeiter-test-passwort"


@pytest.fixture
def workflow_client() -> Generator[tuple[TestClient, sessionmaker[Session]], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    connection = engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    def override_get_db() -> Generator[Session, None, None]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    admin_permissions = {
        "customers.create",
        "customers.read",
        "objects.manage",
        "objects.read",
        "objects.read_all",
        "objects.assign",
        "objects.manage_all",
        "employees.manage",
        "employees.read",
        "scheduling.manage",
        "scheduling.read",
        "time_tracking.create",
        "time_tracking.read_own",
        "time_tracking.read_all",
        "time_tracking.approve",
        "owks.read",
        "owks.manage",
        "owks.write",
        "incidents.create",
        "incidents.read",
        "incidents.read_all",
        "incidents.update",
        "incidents.manage_all",
        "incidents.sensitive.manage",
        "billing.rates.manage",
        "billing.invoices.create",
        "billing.invoices.read",
        "billing.invoices.approve",
    }
    employee_permissions = {
        "objects.read",
        "scheduling.read",
        "time_tracking.create",
        "time_tracking.read_own",
        "owks.read",
        "owks.write",
        "incidents.create",
        "incidents.read",
    }

    with session_factory() as db:
        permissions = {
            code: Permission(code=code, description=code)
            for code in admin_permissions | employee_permissions
        }
        administrator = Role(
            code="administrator",
            name="Administrator",
            description="Synthetische Workflow-Testrolle",
            permissions=[permissions[code] for code in sorted(admin_permissions)],
        )
        employee_role = Role(
            code="employee",
            name="Mitarbeiter",
            description="Synthetische Workflow-Testrolle",
            permissions=[permissions[code] for code in sorted(employee_permissions)],
        )
        db.add_all(
            [
                *permissions.values(),
                administrator,
                employee_role,
                ScheduleSettings(id=1, time_zone="Europe/Berlin", minimum_rest_hours=11),
                User(
                    username="workflow-admin",
                    email="workflow-admin@example.com",
                    full_name="Synthetische Administration",
                    password_hash=password_hasher.hash(ADMIN_PASSWORD),
                    roles=[administrator],
                ),
            ]
        )
        db.commit()

    app.dependency_overrides[get_db] = override_get_db
    limiter.reset()
    try:
        with TestClient(app, base_url="https://testserver") as client:
            yield client, session_factory
    finally:
        app.dependency_overrides.pop(get_db, None)
        transaction.rollback()
        connection.close()
        engine.dispose()
        limiter.reset()


def login(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": client.cookies.get("securityops_csrf", "")}


def restore_session(client: TestClient, session_cookie: str, csrf_cookie: str) -> dict[str, str]:
    client.cookies.clear()
    client.cookies.set("securityops_session", session_cookie, domain="testserver.local", path="/")
    client.cookies.set("securityops_csrf", csrf_cookie, domain="testserver.local", path="/")
    return {"X-CSRF-Token": csrf_cookie}


def test_synthetic_backend_workflow_end_to_end(
    workflow_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, session_factory = workflow_client
    admin_headers = login(client, "workflow-admin", ADMIN_PASSWORD)
    admin_session_cookie = client.cookies.get("securityops_session")
    admin_csrf_cookie = client.cookies.get("securityops_csrf")
    assert admin_session_cookie is not None and admin_csrf_cookie is not None
    today = date.today()

    customer_response = client.post(
        "/api/v1/customers",
        headers=admin_headers,
        json={"company_name": "Synthetischer Ablaufkunde GmbH"},
    )
    assert customer_response.status_code == 201, customer_response.text
    customer = customer_response.json()

    object_response = client.post(
        "/api/v1/objects",
        headers=admin_headers,
        json={
            "customer_id": customer["id"],
            "name": "Synthetisches Testobjekt",
            "code": "E2E-WORKFLOW-01",
        },
    )
    assert object_response.status_code == 201, object_response.text
    obj = object_response.json()

    foreign_object_response = client.post(
        "/api/v1/objects",
        headers=admin_headers,
        json={
            "customer_id": customer["id"],
            "name": "Nicht zugewiesenes Testobjekt",
            "code": "E2E-WORKFLOW-02",
        },
    )
    assert foreign_object_response.status_code == 201, foreign_object_response.text
    foreign_object = foreign_object_response.json()

    with session_factory() as db:
        employee_role = db.query(Role).filter_by(code="employee").one()
        employee_user = User(
            username="workflow-employee",
            email="workflow-employee@example.com",
            full_name="Synthetische Einsatzkraft",
            password_hash=password_hasher.hash(EMPLOYEE_PASSWORD),
            roles=[employee_role],
        )
        db.add(employee_user)
        db.commit()
        employee_user_id = employee_user.id

    employee_response = client.post(
        "/api/v1/employees",
        headers=admin_headers,
        json={
            "employee_number": "E2E-EMP-001",
            "user_id": str(employee_user_id),
            "full_name": "Synthetische Einsatzkraft",
            "hired_on": str(today - timedelta(days=30)),
        },
    )
    assert employee_response.status_code == 201, employee_response.text
    employee = employee_response.json()

    qualification_response = client.post(
        f"/api/v1/employees/{employee['id']}/qualifications",
        headers=admin_headers,
        json={
            "category": "Erste Hilfe",
            "name": "Erste Hilfe",
            "issuer": "Synthetische interne Schulung",
            "valid_from": str(today - timedelta(days=1)),
            "expires_on": str(today + timedelta(days=365)),
        },
    )
    assert qualification_response.status_code == 201, qualification_response.text

    assignment_response = client.post(
        f"/api/v1/employees/{employee['id']}/objects/{obj['id']}",
        headers=admin_headers,
    )
    assert assignment_response.status_code == 201, assignment_response.text

    employee_headers = login(client, "workflow-employee", EMPLOYEE_PASSWORD)
    employee_session_cookie = client.cookies.get("securityops_session")
    employee_csrf_cookie = client.cookies.get("securityops_csrf")
    assert employee_session_cookie is not None and employee_csrf_cookie is not None
    visible_objects = client.get("/api/v1/owks/objects", headers=employee_headers)
    assert visible_objects.status_code == 200, visible_objects.text
    assert [item["id"] for item in visible_objects.json()] == [obj["id"]]
    assert (
        client.get(
            f"/api/v1/owks/objects/{foreign_object['id']}/events",
            headers=employee_headers,
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/objects/{foreign_object['id']}",
            headers=employee_headers,
        ).status_code
        == 404
    )
    assert client.get("/api/v1/billing/invoices", headers=employee_headers).status_code == 403

    local_now = datetime.now(ZoneInfo("Europe/Berlin")).replace(
        tzinfo=None,
        second=0,
        microsecond=0,
    )
    starts_at = local_now - timedelta(minutes=45)
    ends_at = local_now + timedelta(hours=5)
    shift_payload = {
        "employee_id": employee["id"],
        "object_id": obj["id"],
        "starts_at_local": starts_at.isoformat(timespec="minutes"),
        "ends_at_local": ends_at.isoformat(timespec="minutes"),
        "break_minutes": 30,
        "required_qualification": "Erste Hilfe",
    }
    missing_qualification_payload = {
        **shift_payload,
        "required_qualification": "Nicht vorhandene Qualifikation",
    }
    admin_headers = restore_session(client, admin_session_cookie, admin_csrf_cookie)
    missing_qualification = client.post(
        "/api/v1/scheduling/shifts",
        headers=admin_headers,
        json=missing_qualification_payload,
    )
    assert missing_qualification.status_code == 409, missing_qualification.text
    assert missing_qualification.json()["detail"]["conflicts"][0]["code"] == "qualification_missing"

    shift_response = client.post(
        "/api/v1/scheduling/shifts",
        headers=admin_headers,
        json=shift_payload,
    )
    assert shift_response.status_code == 201, shift_response.text
    shift = shift_response.json()
    overlap_response = client.post(
        "/api/v1/scheduling/shifts",
        headers=admin_headers,
        json={
            **shift_payload,
            "starts_at_local": (starts_at + timedelta(hours=1)).isoformat(timespec="minutes"),
            "ends_at_local": (starts_at + timedelta(hours=2)).isoformat(timespec="minutes"),
        },
    )
    assert overlap_response.status_code == 409, overlap_response.text
    assert any(
        conflict["code"] == "time_overlap"
        for conflict in overlap_response.json()["detail"]["conflicts"]
    )
    published_shift = client.post(
        f"/api/v1/scheduling/shifts/{shift['id']}/publish",
        headers=admin_headers,
    )
    assert published_shift.status_code == 200, published_shift.text
    assert published_shift.json()["status"] == "published"

    employee_headers = restore_session(client, employee_session_cookie, employee_csrf_cookie)
    started = client.post(
        "/api/v1/time-tracking/start",
        headers=employee_headers,
        json={"shift_id": shift["id"]},
    )
    assert started.status_code == 201, started.text
    entry = started.json()
    sleep(1.1)
    submitted = client.post(
        f"/api/v1/time-tracking/entries/{entry['id']}/stop",
        headers=employee_headers,
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"
    assert submitted.json()["actual_work_seconds"] > 0

    admin_headers = restore_session(client, admin_session_cookie, admin_csrf_cookie)
    approved_entry = client.post(
        f"/api/v1/time-tracking/entries/{entry['id']}/approve",
        headers=admin_headers,
    )
    assert approved_entry.status_code == 200, approved_entry.text
    assert approved_entry.json()["status"] == "approved"
    report_response = client.get(
        "/api/v1/time-tracking/reports",
        headers=admin_headers,
        params={
            "from_date": today.isoformat(),
            "to_date": today.isoformat(),
        },
    )
    assert report_response.status_code == 200, report_response.text
    assert report_response.json()["entry_count"] == 1
    assert report_response.json()["actual_work_seconds"] > 0

    admin_headers = restore_session(client, admin_session_cookie, admin_csrf_cookie)
    control_point_response = client.post(
        f"/api/v1/owks/objects/{obj['id']}/control-points",
        headers=admin_headers,
        json={"name": "Synthetischer Haupteingang", "identifier_type": "qr"},
    )
    assert control_point_response.status_code == 201, control_point_response.text
    control_point = control_point_response.json()
    route_response = client.post(
        f"/api/v1/owks/objects/{obj['id']}/routes",
        headers=admin_headers,
        json={
            "name": "Synthetischer Kontrollgang",
            "interval_minutes": 60,
            "control_point_ids": [control_point["id"]],
        },
    )
    assert route_response.status_code == 201, route_response.text

    employee_headers = restore_session(client, employee_session_cookie, employee_csrf_cookie)
    challenge_response = client.post(
        f"/api/v1/owks/objects/{obj['id']}/challenges",
        headers=employee_headers,
    )
    assert challenge_response.status_code == 200, challenge_response.text
    scan_response = client.post(
        "/api/v1/owks/scans",
        headers=employee_headers,
        json={
            "challenge_id": challenge_response.json()["id"],
            "credential": control_point["credential"],
            "client_event_id": str(uuid4()),
            "route_id": route_response.json()["id"],
        },
    )
    assert scan_response.status_code == 201, scan_response.text
    assert scan_response.json()["event_type"] == "control"
    event = scan_response.json()

    incident_response = client.post(
        "/api/v1/incidents",
        headers=employee_headers,
        json={
            "title": "Synthetische Vorfallmeldung",
            "report": "Rein synthetische Meldung zum Testablauf.",
            "incident_type": "incident",
            "severity": "medium",
            "object_id": obj["id"],
            "owks_event_id": event["id"],
        },
    )
    assert incident_response.status_code == 201, incident_response.text
    incident = incident_response.json()
    assert incident["owks_event_id"] == event["id"]
    assert (
        client.get(
            f"/api/v1/incidents/{incident['id']}",
            headers=employee_headers,
        ).status_code
        == 200
    )
    admin_headers = restore_session(client, admin_session_cookie, admin_csrf_cookie)
    foreign_incident = client.post(
        "/api/v1/incidents",
        headers=admin_headers,
        json={
            "title": "Fremder synthetischer Vorgang",
            "report": "Nur zum Prüfen des Objektscopes.",
            "incident_type": "incident",
            "severity": "low",
            "object_id": foreign_object["id"],
        },
    )
    assert foreign_incident.status_code == 201, foreign_incident.text
    employee_headers = restore_session(client, employee_session_cookie, employee_csrf_cookie)
    assert (
        client.get(
            f"/api/v1/incidents/{foreign_incident.json()['id']}",
            headers=employee_headers,
        ).status_code
        == 404
    )

    admin_headers = restore_session(client, admin_session_cookie, admin_csrf_cookie)
    measure_response = client.post(
        f"/api/v1/incidents/{incident['id']}/measures",
        headers=admin_headers,
        json={
            "title": "Synthetische Prüfmaßnahme",
            "description": "Abschluss der Testmaßnahme.",
            "assigned_to_id": str(employee_user_id),
        },
    )
    assert measure_response.status_code == 201, measure_response.text
    measure_response = client.patch(
        f"/api/v1/incidents/{incident['id']}/measures/{measure_response.json()['id']}",
        headers=admin_headers,
        json={"status": "completed"},
    )
    assert measure_response.status_code == 200, measure_response.text
    sensitive_details = client.patch(
        f"/api/v1/incidents/{incident['id']}/sensitive",
        headers=admin_headers,
        json={"closure_report": "Synthetischer Abschlussbericht."},
    )
    assert sensitive_details.status_code == 200, sensitive_details.text
    for status in ("investigating", "action_required", "closed"):
        status_response = client.post(
            f"/api/v1/incidents/{incident['id']}/status",
            headers=admin_headers,
            json={"status": status},
        )
        assert status_response.status_code == 200, status_response.text
    closed_incident = client.get(
        f"/api/v1/incidents/{incident['id']}",
        headers=admin_headers,
    )
    assert closed_incident.status_code == 200, closed_incident.text
    assert closed_incident.json()["status"] == "closed"

    rate_response = client.post(
        "/api/v1/billing/rates",
        headers=admin_headers,
        json={
            "code": "E2E-TEST-RATE",
            "name": "Synthetischer Zeitnachweis",
            "kind": "hourly",
            "unit": "Stunde",
            "unit_price": "0",
            "tax_code": "TEST",
            "tax_rate": "0",
        },
    )
    assert rate_response.status_code == 201, rate_response.text
    invoice_response = client.post(
        "/api/v1/billing/invoices",
        headers=admin_headers,
        json={
            "idempotency_key": "workflow-invoice-test-001",
            "customer_id": customer["id"],
            "issued_on": today.isoformat(),
            "due_on": (today + timedelta(days=30)).isoformat(),
            "lines": [
                {
                    "rate_id": rate_response.json()["id"],
                    "quantity": "1",
                    "source_time_entry_ids": [entry["id"]],
                }
            ],
        },
    )
    assert invoice_response.status_code == 201, invoice_response.text
    invoice = invoice_response.json()
    assert invoice["status"] == "draft"
    assert invoice["lines"][0]["quantity"] != "1.0000"
    with session_factory() as db:
        stored_invoice = db.get(BillingInvoice, UUID(invoice["id"]))
        assert stored_invoice is not None
        assert (
            stored_invoice.inputs_snapshot["source_time_entries"][0]["time_entry_id"] == entry["id"]
        )
