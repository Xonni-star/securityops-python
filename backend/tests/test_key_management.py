import importlib
from datetime import date
from uuid import UUID

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from conftest import ADMIN_PASSWORD, TestingSessionLocal, test_engine
from fastapi.testclient import TestClient
from sqlalchemy import delete, inspect, select, update
from sqlalchemy.exc import DBAPIError

from app.identity_api import password_hasher
from app.models import (
    AuditLog,
    Employee,
    KeyMovement,
    ObjectAssignment,
    PhysicalKey,
    Role,
    User,
)


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


def create_object(client: TestClient, headers: dict[str, str], code: str) -> str:
    customer = client.post(
        "/api/v1/customers",
        headers=headers,
        json={"company_name": f"Kunde {code}"},
    )
    assert customer.status_code == 201, customer.text
    obj = client.post(
        "/api/v1/objects",
        headers=headers,
        json={"customer_id": customer.json()["id"], "name": f"Objekt {code}", "code": code},
    )
    assert obj.status_code == 201, obj.text
    return obj.json()["id"]


def create_employee(object_id: str, username: str) -> str:
    with TestingSessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "employee"))
        user = User(
            username=username,
            email=f"{username}@example.com",
            full_name=f"Test {username}",
            password_hash=password_hasher.hash("schluessel-test-passwort-2026"),
            roles=[role],
        )
        db.add(user)
        db.flush()
        employee = Employee(
            employee_number=f"MA-{username}",
            user_id=user.id,
            full_name=user.full_name,
            employment_status="active",
            hired_on=date(2026, 1, 1),
        )
        db.add(employee)
        db.flush()
        db.add(ObjectAssignment(object_id=UUID(object_id), user_id=user.id))
        db.commit()
        return str(employee.id)


def create_key(
    client: TestClient, headers: dict[str, str], object_id: str, key_number: str
) -> dict:
    response = client.post(
        "/api/v1/keys",
        headers=headers,
        json={"key_number": key_number, "description": "Haupteingang", "object_id": object_id},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_key_register_issue_return_inventory_and_immutable_history(client: TestClient) -> None:
    headers = sign_in(client)
    object_id = create_object(client, headers, "KEY-001")
    employee_id = create_employee(object_id, "schluessel-ma")
    key = create_key(client, headers, object_id, "K-100")
    updated = client.patch(
        f"/api/v1/keys/{key['id']}",
        headers=headers,
        json={"description": "Haupteingang rechts"},
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "Haupteingang rechts"
    duplicate_number = client.post(
        "/api/v1/keys",
        headers=headers,
        json={"key_number": "K-100", "description": "Doppelte Nummer", "object_id": object_id},
    )
    assert duplicate_number.status_code == 409

    objects = client.get("/api/v1/keys/objects", headers=headers)
    assert objects.status_code == 200
    assert objects.json() == [{"id": object_id, "code": "KEY-001", "name": "Objekt KEY-001"}]
    eligible = client.get(
        f"/api/v1/keys/eligible-employees?object_id={object_id}",
        headers=headers,
    )
    assert eligible.status_code == 200
    assert eligible.json()[0]["id"] == employee_id

    page = client.get("/api/v1/keys?q=K-100&limit=1&offset=0", headers=headers)
    assert page.status_code == 200
    assert page.json()["total"] == 1
    assert page.json()["items"][0]["object_id"] == object_id

    issue = client.post(
        f"/api/v1/keys/{key['id']}/movements",
        headers=headers,
        json={"movement_type": "issued", "employee_id": employee_id, "acknowledged": True},
    )
    assert issue.status_code == 201, issue.text
    assert issue.json()["movement_type"] == "issued"
    assert issue.json()["employee_id"] == employee_id
    assert issue.json()["acknowledged_at"] is not None
    assert issue.json()["actor_name"] == "Test Administration"

    duplicate_issue = client.post(
        f"/api/v1/keys/{key['id']}/movements",
        headers=headers,
        json={"movement_type": "issued", "employee_id": employee_id, "acknowledged": True},
    )
    assert duplicate_issue.status_code == 409

    returned = client.post(
        f"/api/v1/keys/{key['id']}/movements",
        headers=headers,
        json={"movement_type": "returned", "note": "Rückgabe geprüft"},
    )
    assert returned.status_code == 201, returned.text
    assert returned.json()["employee_id"] == employee_id
    assert returned.json()["key_status_after"] == "available"
    second_return = client.post(
        f"/api/v1/keys/{key['id']}/movements",
        headers=headers,
        json={"movement_type": "returned"},
    )
    assert second_return.status_code == 409

    inventory = client.post(
        f"/api/v1/keys/{key['id']}/movements",
        headers=headers,
        json={"movement_type": "inventory", "note": "Schlüssel vor Ort gezählt"},
    )
    assert inventory.status_code == 201
    assert inventory.json()["key_status_after"] == "available"

    history = client.get(f"/api/v1/keys/{key['id']}/movements?limit=2", headers=headers)
    assert history.status_code == 200
    assert history.json()["total"] == 3
    assert len(history.json()["items"]) == 2
    assert history.json()["items"][0]["movement_type"] == "inventory"

    lost_without_note = client.post(
        f"/api/v1/keys/{key['id']}/movements",
        headers=headers,
        json={"movement_type": "lost"},
    )
    assert lost_without_note.status_code == 422
    lost = client.post(
        f"/api/v1/keys/{key['id']}/movements",
        headers=headers,
        json={"movement_type": "lost", "note": "Nicht im Schlüsselkasten"},
    )
    assert lost.status_code == 201
    listed = client.get("/api/v1/keys?status=lost", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["status"] == "lost"
    assert listed.json()["items"][0]["current_employee_id"] is None

    with TestingSessionLocal() as db:
        assert (
            db.scalar(select(KeyMovement).where(KeyMovement.movement_type == "issued")) is not None
        )
        assert db.scalar(select(AuditLog).where(AuditLog.action == "keys.issued")) is not None

    defective_key = create_key(client, headers, object_id, "K-DEFECT")
    defect = client.post(
        f"/api/v1/keys/{defective_key['id']}/movements",
        headers=headers,
        json={"movement_type": "defective", "note": "Schließzylinder beschädigt"},
    )
    assert defect.status_code == 201
    assert defect.json()["key_status_after"] == "defective"

    archived_key = create_key(client, headers, object_id, "K-ARCHIVE")
    archived = client.post(f"/api/v1/keys/{archived_key['id']}/archive", headers=headers)
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    archived_page = client.get(
        "/api/v1/keys?status=archived&include_archived=true", headers=headers
    )
    assert archived_page.status_code == 200
    assert archived_page.json()["total"] == 1


def test_key_employee_must_have_access_to_the_key_object(client: TestClient) -> None:
    headers = sign_in(client)
    object_id = create_object(client, headers, "KEY-SCOPE-1")
    other_object_id = create_object(client, headers, "KEY-SCOPE-2")
    employee_id = create_employee(other_object_id, "schluessel-fremd")
    key = create_key(client, headers, object_id, "K-SCOPE")

    issued = client.post(
        f"/api/v1/keys/{key['id']}/movements",
        headers=headers,
        json={"movement_type": "issued", "employee_id": employee_id, "acknowledged": True},
    )
    assert issued.status_code == 422

    no_acknowledgement = client.post(
        f"/api/v1/keys/{key['id']}/movements",
        headers=headers,
        json={"movement_type": "issued", "employee_id": employee_id},
    )
    assert no_acknowledgement.status_code == 422


def test_key_read_is_object_scoped_and_requires_permission(client: TestClient) -> None:
    admin_headers = sign_in(client)
    first_object_id = create_object(client, admin_headers, "KEY-SCOPED-A")
    second_object_id = create_object(client, admin_headers, "KEY-SCOPED-B")
    first_key = create_key(client, admin_headers, first_object_id, "K-SCOPED-A")
    second_key = create_key(client, admin_headers, second_object_id, "K-SCOPED-B")
    employee_id = create_employee(first_object_id, "schluessel-objektleitung")
    with TestingSessionLocal() as db:
        employee = db.get(Employee, UUID(employee_id))
        manager = db.scalar(select(User).where(User.id == employee.user_id))
        manager.roles = [db.scalar(select(Role).where(Role.code == "object_manager"))]
        db.commit()

    manager_headers = sign_in(client, "schluessel-objektleitung", "schluessel-test-passwort-2026")
    visible = client.get("/api/v1/keys", headers=manager_headers)
    assert visible.status_code == 200
    assert [item["id"] for item in visible.json()["items"]] == [first_key["id"]]
    assert (
        client.get(
            f"/api/v1/keys/{second_key['id']}/movements", headers=manager_headers
        ).status_code
        == 404
    )

    with TestingSessionLocal() as db:
        employee_role = db.scalar(select(Role).where(Role.code == "employee"))
        role_user = User(
            username="schluessel-ohne-recht",
            email="schluessel-ohne-recht@example.com",
            full_name="Test ohne Schlüsselrecht",
            password_hash=password_hasher.hash("schluessel-test-passwort-2026"),
            roles=[employee_role],
        )
        db.add(role_user)
        db.commit()
    employee_headers = sign_in(
        client,
        "schluessel-ohne-recht",
        "schluessel-test-passwort-2026",
    )
    assert client.get("/api/v1/keys", headers=employee_headers).status_code == 403
    assert employee_headers


def test_key_model_constraints_indexes_and_foreign_keys() -> None:
    constraints = {constraint.name for constraint in PhysicalKey.__table__.constraints}
    assert {
        "ck_physical_keys_status",
        "ck_physical_keys_number",
        "ck_physical_keys_description",
        "ck_physical_keys_holder_status",
        "ck_physical_keys_archived_at",
    } <= constraints
    assert any(
        constraint.__class__.__name__ == "UniqueConstraint"
        for constraint in PhysicalKey.__table__.constraints
    )
    assert {
        "ix_physical_keys_object_status",
        "ix_physical_keys_holder_status",
    } <= {index.name for index in PhysicalKey.__table__.indexes}
    foreign_keys = {
        foreign_key.target_fullname: foreign_key.ondelete
        for foreign_key in PhysicalKey.__table__.foreign_keys
    }
    assert foreign_keys["objects.id"] == "RESTRICT"
    assert foreign_keys["employees.id"] == "RESTRICT"

    movement_constraints = {constraint.name for constraint in KeyMovement.__table__.constraints}
    assert {
        "ck_key_movements_type",
        "ck_key_movements_status_after",
        "ck_key_movements_issue_acknowledged",
        "ck_key_movements_type_status",
    } <= movement_constraints
    assert {
        "ix_key_movements_key_created",
        "ix_key_movements_object_created",
        "ix_key_movements_employee_created",
    } <= {index.name for index in KeyMovement.__table__.indexes}
    assert all(
        foreign_key.ondelete == "RESTRICT" for foreign_key in KeyMovement.__table__.foreign_keys
    )


def test_key_migration_is_linear_after_notifications() -> None:
    migration = importlib.import_module("migrations.versions.0021_key_management")
    assert migration.revision == "0021_key_management"
    assert migration.down_revision == "0020_notifications"


@pytest.mark.skipif(
    test_engine.dialect.name != "postgresql",
    reason="PostgreSQL-Migrationen und Trigger werden in PostgreSQL geprüft",
)
def test_postgresql_key_migration_append_only_and_data_safe_downgrade(
    client: TestClient,
) -> None:
    admin_headers = sign_in(client)
    object_id = create_object(client, admin_headers, "KEY-PG-001")
    key = create_key(client, admin_headers, object_id, "K-PG-001")
    event = client.post(
        f"/api/v1/keys/{key['id']}/movements",
        headers=admin_headers,
        json={"movement_type": "inventory"},
    )
    assert event.status_code == 201
    with TestingSessionLocal() as db:
        with pytest.raises(DBAPIError):
            db.execute(
                update(KeyMovement)
                .where(KeyMovement.id == UUID(event.json()["id"]))
                .values(note="Änderung unzulässig")
            )
        db.rollback()
        with pytest.raises(DBAPIError):
            db.execute(delete(KeyMovement).where(KeyMovement.id == UUID(event.json()["id"])))
        db.rollback()

    migration = importlib.import_module("migrations.versions.0021_key_management")
    with test_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        with (
            Operations.context(context),
            pytest.raises(RuntimeError, match="Schlüsselverwaltungs-Downgrade"),
        ):
            migration.downgrade()
        connection.rollback()
        assert context.get_current_revision() == "0037_object_qual_requirements"
        assert inspect(connection).has_table("key_movements")


@pytest.mark.skipif(
    test_engine.dialect.name != "postgresql",
    reason="PostgreSQL-Migration wird in PostgreSQL geprüft",
)
def test_postgresql_database_has_key_management_migration_applied(client: TestClient) -> None:
    with test_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        assert context.get_current_revision() == "0037_object_qual_requirements"
        inspector = inspect(connection)
        assert {
            "physical_keys",
            "key_movements",
            "incidents",
            "incident_measures",
            "inventory_assets",
            "inventory_events",
        } <= set(inspector.get_table_names())
