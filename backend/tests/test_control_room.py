from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from conftest import ADMIN_PASSWORD, TestingSessionLocal
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.identity_api import password_hasher
from app.models import (
    BillingInvoice,
    Contract,
    Customer,
    Employee,
    EmployeeAbsence,
    EmployeeQualification,
    Incident,
    ObjectAssignment,
    ObjectQualificationRequirement,
    OWKSEvent,
    OWKSEventStatus,
    Permission,
    Role,
    ScheduleShift,
    SecurityObject,
    Task,
    User,
)


def sign_in(client: TestClient, username: str = "admin", password: str = ADMIN_PASSWORD):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": client.cookies.get("securityops_csrf", "")}


def setup_control_room_scope() -> tuple[str, str, str]:
    with TestingSessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "object_manager"))
        assert role is not None
        needed_codes = (
            "control_room.read",
            "objects.read",
            "scheduling.read",
            "employees.read",
            "employees.absences.read",
            "owks.read",
            "incidents.read",
            "tasks.read_own",
            "billing.invoices.read",
            "billing.invoices.approve",
        )
        permissions = {
            permission.code: permission
            for permission in db.scalars(
                select(Permission).where(Permission.code.in_(needed_codes))
            ).all()
        }
        role.permissions = [permissions[code] for code in needed_codes]
        user = User(
            username="control_room_operator",
            email="control_room_operator@example.com",
            full_name="Test Leitstellenzugriff",
            password_hash=password_hasher.hash("leitstelle-test-passwort-2026"),
            roles=[role],
        )
        customer_a = Customer(
            customer_number="K-CR-A",
            company_name="Testkunde Leitstelle A",
        )
        customer_b = Customer(
            customer_number="K-CR-B",
            company_name="Testkunde Leitstelle B",
        )
        db.add_all((user, customer_a, customer_b))
        db.flush()
        object_a = SecurityObject(
            customer_id=customer_a.id,
            code="CR-TEST-A",
            name="Testobjekt Leitstelle A",
        )
        object_b = SecurityObject(
            customer_id=customer_b.id,
            code="CR-TEST-B",
            name="Testobjekt Leitstelle B",
        )
        db.add_all((object_a, object_b))
        db.flush()
        db.add(ObjectAssignment(object_id=object_a.id, user_id=user.id))
        employee = Employee(
            employee_number="P-CR-TEST",
            user_id=user.id,
            full_name="Testbeschäftigte Leitstelle",
            hired_on=date.today() - timedelta(days=30),
        )
        db.add(employee)
        db.flush()
        now = datetime.now(UTC)
        db.add_all(
            (
                ScheduleShift(
                    employee_id=employee.id,
                    object_id=object_a.id,
                    starts_at=now - timedelta(hours=1),
                    ends_at=now + timedelta(hours=1),
                    status="published",
                ),
                ScheduleShift(
                    employee_id=employee.id,
                    object_id=object_b.id,
                    starts_at=now + timedelta(hours=2),
                    ends_at=now + timedelta(hours=3),
                    status="published",
                ),
                OWKSEvent(
                    object_id=object_a.id,
                    event_type="missed",
                    severity="warning",
                    title="Synthetische versäumte Kontrolle",
                    occurred_at=now,
                ),
                OWKSEvent(
                    object_id=object_a.id,
                    event_type="missed",
                    severity="warning",
                    title="Bereits erledigtes synthetisches Kontrollereignis",
                    occurred_at=now,
                ),
                OWKSEvent(
                    object_id=object_b.id,
                    event_type="missed",
                    severity="critical",
                    title="Fremdes synthetisches Kontrollereignis",
                    occurred_at=now,
                ),
                Incident(
                    title="Synthetischer offener Vorfall",
                    report="Testbericht ohne personenbezogene Daten.",
                    incident_type="incident",
                    severity="high",
                    object_id=object_a.id,
                    status="action_required",
                    due_at=now - timedelta(hours=1),
                    assigned_to_id=user.id,
                ),
                Incident(
                    title="Fremder synthetischer Vorfall",
                    report="Testbericht ohne personenbezogene Daten.",
                    incident_type="incident",
                    severity="critical",
                    object_id=object_b.id,
                    status="reported",
                    assigned_to_id=user.id,
                ),
                Task(
                    title="Synthetische dringende Aufgabe",
                    assigned_to_id=user.id,
                    object_id=object_a.id,
                    priority="urgent",
                    status="open",
                    due_at=now - timedelta(hours=1),
                ),
                Task(
                    title="Fremde synthetische Aufgabe",
                    assigned_to_id=user.id,
                    object_id=object_b.id,
                    priority="urgent",
                    status="open",
                    due_at=now - timedelta(hours=1),
                ),
                EmployeeAbsence(
                    employee_id=employee.id,
                    absence_type="vacation",
                    status="approved",
                    starts_on=date.today(),
                    ends_on=date.today() + timedelta(days=2),
                ),
                EmployeeQualification(
                    employee_id=employee.id,
                    category="Testqualifikation",
                    name="Synthetischer Nachweis",
                    expires_on=date.today() + timedelta(days=14),
                ),
            )
        )
        db.flush()
        object_a_contract = Contract(
            contract_number="CR-CONTRACT-A",
            name="Testvertrag Leitstelle A",
            contract_type="object",
            counterparty=customer_a.company_name,
            customer_id=customer_a.id,
            object_id=object_a.id,
            starts_on=date.today(),
        )
        object_b_contract = Contract(
            contract_number="CR-CONTRACT-B",
            name="Testvertrag Leitstelle B",
            contract_type="object",
            counterparty=customer_b.company_name,
            customer_id=customer_b.id,
            object_id=object_b.id,
            starts_on=date.today(),
        )
        db.add_all((object_a_contract, object_b_contract))
        db.flush()
        db.add_all(
            (
                BillingInvoice(
                    invoice_number="CR-INVOICE-A",
                    idempotency_key="control-room-invoice-a",
                    customer_id=customer_a.id,
                    contract_id=object_a_contract.id,
                    kind="invoice",
                    status="draft",
                    currency="EUR",
                    issued_on=date.today(),
                    due_on=date.today() + timedelta(days=30),
                    customer_snapshot={"name": customer_a.company_name},
                    inputs_snapshot={},
                    net_amount=Decimal("100.00"),
                    tax_amount=Decimal("19.00"),
                    gross_amount=Decimal("119.00"),
                ),
                BillingInvoice(
                    invoice_number="CR-INVOICE-B",
                    idempotency_key="control-room-invoice-b",
                    customer_id=customer_b.id,
                    contract_id=object_b_contract.id,
                    kind="invoice",
                    status="draft",
                    currency="EUR",
                    issued_on=date.today(),
                    due_on=date.today() + timedelta(days=30),
                    customer_snapshot={"name": customer_b.company_name},
                    inputs_snapshot={},
                    net_amount=Decimal("100.00"),
                    tax_amount=Decimal("19.00"),
                    gross_amount=Decimal("119.00"),
                ),
            )
        )
        db.flush()
        active_event = db.scalar(
            select(OWKSEvent).where(OWKSEvent.title == "Synthetische versäumte Kontrolle")
        )
        assert active_event is not None
        resolved_event = db.scalar(
            select(OWKSEvent).where(
                OWKSEvent.title == "Bereits erledigtes synthetisches Kontrollereignis"
            )
        )
        assert resolved_event is not None
        db.add(
            OWKSEventStatus(
                event_id=active_event.id,
                sequence_no=1,
                status="open",
                note="",
            )
        )
        db.add(
            OWKSEventStatus(
                event_id=resolved_event.id,
                sequence_no=1,
                status="resolved",
                note="",
            )
        )
        assert object_a is not None
        object_a.qualification_requirement_records.append(
            ObjectQualificationRequirement(name="Synthetischer Nachweis")
        )
        db.commit()
        return str(user.id), str(object_a.id), str(object_b.id)


def test_control_room_uses_real_sources_and_scopes_every_source_to_assignment(
    client: TestClient,
) -> None:
    user_id, object_a_id, object_b_id = setup_control_room_scope()
    headers = sign_in(client, "control_room_operator", "leitstelle-test-passwort-2026")
    response = client.get(
        "/api/v1/control-room",
        headers=headers,
        params={
            "object_id": object_a_id,
            "from_date": str(date.today() - timedelta(days=1)),
            "to_date": str(date.today() + timedelta(days=30)),
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["counts"]["active_objects"] == 1
    assert payload["counts"]["active_shifts"] == 1
    assert payload["counts"]["open_owks_events"] == 1
    assert payload["counts"]["open_incidents"] == 1
    assert payload["counts"]["overdue_incidents"] == 1
    assert payload["counts"]["open_tasks"] == 1
    assert payload["counts"]["urgent_tasks"] == 1
    assert payload["counts"]["active_absences"] == 1
    assert payload["counts"]["qualification_problems"] == 1
    assert payload["counts"]["billing_approvals"] == 1
    assert payload["shifts"][0]["employee_name"] == "Testbeschäftigte Leitstelle"
    assert payload["incidents"][0]["title"] == "Synthetischer offener Vorfall"
    assert "report" not in payload["incidents"][0]
    assert payload["tasks"][0]["assigned_to_name"] == "Test Leitstellenzugriff"
    assert payload["billing_approvals"][0]["invoice_number"] == "CR-INVOICE-A"
    serialized = response.text
    assert object_b_id not in serialized
    assert "Fremdes synthetisches" not in serialized
    assert "Testbericht ohne personenbezogene Daten." not in serialized
    assert user_id not in serialized

    assert (
        client.get(
            "/api/v1/control-room",
            headers=headers,
            params={"object_id": object_b_id},
        ).status_code
        == 404
    )


def test_control_room_requires_permission_and_omits_unavailable_sources(client: TestClient) -> None:
    denied = User(
        username="control_room_denied",
        email="control_room_denied@example.com",
        full_name="Test ohne Leitstellenrecht",
        password_hash=password_hasher.hash("leitstelle-test-passwort-2026"),
        roles=[],
    )
    with TestingSessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "employee"))
        assert role is not None
        denied.roles = [role]
        db.add(denied)
        db.commit()

    headers = sign_in(client, "control_room_denied", "leitstelle-test-passwort-2026")
    assert client.get("/api/v1/control-room", headers=headers).status_code == 403

    _, object_a_id, _ = setup_control_room_scope()
    with TestingSessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "object_manager"))
        assert role is not None
        object_permission = db.scalar(select(Permission).where(Permission.code == "objects.read"))
        control_room_permission = db.scalar(
            select(Permission).where(Permission.code == "control_room.read")
        )
        assert object_permission is not None and control_room_permission is not None
        role.permissions = [object_permission, control_room_permission]
        db.commit()
    scoped_headers = sign_in(client, "control_room_operator", "leitstelle-test-passwort-2026")
    response = client.get(
        "/api/v1/control-room",
        headers=scoped_headers,
        params={"object_id": object_a_id},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["objects"]
    assert "shifts" not in payload
    assert "owks_events" not in payload
    assert "incidents" not in payload
    assert "tasks" not in payload
    assert "absences" not in payload
    assert "qualifications" not in payload
    assert "billing_approvals" not in payload


def test_control_room_applies_date_range_to_events_and_absences(client: TestClient) -> None:
    _, object_a_id, _ = setup_control_room_scope()
    headers = sign_in(client, "control_room_operator", "leitstelle-test-passwort-2026")
    response = client.get(
        "/api/v1/control-room",
        headers=headers,
        params={
            "object_id": object_a_id,
            "from_date": str(date.today() + timedelta(days=3)),
            "to_date": str(date.today() + timedelta(days=30)),
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["counts"]["open_owks_events"] == 0
    assert payload["counts"]["active_absences"] == 0
    assert payload["counts"]["active_shifts"] == 1
    assert payload["counts"]["open_incidents"] == 1
    assert payload["counts"]["open_tasks"] == 1


def test_object_operations_report_aggregates_date_bounded_data_without_narratives(
    client: TestClient,
) -> None:
    user_id, object_a_id, object_b_id = setup_control_room_scope()
    headers = sign_in(client, "control_room_operator", "leitstelle-test-passwort-2026")
    today = datetime.now(UTC).date()
    range_start = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
    range_end = range_start + timedelta(days=1)
    with TestingSessionLocal() as db:
        report_employee = Employee(
            employee_number="P-REPORT-TEST",
            full_name="Testkraft Objektbericht",
            employment_status="active",
            hired_on=today,
        )
        db.add(report_employee)
        db.flush()
        db.add_all(
            (
                OWKSEvent(
                    object_id=UUID(object_a_id),
                    event_type="control",
                    severity="info",
                    title="Nicht auszugebender Kontrolltext",
                    occurred_at=range_start,
                ),
                OWKSEvent(
                    object_id=UUID(object_a_id),
                    event_type="missed",
                    severity="warning",
                    title="Ereignis genau am exklusiven Ende",
                    occurred_at=range_end,
                ),
                Incident(
                    title="Vorfall genau am exklusiven Ende",
                    report="Dieser Text darf nicht im Bericht stehen.",
                    incident_type="incident",
                    severity="high",
                    object_id=UUID(object_a_id),
                    status="reported",
                    assigned_to_id=UUID(user_id),
                    created_at=range_end,
                ),
                Task(
                    title="Aufgabe an der Startgrenze",
                    assigned_to_id=UUID(user_id),
                    object_id=UUID(object_a_id),
                    status="completed",
                    created_at=range_start,
                ),
                Task(
                    title="Aufgabe am exklusiven Ende",
                    assigned_to_id=UUID(user_id),
                    object_id=UUID(object_a_id),
                    status="open",
                    created_at=range_end,
                ),
                ScheduleShift(
                    employee_id=report_employee.id,
                    object_id=UUID(object_a_id),
                    starts_at=range_end - timedelta(hours=1),
                    ends_at=range_end,
                    status="published",
                ),
                ScheduleShift(
                    employee_id=report_employee.id,
                    object_id=UUID(object_a_id),
                    starts_at=range_end,
                    ends_at=range_end + timedelta(hours=1),
                    status="published",
                ),
                ScheduleShift(
                    employee_id=report_employee.id,
                    object_id=UUID(object_a_id),
                    starts_at=range_start,
                    ends_at=range_start + timedelta(hours=1),
                    status="draft",
                ),
            )
        )
        db.commit()

    response = client.get(
        "/api/v1/object-operations-report",
        headers=headers,
        params={"object_id": object_a_id, "from_date": today, "to_date": today},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["published_assigned_shifts"] == 2
    assert item["incidents_created"] == 1
    assert item["control_events"] == 1
    assert item["missed_controls"] == 2
    assert item["qualification_conflict_shifts"] == 1
    assert item["task_status_counts"]["open"] == 1
    assert item["task_status_counts"]["completed"] == 1
    assert object_b_id not in response.text
    assert "Nicht auszugebender Kontrolltext" not in response.text
    assert "Dieser Text darf nicht im Bericht stehen." not in response.text
    assert user_id not in response.text
    assert (
        client.get(
            "/api/v1/object-operations-report",
            headers=headers,
            params={"object_id": object_b_id, "from_date": today, "to_date": today},
        ).status_code
        == 404
    )
    assert (
        client.get(
            "/api/v1/object-operations-report",
            headers=headers,
            params={"from_date": today - timedelta(days=367), "to_date": today},
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/object-operations-report",
            headers=headers,
            params={"from_date": today, "to_date": today - timedelta(days=1)},
        ).status_code
        == 422
    )


def test_object_operations_report_requires_object_read_and_bounds_pages_and_csv(
    client: TestClient,
) -> None:
    _, _object_a_id, object_b_id = setup_control_room_scope()
    headers = sign_in(client, "control_room_operator", "leitstelle-test-passwort-2026")
    today = datetime.now(UTC).date()
    with TestingSessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "object_manager"))
        assert role is not None
        object_read_all = db.scalar(select(Permission).where(Permission.code == "objects.read_all"))
        assert object_read_all is not None
        role.permissions = [*role.permissions, object_read_all]
        object_b = db.scalar(select(SecurityObject).where(SecurityObject.id == UUID(object_b_id)))
        assert object_b is not None
        object_b.name = "=1+1"
        db.commit()

    params = {"from_date": today, "to_date": today, "limit": 1}
    first_page = client.get("/api/v1/object-operations-report", headers=headers, params=params)
    assert first_page.status_code == 200, first_page.text
    assert first_page.json()["total"] == 2
    assert first_page.json()["has_more"] is True
    second_page = client.get(
        "/api/v1/object-operations-report",
        headers=headers,
        params={**params, "offset": 1},
    )
    assert second_page.status_code == 200, second_page.text
    assert second_page.json()["has_more"] is False
    assert second_page.json()["items"][0]["object_id"] != first_page.json()["items"][0]["object_id"]
    assert (
        client.get(
            "/api/v1/object-operations-report",
            headers=headers,
            params={**params, "limit": 101},
        ).status_code
        == 422
    )

    export = client.get(
        "/api/v1/object-operations-report.csv",
        headers=headers,
        params={**params, "object_id": object_b_id},
    )
    assert export.status_code == 200, export.text
    assert export.headers["content-type"].startswith("text/csv")
    assert (
        'attachment; filename="objektbetriebsbericht.csv"' in export.headers["content-disposition"]
    )
    assert "Objektnummer;Objekt;" in export.text
    assert "Veröffentlichte Schichten mit Qualifikationslücken" in export.text
    assert ";0;" in export.text
    assert "'=1+1" in export.text
    assert "Dieser Text darf nicht im Bericht stehen." not in export.text

    with TestingSessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "object_manager"))
        assert role is not None
        objects_read = db.scalar(select(Permission).where(Permission.code == "objects.read"))
        control_room_read = db.scalar(
            select(Permission).where(Permission.code == "control_room.read")
        )
        assert objects_read is not None and control_room_read is not None
        role.permissions = [control_room_read]
        db.commit()
    no_object_read_headers = sign_in(
        client, "control_room_operator", "leitstelle-test-passwort-2026"
    )
    assert (
        client.get(
            "/api/v1/object-operations-report",
            headers=no_object_read_headers,
            params={"from_date": today, "to_date": today},
        ).status_code
        == 403
    )


def test_object_operations_report_omits_qualification_metric_without_employee_permission(
    client: TestClient,
) -> None:
    _, object_a_id, _ = setup_control_room_scope()
    headers = sign_in(client, "control_room_operator", "leitstelle-test-passwort-2026")
    today = datetime.now(UTC).date()
    with TestingSessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "object_manager"))
        assert role is not None
        role.permissions = [
            permission for permission in role.permissions if permission.code != "employees.read"
        ]
        db.commit()

    response = client.get(
        "/api/v1/object-operations-report",
        headers=headers,
        params={"object_id": object_a_id, "from_date": today, "to_date": today},
    )
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["qualification_conflict_shifts"] is None
