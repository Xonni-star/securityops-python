from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from conftest import TestingSessionLocal
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.identity_api import password_hasher
from app.models import (
    AuditLog,
    Customer,
    Employee,
    EmployeeAbsence,
    EmployeeQualification,
    Notification,
    NotificationOutbox,
    ObjectAssignment,
    Role,
    ScheduleAvailabilityRequest,
    ScheduleShift,
    SecurityObject,
    Task,
    TimeEntry,
    TimeEntrySegment,
    User,
)

EMPLOYEE_PASSWORD = "mitarbeiter-test-passwort-2026"


def create_linked_employee(
    username: str,
    *,
    employment_status: str = "active",
    archived: bool = False,
) -> tuple[UUID, UUID]:
    with TestingSessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "employee"))
        assert role is not None
        user = User(
            username=username,
            email=f"{username}@example.de",
            full_name=f"Testkonto {username}",
            password_hash=password_hasher.hash(EMPLOYEE_PASSWORD),
            roles=[role],
        )
        employee = Employee(
            employee_number=f"P-{username.upper()}",
            user=user,
            full_name=f"Testmitarbeiter {username}",
            email=f"{username}.personal@example.de",
            job_title="Sicherheitsmitarbeiter",
            employment_status=employment_status,
            hired_on=date(2020, 1, 1),
            archived_at=datetime.now(UTC) if archived else None,
        )
        db.add(employee)
        db.commit()
        return user.id, employee.id


def create_user_without_employee_role(username: str) -> UUID:
    with TestingSessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "hr"))
        assert role is not None
        user = User(
            username=username,
            email=f"{username}@example.de",
            full_name=f"Testkonto {username}",
            password_hash=password_hasher.hash(EMPLOYEE_PASSWORD),
            roles=[role],
        )
        db.add(user)
        db.commit()
        return user.id


def sign_in(client: TestClient, username: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": EMPLOYEE_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return client.cookies.get("securityops_csrf", "")


def seed_portal_records(
    employee_id: UUID, user_id: UUID, other_employee_id: UUID, other_user_id: UUID
):
    with TestingSessionLocal() as db:
        customer = Customer(
            customer_number=f"K-{uuid4().hex[:8]}",
            company_name="Portal-Testkunde",
        )
        obj = SecurityObject(
            customer=customer,
            code=f"O-{uuid4().hex[:8]}",
            name="Portal-Testobjekt",
            description="Vertrauliche Objektbeschreibung",
        )
        unassigned_object = SecurityObject(
            customer=customer,
            code=f"O-{uuid4().hex[:8]}",
            name="Nicht zugewiesenes Objekt",
        )
        db.add(ObjectAssignment(user_id=user_id, object=obj))
        starts_at = datetime.now(UTC) + timedelta(days=2)
        published_shift = ScheduleShift(
            employee_id=employee_id,
            object=obj,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=8),
            break_minutes=30,
            required_qualification="Interne Zusatzqualifikation",
            status="published",
        )
        draft_shift = ScheduleShift(
            employee_id=employee_id,
            object=obj,
            starts_at=starts_at + timedelta(days=1),
            ends_at=starts_at + timedelta(days=1, hours=8),
            status="draft",
        )
        foreign_shift = ScheduleShift(
            employee_id=other_employee_id,
            object=obj,
            starts_at=starts_at + timedelta(days=2),
            ends_at=starts_at + timedelta(days=2, hours=8),
            status="published",
        )
        unassigned_shift = ScheduleShift(
            employee_id=employee_id,
            object=unassigned_object,
            starts_at=starts_at + timedelta(days=3),
            ends_at=starts_at + timedelta(days=3, hours=8),
            status="published",
        )
        own_task = Task(
            title="Eigene Aufgabe",
            description="Nicht für das Portal freigegebene interne Notiz",
            assigned_to_id=user_id,
            created_by_id=other_user_id,
            completion_evidence="Interner Erledigungsnachweis",
        )
        foreign_task = Task(
            title="Fremde Aufgabe",
            assigned_to_id=other_user_id,
        )
        qualification = EmployeeQualification(
            employee_id=employee_id,
            category="Erste Hilfe",
            name="Betriebliche Ersthelferschulung",
            issuer="Schulungsanbieter",
            valid_from=date(2025, 1, 1),
            expires_on=date(2027, 1, 1),
        )
        foreign_qualification = EmployeeQualification(
            employee_id=other_employee_id,
            category="Other",
            name="Fremde Qualifikation",
        )
        foreign_absence = EmployeeAbsence(
            employee_id=other_employee_id,
            absence_type="vacation",
            starts_on=date(2026, 12, 10),
            ends_on=date(2026, 12, 12),
            status="approved",
            created_by_id=other_user_id,
        )
        foreign_availability = ScheduleAvailabilityRequest(
            employee_id=other_employee_id,
            kind="blocked",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=4),
            status="open",
            created_by_id=other_user_id,
        )
        db.add_all(
            [
                customer,
                published_shift,
                draft_shift,
                foreign_shift,
                unassigned_shift,
                own_task,
                foreign_task,
                qualification,
                foreign_qualification,
                foreign_absence,
                foreign_availability,
            ]
        )
        db.flush()
        own_entry = TimeEntry(
            employee_id=employee_id,
            object=obj,
            started_at=datetime.now(UTC) - timedelta(hours=4),
            ended_at=datetime.now(UTC) - timedelta(hours=1),
            status="approved",
            decision_reason="Interne HR-Notiz",
        )
        db.add(own_entry)
        db.flush()
        db.add_all(
            [
                TimeEntrySegment(
                    entry_id=own_entry.id,
                    position=1,
                    kind="work",
                    started_at=own_entry.started_at,
                    ended_at=own_entry.started_at + timedelta(hours=2),
                ),
                TimeEntrySegment(
                    entry_id=own_entry.id,
                    position=2,
                    kind="break",
                    started_at=own_entry.started_at + timedelta(hours=2),
                    ended_at=own_entry.ended_at,
                ),
                TimeEntry(
                    employee_id=other_employee_id,
                    object=obj,
                    started_at=datetime.now(UTC) - timedelta(days=1),
                    status="open",
                ),
                TimeEntry(
                    employee_id=employee_id,
                    object=unassigned_object,
                    started_at=datetime.now(UTC) - timedelta(days=2),
                    status="open",
                ),
            ]
        )
        own_outbox = NotificationOutbox(
            dedupe_key=f"portal-own-{uuid4()}",
            event_type="task.assigned",
            aggregate_type="task",
            aggregate_id=own_task.id,
            payload={},
        )
        foreign_outbox = NotificationOutbox(
            dedupe_key=f"portal-foreign-{uuid4()}",
            event_type="task.assigned",
            aggregate_type="task",
            aggregate_id=foreign_task.id,
            payload={},
        )
        db.add_all([own_outbox, foreign_outbox])
        db.flush()
        own_notification = Notification(
            outbox_id=own_outbox.id,
            recipient_id=user_id,
            task_id=own_task.id,
            event_type="task.assigned",
            title="Neue eigene Aufgabe",
            body=own_task.title,
        )
        foreign_notification = Notification(
            outbox_id=foreign_outbox.id,
            recipient_id=other_user_id,
            task_id=foreign_task.id,
            event_type="task.assigned",
            title="Fremde Benachrichtigung",
            body=foreign_task.title,
        )
        db.add_all([own_notification, foreign_notification])
        db.commit()
        return {
            "published_shift_id": published_shift.id,
            "draft_shift_id": draft_shift.id,
            "foreign_shift_id": foreign_shift.id,
            "unassigned_shift_id": unassigned_shift.id,
            "own_notification_id": own_notification.id,
            "foreign_notification_id": foreign_notification.id,
            "own_entry_id": own_entry.id,
        }


def test_employee_portal_returns_only_minimized_own_data(client: TestClient) -> None:
    user_id, employee_id = create_linked_employee("portal-eins")
    other_user_id, other_employee_id = create_linked_employee("portal-zwei")
    record_ids = seed_portal_records(employee_id, user_id, other_employee_id, other_user_id)
    sign_in(client, "portal-eins")

    profile = client.get("/api/v1/employee-portal/me")
    assert client.get("/api/v1/employees").status_code == 403
    shifts = client.get("/api/v1/employee-portal/me/shifts")
    shift_detail = client.get(
        f"/api/v1/employee-portal/me/shifts/{record_ids['published_shift_id']}"
    )
    tasks = client.get("/api/v1/employee-portal/me/tasks")
    notifications = client.get("/api/v1/employee-portal/me/notifications")
    qualifications = client.get("/api/v1/employee-portal/me/qualifications")
    time_entries = client.get("/api/v1/employee-portal/me/time-entries")
    absences = client.get("/api/v1/employee-portal/me/absences")
    availability_requests = client.get("/api/v1/employee-portal/me/availability-requests")

    assert profile.status_code == 200
    assert profile.json() == {
        "full_name": "Testmitarbeiter portal-eins",
        "job_title": "Sicherheitsmitarbeiter",
    }
    assert "employee_id" not in profile.json()
    assert shifts.status_code == 200
    assert len(shifts.json()) == 1
    assert shifts.json()[0]["id"] == str(record_ids["published_shift_id"])
    assert "required_qualification" not in shifts.json()[0]
    assert shift_detail.json()["object_name"] == "Portal-Testobjekt"
    assert "description" not in shift_detail.json()
    assert (
        client.get(
            f"/api/v1/employee-portal/me/shifts/{record_ids['foreign_shift_id']}"
        ).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/employee-portal/me/shifts/{record_ids['draft_shift_id']}").status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/employee-portal/me/shifts/{record_ids['unassigned_shift_id']}"
        ).status_code
        == 404
    )
    assert tasks.status_code == 200
    assert [item["title"] for item in tasks.json()] == ["Eigene Aufgabe"]
    assert "description" not in tasks.json()[0]
    assert "completion_evidence" not in tasks.json()[0]
    assert notifications.status_code == 200
    assert [item["title"] for item in notifications.json()] == ["Neue eigene Aufgabe"]
    assert notifications.json()[0]["id"] == str(record_ids["own_notification_id"])
    assert qualifications.status_code == 200
    assert len(qualifications.json()) == 1
    assert qualifications.json()[0]["name"] == "Betriebliche Ersthelferschulung"
    assert "documents" not in qualifications.json()[0]
    assert time_entries.status_code == 200
    assert time_entries.json()["total"] == 1
    assert time_entries.json()["items"][0]["id"] == str(record_ids["own_entry_id"])
    assert time_entries.json()["items"][0]["actual_work_seconds"] == 7200
    assert "decision_reason" not in time_entries.json()["items"][0]
    assert absences.status_code == 200
    assert absences.json() == []
    assert availability_requests.status_code == 200
    assert availability_requests.json() == []


def test_employee_portal_requests_are_owned_pending_and_not_self_approvable(
    client: TestClient,
) -> None:
    _, employee_id = create_linked_employee("portal-antrag")
    csrf = sign_in(client, "portal-antrag")
    headers = {"X-CSRF-Token": csrf}

    absence = client.post(
        "/api/v1/employee-portal/me/absences",
        headers=headers,
        json={
            "absence_type": "vacation",
            "starts_on": "2026-12-01",
            "ends_on": "2026-12-03",
            "status": "approved",
        },
    )
    assert absence.status_code == 422
    assert (
        client.post(
            "/api/v1/employee-portal/me/absences",
            headers=headers,
            json={
                "employee_id": str(uuid4()),
                "absence_type": "vacation",
                "starts_on": "2026-12-01",
                "ends_on": "2026-12-03",
            },
        ).status_code
        == 422
    )
    absence = client.post(
        "/api/v1/employee-portal/me/absences",
        headers=headers,
        json={
            "absence_type": "vacation",
            "starts_on": "2026-12-01",
            "ends_on": "2026-12-03",
        },
    )
    assert absence.status_code == 201, absence.text
    assert absence.json()["status"] == "pending"
    assert absence.json()["id"]

    availability = client.post(
        "/api/v1/employee-portal/me/availability-requests",
        headers=headers,
        json={
            "kind": "blocked",
            "starts_at_local": "2026-12-05T08:00:00",
            "ends_at_local": "2026-12-05T12:00:00",
        },
    )
    assert availability.status_code == 201, availability.text
    assert availability.json()["status"] == "open"
    assert availability.json()["time_zone"] == "Europe/Berlin"
    assert (
        client.post(
            "/api/v1/employee-portal/me/availability-requests",
            headers=headers,
            json={
                "employee_id": str(uuid4()),
                "kind": "blocked",
                "starts_at_local": "2026-12-05T08:00:00",
                "ends_at_local": "2026-12-05T12:00:00",
            },
        ).status_code
        == 422
    )

    with TestingSessionLocal() as db:
        saved_absence = db.scalar(
            select(EmployeeAbsence).where(EmployeeAbsence.employee_id == employee_id)
        )
        assert saved_absence is not None
        assert saved_absence.status == "pending"
        assert saved_absence.created_by_id is not None
        assert (
            db.scalar(
                select(EmployeeAbsence.status).where(
                    EmployeeAbsence.id == UUID(absence.json()["id"])
                )
            )
            == "pending"
        )
        request_record = db.scalar(
            select(ScheduleAvailabilityRequest).where(
                ScheduleAvailabilityRequest.employee_id == employee_id
            )
        )
        assert request_record is not None
        assert request_record.status == "open"
        assert request_record.created_by_id == saved_absence.created_by_id


def test_employee_portal_can_edit_only_own_undecided_requests(client: TestClient) -> None:
    _, _ = create_linked_employee("portal-bearbeiten")
    _, other_employee_id = create_linked_employee("portal-bearbeiten-fremd")
    csrf = sign_in(client, "portal-bearbeiten")
    headers = {"X-CSRF-Token": csrf}
    absence = client.post(
        "/api/v1/employee-portal/me/absences",
        headers=headers,
        json={
            "absence_type": "vacation",
            "starts_on": "2026-12-01",
            "ends_on": "2026-12-03",
        },
    )
    availability = client.post(
        "/api/v1/employee-portal/me/availability-requests",
        headers=headers,
        json={
            "kind": "blocked",
            "starts_at_local": "2026-12-05T08:00:00",
            "ends_at_local": "2026-12-05T12:00:00",
        },
    )
    assert absence.status_code == 201
    assert availability.status_code == 201
    absence_id = UUID(absence.json()["id"])
    availability_id = UUID(availability.json()["id"])

    updated_absence = client.patch(
        f"/api/v1/employee-portal/me/absences/{absence_id}",
        headers=headers,
        json={"starts_on": "2026-12-02", "ends_on": "2026-12-04"},
    )
    updated_availability = client.patch(
        f"/api/v1/employee-portal/me/availability-requests/{availability_id}",
        headers=headers,
        json={"kind": "preferred"},
    )
    assert updated_absence.status_code == 200, updated_absence.text
    assert updated_absence.json()["starts_on"] == "2026-12-02"
    assert updated_absence.json()["history"][-1]["event"] == "updated"
    assert updated_availability.status_code == 200, updated_availability.text
    assert updated_availability.json()["kind"] == "preferred"
    assert updated_availability.json()["history"][-1]["event"] == "updated"

    with TestingSessionLocal() as db:
        foreign_absence = EmployeeAbsence(
            employee_id=other_employee_id,
            absence_type="vacation",
            starts_on=date(2026, 12, 1),
            ends_on=date(2026, 12, 2),
            status="pending",
        )
        foreign_request = ScheduleAvailabilityRequest(
            employee_id=other_employee_id,
            kind="blocked",
            starts_at=datetime(2026, 12, 5, 7, tzinfo=UTC),
            ends_at=datetime(2026, 12, 5, 11, tzinfo=UTC),
            status="open",
        )
        db.add_all([foreign_absence, foreign_request])
        db.commit()
        foreign_absence_id = foreign_absence.id
        foreign_request_id = foreign_request.id

    for path, body in (
        (
            f"/api/v1/employee-portal/me/absences/{foreign_absence_id}",
            {"starts_on": "2026-12-02"},
        ),
        (
            f"/api/v1/employee-portal/me/availability-requests/{foreign_request_id}",
            {"kind": "preferred"},
        ),
    ):
        assert client.patch(path, headers=headers, json=body).status_code == 404

    assert (
        client.patch(
            f"/api/v1/employee-portal/me/absences/{absence_id}",
            headers=headers,
            json={"status": "approved"},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/employee-portal/me/absences/{absence_id}",
            headers=headers,
            json={"starts_on": "2026-12-05", "ends_on": "2026-12-04"},
        ).status_code
        == 422
    )

    with TestingSessionLocal() as db:
        saved_absence = db.get(EmployeeAbsence, absence_id)
        saved_request = db.get(ScheduleAvailabilityRequest, availability_id)
        assert saved_absence is not None
        assert saved_request is not None
        saved_absence.status = "approved"
        saved_request.status = "accepted"
        saved_request.reviewed_at = datetime.now(UTC)
        db.commit()
        absence_decision_log = AuditLog(
            action="employee_portal.absence_updated",
            entity_type="employee_absence",
            entity_id=str(absence_id),
            details={"fields": ["status"]},
        )
        availability_decision_log = AuditLog(
            action="scheduling.availability_request_reviewed",
            entity_type="schedule_availability_request",
            entity_id=str(availability_id),
            details={"status": "accepted"},
        )
        db.add_all([absence_decision_log, availability_decision_log])
        db.commit()
    assert (
        client.patch(
            f"/api/v1/employee-portal/me/absences/{absence_id}",
            headers=headers,
            json={"starts_on": "2026-12-03"},
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"/api/v1/employee-portal/me/availability-requests/{availability_id}",
            headers=headers,
            json={"kind": "blocked"},
        ).status_code
        == 409
    )
    assert (
        client.get("/api/v1/employee-portal/me/availability-requests").json()[0]["history"][-1][
            "event"
        ]
        == "accepted"
    )
    with TestingSessionLocal() as db:
        assert db.get(EmployeeAbsence, absence_id) is not None
        assert db.get(ScheduleAvailabilityRequest, availability_id) is not None
        actions = db.scalars(
            select(AuditLog.action).where(
                AuditLog.entity_id.in_([str(absence_id), str(availability_id)])
            )
        ).all()
        assert "employee_portal.absence_updated" in actions
        assert "employee_portal.availability_updated" in actions


def test_employee_portal_authentication_role_and_active_link_are_required(
    client: TestClient,
) -> None:
    assert client.get("/api/v1/employee-portal/me").status_code == 401
    create_user_without_employee_role("portal-hr")
    sign_in(client, "portal-hr")
    assert client.get("/api/v1/employee-portal/me").status_code == 403
    assert client.get("/api/v1/employees").status_code == 200

    client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": client.cookies.get("securityops_csrf")}
    )
    with TestingSessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "employee"))
        assert role is not None
        user = User(
            username="portal-unlinked",
            email="portal-unlinked@example.de",
            full_name="Nicht verknüpft",
            password_hash=password_hasher.hash(EMPLOYEE_PASSWORD),
            roles=[role],
        )
        db.add(user)
        db.commit()
    sign_in(client, "portal-unlinked")
    assert client.get("/api/v1/employee-portal/me").status_code == 404

    client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": client.cookies.get("securityops_csrf")}
    )
    create_linked_employee("portal-inaktiv", employment_status="inactive")
    sign_in(client, "portal-inaktiv")
    assert client.get("/api/v1/employee-portal/me").status_code == 404


def test_employee_portal_notification_mark_read_is_idor_safe(client: TestClient) -> None:
    user_id, employee_id = create_linked_employee("portal-notification-eins")
    other_user_id, other_employee_id = create_linked_employee("portal-notification-zwei")
    record_ids = seed_portal_records(employee_id, user_id, other_employee_id, other_user_id)
    csrf = sign_in(client, "portal-notification-eins")

    own = client.patch(
        f"/api/v1/employee-portal/me/notifications/{record_ids['own_notification_id']}/read",
        headers={"X-CSRF-Token": csrf},
    )
    foreign = client.patch(
        f"/api/v1/employee-portal/me/notifications/{record_ids['foreign_notification_id']}/read",
        headers={"X-CSRF-Token": csrf},
    )

    assert own.status_code == 200
    assert own.json()["read_at"] is not None
    assert foreign.status_code == 404
    with TestingSessionLocal() as db:
        foreign_notification = db.get(Notification, record_ids["foreign_notification_id"])
        assert foreign_notification is not None
        assert foreign_notification.read_at is None


def test_employee_portal_denies_inactive_archived_and_hr_only_access(client: TestClient) -> None:
    create_linked_employee("portal-archiviert", archived=True)
    sign_in(client, "portal-archiviert")
    assert client.get("/api/v1/employee-portal/me").status_code == 404

    client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": client.cookies.get("securityops_csrf")}
    )
    create_user_without_employee_role("portal-hr-only")
    sign_in(client, "portal-hr-only")
    assert client.get("/api/v1/employee-portal/me/qualifications").status_code == 403
    assert client.get("/api/v1/employee-portal/me/absences").status_code == 403
