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
    InventoryAsset,
    InventoryEvent,
    ObjectAssignment,
    Permission,
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
        employee_role = db.scalar(select(Role).where(Role.code == "employee"))
        user = User(
            username=username,
            email=f"{username}@example.com",
            full_name=f"Test {username}",
            password_hash=password_hasher.hash("inventar-test-passwort-2026"),
            roles=[employee_role],
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


def create_asset(
    client: TestClient,
    headers: dict[str, str],
    asset_number: str,
    object_id: str | None,
) -> dict:
    response = client.post(
        "/api/v1/inventory/assets",
        headers=headers,
        json={
            "asset_number": asset_number,
            "serial_number": f"SER-{asset_number}",
            "name": f"Funkgerät {asset_number}",
            "category": "radio",
            "condition": "good",
            "location": "Materialraum",
            "object_id": object_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_inventory_lifecycle_search_and_append_only_history(client: TestClient) -> None:
    headers = sign_in(client)
    object_id = create_object(client, headers, "INV-001")
    employee_a = create_employee(object_id, "inventar-ma-a")
    employee_b = create_employee(object_id, "inventar-ma-b")
    asset = create_asset(client, headers, "I-100", object_id)
    assert asset["status"] == "available"
    assert asset["object_id"] == object_id

    duplicate = client.post(
        "/api/v1/inventory/assets",
        headers=headers,
        json={
            "asset_number": "I-100",
            "name": "Doppelte Nummer",
            "category": "radio",
            "location": "Materialraum",
            "object_id": object_id,
        },
    )
    assert duplicate.status_code == 409
    invalid_category = client.get("/api/v1/inventory/assets?category=unbekannt", headers=headers)
    assert invalid_category.status_code == 422

    employee_options = client.get(
        f"/api/v1/inventory/eligible-employees?object_id={object_id}",
        headers=headers,
    )
    assert employee_options.status_code == 200
    assert {candidate["id"] for candidate in employee_options.json()} == {
        employee_a,
        employee_b,
    }

    missing_ack = client.post(
        f"/api/v1/inventory/assets/{asset['id']}/events",
        headers=headers,
        json={"event_type": "issued", "employee_id": employee_a},
    )
    assert missing_ack.status_code == 422
    issued = client.post(
        f"/api/v1/inventory/assets/{asset['id']}/events",
        headers=headers,
        json={
            "event_type": "issued",
            "employee_id": employee_a,
            "acknowledged": True,
            "acknowledgement_note": "Empfang bestätigt",
        },
    )
    assert issued.status_code == 201, issued.text
    assert issued.json()["to_employee_id"] == employee_a
    assert issued.json()["acknowledged_at"] is not None
    assert issued.json()["actor_name"] == "Test Administration"
    assigned_page = client.get(
        f"/api/v1/inventory/assets?employee_id={employee_a}",
        headers=headers,
    )
    assert assigned_page.status_code == 200
    assert [item["id"] for item in assigned_page.json()["items"]] == [asset["id"]]

    duplicate_issue = client.post(
        f"/api/v1/inventory/assets/{asset['id']}/events",
        headers=headers,
        json={"event_type": "issued", "employee_id": employee_a, "acknowledged": True},
    )
    assert duplicate_issue.status_code == 409

    transferred = client.post(
        f"/api/v1/inventory/assets/{asset['id']}/events",
        headers=headers,
        json={"event_type": "transferred", "employee_id": employee_b, "acknowledged": True},
    )
    assert transferred.status_code == 201, transferred.text
    assert transferred.json()["from_employee_id"] == employee_a
    assert transferred.json()["to_employee_id"] == employee_b

    returned = client.post(
        f"/api/v1/inventory/assets/{asset['id']}/events",
        headers=headers,
        json={"event_type": "returned", "note": "Rückgabe geprüft"},
    )
    assert returned.status_code == 201, returned.text
    assert returned.json()["from_employee_id"] == employee_b
    assert returned.json()["status_after"] == "available"

    maintenance = client.post(
        f"/api/v1/inventory/assets/{asset['id']}/events",
        headers=headers,
        json={"event_type": "maintenance", "note": "Wartung abgeschlossen"},
    )
    assert maintenance.status_code == 201, maintenance.text
    assert maintenance.json()["status_after"] == "maintenance"
    repair = client.post(
        f"/api/v1/inventory/assets/{asset['id']}/events",
        headers=headers,
        json={"event_type": "repair", "condition": "used", "note": "Antenne ersetzt"},
    )
    assert repair.status_code == 201, repair.text
    assert repair.json()["status_after"] == "available"
    assert repair.json()["condition_after"] == "used"

    page = client.get(
        "/api/v1/inventory/assets?q=I-100&category=radio&condition=used",
        headers=headers,
    )
    assert page.status_code == 200
    assert page.json()["total"] == 1
    assert page.json()["items"][0]["asset_number"] == "I-100"

    history = client.get(f"/api/v1/inventory/assets/{asset['id']}/events?limit=3", headers=headers)
    assert history.status_code == 200
    assert history.json()["total"] == 6
    assert [entry["event_type"] for entry in history.json()["items"]] == [
        "repair",
        "maintenance",
        "returned",
    ]
    with TestingSessionLocal() as db:
        assert db.scalar(select(InventoryEvent).where(InventoryEvent.event_type == "issued"))
        assert db.scalar(select(AuditLog).where(AuditLog.action == "inventory.transferred"))


def test_inventory_damage_loss_repair_and_archive_are_recorded(client: TestClient) -> None:
    headers = sign_in(client)
    object_id = create_object(client, headers, "INV-STATE")
    damaged_asset = create_asset(client, headers, "I-DAMAGED", object_id)
    damaged = client.post(
        f"/api/v1/inventory/assets/{damaged_asset['id']}/events",
        headers=headers,
        json={"event_type": "damaged", "note": "Display beschädigt"},
    )
    assert damaged.status_code == 201
    assert damaged.json()["status_after"] == "damaged"
    assert damaged.json()["condition_after"] == "defective"

    repair = client.post(
        f"/api/v1/inventory/assets/{damaged_asset['id']}/events",
        headers=headers,
        json={"event_type": "repair", "condition": "good", "note": "Display ersetzt"},
    )
    assert repair.status_code == 201
    archived = client.post(
        f"/api/v1/inventory/assets/{damaged_asset['id']}/archive",
        headers=headers,
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    lost_asset = create_asset(client, headers, "I-LOST", object_id)
    missing_note = client.post(
        f"/api/v1/inventory/assets/{lost_asset['id']}/events",
        headers=headers,
        json={"event_type": "lost"},
    )
    assert missing_note.status_code == 422
    lost = client.post(
        f"/api/v1/inventory/assets/{lost_asset['id']}/events",
        headers=headers,
        json={"event_type": "lost", "note": "Bei der Übergabe nicht auffindbar"},
    )
    assert lost.status_code == 201
    assert lost.json()["status_after"] == "lost"
    listed = client.get("/api/v1/inventory/assets?status=lost", headers=headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [lost_asset["id"]]
    archived_page = client.get(
        "/api/v1/inventory/assets?status=archived&include_archived=true",
        headers=headers,
    )
    assert archived_page.status_code == 200
    assert archived_page.json()["total"] == 1


def test_inventory_is_object_scoped_and_requires_permissions(client: TestClient) -> None:
    admin_headers = sign_in(client)
    object_a = create_object(client, admin_headers, "INV-SCOPE-A")
    object_b = create_object(client, admin_headers, "INV-SCOPE-B")
    asset_a = create_asset(client, admin_headers, "I-SCOPE-A", object_a)
    asset_b = create_asset(client, admin_headers, "I-SCOPE-B", object_b)
    manager_employee_id = create_employee(object_a, "inventar-objektleitung")
    with TestingSessionLocal() as db:
        manager_employee = db.get(Employee, UUID(manager_employee_id))
        manager = db.scalar(select(User).where(User.id == manager_employee.user_id))
        manager.roles = [db.scalar(select(Role).where(Role.code == "object_manager"))]
        db.commit()

    manager_headers = sign_in(
        client,
        "inventar-objektleitung",
        "inventar-test-passwort-2026",
    )
    visible = client.get("/api/v1/inventory/assets", headers=manager_headers)
    assert visible.status_code == 200
    assert [item["id"] for item in visible.json()["items"]] == [asset_a["id"]]
    assert (
        client.get(
            f"/api/v1/inventory/assets/{asset_b['id']}/events", headers=manager_headers
        ).status_code
        == 404
    )
    object_options = client.get("/api/v1/inventory/objects", headers=manager_headers)
    assert [obj["id"] for obj in object_options.json()] == [object_a]
    assert (
        client.get(
            f"/api/v1/inventory/eligible-employees?object_id={object_b}",
            headers=manager_headers,
        ).status_code
        == 404
    )
    denied_update = client.patch(
        f"/api/v1/inventory/assets/{asset_a['id']}",
        headers=manager_headers,
        json={"name": "Nicht erlaubt"},
    )
    assert denied_update.status_code == 403

    with TestingSessionLocal() as db:
        employee_role = db.scalar(select(Role).where(Role.code == "employee"))
        user = User(
            username="inventar-ohne-recht",
            email="inventar-ohne-recht@example.com",
            full_name="Test ohne Inventarrecht",
            password_hash=password_hasher.hash("inventar-test-passwort-2026"),
            roles=[employee_role],
        )
        db.add(user)
        db.commit()
    employee_headers = sign_in(
        client,
        "inventar-ohne-recht",
        "inventar-test-passwort-2026",
    )
    assert client.get("/api/v1/inventory/assets", headers=employee_headers).status_code == 403


def test_global_object_read_does_not_grant_movement_access_to_central_inventory(
    client: TestClient,
) -> None:
    admin_headers = sign_in(client)
    asset = create_asset(client, admin_headers, "I-CENTRAL-SCOPE", None)
    with TestingSessionLocal() as db:
        permissions = db.scalars(
            select(Permission).where(
                Permission.code.in_({"inventory.read", "inventory.move", "objects.read_all"})
            )
        ).all()
        role = Role(
            code="inventory_read_all_mover",
            name="Inventarbereich mit Lesebereich",
            description="Testrolle ohne globale Objektverwaltung",
            permissions=permissions,
        )
        user = User(
            username="inventar-read-all-mover",
            email="inventar-read-all-mover@example.com",
            full_name="Test Inventar mit Lesebereich",
            password_hash=password_hasher.hash("inventar-test-passwort-2026"),
            roles=[role],
        )
        db.add(user)
        db.commit()
    scoped_headers = sign_in(
        client,
        "inventar-read-all-mover",
        "inventar-test-passwort-2026",
    )
    assert client.get("/api/v1/inventory/assets", headers=scoped_headers).json()["total"] == 1
    denied = client.post(
        f"/api/v1/inventory/assets/{asset['id']}/events",
        headers=scoped_headers,
        json={"event_type": "lost", "note": "Nicht global verwaltbar"},
    )
    assert denied.status_code == 403


def test_inventory_model_constraints_and_migration_chain() -> None:
    asset_constraints = {constraint.name for constraint in InventoryAsset.__table__.constraints}
    assert {
        "ck_inventory_assets_category",
        "ck_inventory_assets_condition",
        "ck_inventory_assets_status",
        "ck_inventory_assets_number",
        "ck_inventory_assets_name",
        "ck_inventory_assets_holder_status",
        "ck_inventory_assets_archived_at",
    } <= asset_constraints
    assert {
        "ix_inventory_assets_object_status",
        "ix_inventory_assets_holder_status",
        "ix_inventory_assets_category_condition",
    } <= {index.name for index in InventoryAsset.__table__.indexes}
    event_constraints = {constraint.name for constraint in InventoryEvent.__table__.constraints}
    assert {
        "ck_inventory_events_type",
        "ck_inventory_events_status",
        "ck_inventory_events_issue_acknowledged",
        "ck_inventory_events_transfer_acknowledged",
        "ck_inventory_events_type_status",
    } <= event_constraints
    assert all(
        foreign_key.ondelete == "RESTRICT" for foreign_key in InventoryEvent.__table__.foreign_keys
    )

    migration = importlib.import_module("migrations.versions.0030_inventory_management")
    assert migration.revision == "0030_inventory_management"
    assert migration.down_revision == "0029_audit_integrity"


@pytest.mark.skipif(
    test_engine.dialect.name != "postgresql",
    reason="PostgreSQL-Migrationen und Trigger werden in PostgreSQL geprüft",
)
def test_postgresql_inventory_events_are_append_only_and_data_safe_downgrade(
    client: TestClient,
) -> None:
    headers = sign_in(client)
    object_id = create_object(client, headers, "INV-PG-001")
    asset = create_asset(client, headers, "I-PG-001", object_id)
    event_id = client.get(f"/api/v1/inventory/assets/{asset['id']}/events", headers=headers).json()[
        "items"
    ][0]["id"]
    with TestingSessionLocal() as db:
        with pytest.raises(DBAPIError):
            db.execute(
                update(InventoryEvent)
                .where(InventoryEvent.id == UUID(event_id))
                .values(note="Änderung unzulässig")
            )
        db.rollback()
        with pytest.raises(DBAPIError):
            db.execute(delete(InventoryEvent).where(InventoryEvent.id == UUID(event_id)))
        db.rollback()

    migration = importlib.import_module("migrations.versions.0030_inventory_management")
    with test_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        with (
            Operations.context(context),
            pytest.raises(RuntimeError, match="Inventar-Downgrade"),
        ):
            migration.downgrade()
        connection.rollback()
        assert context.get_current_revision() == "0033_encrypted_document_storage"
        assert inspect(connection).has_table("inventory_assets")
