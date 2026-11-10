from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time, timedelta
from threading import Barrier
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from conftest import ADMIN_PASSWORD, TestingSessionLocal, app, test_engine
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.identity_api import password_hasher
from app.models import (
    Employee,
    EmployeeAbsence,
    EmployeeAvailabilityWindow,
    EmployeeQualification,
    Permission,
    Role,
    ScheduleShift,
    User,
)


def sign_in(client: TestClient, username: str = "admin", password: str = ADMIN_PASSWORD) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return client.cookies.get("securityops_csrf", "")


def create_employee_user(username: str) -> UUID:
    with TestingSessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "employee"))
        assert role is not None
        user = User(
            username=username,
            email=f"{username}@example.com",
            full_name=f"Test {username}",
            password_hash=password_hasher.hash("dienstplan-test-passwort-2026"),
            roles=[role],
        )
        db.add(user)
        db.commit()
        return user.id


def setup_schedule(client: TestClient) -> tuple[dict, dict, str]:
    headers = {"X-CSRF-Token": sign_in(client)}
    user_id = create_employee_user("dienstplan-person")
    employee_response = client.post(
        "/api/v1/employees",
        headers=headers,
        json={
            "employee_number": "P-SCH-001",
            "user_id": str(user_id),
            "full_name": "Testperson Dienstplan",
            "hired_on": str(date.today() - timedelta(days=100)),
        },
    )
    assert employee_response.status_code == 201, employee_response.text
    employee = employee_response.json()

    customer = client.post(
        "/api/v1/customers",
        headers=headers,
        json={"company_name": "Testkunde Dienstplanung"},
    )
    assert customer.status_code == 201, customer.text
    obj_response = client.post(
        "/api/v1/objects",
        headers=headers,
        json={
            "customer_id": customer.json()["id"],
            "name": "Testobjekt Dienstplanung",
            "code": "OBJ-SCH-001",
        },
    )
    assert obj_response.status_code == 201, obj_response.text
    obj = obj_response.json()
    assignment = client.put(
        f"/api/v1/objects/{obj['id']}/assignments",
        headers=headers,
        json={"user_ids": [str(user_id)]},
    )
    assert assignment.status_code == 200, assignment.text
    return employee, obj, headers["X-CSRF-Token"]


def shift_payload(employee: dict, obj: dict, starts_at: datetime, ends_at: datetime) -> dict:
    return {
        "employee_id": employee["id"],
        "object_id": obj["id"],
        "starts_at_local": starts_at.isoformat(timespec="minutes"),
        "ends_at_local": ends_at.isoformat(timespec="minutes"),
        "break_minutes": 30,
    }


def add_employee_to_object(client: TestClient, obj: dict, csrf: str, suffix: str) -> dict:
    user_id = create_employee_user(f"dienstplan-{suffix}")
    response = client.post(
        "/api/v1/employees",
        headers={"X-CSRF-Token": csrf},
        json={
            "employee_number": f"P-SCH-{suffix.upper()}",
            "user_id": str(user_id),
            "full_name": f"Testperson {suffix}",
            "hired_on": str(date.today() - timedelta(days=100)),
        },
    )
    assert response.status_code == 201, response.text
    current_assignments = client.get(f"/api/v1/objects/{obj['id']}/assignments")
    assert current_assignments.status_code == 200, current_assignments.text
    assignments = client.put(
        f"/api/v1/objects/{obj['id']}/assignments",
        headers={"X-CSRF-Token": csrf},
        json={
            "user_ids": [
                *(item["user_id"] for item in current_assignments.json()),
                str(user_id),
            ]
        },
    )
    assert assignments.status_code == 200, assignments.text
    return response.json()


def test_shift_creation_conflicts_publication_and_history(client: TestClient) -> None:
    employee, obj, csrf = setup_schedule(client)
    headers = {"X-CSRF-Token": csrf}
    starts_at = datetime.combine(date.today() + timedelta(days=40), time(9))
    payload = shift_payload(employee, obj, starts_at, starts_at + timedelta(hours=8))

    created = client.post("/api/v1/scheduling/shifts", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    shift = created.json()
    assert shift["status"] == "draft"
    assert shift["time_zone"] == "Europe/Berlin"
    assert (
        datetime.fromisoformat(shift["starts_at"])
        .astimezone(ZoneInfo("Europe/Berlin"))
        .replace(tzinfo=None)
        == starts_at
    )
    updated = client.patch(
        f"/api/v1/scheduling/shifts/{shift['id']}",
        headers=headers,
        json={"break_minutes": 45},
    )
    assert updated.status_code == 200
    assert updated.json()["break_minutes"] == 45

    overlap = client.post(
        "/api/v1/scheduling/shifts",
        headers=headers,
        json=shift_payload(
            employee,
            obj,
            starts_at + timedelta(hours=1),
            starts_at + timedelta(hours=4),
        ),
    )
    assert overlap.status_code == 409
    assert overlap.json()["detail"]["conflicts"][0]["code"] == "time_overlap"

    rest_conflict = client.post(
        "/api/v1/scheduling/shifts",
        headers=headers,
        json=shift_payload(
            employee,
            obj,
            starts_at + timedelta(hours=9),
            starts_at + timedelta(hours=13),
        ),
    )
    assert rest_conflict.status_code == 409
    assert any(
        item["code"] == "minimum_rest" for item in rest_conflict.json()["detail"]["conflicts"]
    )

    published = client.post(
        f"/api/v1/scheduling/shifts/{shift['id']}/publish",
        headers=headers,
    )
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    history = client.get(f"/api/v1/scheduling/shifts/{shift['id']}/history")
    assert history.status_code == 200
    assert [row["action"] for row in history.json()] == ["published", "updated", "created"]

    filtered = client.get(
        "/api/v1/scheduling/shifts",
        params={
            "from_date": starts_at.date().isoformat(),
            "to_date": starts_at.date().isoformat(),
            "employee_id": employee["id"],
            "object_id": obj["id"],
        },
    )
    assert filtered.status_code == 200
    assert [row["id"] for row in filtered.json()] == [shift["id"]]
    cancelled = client.post(
        f"/api/v1/scheduling/shifts/{shift['id']}/cancel",
        headers=headers,
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert (
        client.get(
            "/api/v1/scheduling/shifts",
            params={
                "from_date": starts_at.date().isoformat(),
                "to_date": starts_at.date().isoformat(),
            },
        ).json()
        == []
    )
    assert (
        len(
            client.get(
                "/api/v1/scheduling/shifts",
                params={
                    "from_date": starts_at.date().isoformat(),
                    "to_date": starts_at.date().isoformat(),
                    "include_cancelled": "true",
                },
            ).json()
        )
        == 1
    )


def test_recurring_availability_is_enforced_and_preserved_for_existing_shifts(
    client: TestClient,
) -> None:
    employee, obj, csrf = setup_schedule(client)
    headers = {"X-CSRF-Token": csrf}
    work_date = date.today() + timedelta(days=60)
    starts_at = datetime.combine(work_date, time(9))
    payload = shift_payload(employee, obj, starts_at, starts_at + timedelta(hours=8))
    created = client.post("/api/v1/scheduling/shifts", headers=headers, json=payload)
    assert created.status_code == 201, created.text

    weekday = work_date.weekday()
    saved = client.put(
        f"/api/v1/scheduling/employees/{employee['id']}/availability",
        headers=headers,
        json={
            "windows": [
                {"weekday": weekday, "starts_at": "09:00", "ends_at": "17:00"},
                {"weekday": 6, "starts_at": "01:00", "ends_at": "04:00"},
            ]
        },
    )
    assert saved.status_code == 200, saved.text
    assert len(saved.json()) == 2
    out_of_window = client.post(
        "/api/v1/scheduling/shifts",
        headers=headers,
        json=shift_payload(
            employee,
            obj,
            datetime.combine(work_date, time(8)),
            datetime.combine(work_date, time(12)),
        ),
    )
    assert out_of_window.status_code == 409
    assert "outside_availability" in {
        item["code"] for item in out_of_window.json()["detail"]["conflicts"]
    }

    invalid_update = client.put(
        f"/api/v1/scheduling/employees/{employee['id']}/availability",
        headers=headers,
        json={
            "windows": [
                {"weekday": weekday, "starts_at": "10:00", "ends_at": "17:00"},
            ]
        },
    )
    assert invalid_update.status_code == 409
    existing = client.get(f"/api/v1/scheduling/employees/{employee['id']}/availability")
    assert existing.status_code == 200
    assert existing.json()[0]["starts_at"] == "09:00:00"

    dst_shift = client.post(
        "/api/v1/scheduling/shifts",
        headers=headers,
        json=shift_payload(
            employee,
            obj,
            datetime(2027, 3, 28, 1, 30),
            datetime(2027, 3, 28, 3, 30),
        ),
    )
    assert dst_shift.status_code == 201, dst_shift.text
    assert datetime.fromisoformat(dst_shift.json()["ends_at"]) - datetime.fromisoformat(
        dst_shift.json()["starts_at"]
    ) == timedelta(hours=1)


def test_availability_requests_block_shifts_and_surface_unresolved_conflicts(
    client: TestClient,
) -> None:
    employee, obj, admin_csrf = setup_schedule(client)
    work_date = date.today() + timedelta(days=65)
    starts_at = datetime.combine(work_date, time(9))
    scheduled = client.post(
        "/api/v1/scheduling/shifts",
        headers={"X-CSRF-Token": admin_csrf},
        json=shift_payload(employee, obj, starts_at, starts_at + timedelta(hours=8)),
    )
    assert scheduled.status_code == 201, scheduled.text

    employee_csrf = sign_in(client, "dienstplan-person", "dienstplan-test-passwort-2026")
    request_payload = {
        "employee_id": employee["id"],
        "kind": "blocked",
        "starts_at_local": (starts_at + timedelta(hours=1)).isoformat(timespec="minutes"),
        "ends_at_local": (starts_at + timedelta(hours=2)).isoformat(timespec="minutes"),
    }
    submitted = client.post(
        "/api/v1/scheduling/availability-requests",
        headers={"X-CSRF-Token": employee_csrf},
        json=request_payload,
    )
    assert submitted.status_code == 201, submitted.text
    assert submitted.json()["status"] == "open"
    assert submitted.json()["conflicting_shift_ids"] == [scheduled.json()["id"]]

    preferred = client.post(
        "/api/v1/scheduling/availability-requests",
        headers={"X-CSRF-Token": employee_csrf},
        json={**request_payload, "kind": "preferred"},
    )
    assert preferred.status_code == 201, preferred.text
    assert preferred.json()["conflicting_shift_ids"] == []
    own_requests = client.get(
        "/api/v1/scheduling/availability-requests",
        params={"employee_id": employee["id"]},
    )
    assert own_requests.status_code == 200
    assert len(own_requests.json()) == 2

    other_user_id = create_employee_user("dienstplan-andere-person")
    admin_csrf = sign_in(client)
    other_employee_response = client.post(
        "/api/v1/employees",
        headers={"X-CSRF-Token": admin_csrf},
        json={
            "employee_number": "P-SCH-ANDERE",
            "user_id": str(other_user_id),
            "full_name": "Testperson andere Person",
            "hired_on": str(date.today() - timedelta(days=100)),
        },
    )
    assert other_employee_response.status_code == 201
    employee_csrf = sign_in(client, "dienstplan-person", "dienstplan-test-passwort-2026")
    denied = client.post(
        "/api/v1/scheduling/availability-requests",
        headers={"X-CSRF-Token": employee_csrf},
        json={**request_payload, "employee_id": other_employee_response.json()["id"]},
    )
    assert denied.status_code == 404

    admin_csrf = sign_in(client)
    blocked_payload = shift_payload(
        employee,
        obj,
        starts_at + timedelta(hours=1, minutes=15),
        starts_at + timedelta(hours=1, minutes=45),
    )
    blocked_payload["break_minutes"] = 0
    blocked_shift = client.post(
        "/api/v1/scheduling/shifts",
        headers={"X-CSRF-Token": admin_csrf},
        json=blocked_payload,
    )
    assert blocked_shift.status_code == 409
    assert "availability_blocked" in {
        item["code"] for item in blocked_shift.json()["detail"]["conflicts"]
    }
    accepted = client.patch(
        f"/api/v1/scheduling/availability-requests/{submitted.json()['id']}",
        headers={"X-CSRF-Token": admin_csrf},
        json={"status": "accepted"},
    )
    assert accepted.status_code == 409
    rejected = client.patch(
        f"/api/v1/scheduling/availability-requests/{submitted.json()['id']}",
        headers={"X-CSRF-Token": admin_csrf},
        json={"status": "rejected"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["conflicting_shift_ids"] == []


def test_shift_replacement_is_validated_and_audited(client: TestClient) -> None:
    employee, obj, csrf = setup_schedule(client)
    substitute = add_employee_to_object(client, obj, csrf, "vertretung")
    unassigned_user_id = create_employee_user("dienstplan-ohne-objekt")
    unassigned = client.post(
        "/api/v1/employees",
        headers={"X-CSRF-Token": csrf},
        json={
            "employee_number": "P-SCH-OHNE-OBJEKT",
            "user_id": str(unassigned_user_id),
            "full_name": "Testperson ohne Objekt",
            "hired_on": str(date.today() - timedelta(days=100)),
        },
    )
    assert unassigned.status_code == 201
    starts_at = datetime.combine(date.today() + timedelta(days=70), time(9))
    original = client.post(
        "/api/v1/scheduling/shifts",
        headers={"X-CSRF-Token": csrf},
        json=shift_payload(employee, obj, starts_at, starts_at + timedelta(hours=8)),
    )
    conflicting_shift = client.post(
        "/api/v1/scheduling/shifts",
        headers={"X-CSRF-Token": csrf},
        json=shift_payload(
            substitute,
            obj,
            starts_at + timedelta(hours=1),
            starts_at + timedelta(hours=3),
        ),
    )
    assert original.status_code == conflicting_shift.status_code == 201
    candidates = client.get(
        f"/api/v1/scheduling/shifts/{original.json()['id']}/replacement-candidates"
    )
    assert candidates.status_code == 200
    unavailable_candidate = next(
        item for item in candidates.json() if item["employee_id"] == substitute["id"]
    )
    assert unavailable_candidate["is_eligible"] is False
    assert unavailable_candidate["eligibility_reasons"] == []
    assert any(
        "bereits für einen Dienst eingeplant" in reason
        for reason in unavailable_candidate["exclusion_reasons"]
    )
    conflict = client.post(
        f"/api/v1/scheduling/shifts/{original.json()['id']}/replacement",
        headers={"X-CSRF-Token": csrf},
        json={"employee_id": substitute["id"], "reason": "short_notice"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["conflicts"][0]["code"] == "time_overlap"

    cancelled = client.post(
        f"/api/v1/scheduling/shifts/{conflicting_shift.json()['id']}/cancel",
        headers={"X-CSRF-Token": csrf},
    )
    assert cancelled.status_code == 200
    candidates = client.get(
        f"/api/v1/scheduling/shifts/{original.json()['id']}/replacement-candidates"
    )
    assert candidates.status_code == 200
    eligible_candidate = next(
        item for item in candidates.json() if item["employee_id"] == substitute["id"]
    )
    assert eligible_candidate["is_eligible"] is True
    assert eligible_candidate["exclusion_reasons"] == []
    assert any(
        "Objekt aktuell zugewiesen" in reason
        for reason in eligible_candidate["eligibility_reasons"]
    )
    assert any(
        "Dienstüberschneidung" in reason for reason in eligible_candidate["eligibility_reasons"]
    )

    stale_conflict = client.post(
        "/api/v1/scheduling/shifts",
        headers={"X-CSRF-Token": csrf},
        json=shift_payload(
            substitute,
            obj,
            starts_at + timedelta(hours=2),
            starts_at + timedelta(hours=4),
        ),
    )
    assert stale_conflict.status_code == 201
    stale_replacement = client.post(
        f"/api/v1/scheduling/shifts/{original.json()['id']}/replacement",
        headers={"X-CSRF-Token": csrf},
        json={"employee_id": substitute["id"], "reason": "short_notice"},
    )
    assert stale_replacement.status_code == 409
    assert any(
        item["code"] == "time_overlap" for item in stale_replacement.json()["detail"]["conflicts"]
    )
    assert (
        client.post(
            f"/api/v1/scheduling/shifts/{stale_conflict.json()['id']}/cancel",
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 200
    )

    replaced = client.post(
        f"/api/v1/scheduling/shifts/{original.json()['id']}/replacement",
        headers={"X-CSRF-Token": csrf},
        json={"employee_id": substitute["id"], "reason": "short_notice"},
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["employee_id"] == substitute["id"]
    history = client.get(f"/api/v1/scheduling/shifts/{original.json()['id']}/history")
    replacement_event = next(item for item in history.json() if item["action"] == "replaced")
    assert replacement_event["details"] == {
        "previous_employee_id": employee["id"],
        "replacement_employee_id": substitute["id"],
        "reason": "short_notice",
    }
    cancelled_candidates = client.get(
        f"/api/v1/scheduling/shifts/{conflicting_shift.json()['id']}/replacement-candidates"
    )
    assert cancelled_candidates.status_code == 409
    sign_in(client, "dienstplan-person", "dienstplan-test-passwort-2026")
    denied = client.get(f"/api/v1/scheduling/shifts/{original.json()['id']}/replacement-candidates")
    assert denied.status_code == 403


def test_replacement_candidates_explain_absence_availability_and_inactive_employee(
    client: TestClient,
) -> None:
    employee, obj, csrf = setup_schedule(client)
    substitute = add_employee_to_object(client, obj, csrf, "regeln")
    inactive = add_employee_to_object(client, obj, csrf, "inaktiv")
    unavailable = add_employee_to_object(client, obj, csrf, "verfuegbarkeit")
    starts_at = datetime.combine(date.today() + timedelta(days=75), time(9))
    original = client.post(
        "/api/v1/scheduling/shifts",
        headers={"X-CSRF-Token": csrf},
        json=shift_payload(employee, obj, starts_at, starts_at + timedelta(hours=8)),
    )
    assert original.status_code == 201, original.text

    with TestingSessionLocal() as db:
        db.add(
            EmployeeAbsence(
                employee_id=UUID(substitute["id"]),
                absence_type="vacation",
                starts_on=starts_at.date(),
                ends_on=starts_at.date(),
                status="approved",
            )
        )
        inactive_record = db.get(Employee, UUID(inactive["id"]))
        assert inactive_record is not None
        inactive_record.employment_status = "inactive"
        db.add(
            EmployeeAvailabilityWindow(
                employee_id=UUID(unavailable["id"]),
                weekday=starts_at.weekday(),
                starts_at=time(20),
                ends_at=time(21),
            )
        )
        db.commit()

    candidates = client.get(
        f"/api/v1/scheduling/shifts/{original.json()['id']}/replacement-candidates"
    )
    assert candidates.status_code == 200
    by_id = {item["employee_id"]: item for item in candidates.json()}
    absence_candidate = by_id[substitute["id"]]
    assert absence_candidate["is_eligible"] is False
    assert any("Abwesenheit" in reason for reason in absence_candidate["exclusion_reasons"])
    inactive_candidate = by_id[inactive["id"]]
    assert inactive_candidate["is_eligible"] is False
    assert any(
        "nicht aktiv beschäftigt" in reason for reason in inactive_candidate["exclusion_reasons"]
    )
    unavailable_candidate = by_id[unavailable["id"]]
    assert unavailable_candidate["is_eligible"] is False
    assert any(
        "außerhalb der regelmäßigen Verfügbarkeit" in reason
        for reason in unavailable_candidate["exclusion_reasons"]
    )

    rejected = client.post(
        f"/api/v1/scheduling/shifts/{original.json()['id']}/replacement",
        headers={"X-CSRF-Token": csrf},
        json={"employee_id": substitute["id"], "reason": "short_notice"},
    )
    assert rejected.status_code == 409
    assert any(
        item["code"] == "employee_absence" for item in rejected.json()["detail"]["conflicts"]
    )


def test_replacement_candidates_respect_object_scope(client: TestClient) -> None:
    employee, obj, csrf = setup_schedule(client)
    starts_at = datetime.combine(date.today() + timedelta(days=80), time(9))
    shift = client.post(
        "/api/v1/scheduling/shifts",
        headers={"X-CSRF-Token": csrf},
        json=shift_payload(employee, obj, starts_at, starts_at + timedelta(hours=8)),
    )
    assert shift.status_code == 201, shift.text

    with TestingSessionLocal() as db:
        role = Role(
            code="scoped-scheduling-manager",
            name="Einsatzleitung im Objektbereich",
            description="Testrolle für den Objektbereich",
            permissions=list(
                db.scalars(
                    select(Permission).where(
                        Permission.code.in_(("scheduling.manage", "employees.read"))
                    )
                ).all()
            ),
        )
        user = User(
            username="scoped-scheduling-manager",
            email="scoped-scheduling-manager@example.com",
            full_name="Test Einsatzleitung",
            password_hash=password_hasher.hash(ADMIN_PASSWORD),
            roles=[role],
        )
        db.add_all([role, user])
        db.commit()

    sign_in(client, "scoped-scheduling-manager", ADMIN_PASSWORD)
    response = client.get(f"/api/v1/scheduling/shifts/{shift.json()['id']}/replacement-candidates")
    assert response.status_code == 404


def test_qualification_absence_and_local_time_validation(client: TestClient) -> None:
    employee, obj, csrf = setup_schedule(client)
    headers = {"X-CSRF-Token": csrf}
    work_date = date.today() + timedelta(days=50)
    starts_at = datetime.combine(work_date, time(9))
    payload = shift_payload(employee, obj, starts_at, starts_at + timedelta(hours=8))
    payload["required_qualification"] = "Erste Hilfe"
    missing_qualification = client.post(
        "/api/v1/scheduling/shifts",
        headers=headers,
        json=payload,
    )
    assert missing_qualification.status_code == 409
    assert missing_qualification.json()["detail"]["conflicts"][0]["code"] == "qualification_missing"

    with TestingSessionLocal() as db:
        db.add(
            EmployeeQualification(
                employee_id=UUID(employee["id"]),
                category="Erste Hilfe",
                name="Erste Hilfe",
                valid_from=work_date - timedelta(days=1),
                expires_on=work_date + timedelta(days=30),
            )
        )
        db.commit()
    qualified_payload = shift_payload(
        employee,
        obj,
        datetime.combine(work_date + timedelta(days=10), time(9)),
        datetime.combine(work_date + timedelta(days=10), time(17)),
    )
    qualified_payload["required_qualification"] = "Erste Hilfe"
    qualified_shift = client.post(
        "/api/v1/scheduling/shifts",
        headers=headers,
        json=qualified_payload,
    )
    assert qualified_shift.status_code == 201, qualified_shift.text
    absence = client.post(
        f"/api/v1/employees/{employee['id']}/absences",
        headers=headers,
        json={
            "absence_type": "vacation",
            "starts_on": work_date.isoformat(),
            "ends_on": work_date.isoformat(),
            "status": "approved",
        },
    )
    assert absence.status_code == 201
    absent_employee = client.post("/api/v1/scheduling/shifts", headers=headers, json=payload)
    assert absent_employee.status_code == 409
    assert absent_employee.json()["detail"]["conflicts"][0]["code"] == "employee_absence"

    invalid_zone = client.patch(
        "/api/v1/scheduling/settings",
        headers=headers,
        json={"time_zone": "Not/A_Timezone", "minimum_rest_hours": 11},
    )
    assert invalid_zone.status_code == 422
    invalid_local_time = client.post(
        "/api/v1/scheduling/shifts",
        headers=headers,
        json=shift_payload(
            employee,
            obj,
            datetime(2027, 3, 28, 2, 30),
            datetime(2027, 3, 28, 4, 0),
        ),
    )
    assert invalid_local_time.status_code == 422
    assert "Zeitumstellung" in invalid_local_time.json()["detail"]
    first_occurrence = datetime(2027, 10, 31, 2, 30).replace(
        tzinfo=ZoneInfo("Europe/Berlin"),
        fold=0,
    )
    second_occurrence = first_occurrence.replace(fold=1)
    assert second_occurrence.astimezone(UTC) - first_occurrence.astimezone(UTC) == timedelta(
        hours=1
    )
    configured = client.patch(
        "/api/v1/scheduling/settings",
        headers=headers,
        json={"time_zone": "UTC", "minimum_rest_hours": 8},
    )
    assert configured.status_code == 200
    assert configured.json()["time_zone"] == "UTC"
    assert configured.json()["minimum_rest_hours"] == 8


def test_employee_must_be_assigned_to_the_scheduled_object(client: TestClient) -> None:
    employee, obj, csrf = setup_schedule(client)
    headers = {"X-CSRF-Token": csrf}
    removed = client.put(
        f"/api/v1/objects/{obj['id']}/assignments",
        headers=headers,
        json={"user_ids": []},
    )
    assert removed.status_code == 200
    starts_at = datetime.combine(date.today() + timedelta(days=80), time(9))
    conflict = client.post(
        "/api/v1/scheduling/shifts",
        headers=headers,
        json=shift_payload(employee, obj, starts_at, starts_at + timedelta(hours=8)),
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["conflicts"][0]["code"] == "object_assignment"


def test_object_qualification_requirements_cover_all_shift_assignment_paths(
    client: TestClient,
) -> None:
    employee, obj, csrf = setup_schedule(client)
    substitute = add_employee_to_object(client, obj, csrf, "qualifikation-vertretung")
    work_date = date.today() + timedelta(days=50)
    starts_at = datetime.combine(work_date, time(9))
    payload = shift_payload(employee, obj, starts_at, starts_at + timedelta(days=1, hours=2))

    draft = client.post(
        "/api/v1/scheduling/shifts",
        headers={"X-CSRF-Token": csrf},
        json=payload,
    )
    assert draft.status_code == 201, draft.text

    requirements_response = client.patch(
        f"/api/v1/objects/{obj['id']}",
        headers={"X-CSRF-Token": csrf},
        json={"qualification_requirements": ["Brandschutzhelfer"]},
    )
    assert requirements_response.status_code == 200, requirements_response.text
    assert requirements_response.json()["qualification_requirements"] == ["Brandschutzhelfer"]

    duplicate_requirements = client.patch(
        f"/api/v1/objects/{obj['id']}",
        headers={"X-CSRF-Token": csrf},
        json={"qualification_requirements": ["Brandschutzhelfer", " brandschutzhelfer "]},
    )
    assert duplicate_requirements.status_code == 422
    assert client.get(f"/api/v1/objects/{obj['id']}").json()["qualification_requirements"] == [
        "Brandschutzhelfer"
    ]

    missing_qualification = client.post(
        "/api/v1/scheduling/shifts",
        headers={"X-CSRF-Token": csrf},
        json=payload,
    )
    assert missing_qualification.status_code == 409
    conflict = missing_qualification.json()["detail"]["conflicts"][0]
    assert conflict["code"] == "object_qualification_missing"
    assert "Brandschutzhelfer" in conflict["message"]
    assert (
        client.post(
            f"/api/v1/scheduling/shifts/{draft.json()['id']}/publish",
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"/api/v1/scheduling/shifts/{draft.json()['id']}",
            headers={"X-CSRF-Token": csrf},
            json={"break_minutes": 20},
        ).status_code
        == 409
    )

    with TestingSessionLocal() as db:
        db.add_all(
            [
                EmployeeQualification(
                    employee_id=UUID(substitute["id"]),
                    category="Brandschutzhelfer",
                    name="Brandschutzhelfer",
                    valid_from=work_date - timedelta(days=10),
                    expires_on=work_date - timedelta(days=1),
                ),
                EmployeeQualification(
                    employee_id=UUID(substitute["id"]),
                    category="Brandschutzhelfer",
                    name="Brandschutzhelfer",
                    valid_from=work_date + timedelta(days=1),
                ),
                EmployeeQualification(
                    employee_id=UUID(substitute["id"]),
                    category="Brandschutzhelfer",
                    name="Brandschutzhelfer",
                    valid_from=work_date - timedelta(days=10),
                    expires_on=work_date + timedelta(days=10),
                    archived_at=datetime.now(UTC),
                ),
            ]
        )
        db.commit()

    candidates_url = f"/api/v1/scheduling/shifts/{draft.json()['id']}/replacement-candidates"
    candidates_response = client.get(candidates_url)
    assert candidates_response.status_code == 200
    qualification_candidate = next(
        item for item in candidates_response.json() if item["employee_id"] == substitute["id"]
    )
    assert qualification_candidate["is_eligible"] is False
    assert any(
        "Der gültige Qualifikationsnachweis" in reason
        for reason in qualification_candidate["exclusion_reasons"]
    )
    rejected_replacement = client.post(
        f"/api/v1/scheduling/shifts/{draft.json()['id']}/replacement",
        headers={"X-CSRF-Token": csrf},
        json={"employee_id": substitute["id"], "reason": "short_notice"},
    )
    assert rejected_replacement.status_code == 409
    assert (
        rejected_replacement.json()["detail"]["conflicts"][0]["code"]
        == "object_qualification_missing"
    )

    with TestingSessionLocal() as db:
        db.add(
            EmployeeQualification(
                employee_id=UUID(substitute["id"]),
                category="Brandschutzhelfer",
                name="Brandschutzhelfer",
                valid_from=work_date - timedelta(days=10),
                expires_on=work_date + timedelta(days=10),
            )
        )
        db.commit()

    candidates = client.get(candidates_url)
    assert candidates.status_code == 200
    assert [item["employee_id"] for item in candidates.json()] == [substitute["id"]]
    assert candidates.json()[0]["is_eligible"] is True
    assert any(
        "Brandschutzhelfer" in reason for reason in candidates.json()[0]["eligibility_reasons"]
    )
    replacement = client.post(
        f"/api/v1/scheduling/shifts/{draft.json()['id']}/replacement",
        headers={"X-CSRF-Token": csrf},
        json={"employee_id": substitute["id"], "reason": "short_notice"},
    )
    assert replacement.status_code == 200, replacement.text
    published = client.post(
        f"/api/v1/scheduling/shifts/{draft.json()['id']}/publish",
        headers={"X-CSRF-Token": csrf},
    )
    assert published.status_code == 200, published.text

    employee_csrf = sign_in(
        client,
        "dienstplan-qualifikation-vertretung",
        "dienstplan-test-passwort-2026",
    )
    denied = client.patch(
        f"/api/v1/objects/{obj['id']}",
        headers={"X-CSRF-Token": employee_csrf},
        json={"qualification_requirements": []},
    )
    assert denied.status_code == 403


def test_object_qualification_requirement_migration_is_registered() -> None:
    import importlib

    migration = importlib.import_module(
        "migrations.versions.0037_object_qualification_requirements"
    )
    assert migration.revision == "0037_object_qual_requirements"
    assert migration.down_revision == "0036_billing_approval_automation"


@pytest.mark.skipif(
    test_engine.dialect.name != "postgresql",
    reason="PostgreSQL-Migration und data-safe Downgrade",
)
def test_postgresql_object_qualification_requirements_migration_preserves_data(
    client: TestClient,
) -> None:
    import importlib

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect

    _, obj, csrf = setup_schedule(client)
    saved = client.patch(
        f"/api/v1/objects/{obj['id']}",
        headers={"X-CSRF-Token": csrf},
        json={"qualification_requirements": ["Brandschutzhelfer"]},
    )
    assert saved.status_code == 200, saved.text

    migration = importlib.import_module(
        "migrations.versions.0037_object_qualification_requirements"
    )
    with test_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        with (
            Operations.context(context),
            pytest.raises(RuntimeError, match="Objektqualifikations-Downgrade"),
        ):
            migration.downgrade()
        connection.rollback()
        assert context.get_current_revision() == "0041_owks_shift_handovers"
        assert inspect(connection).has_table("object_qualification_requirements")


def test_schedule_permissions_are_checked_server_side(client: TestClient) -> None:
    setup_schedule(client)
    settings = client.get("/api/v1/scheduling/settings")
    assert settings.status_code == 200

    employee_csrf = sign_in(client, "dienstplan-person", "dienstplan-test-passwort-2026")
    denied = client.patch(
        "/api/v1/scheduling/settings",
        headers={"X-CSRF-Token": employee_csrf},
        json={"time_zone": "UTC", "minimum_rest_hours": 8},
    )
    assert denied.status_code == 403
    assert client.get("/api/v1/scheduling/shifts").status_code == 200

    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": employee_csrf})
    assert client.get("/api/v1/scheduling/settings").status_code == 401


@pytest.mark.skipif(test_engine.dialect.name != "postgresql", reason="PostgreSQL-Constraint-Test")
def test_exclusion_constraint_rejects_overlapping_inserts(client: TestClient) -> None:
    employee, obj, _ = setup_schedule(client)
    employee_id = UUID(employee["id"])
    object_id = UUID(obj["id"])
    starts_at = datetime.now(UTC) + timedelta(days=60)
    with TestingSessionLocal() as db:
        db.add(
            ScheduleShift(
                employee_id=employee_id,
                object_id=object_id,
                starts_at=starts_at,
                ends_at=starts_at + timedelta(hours=4),
                break_minutes=0,
                status="draft",
            )
        )
        db.commit()
        db.add(
            ScheduleShift(
                employee_id=employee_id,
                object_id=object_id,
                starts_at=starts_at,
                ends_at=starts_at + timedelta(hours=4),
                break_minutes=0,
                status="draft",
            )
        )
        with pytest.raises(IntegrityError) as error:
            db.commit()
        assert error.value.orig.sqlstate == "23P01"
        assert error.value.orig.diag.constraint_name == "ex_schedule_shifts_employee_time"
        db.rollback()


@pytest.mark.skipif(
    test_engine.dialect.name != "postgresql", reason="PostgreSQL-Advisory-Lock-Test"
)
def test_parallel_api_overlapping_shifts_are_serialized(client: TestClient) -> None:
    employee, obj, _ = setup_schedule(client)
    starts_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=60)
    starts_at = starts_at.replace(second=0, microsecond=0)
    barrier = Barrier(2)

    def create_shift() -> tuple[int, dict]:
        with TestClient(app, base_url="https://testserver") as local_client:
            csrf = sign_in(local_client)
            barrier.wait(timeout=10)
            response = local_client.post(
                "/api/v1/scheduling/shifts",
                headers={"X-CSRF-Token": csrf},
                json=shift_payload(employee, obj, starts_at, starts_at + timedelta(hours=4)),
            )
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: create_shift(), range(2)))
    assert sorted(status_code for status_code, _ in results) == [201, 409]
    conflict = next(body for status_code, body in results if status_code == 409)
    assert any(item["code"] == "time_overlap" for item in conflict["detail"]["conflicts"])


@pytest.mark.skipif(
    test_engine.dialect.name != "postgresql", reason="PostgreSQL-Advisory-Lock-Test"
)
def test_parallel_block_request_and_shift_creation_are_serialized(client: TestClient) -> None:
    employee, obj, _ = setup_schedule(client)
    work_date = date.today() + timedelta(days=90)
    starts_at = datetime.combine(work_date, time(9))
    barrier = Barrier(2)

    def create_shift() -> int:
        with TestClient(app, base_url="https://testserver") as local_client:
            csrf = sign_in(local_client)
            barrier.wait(timeout=10)
            response = local_client.post(
                "/api/v1/scheduling/shifts",
                headers={"X-CSRF-Token": csrf},
                json=shift_payload(employee, obj, starts_at, starts_at + timedelta(hours=4)),
            )
            return response.status_code

    def create_block_request() -> tuple[int, list[str]]:
        with TestClient(app, base_url="https://testserver") as local_client:
            csrf = sign_in(local_client)
            barrier.wait(timeout=10)
            response = local_client.post(
                "/api/v1/scheduling/availability-requests",
                headers={"X-CSRF-Token": csrf},
                json={
                    "employee_id": employee["id"],
                    "kind": "blocked",
                    "starts_at_local": starts_at.isoformat(timespec="minutes"),
                    "ends_at_local": (starts_at + timedelta(hours=4)).isoformat(timespec="minutes"),
                },
            )
            assert response.status_code == 201, response.text
            return response.status_code, response.json()["conflicting_shift_ids"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        shift_future = pool.submit(create_shift)
        request_future = pool.submit(create_block_request)
        shift_status = shift_future.result()
        request_status, conflicting_shift_ids = request_future.result()
    assert request_status == 201
    assert (shift_status == 201 and len(conflicting_shift_ids) == 1) or (
        shift_status == 409 and conflicting_shift_ids == []
    )
