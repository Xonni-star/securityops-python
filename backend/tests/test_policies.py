from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from conftest import ADMIN_PASSWORD, TestingSessionLocal
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.identity_api import password_hasher
from app.models import (
    Customer,
    Employee,
    ObjectAssignment,
    PolicyReceipt,
    Role,
    SecurityObject,
    User,
)


def sign_in(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return client.cookies.get("securityops_csrf", "")


def create_user(username: str, role_code: str) -> UUID:
    with TestingSessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == role_code))
        assert role is not None
        user = User(
            username=username,
            email=f"{username}@example.com",
            full_name=f"Test {username}",
            password_hash=password_hasher.hash("policy-test-passwort-2026"),
            roles=[role],
        )
        db.add(user)
        db.commit()
        return user.id


def create_policy_fixture(
    employee_username: str = "unterweisung-person",
) -> tuple[UUID, UUID, UUID]:
    employee_user_id = create_user(employee_username, "employee")
    with TestingSessionLocal() as db:
        customer = Customer(
            customer_number=f"C-{employee_username}",
            company_name="Testkunde",
            status="active",
        )
        db.add(customer)
        db.flush()
        obj = SecurityObject(
            customer_id=customer.id,
            code=f"O-{employee_username}",
            name="Testobjekt",
            status="active",
        )
        db.add(obj)
        db.flush()
        employee = Employee(
            employee_number=f"P-{employee_username}",
            user_id=employee_user_id,
            full_name="Testperson Beispiel",
            employment_status="active",
            hired_on=date.today(),
        )
        db.add(employee)
        db.flush()
        db.add(
            ObjectAssignment(
                object_id=obj.id,
                user_id=employee_user_id,
                assigned_by_id=None,
            )
        )
        db.commit()
        return employee_user_id, employee.id, obj.id


def create_policy_and_version(
    client: TestClient,
    manager_headers: dict[str, str],
    object_id: UUID,
    *,
    kind: str = "training",
    title: str = "Sicherheitsunterweisung",
    repeat_interval_days: int | None = 30,
    reminder_days: int | None = 5,
) -> tuple[dict, dict]:
    policy_response = client.post(
        "/api/v1/policies",
        headers=manager_headers,
        json={
            "kind": kind,
            "title": title,
            "object_id": str(object_id),
            "repeat_interval_days": repeat_interval_days,
            "reminder_days": reminder_days,
        },
    )
    assert policy_response.status_code == 201, policy_response.text
    policy = policy_response.json()
    now = datetime.now(UTC)
    version_response = client.post(
        f"/api/v1/policies/{policy['id']}/versions",
        headers=manager_headers,
        json={
            "content": "Lesbarer Testinhalt",
            "valid_from": (now - timedelta(days=5)).isoformat(),
            "valid_until": (now + timedelta(days=365)).isoformat(),
        },
    )
    assert version_response.status_code == 201, version_response.text
    return policy, version_response.json()


def test_policy_versioned_training_scope_receipts_repetition_and_export(
    client: TestClient,
) -> None:
    _, employee_id, object_id = create_policy_fixture()
    _, other_employee_id, _ = create_policy_fixture("andere-unterweisung-person")
    manager_csrf = sign_in(client, "admin", ADMIN_PASSWORD)
    manager_headers = {"X-CSRF-Token": manager_csrf}
    policy, version = create_policy_and_version(client, manager_headers, object_id)

    due_at = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    assigned = client.post(
        f"/api/v1/policies/{policy['id']}/versions/{version['id']}/assignments",
        headers=manager_headers,
        json={"employee_id": str(employee_id), "due_at": due_at},
    )
    assert assigned.status_code == 201, assigned.text
    assignment = assigned.json()
    assert assignment["overdue"] is True
    assert assignment["reminder_due"] is True

    rejected_assignment = client.post(
        f"/api/v1/policies/{policy['id']}/versions/{version['id']}/assignments",
        headers=manager_headers,
        json={"employee_id": str(other_employee_id)},
    )
    assert rejected_assignment.status_code == 404

    employee_csrf = sign_in(client, "unterweisung-person", "policy-test-passwort-2026")
    employee_headers = {"X-CSRF-Token": employee_csrf}
    own = client.get("/api/v1/policies/assignments/me")
    assert own.status_code == 200
    assert len(own.json()) == 1
    assert own.json()[0]["version_id"] == version["id"]
    assert own.json()[0]["content"] == "Lesbarer Testinhalt"
    assert (
        client.post(
            f"/api/v1/policies/assignments/{assignment['id']}/confirm",
            headers=employee_headers,
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/policies/assignments/{assignment['id']}/read",
            headers=employee_headers,
        ).status_code
        == 200
    )
    confirmation = client.post(
        f"/api/v1/policies/assignments/{assignment['id']}/confirm",
        headers=employee_headers,
    )
    assert confirmation.status_code == 200, confirmation.text
    assert confirmation.json()["confirmed_at"] is not None
    assert confirmation.json()["overdue"] is False
    repeated = client.get("/api/v1/policies/assignments/me")
    assert len(repeated.json()) == 2
    next_cycle = next(item for item in repeated.json() if item["cycle_number"] == 2)
    assert next_cycle["due_at"] is not None
    assert next_cycle["reminder_due"] is False

    client.post("/api/v1/auth/logout", headers=employee_headers)
    manager_csrf = sign_in(client, "admin", ADMIN_PASSWORD)
    manager_headers = {"X-CSRF-Token": manager_csrf}
    history = client.get(f"/api/v1/policies/{policy['id']}/history")
    assert history.status_code == 200
    assert len(history.json()["assignments"]) == 2
    first_cycle = next(item for item in history.json()["assignments"] if item["cycle_number"] == 1)
    assert first_cycle["version_id"] == version["id"]
    assert first_cycle["read_at"] is not None
    assert first_cycle["confirmed_at"] is not None

    export = client.get(f"/api/v1/policies/{policy['id']}/export.csv")
    assert export.status_code == 200
    assert "Mitarbeiternummer" in export.text
    assert "Testperson Beispiel" in export.text
    with TestingSessionLocal() as db:
        assert db.scalar(select(PolicyReceipt).where(PolicyReceipt.action == "read")) is not None
        assert (
            db.scalar(select(PolicyReceipt).where(PolicyReceipt.action == "confirmed")) is not None
        )

    client.post("/api/v1/auth/logout", headers=manager_headers)
    other_csrf = sign_in(client, "andere-unterweisung-person", "policy-test-passwort-2026")
    assert (
        client.post(
            f"/api/v1/policies/assignments/{assignment['id']}/read",
            headers={"X-CSRF-Token": other_csrf},
        ).status_code
        == 404
    )


def test_policy_version_validity_and_object_manager_scope(client: TestClient) -> None:
    _, employee_id, object_id = create_policy_fixture("scope-employee")
    manager_csrf = sign_in(client, "admin", ADMIN_PASSWORD)
    manager_headers = {"X-CSRF-Token": manager_csrf}
    policy, first_version = create_policy_and_version(
        client,
        manager_headers,
        object_id,
        kind="instruction",
        title="Objektanweisung",
        repeat_interval_days=None,
        reminder_days=None,
    )
    start = datetime.now(UTC) + timedelta(days=90)
    second_version = client.post(
        f"/api/v1/policies/{policy['id']}/versions",
        headers=manager_headers,
        json={
            "content": "Künftige unveränderte Fassung",
            "valid_from": start.isoformat(),
            "valid_until": None,
        },
    )
    assert second_version.status_code == 201
    policy_after_new_version = client.get("/api/v1/policies").json()[0]
    prior_version = next(
        item for item in policy_after_new_version["versions"] if item["id"] == first_version["id"]
    )
    assert datetime.fromisoformat(prior_version["valid_until"]).astimezone(UTC) == start
    out_of_order = client.post(
        f"/api/v1/policies/{policy['id']}/versions",
        headers=manager_headers,
        json={
            "content": "Rückdatierte Fassung",
            "valid_from": (start - timedelta(days=1)).isoformat(),
            "valid_until": None,
        },
    )
    assert out_of_order.status_code == 409
    assert (
        client.post(
            f"/api/v1/policies/{policy['id']}/versions/{first_version['id']}/assignments",
            headers=manager_headers,
            json={"employee_id": str(employee_id)},
        ).status_code
        == 201
    )
    with TestingSessionLocal() as db:
        scope_user = db.scalar(select(User).where(User.username == "scope-manager"))
        if scope_user is None:
            role = db.scalar(select(Role).where(Role.code == "object_manager"))
            assert role is not None
            scope_user = User(
                username="scope-manager",
                email="scope-manager@example.com",
                full_name="Objektleitung Test",
                password_hash=password_hasher.hash("policy-test-passwort-2026"),
                roles=[role],
            )
            db.add(scope_user)
            db.flush()
        db.add(
            ObjectAssignment(
                object_id=object_id,
                user_id=scope_user.id,
                assigned_by_id=None,
            )
        )
        db.commit()

    scope_csrf = sign_in(client, "scope-manager", "policy-test-passwort-2026")
    scope_headers = {"X-CSRF-Token": scope_csrf}
    visible = client.get("/api/v1/policies")
    assert visible.status_code == 200
    assert [item["id"] for item in visible.json()] == [policy["id"]]
    assert client.get(f"/api/v1/policies/{policy['id']}/history").status_code == 200
    assert (
        client.get(f"/api/v1/policies/{'00000000-0000-0000-0000-000000000001'}/history").status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/policies",
            headers=scope_headers,
            json={"kind": "instruction", "title": "Globale Anweisung"},
        ).status_code
        == 403
    )


def test_policy_validation_expiration_and_employee_permission_boundaries(
    client: TestClient,
    monkeypatch,
) -> None:
    _, employee_id, object_id = create_policy_fixture("expired-policy-person")
    manager_csrf = sign_in(client, "admin", ADMIN_PASSWORD)
    manager_headers = {"X-CSRF-Token": manager_csrf}
    policy_response = client.post(
        "/api/v1/policies",
        headers=manager_headers,
        json={
            "kind": "instruction",
            "title": "Abgelaufene Objektanweisung",
            "object_id": str(object_id),
        },
    )
    assert policy_response.status_code == 201
    policy = policy_response.json()
    now = datetime.now(UTC)
    version = client.post(
        f"/api/v1/policies/{policy['id']}/versions",
        headers=manager_headers,
        json={
            "content": "Vergangene Fassung",
            "valid_from": (now - timedelta(days=10)).isoformat(),
            "valid_until": (now + timedelta(days=1)).isoformat(),
        },
    )
    assert version.status_code == 201
    assignment = client.post(
        f"/api/v1/policies/{policy['id']}/versions/{version.json()['id']}/assignments",
        headers=manager_headers,
        json={"employee_id": str(employee_id)},
    )
    assert assignment.status_code == 201
    monkeypatch.setattr("app.policies_api.utc_now", lambda: now + timedelta(days=2))
    employee_csrf = sign_in(client, "expired-policy-person", "policy-test-passwort-2026")
    employee_headers = {"X-CSRF-Token": employee_csrf}
    assert client.get("/api/v1/policies/assignments/me").json() == []
    assert (
        client.post(
            f"/api/v1/policies/assignments/{assignment.json()['id']}/read",
            headers=employee_headers,
        ).status_code
        == 404
    )
    assert client.get("/api/v1/policies").status_code == 403
    client.post("/api/v1/auth/logout", headers=employee_headers)
    manager_csrf = sign_in(client, "admin", ADMIN_PASSWORD)
    manager_headers = {"X-CSRF-Token": manager_csrf}
    assert (
        client.post(
            "/api/v1/policies",
            headers=manager_headers,
            json={
                "kind": "training",
                "title": "Fehlerhafte Erinnerung",
                "repeat_interval_days": 30,
                "reminder_days": 30,
            },
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/api/v1/policies/{policy['id']}/versions",
            headers=manager_headers,
            json={"content": "Ohne Zeitzone", "valid_from": "2026-10-01T10:00:00"},
        ).status_code
        == 422
    )


def test_policy_migration_is_linear_after_object_qualifications() -> None:
    import importlib

    migration = importlib.import_module("migrations.versions.0038_digital_policies")
    assert migration.revision == "0038_digital_policies"
    assert migration.down_revision == "0037_object_qual_requirements"
    assert migration.MANAGER_ROLES == ("administrator", "management", "object_manager")
