from datetime import date, timedelta
from uuid import UUID

from conftest import ADMIN_PASSWORD, TestingSessionLocal
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.identity_api import password_hasher
from app.malware_scanner import MalwareScannerError
from app.models import (
    EmployeeQualificationDocument,
    ObjectAssignment,
    Permission,
    Role,
    User,
)


def sign_in_as(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return client.cookies.get("securityops_csrf", "")


def create_test_user(username: str, role_code: str, *, is_active: bool = True) -> UUID:
    with TestingSessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == role_code))
        assert role is not None
        user = User(
            username=username,
            email=f"{username}@example.com",
            full_name=f"Test {username}",
            password_hash=password_hasher.hash("personal-test-passwort-2026"),
            is_active=is_active,
            roles=[role],
        )
        db.add(user)
        db.commit()
        return user.id


def create_test_user_with_permissions(username: str, permission_codes: tuple[str, ...]) -> UUID:
    with TestingSessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "personnel_auditor"))
        if role is None:
            role = Role(
                code="personnel_auditor",
                name="Personal-Auditor",
                description="Testrolle mit eingeschränktem Personalzugriff",
            )
        role.permissions = list(
            db.scalars(select(Permission).where(Permission.code.in_(permission_codes))).all()
        )
        user = User(
            username=username,
            email=f"{username}@example.com",
            full_name=f"Test {username}",
            password_hash=password_hasher.hash("personal-test-passwort-2026"),
            is_active=True,
            roles=[role],
        )
        db.add(user)
        db.commit()
        return user.id


def test_employee_management_qualification_expiry_and_retention(client: TestClient) -> None:
    admin_headers = {"X-CSRF-Token": sign_in_as(client, "admin", ADMIN_PASSWORD)}
    employee_user_id = create_test_user("mitarbeiterkonto", "employee")
    today = date.today()
    created = client.post(
        "/api/v1/employees",
        headers=admin_headers,
        json={
            "employee_number": "P-1001",
            "user_id": str(employee_user_id),
            "full_name": "Testperson Beispiel",
            "email": "PERSON@example.com",
            "job_title": "Sicherheitsmitarbeiter",
            "hired_on": str(today - timedelta(days=30)),
            "contract_type": "Vollzeit",
            "weekly_hours": 40,
        },
    )
    assert created.status_code == 201
    employee = created.json()
    assert employee["email"] == "person@example.com"
    assert employee["user_id"] == str(employee_user_id)
    assert "address" not in employee
    assert "internal_notes" not in employee
    duplicate_user_link = client.post(
        "/api/v1/employees",
        headers=admin_headers,
        json={
            "employee_number": "P-1003",
            "user_id": str(employee_user_id),
            "full_name": "Doppelte Kontoverknüpfung",
            "hired_on": str(today),
        },
    )
    assert duplicate_user_link.status_code == 409
    inactive_user_id = create_test_user("deaktiviertes-konto", "employee", is_active=False)
    inactive_user_link = client.post(
        "/api/v1/employees",
        headers=admin_headers,
        json={
            "employee_number": "P-1004",
            "user_id": str(inactive_user_id),
            "full_name": "Konto nicht aktiv",
            "hired_on": str(today),
        },
    )
    assert inactive_user_link.status_code == 422
    assert (
        client.patch(
            f"/api/v1/employees/{employee['id']}",
            headers=admin_headers,
            json={"hired_on": None},
        ).status_code
        == 422
    )

    absence = client.post(
        f"/api/v1/employees/{employee['id']}/absences",
        headers=admin_headers,
        json={
            "absence_type": "vacation",
            "starts_on": str(today + timedelta(days=5)),
            "ends_on": str(today + timedelta(days=9)),
        },
    )
    assert absence.status_code == 201
    invalid_absence = client.post(
        f"/api/v1/employees/{employee['id']}/absences",
        headers=admin_headers,
        json={
            "absence_type": "vacation",
            "starts_on": str(today + timedelta(days=9)),
            "ends_on": str(today + timedelta(days=5)),
        },
    )
    assert invalid_absence.status_code == 422
    approved_absence = client.patch(
        f"/api/v1/employees/{employee['id']}/absences/{absence.json()['id']}",
        headers=admin_headers,
        json={"status": "approved"},
    )
    assert approved_absence.status_code == 200
    assert approved_absence.json()["status"] == "approved"

    duplicate = client.post(
        "/api/v1/employees",
        headers=admin_headers,
        json={
            "employee_number": "P-1001",
            "full_name": "Andere Person",
            "hired_on": str(today),
        },
    )
    assert duplicate.status_code == 409
    assert client.get("/api/v1/employees").json()["total"] == 1

    invalid_dates = client.post(
        "/api/v1/employees",
        headers=admin_headers,
        json={
            "employee_number": "P-1002",
            "full_name": "Ungültige Datumsangaben",
            "hired_on": str(today),
            "ended_on": str(today - timedelta(days=1)),
        },
    )
    assert invalid_dates.status_code == 422

    qualification = client.post(
        f"/api/v1/employees/{employee['id']}/qualifications",
        headers=admin_headers,
        json={
            "category": "Unterweisung",
            "name": "Arbeitsschutz",
            "issuer": "Interne Schulung",
            "valid_from": str(today - timedelta(days=20)),
            "expires_on": str(today + timedelta(days=10)),
        },
    )
    assert qualification.status_code == 201
    assert (
        client.patch(
            f"/api/v1/employees/{employee['id']}/qualifications/{qualification.json()['id']}",
            headers=admin_headers,
            json={"name": None},
        ).status_code
        == 422
    )
    past_due = client.post(
        f"/api/v1/employees/{employee['id']}/qualifications",
        headers=admin_headers,
        json={
            "category": "Zertifikat",
            "name": "Erste Hilfe",
            "expires_on": str(today - timedelta(days=2)),
        },
    )
    assert past_due.status_code == 201
    far_future = client.post(
        f"/api/v1/employees/{employee['id']}/qualifications",
        headers=admin_headers,
        json={
            "category": "Qualifikation",
            "name": "Brandschutz",
            "expires_on": str(today + timedelta(days=90)),
        },
    )
    assert far_future.status_code == 201

    invalid_qualification_dates = client.post(
        f"/api/v1/employees/{employee['id']}/qualifications",
        headers=admin_headers,
        json={
            "category": "Zertifikat",
            "name": "Ungültig",
            "valid_from": str(today),
            "expires_on": str(today - timedelta(days=1)),
        },
    )
    assert invalid_qualification_dates.status_code == 422

    expiring = client.get("/api/v1/employees/qualifications/expiring", params={"days": 30})
    assert expiring.status_code == 200
    assert {row["name"] for row in expiring.json()} == {"Arbeitsschutz", "Erste Hilfe"}
    overdue = next(row for row in expiring.json() if row["name"] == "Erste Hilfe")
    assert overdue["days_until_expiry"] == -2

    archived_qualification = client.post(
        f"/api/v1/employees/{employee['id']}/qualifications/{qualification.json()['id']}/archive",
        headers=admin_headers,
    )
    assert archived_qualification.status_code == 200
    assert len(client.get(f"/api/v1/employees/{employee['id']}/qualifications").json()) == 2
    assert (
        len(
            client.get(
                f"/api/v1/employees/{employee['id']}/qualifications",
                params={"include_archived": True},
            ).json()
        )
        == 3
    )

    archived_employee = client.post(
        f"/api/v1/employees/{employee['id']}/archive",
        headers=admin_headers,
    )
    assert archived_employee.status_code == 200
    assert archived_employee.json()["archived_at"] is not None
    assert client.get("/api/v1/employees").json()["total"] == 0
    assert client.get("/api/v1/employees", params={"include_archived": True}).json()["total"] == 1
    assert len(client.get(f"/api/v1/employees/{employee['id']}/qualifications").json()) == 2
    assert len(client.get(f"/api/v1/employees/{employee['id']}/absences").json()) == 1
    history = client.get(f"/api/v1/employees/{employee['id']}/history")
    assert history.status_code == 200
    assert {row["action"] for row in history.json()} >= {
        "created",
        "qualification_created",
        "qualification_archived",
        "absence_created",
        "absence_updated",
        "archived",
    }

    reactivated = client.post(
        f"/api/v1/employees/{employee['id']}/reactivate",
        headers=admin_headers,
    )
    assert reactivated.status_code == 200
    assert reactivated.json()["archived_at"] is None


def test_sensitive_employee_details_are_separately_authorized(client: TestClient) -> None:
    admin_headers = {"X-CSRF-Token": sign_in_as(client, "admin", ADMIN_PASSWORD)}
    employee = client.post(
        "/api/v1/employees",
        headers=admin_headers,
        json={
            "employee_number": "P-2001",
            "full_name": "Sensible Testperson",
            "hired_on": str(date.today()),
        },
    ).json()
    saved = client.patch(
        f"/api/v1/employees/{employee['id']}/sensitive",
        headers=admin_headers,
        json={
            "address": "Beispielstraße 1, 12345 Beispielstadt",
            "emergency_contact": "Testkontakt 0123 456789",
            "internal_notes": "Nur für berechtigte Personalverwaltung",
        },
    )
    assert saved.status_code == 200
    assert "internal_notes" not in client.get("/api/v1/employees").json()["items"][0]
    assert "internal_notes" not in client.get(f"/api/v1/employees/{employee['id']}").json()

    create_test_user("personalverwaltung", "hr")
    sign_in_as(client, "personalverwaltung", "personal-test-passwort-2026")
    assert (
        client.get(f"/api/v1/employees/{employee['id']}/sensitive").json()["emergency_contact"]
        == "Testkontakt 0123 456789"
    )
    history = client.get(f"/api/v1/employees/{employee['id']}/history").json()
    sensitive_event = next(row for row in history if row["action"] == "sensitive_updated")
    assert "emergency_contact" in sensitive_event["changed_fields"]
    assert "Testkontakt 0123 456789" not in str(sensitive_event)

    create_test_user("personal-leser", "management")
    manager_headers = {
        "X-CSRF-Token": sign_in_as(client, "personal-leser", "personal-test-passwort-2026")
    }
    assert client.get("/api/v1/employees").status_code == 200
    assert client.get(f"/api/v1/employees/{employee['id']}/sensitive").status_code == 403
    assert (
        client.patch(
            f"/api/v1/employees/{employee['id']}/sensitive",
            headers=manager_headers,
            json={"internal_notes": "Keine Berechtigung"},
        ).status_code
        == 403
    )

    create_test_user("normaler-mitarbeiter", "employee")
    sign_in_as(client, "normaler-mitarbeiter", "personal-test-passwort-2026")
    assert client.get("/api/v1/employees").status_code == 403


def test_employee_object_assignments_update_object_access_and_keep_history(
    client: TestClient,
) -> None:
    admin_headers = {"X-CSRF-Token": sign_in_as(client, "admin", ADMIN_PASSWORD)}
    employee_user_id = create_test_user("zugewiesenes-konto", "employee")
    employee = client.post(
        "/api/v1/employees",
        headers=admin_headers,
        json={
            "employee_number": "P-3001",
            "user_id": str(employee_user_id),
            "full_name": "Zugewiesene Testperson",
            "hired_on": str(date.today()),
        },
    ).json()
    customer = client.post(
        "/api/v1/customers",
        headers=admin_headers,
        json={"company_name": "Testkunde Zuweisung GmbH"},
    ).json()
    obj = client.post(
        "/api/v1/objects",
        headers=admin_headers,
        json={
            "customer_id": customer["id"],
            "name": "Testobjekt Zuweisung",
            "code": "OBJ-PERSONAL-1",
        },
    ).json()

    candidates = client.get("/api/v1/employees/object-assignment-candidates")
    assert candidates.status_code == 200
    assert any(item["object_id"] == obj["id"] for item in candidates.json())
    assigned = client.post(
        f"/api/v1/employees/{employee['id']}/objects/{obj['id']}", headers=admin_headers
    )
    assert assigned.status_code == 201
    assert assigned.json()[0]["object_id"] == obj["id"]
    assert client.get(f"/api/v1/employees/{employee['id']}").json()["assigned_objects"] == [
        "Testobjekt Zuweisung (OBJ-PERSONAL-1)"
    ]

    sign_in_as(client, "zugewiesenes-konto", "personal-test-passwort-2026")
    assert client.get(f"/api/v1/objects/{obj['id']}").status_code == 200

    admin_headers = {"X-CSRF-Token": sign_in_as(client, "admin", ADMIN_PASSWORD)}
    ended = client.delete(
        f"/api/v1/employees/{employee['id']}/objects/{obj['id']}",
        headers=admin_headers,
    )
    assert ended.status_code == 200
    assert ended.json() == []
    assert client.get(f"/api/v1/employees/{employee['id']}").json()["assigned_objects"] == []
    history = client.get(f"/api/v1/employees/{employee['id']}/object-assignment-history")
    assert history.status_code == 200
    assert [entry["action"] for entry in history.json()] == ["ended", "assigned"]

    sign_in_as(client, "zugewiesenes-konto", "personal-test-passwort-2026")
    assert client.get(f"/api/v1/objects/{obj['id']}").status_code == 404

    admin_headers = {"X-CSRF-Token": sign_in_as(client, "admin", ADMIN_PASSWORD)}
    legacy_update = client.put(
        f"/api/v1/objects/{obj['id']}/assignments",
        headers=admin_headers,
        json={"user_ids": [str(employee_user_id)]},
    )
    assert legacy_update.status_code == 200
    history = client.get(f"/api/v1/employees/{employee['id']}/object-assignment-history").json()
    assert [entry["action"] for entry in history] == ["assigned", "ended", "assigned"]

    client.post(f"/api/v1/employees/{employee['id']}/archive", headers=admin_headers)
    history = client.get(f"/api/v1/employees/{employee['id']}/object-assignment-history").json()
    assert [entry["action"] for entry in history] == ["ended", "assigned", "ended", "assigned"]
    assert client.get(f"/api/v1/employees/{employee['id']}/objects").json() == []


def test_employee_object_assignment_requires_explicit_permission(client: TestClient) -> None:
    admin_headers = {"X-CSRF-Token": sign_in_as(client, "admin", ADMIN_PASSWORD)}
    employee_user_id = create_test_user("rechte-test-mitarbeiter", "employee")
    employee = client.post(
        "/api/v1/employees",
        headers=admin_headers,
        json={
            "employee_number": "P-3501",
            "user_id": str(employee_user_id),
            "full_name": "Rechte-Testperson",
            "hired_on": str(date.today()),
        },
    ).json()
    customer = client.post(
        "/api/v1/customers",
        headers=admin_headers,
        json={"company_name": "Testkunde Rechteprüfung GmbH"},
    ).json()
    obj = client.post(
        "/api/v1/objects",
        headers=admin_headers,
        json={
            "customer_id": customer["id"],
            "name": "Testobjekt Rechteprüfung",
            "code": "OBJ-PERSONAL-RECHTE",
        },
    ).json()

    create_test_user("hr-ohne-objektrechte", "hr")
    hr_headers = {
        "X-CSRF-Token": sign_in_as(client, "hr-ohne-objektrechte", "personal-test-passwort-2026")
    }
    assert client.get("/api/v1/employees/object-assignment-candidates").status_code == 403
    assert (
        client.post(
            f"/api/v1/employees/{employee['id']}/objects/{obj['id']}",
            headers=hr_headers,
        ).status_code
        == 403
    )


def test_employee_object_details_are_limited_to_accessible_objects(client: TestClient) -> None:
    admin_headers = {"X-CSRF-Token": sign_in_as(client, "admin", ADMIN_PASSWORD)}
    employee_user_id = create_test_user("bereichs-mitarbeiter", "employee")
    employee = client.post(
        "/api/v1/employees",
        headers=admin_headers,
        json={
            "employee_number": "P-3601",
            "user_id": str(employee_user_id),
            "full_name": "Bereichs-Testperson",
            "hired_on": str(date.today()),
        },
    ).json()
    customer = client.post(
        "/api/v1/customers",
        headers=admin_headers,
        json={"company_name": "Testkunde Bereichsschutz GmbH"},
    ).json()

    objects = []
    for index in (1, 2):
        created_object = client.post(
            "/api/v1/objects",
            headers=admin_headers,
            json={
                "customer_id": customer["id"],
                "name": f"Bereichsobjekt {index}",
                "code": f"OBJ-BEREICH-{index}",
            },
        )
        assert created_object.status_code == 201
        objects.append(created_object.json())
        assigned = client.post(
            f"/api/v1/employees/{employee['id']}/objects/{objects[-1]['id']}",
            headers=admin_headers,
        )
        assert assigned.status_code == 201

    auditor_id = create_test_user_with_permissions("personal-auditor", ("employees.read",))
    with TestingSessionLocal() as db:
        db.add(
            ObjectAssignment(
                object_id=UUID(objects[0]["id"]),
                user_id=auditor_id,
            )
        )
        db.commit()

    auditor_headers = {
        "X-CSRF-Token": sign_in_as(client, "personal-auditor", "personal-test-passwort-2026")
    }
    authenticated_user = client.get("/api/v1/auth/me").json()["user"]
    assert authenticated_user["username"] == "personal-auditor"
    assert authenticated_user["permissions"] == ["employees.read"]
    with TestingSessionLocal() as db:
        auditor = db.scalar(select(User).where(User.id == auditor_id))
        assert auditor is not None
        assert {permission.code for role in auditor.roles for permission in role.permissions} == {
            "employees.read"
        }
    detail = client.get(f"/api/v1/employees/{employee['id']}", headers=auditor_headers)
    assert detail.status_code == 200
    assert detail.json()["assigned_objects"] == ["Bereichsobjekt 1 (OBJ-BEREICH-1)"]

    employee_list = client.get("/api/v1/employees", headers=auditor_headers)
    assert employee_list.status_code == 200
    listed_employee = next(
        item for item in employee_list.json()["items"] if item["id"] == employee["id"]
    )
    assert listed_employee["assigned_objects"] == ["Bereichsobjekt 1 (OBJ-BEREICH-1)"]

    assignments = client.get(f"/api/v1/employees/{employee['id']}/objects", headers=auditor_headers)
    assert assignments.status_code == 200
    assert [item["object_id"] for item in assignments.json()] == [objects[0]["id"]]

    history = client.get(
        f"/api/v1/employees/{employee['id']}/object-assignment-history",
        headers=auditor_headers,
    )
    assert history.status_code == 200
    assert [item["object_id"] for item in history.json()] == [objects[0]["id"]]


def test_qualification_documents_are_versioned_and_permission_protected(
    client: TestClient,
) -> None:
    admin_headers = {"X-CSRF-Token": sign_in_as(client, "admin", ADMIN_PASSWORD)}
    employee = client.post(
        "/api/v1/employees",
        headers=admin_headers,
        json={
            "employee_number": "P-4001",
            "full_name": "Dokument Testperson",
            "hired_on": str(date.today()),
        },
    ).json()
    qualification = client.post(
        f"/api/v1/employees/{employee['id']}/qualifications",
        headers=admin_headers,
        json={"category": "Zertifikat", "name": "Erste Hilfe"},
    ).json()
    route = f"/api/v1/employees/{employee['id']}/qualifications/{qualification['id']}/documents"
    first_content = b"%PDF-1.4\nfirst version"
    first = client.post(
        route,
        headers=admin_headers,
        files={"document": ("nachweis.pdf", first_content, "application/pdf")},
    )
    assert first.status_code == 201
    assert first.json()["version"] == 1
    with TestingSessionLocal() as db:
        stored = db.get(EmployeeQualificationDocument, UUID(first.json()["id"]))
        assert stored is not None
        assert stored.storage_key is not None and stored.content is None
        encoded_file = (get_settings().document_storage_path / stored.storage_key).read_bytes()
        assert encoded_file.startswith(b"SECOPS-DOC\x00")
        assert first_content not in encoded_file
    second = client.post(
        route,
        headers=admin_headers,
        files={"document": ("nachweis.pdf", b"%PDF-1.4\nsecond version", "application/pdf")},
    )
    assert second.status_code == 201
    assert second.json()["version"] == 2

    document_route = (
        f"/api/v1/employees/{employee['id']}/qualifications/{qualification['id']}/"
        f"documents/{first.json()['id']}"
    )
    preview = client.get(document_route)
    assert preview.status_code == 200
    assert preview.content == first_content
    assert preview.headers["content-disposition"].startswith("inline;")
    download = client.get(document_route, params={"download": True})
    assert download.status_code == 200
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["cache-control"] == "private, no-store"
    assert (
        client.get(
            f"/api/v1/employees/{UUID(int=0)}/qualifications/{qualification['id']}/"
            f"documents/{first.json()['id']}"
        ).status_code
        == 404
    )

    mismatched = client.post(
        route,
        headers=admin_headers,
        files={"document": ("fake.pdf", b"\x89PNG\r\n\x1a\nnot a pdf", "application/pdf")},
    )
    assert mismatched.status_code == 415
    wrong_mime = client.post(
        route,
        headers=admin_headers,
        files={"document": ("falscher-typ.pdf", b"%PDF-1.4\nvalid signature", "image/png")},
    )
    assert wrong_mime.status_code == 415
    oversized = client.post(
        route,
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

    create_test_user("personal-dokument-leser", "management")
    sign_in_as(client, "personal-dokument-leser", "personal-test-passwort-2026")
    assert (
        client.get(f"/api/v1/employees/{employee['id']}/qualification-documents").status_code == 403
    )
    assert client.get(document_route).status_code == 403

    admin_headers = {"X-CSRF-Token": sign_in_as(client, "admin", ADMIN_PASSWORD)}
    client.post(f"/api/v1/employees/{employee['id']}/archive", headers=admin_headers)
    rejected = client.post(
        route,
        headers=admin_headers,
        files={"document": ("archiviert.pdf", b"%PDF-1.4\narchived", "application/pdf")},
    )
    assert rejected.status_code == 409


def test_qualification_upload_is_not_created_when_scanner_is_unavailable(
    client: TestClient, monkeypatch
) -> None:
    admin_headers = {"X-CSRF-Token": sign_in_as(client, "admin", ADMIN_PASSWORD)}
    employee = client.post(
        "/api/v1/employees",
        headers=admin_headers,
        json={
            "employee_number": "P-SCAN-001",
            "full_name": "Testperson Scan",
            "hired_on": str(date.today()),
        },
    )
    assert employee.status_code == 201
    qualification = client.post(
        f"/api/v1/employees/{employee.json()['id']}/qualifications",
        headers=admin_headers,
        json={"category": "Zertifikat", "name": "Scanprüfung"},
    )
    assert qualification.status_code == 201

    def unavailable(_content: bytes) -> None:
        raise MalwareScannerError("unavailable")

    monkeypatch.setattr("app.upload_scanning.scan_upload", unavailable)
    rejected = client.post(
        f"/api/v1/employees/{employee.json()['id']}/qualifications/"
        f"{qualification.json()['id']}/documents",
        headers=admin_headers,
        files={"document": ("nachweis.pdf", b"%PDF-1.4\nprivate", "application/pdf")},
    )
    assert rejected.status_code == 503
    with TestingSessionLocal() as db:
        assert db.scalar(select(EmployeeQualificationDocument)) is None
