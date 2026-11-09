from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from conftest import ADMIN_PASSWORD, TestingSessionLocal
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.identity_api import password_hasher
from app.models import (
    Contract,
    Document,
    Employee,
    Incident,
    ObjectAssignment,
    OWKSEvent,
    Permission,
    PhysicalKey,
    Role,
    ScheduleShift,
    SecurityObject,
    Task,
    User,
)


def sign_in(
    client: TestClient, username: str = "admin", password: str = ADMIN_PASSWORD
) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": client.cookies.get("securityops_csrf", "")}


def create_customer(client: TestClient, headers: dict[str, str], name: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/customers",
        headers=headers,
        json={
            "company_name": name,
            "internal_notes": "Suchgeheimnis-Notiz",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_object(
    client: TestClient, headers: dict[str, str], customer_id: str, name: str, code: str
) -> dict[str, str]:
    response = client.post(
        "/api/v1/objects",
        headers=headers,
        json={
            "customer_id": customer_id,
            "name": name,
            "code": code,
            "description": "Suchgeheimnis-Beschreibung",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_object_manager(username: str, object_id: str) -> None:
    with TestingSessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "object_manager"))
        security_object = db.get(SecurityObject, UUID(object_id))
        assert role is not None and security_object is not None
        user = User(
            username=username,
            email=f"{username}@example.com",
            full_name="Test Objektleitung",
            password_hash=password_hasher.hash("such-test-passwort-2026"),
            roles=[role],
        )
        db.add(user)
        db.flush()
        db.add(ObjectAssignment(object_id=security_object.id, user_id=user.id))
        db.commit()


def create_scoped_search_user(
    username: str,
    assigned_object_id: str,
    permission_codes: tuple[str, ...],
) -> UUID:
    with TestingSessionLocal() as db:
        user = User(
            username=username,
            email=f"{username}@example.com",
            full_name="Test Suchkonto",
            password_hash=password_hasher.hash("such-test-passwort-2026"),
        )
        db.add(user)
        db.flush()
        permissions = db.scalars(
            select(Permission).where(Permission.code.in_(permission_codes))
        ).all()
        assert {permission.code for permission in permissions} == set(permission_codes)
        role = Role(
            code=f"{username}_role",
            name="Test Suchrolle",
            description="Testrolle für globale Suche",
            permissions=permissions,
        )
        user.roles.append(role)
        db.add(
            ObjectAssignment(
                object_id=UUID(assigned_object_id),
                user_id=user.id,
            )
        )
        db.commit()
        return user.id


def test_search_returns_minimal_customer_and_object_results(client: TestClient) -> None:
    headers = sign_in(client)
    customer = create_customer(client, headers, "Nordlicht Sicherheits GmbH")
    obj = create_object(client, headers, customer["id"], "Hafenwache Nord", "OBJ-NORD-1")

    response = client.get("/api/v1/search", params={"q": "Nord"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert {(item["type"], item["title"]) for item in payload["items"]} == {
        ("customer", "Nordlicht Sicherheits GmbH"),
        ("object", "Hafenwache Nord"),
    }
    assert all(set(item) == {"id", "type", "title", "reference"} for item in payload["items"])
    assert {item["id"] for item in payload["items"]} == {customer["id"], obj["id"]}
    assert client.get("/api/v1/search", params={"q": "Suchgeheimnis"}).json()["items"] == []


def test_search_limits_objects_to_assigned_scope_and_does_not_expose_customers(
    client: TestClient,
) -> None:
    headers = sign_in(client)
    assigned_customer = create_customer(client, headers, "Zugeordneter Suchkunde")
    other_customer = create_customer(client, headers, "Fremder Suchkunde")
    assigned_object = create_object(
        client, headers, assigned_customer["id"], "Suchobjekt Erreichbar", "OBJ-SCOPE-1"
    )
    other_object = create_object(
        client, headers, other_customer["id"], "Suchobjekt Fremd", "OBJ-SCOPE-2"
    )
    create_object_manager("search_object_manager", assigned_object["id"])
    sign_in(client, "search_object_manager", "such-test-passwort-2026")

    object_results = client.get("/api/v1/search", params={"q": "Suchobjekt"}).json()
    customer_results = client.get(
        "/api/v1/search", params={"q": "Suchkunde", "type": "customer"}
    ).json()

    assert [item["id"] for item in object_results["items"]] == [assigned_object["id"]]
    assert other_object["id"] not in {item["id"] for item in object_results["items"]}
    assert customer_results["items"] == []
    assert customer_results["total"] == 0


def test_search_paginates_and_validates_query_and_bounds(client: TestClient) -> None:
    headers = sign_in(client)
    for suffix in ("A", "B", "C"):
        create_customer(client, headers, f"Pagination Kunde {suffix}")

    first_page = client.get(
        "/api/v1/search",
        params={"q": "Pagination", "type": "customer", "limit": 1, "offset": 0},
    )
    second_page = client.get(
        "/api/v1/search",
        params={"q": "Pagination", "type": "customer", "limit": 1, "offset": 1},
    )

    assert first_page.status_code == second_page.status_code == 200
    assert first_page.json()["total"] == 3
    assert len(first_page.json()["items"]) == len(second_page.json()["items"]) == 1
    assert first_page.json()["items"][0]["id"] != second_page.json()["items"][0]["id"]
    assert client.get("/api/v1/search", params={"q": " "}).status_code == 422
    assert client.get("/api/v1/search", params={"q": "ok", "type": "invoice"}).status_code == 422
    assert client.get("/api/v1/search", params={"q": "ok", "limit": 51}).status_code == 422
    assert client.get("/api/v1/search", params={"q": "ok", "offset": 5001}).status_code == 422


def test_search_requires_at_least_one_search_permission(client: TestClient) -> None:
    sign_in(client)
    with TestingSessionLocal() as db:
        role = Role(
            code="search_no_access",
            name="Keine Suchberechtigung",
            description="Testrolle ohne Suchrechte",
        )
        db.add(role)
        db.flush()
        db.add(
            User(
                username="search_without_permission",
                email="search_without_permission@example.com",
                full_name="Test Suchkonto",
                password_hash=password_hasher.hash("such-test-passwort-2026"),
                roles=[role],
            )
        )
        db.commit()

    sign_in(client, "search_without_permission", "such-test-passwort-2026")

    response = client.get("/api/v1/search", params={"q": "Kunde"})

    assert response.status_code == 403


def test_search_reuses_object_scopes_for_existing_sources(client: TestClient) -> None:
    admin_headers = sign_in(client)
    customer_a = create_customer(client, admin_headers, "Suchkunde A")
    customer_b = create_customer(client, admin_headers, "Suchkunde B")
    object_a = create_object(client, admin_headers, customer_a["id"], "Suchobjekt A", "SCOPE-A")
    object_b = create_object(client, admin_headers, customer_b["id"], "Suchobjekt B", "SCOPE-B")
    permission_codes = (
        "objects.read",
        "documents.read",
        "contracts.read",
        "scheduling.read",
        "tasks.read_own",
        "incidents.read",
        "keys.read",
        "owks.read",
    )
    scoped_user_id = create_scoped_search_user(
        "search_scoped_sources", object_a["id"], permission_codes
    )
    with TestingSessionLocal() as db:
        employee = Employee(
            employee_number="EMP-SEARCH-SCOPE",
            full_name="Nicht in Suchtreffern ausgeben",
            user_id=scoped_user_id,
            employment_status="active",
            hired_on=date(2020, 1, 1),
        )
        db.add(employee)
        db.flush()
        admin_id = db.scalar(select(User.id).where(User.username == "admin"))
        start = datetime.now(UTC) + timedelta(days=1)
        for object_id, customer_id, suffix in (
            (UUID(object_a["id"]), UUID(customer_a["id"]), "A"),
            (UUID(object_b["id"]), UUID(customer_b["id"]), "B"),
        ):
            shift_start = start + (timedelta(days=1) if suffix == "B" else timedelta())
            db.add_all(
                [
                    Document(
                        document_number=f"DOC-SCOPE-{suffix}",
                        title=f"Scoped document {suffix}",
                        category="Test",
                        customer_id=customer_id,
                        object_id=object_id,
                    ),
                    Contract(
                        contract_number=f"CON-SCOPE-{suffix}",
                        name=f"Scoped contract {suffix}",
                        contract_type="object",
                        counterparty="Test",
                        customer_id=customer_id,
                        object_id=object_id,
                        starts_on=date(2025, 1, 1),
                    ),
                    ScheduleShift(
                        employee_id=employee.id,
                        object_id=object_id,
                        starts_at=shift_start,
                        ends_at=shift_start + timedelta(hours=8),
                        status="published",
                    ),
                    Task(
                        title=f"Scoped task {suffix}",
                        description="Suchgeheimnis Aufgabenbeschreibung",
                        assigned_to_id=admin_id,
                        created_by_id=admin_id,
                        customer_id=customer_id,
                        object_id=object_id,
                    ),
                    Incident(
                        title=f"Scoped incident {suffix}",
                        report="Suchgeheimnis Vorfallbericht",
                        incident_type="incident",
                        severity="low",
                        object_id=object_id,
                        assigned_to_id=admin_id,
                        created_by_id=admin_id,
                    ),
                    PhysicalKey(
                        key_number=f"KEY-SCOPE-{suffix}",
                        description="Suchgeheimnis Schlüsselbeschreibung",
                        object_id=object_id,
                    ),
                    OWKSEvent(
                        object_id=object_id,
                        event_type="entry",
                        severity="info",
                        title=f"Private OWKS title {suffix}",
                        description="Suchgeheimnis Wachbuchtext",
                        occurred_at=start,
                    ),
                ]
            )
        db.commit()

    sign_in(client, "search_scoped_sources", "such-test-passwort-2026")
    source_queries = {
        "document": "Scoped document",
        "contract": "Scoped contract",
        "shift": "Suchobjekt",
        "task": "Scoped task",
        "incident": "Scoped incident",
        "key": "KEY-SCOPE",
        "owks_event": "Eintrag",
    }
    for entity_type, query in source_queries.items():
        response = client.get(
            "/api/v1/search",
            params={"q": query, "type": entity_type},
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1, entity_type
        assert items[0]["type"] == entity_type
        if entity_type in {"document", "contract", "task", "incident"}:
            assert items[0]["title"].endswith("A")
        elif entity_type == "key":
            assert items[0]["title"] == "Schlüssel"
            assert items[0]["reference"] == "KEY-SCOPE-A"
        elif entity_type == "owks_event":
            assert items[0]["title"] == "Wachbuch: Eintrag"
        assert set(items[0]) == {"id", "type", "title", "reference"}
        assert all(
            secret not in str(items[0])
            for secret in (
                "Suchgeheimnis",
                "Private OWKS",
                "Nicht in Suchtreffern",
            )
        )

    with TestingSessionLocal() as db:
        db.get(SecurityObject, UUID(object_a["id"])).archived_at = datetime.now(UTC)
        db.commit()
    for entity_type, query in source_queries.items():
        archived_scope = client.get(
            "/api/v1/search",
            params={"q": query, "type": entity_type},
        )
        assert archived_scope.status_code == 200
        assert archived_scope.json()["items"] == [], entity_type


def test_search_employee_requires_employee_read_and_only_returns_minimal_fields(
    client: TestClient,
) -> None:
    admin_headers = sign_in(client)
    customer = create_customer(client, admin_headers, "Mitarbeitersuchkunde")
    obj = create_object(client, admin_headers, customer["id"], "Mitarbeitersuchobjekt", "EMP-OBJ")
    user_id = create_scoped_search_user(
        "search_employee_denied",
        obj["id"],
        ("objects.read",),
    )
    with TestingSessionLocal() as db:
        db.add(
            Employee(
                employee_number="EMP-PRIVATE-SEARCH",
                full_name="Nicht sichtbarer Mitarbeitername",
                user_id=user_id,
                employment_status="active",
                hired_on=date(2020, 1, 1),
            )
        )
        db.commit()

    sign_in(client, "search_employee_denied", "such-test-passwort-2026")
    denied = client.get(
        "/api/v1/search",
        params={"q": "EMP-PRIVATE", "type": "employee"},
    )
    assert denied.status_code == 200
    assert denied.json()["items"] == []

    sign_in(client)
    allowed = client.get(
        "/api/v1/search",
        params={"q": "EMP-PRIVATE", "type": "employee"},
    )
    assert allowed.status_code == 200
    item = allowed.json()["items"][0]
    assert item["type"] == "employee"
    assert item["title"] == "Mitarbeiter"
    assert item["reference"] == "EMP-PRIVATE-SEARCH"
    assert "Nicht sichtbarer Mitarbeitername" not in str(item)
    with TestingSessionLocal() as db:
        employee = db.scalar(
            select(Employee).where(Employee.employee_number == "EMP-PRIVATE-SEARCH")
        )
        assert employee is not None
        employee.archived_at = datetime.now(UTC)
        db.commit()
    archived = client.get(
        "/api/v1/search",
        params={"q": "EMP-PRIVATE", "type": "employee"},
    )
    assert archived.status_code == 200
    assert archived.json()["items"] == []


def test_owks_event_navigation_rechecks_object_scope(client: TestClient) -> None:
    headers = sign_in(client)
    customer = create_customer(client, headers, "Wachbuch-Scope-Kunde")
    assigned = create_object(client, headers, customer["id"], "Wachbuchobjekt A", "OWKS-A")
    other = create_object(client, headers, customer["id"], "Wachbuchobjekt B", "OWKS-B")
    create_scoped_search_user(
        "search_owks_navigation",
        assigned["id"],
        ("owks.read",),
    )
    with TestingSessionLocal() as db:
        user_id = db.scalar(select(User.id).where(User.username == "admin"))
        event_a = OWKSEvent(
            object_id=UUID(assigned["id"]),
            event_type="entry",
            severity="info",
            title="Eintrag A",
            description="Nur nach Objektberechtigung",
            occurred_at=datetime.now(UTC),
            actor_id=user_id,
        )
        event_b = OWKSEvent(
            object_id=UUID(other["id"]),
            event_type="entry",
            severity="info",
            title="Eintrag B",
            description="Nicht für fremden Scope",
            occurred_at=datetime.now(UTC),
            actor_id=user_id,
        )
        db.add_all([event_a, event_b])
        db.commit()
        event_a_id, event_b_id = str(event_a.id), str(event_b.id)

    sign_in(client, "search_owks_navigation", "such-test-passwort-2026")

    assert client.get(f"/api/v1/owks/events/{event_a_id}").status_code == 200
    assert client.get(f"/api/v1/owks/events/{event_b_id}").status_code == 404
