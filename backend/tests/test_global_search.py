from uuid import UUID

from conftest import ADMIN_PASSWORD, TestingSessionLocal
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.identity_api import password_hasher
from app.models import ObjectAssignment, Role, SecurityObject, User


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
