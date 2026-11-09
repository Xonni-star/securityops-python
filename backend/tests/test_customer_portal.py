from uuid import UUID, uuid4

from conftest import ADMIN_PASSWORD, TestingSessionLocal
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.identity_api import password_hasher
from app.malware_scanner import MalwareScannerError
from app.models import (
    AuditLog,
    CustomerPortalDocumentGrantHistory,
    CustomerPortalLink,
    CustomerPortalLinkHistory,
    CustomerPortalRequestHistory,
    ObjectAddress,
    ObjectSecurityDetails,
    Role,
    SecurityObject,
    User,
)
from app.rate_limit import limiter

PORTAL_PASSWORD = "portal-test-password-2026"


def sign_in(client: TestClient, username: str = "admin", password: str = ADMIN_PASSWORD):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": client.cookies.get("securityops_csrf", "")}


def create_role_user(username: str, role_code: str = "customer_portal") -> UUID:
    with TestingSessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == role_code))
        user = User(
            username=username,
            email=f"{username}@example.com",
            full_name="Portal-Testkonto",
            password_hash=password_hasher.hash(PORTAL_PASSWORD),
            roles=[role],
        )
        db.add(user)
        db.commit()
        return user.id


def create_customer(client: TestClient, headers: dict[str, str], company: str):
    response = client.post(
        "/api/v1/customers",
        headers=headers,
        json={
            "company_name": company,
            "email": "kontakt@example.com",
            "phone": "+49 30 000000",
            "legal_form": "GmbH",
            "vat_number": "INTERN-TEST",
            "tax_number": "INTERN-TEST",
            "internal_notes": "Intern und nicht fürs Portal.",
            "business_address": {
                "street": "Teststraße",
                "house_number": "1",
                "postal_code": "10115",
                "city": "Berlin",
                "country_code": "DE",
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_contact(client: TestClient, headers: dict[str, str], customer_id: str):
    response = client.post(
        f"/api/v1/customers/{customer_id}/contacts",
        headers=headers,
        json={
            "first_name": "Portal",
            "last_name": "Kontakt",
            "responsibility": "Geschäftlich",
            "email": "portal@example.com",
            "phone": "+49 30 000001",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_invoice(
    client: TestClient,
    headers: dict[str, str],
    customer_id: str,
    rate_id: str,
    idempotency_key: str,
    description: str,
):
    response = client.post(
        "/api/v1/billing/invoices",
        headers=headers,
        json={
            "idempotency_key": idempotency_key,
            "customer_id": customer_id,
            "issued_on": "2026-11-08",
            "due_on": "2026-12-08",
            "lines": [{"rate_id": rate_id, "quantity": "1", "description": description}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_customer_portal_is_scoped_to_manually_linked_contact_and_approved_invoices(
    client: TestClient,
):
    admin_headers = sign_in(client)
    customer = create_customer(client, admin_headers, "Eigener Testkunde")
    contact = create_contact(client, admin_headers, customer["id"])
    other_customer = create_customer(client, admin_headers, "Fremder Testkunde")
    other_contact = create_contact(client, admin_headers, other_customer["id"])
    user_id = create_role_user("portal-konto")
    other_user_id = create_role_user("portal-konto-zwei")
    employee_user_id = create_role_user("portal-employee-role", "employee")

    rate = client.post(
        "/api/v1/billing/rates",
        headers=admin_headers,
        json={
            "code": "PORTAL-TEST",
            "name": "Portal-Testleistung",
            "kind": "flat",
            "unit": "Pauschale",
            "unit_price": "100.00",
            "tax_code": "TEST",
            "tax_rate": "19",
        },
    )
    assert rate.status_code == 201, rate.text
    own_approved = create_invoice(
        client,
        admin_headers,
        customer["id"],
        rate.json()["id"],
        "portal-own-approved",
        "Freigegebene Leistung",
    )
    own_draft = create_invoice(
        client,
        admin_headers,
        customer["id"],
        rate.json()["id"],
        "portal-own-draft",
        "Entwurf darf nicht erscheinen",
    )
    foreign_approved = create_invoice(
        client,
        admin_headers,
        other_customer["id"],
        rate.json()["id"],
        "portal-foreign-approved",
        "Fremde Rechnung darf nicht erscheinen",
    )
    for invoice in (own_approved, foreign_approved):
        approval = client.post(
            f"/api/v1/billing/invoices/{invoice['id']}/approve",
            headers=admin_headers,
        )
        assert approval.status_code == 200, approval.text

    with TestingSessionLocal() as db:
        obj = SecurityObject(
            customer_id=UUID(customer["id"]),
            code="PORTAL-OBJ",
            name="Eigener Standort",
            object_type="Büro",
            description="Interne Beschreibung",
            staffing_requirements="Interne Personalangabe",
            operating_hours="08:00–18:00",
            service_times="Mo–Fr",
        )
        db.add(obj)
        db.flush()
        db.add(
            ObjectAddress(
                object_id=obj.id,
                street="Objektstraße",
                house_number="2",
                postal_code="10115",
                city="Berlin",
                country_code="DE",
            )
        )
        db.add(
            ObjectSecurityDetails(
                object_id=obj.id,
                security_requirements="Interne Sicherheitsvorgabe",
                access_information="Interne Zutrittsinformation",
            )
        )
        db.add(
            SecurityObject(
                customer_id=UUID(other_customer["id"]),
                code="FOREIGN-OBJ",
                name="Fremder Standort",
                status="active",
            )
        )
        db.commit()

    linked = client.post(
        "/api/v1/customer-portal/links",
        headers=admin_headers,
        json={"user_id": str(user_id), "contact_id": contact["id"]},
    )
    assert linked.status_code == 201, linked.text
    assert client.get("/api/v1/customer-portal/links").status_code == 200
    assert (
        client.post(
            "/api/v1/customer-portal/links",
            headers=admin_headers,
            json={"user_id": str(user_id), "contact_id": other_contact["id"]},
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/v1/customer-portal/links",
            headers=admin_headers,
            json={"user_id": str(employee_user_id), "contact_id": other_contact["id"]},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/customer-portal/links",
            headers=admin_headers,
            json={"user_id": str(other_user_id), "contact_id": contact["id"]},
        ).status_code
        == 409
    )

    client.post("/api/v1/auth/logout", headers=admin_headers)
    portal_headers = sign_in(client, "portal-konto", PORTAL_PASSWORD)
    me_response = client.get("/api/v1/customer-portal/me")
    assert me_response.status_code == 200, me_response.text
    me = me_response.json()
    assert me["contact"]["id"] == contact["id"]
    assert me["customer"]["company_name"] == customer["company_name"]
    assert "internal_notes" not in me["customer"]
    assert "vat_number" not in me["customer"]
    assert "tax_number" not in me["customer"]
    assert me_response.headers["cache-control"] == "private, no-store"
    assert [obj["code"] for obj in me["objects"]] == ["PORTAL-OBJ"]
    assert "staffing_requirements" not in me["objects"][0]
    assert "description" not in me["objects"][0]
    assert "security_requirements" not in me["objects"][0]

    invoices = client.get("/api/v1/customer-portal/invoices")
    assert invoices.status_code == 200, invoices.text
    assert [item["id"] for item in invoices.json()] == [own_approved["id"]]
    assert invoices.json()[0]["lines"][0]["description"] == "Freigegebene Leistung"
    assert "customer_id" not in invoices.json()[0]
    assert "correction_reason" not in invoices.json()[0]

    own_pdf = client.get(f"/api/v1/customer-portal/invoices/{own_approved['id']}/pdf")
    assert own_pdf.status_code == 200
    assert own_pdf.content.startswith(b"%PDF-1.4")
    assert own_pdf.headers["cache-control"] == "private, no-store"
    assert (
        client.get(f"/api/v1/customer-portal/invoices/{foreign_approved['id']}/pdf").status_code
        == 404
    )
    assert client.get(f"/api/v1/customer-portal/invoices/{own_draft['id']}/pdf").status_code == 404

    for path in (
        "/api/v1/customers",
        "/api/v1/objects",
        "/api/v1/documents",
        "/api/v1/incidents",
    ):
        assert client.get(path).status_code == 403
    assert (
        client.post(
            "/api/v1/customer-portal/links",
            headers=portal_headers,
            json={"user_id": str(user_id), "contact_id": other_contact["id"]},
        ).status_code
        == 403
    )

    assert (
        client.delete(
            f"/api/v1/customer-portal/links/{contact['id']}",
            headers=portal_headers,
        ).status_code
        == 403
    )
    client.post("/api/v1/auth/logout", headers=portal_headers)
    admin_headers = sign_in(client)
    unlink = client.delete(
        f"/api/v1/customer-portal/links/{contact['id']}",
        headers=admin_headers,
    )
    assert unlink.status_code == 204
    assert client.get("/api/v1/customer-portal/links").json() == []
    client.post("/api/v1/auth/logout", headers=admin_headers)
    portal_session = client.post(
        "/api/v1/auth/login",
        json={"username": "portal-konto", "password": PORTAL_PASSWORD},
    )
    assert portal_session.status_code == 200
    assert portal_session.json()["user"]["permissions"] == ["customer_portal.access"]
    assert client.get("/api/v1/customer-portal/me").status_code == 403

    with TestingSessionLocal() as db:
        history = db.scalars(
            select(CustomerPortalLinkHistory)
            .where(CustomerPortalLinkHistory.user_id == user_id)
            .order_by(CustomerPortalLinkHistory.created_at)
        ).all()
        assert [event.action for event in history] == ["linked", "unlinked"]
        actions = db.scalars(
            select(AuditLog.action).where(
                AuditLog.entity_type == "customer_portal_link",
            )
        ).all()
        assert {"customer_portal.linked", "customer_portal.unlinked"} <= set(actions)
        assert (
            db.scalar(select(CustomerPortalLink).where(CustomerPortalLink.user_id == user_id))
            is None
        )


def test_customer_portal_link_management_requires_specific_permission(client: TestClient):
    management_headers = sign_in(client, "geschaeftsfuehrung", "management-test-passwort-2026")
    assert client.get("/api/v1/customer-portal/links").status_code == 403
    assert (
        client.post(
            "/api/v1/customer-portal/links",
            headers=management_headers,
            json={"user_id": str(uuid4()), "contact_id": str(uuid4())},
        ).status_code
        == 403
    )


def test_customer_portal_link_activation_is_audited_and_revokes_portal_access(
    client: TestClient,
):
    admin_headers = sign_in(client)
    customer = create_customer(client, admin_headers, "Aktivierungstest")
    contact = create_contact(client, admin_headers, customer["id"])
    user_id = create_role_user("portal-activation")
    link = client.post(
        "/api/v1/customer-portal/links",
        headers=admin_headers,
        json={"user_id": str(user_id), "contact_id": contact["id"]},
    )
    assert link.status_code == 201
    assert link.json()["is_active"] is True

    options = client.get("/api/v1/customer-portal/management-options")
    assert options.status_code == 200
    assert any(option["id"] == str(user_id) for option in options.json()["users"])
    assert any(option["id"] == contact["id"] for option in options.json()["contacts"])
    assert options.headers["cache-control"] == "private, no-store"

    deactivated = client.patch(
        f"/api/v1/customer-portal/links/{contact['id']}",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["is_active"] is False

    client.post("/api/v1/auth/logout", headers=admin_headers)
    portal_headers = sign_in(client, "portal-activation", PORTAL_PASSWORD)
    assert client.get("/api/v1/customer-portal/me").status_code == 403
    client.post("/api/v1/auth/logout", headers=portal_headers)

    admin_headers = sign_in(client)
    activated = client.patch(
        f"/api/v1/customer-portal/links/{contact['id']}",
        headers=admin_headers,
        json={"is_active": True},
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["is_active"] is True
    history = client.get("/api/v1/customer-portal/link-history")
    assert history.status_code == 200, history.text
    assert [
        item["action"] for item in reversed(history.json()) if item["user_id"] == str(user_id)
    ] == ["linked", "deactivated", "activated"]
    assert "customer_name" not in history.text
    access_history = client.get("/api/v1/customer-portal/access-history")
    assert access_history.status_code == 200
    assert {
        event["action"]
        for event in access_history.json()
        if event["entity_type"] == "customer_portal_link"
    } >= {"customer_portal.linked", "customer_portal.deactivated", "customer_portal.activated"}
    assert "details" not in access_history.json()[0]


def test_customer_document_requires_explicit_active_grant_and_is_scoped(
    client: TestClient, tmp_path, monkeypatch
):
    monkeypatch.setattr(get_settings(), "document_storage_path", tmp_path)
    admin_headers = sign_in(client)
    customer = create_customer(client, admin_headers, "Dokumentenfreigabe")
    contact = create_contact(client, admin_headers, customer["id"])
    foreign_customer = create_customer(client, admin_headers, "Fremde Dokumentenfreigabe")
    user_id = create_role_user("portal-document-reader")
    linked = client.post(
        "/api/v1/customer-portal/links",
        headers=admin_headers,
        json={"user_id": str(user_id), "contact_id": contact["id"]},
    )
    assert linked.status_code == 201

    upload = client.post(
        "/api/v1/documents",
        headers=admin_headers,
        data={
            "document_number": "PORTAL-DOC-1",
            "title": "Freigegebene Kundenunterlage",
            "category": "Information",
            "status": "active",
            "customer_id": customer["id"],
        },
        files={"file": ("information.pdf", b"%PDF-1.7\nsynthetic portal file", "application/pdf")},
    )
    foreign_upload = client.post(
        "/api/v1/documents",
        headers=admin_headers,
        data={
            "document_number": "PORTAL-DOC-2",
            "title": "Fremde Kundenunterlage",
            "category": "Information",
            "status": "active",
            "customer_id": foreign_customer["id"],
        },
        files={"file": ("fremd.pdf", b"%PDF-1.7\nsynthetic foreign file", "application/pdf")},
    )
    assert upload.status_code == 201, upload.text
    assert foreign_upload.status_code == 201, foreign_upload.text
    version_id = upload.json()["latest_version"]["id"]
    candidate_ids = {
        candidate["document_id"]
        for candidate in client.get(
            "/api/v1/customer-portal/document-candidates",
            headers=admin_headers,
        ).json()
    }
    assert upload.json()["id"] in candidate_ids
    assert foreign_upload.json()["id"] in candidate_ids

    client.post("/api/v1/auth/logout", headers=admin_headers)
    portal_headers = sign_in(client, "portal-document-reader", PORTAL_PASSWORD)
    assert client.get("/api/v1/customer-portal/documents").json() == []
    assert (
        client.get(f"/api/v1/customer-portal/documents/{upload.json()['id']}/download").status_code
        == 404
    )
    client.post("/api/v1/auth/logout", headers=portal_headers)

    admin_headers = sign_in(client)
    grant = client.post(
        "/api/v1/customer-portal/document-grants",
        headers=admin_headers,
        json={"document_id": upload.json()["id"], "version_id": version_id},
    )
    assert grant.status_code == 201, grant.text
    foreign_grant = client.post(
        "/api/v1/customer-portal/document-grants",
        headers=admin_headers,
        json={
            "document_id": foreign_upload.json()["id"],
            "version_id": foreign_upload.json()["latest_version"]["id"],
        },
    )
    assert foreign_grant.status_code == 201, foreign_grant.text
    assert (
        client.post(
            "/api/v1/customer-portal/document-grants",
            headers=admin_headers,
            json={"document_id": upload.json()["id"], "version_id": version_id},
        ).status_code
        == 409
    )

    client.post("/api/v1/auth/logout", headers=admin_headers)
    portal_headers = sign_in(client, "portal-document-reader", PORTAL_PASSWORD)
    visible = client.get("/api/v1/customer-portal/documents")
    assert visible.status_code == 200
    assert [document["document_id"] for document in visible.json()] == [upload.json()["id"]]
    downloaded = client.get(f"/api/v1/customer-portal/documents/{grant.json()['id']}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == b"%PDF-1.7\nsynthetic portal file"
    assert downloaded.headers["cache-control"] == "private, no-store"
    assert (
        client.get(
            f"/api/v1/customer-portal/documents/{foreign_grant.json()['id']}/download"
        ).status_code
        == 404
    )
    assert client.get("/api/v1/documents").status_code == 403

    client.post("/api/v1/auth/logout", headers=portal_headers)
    admin_headers = sign_in(client)
    revoked = client.delete(
        f"/api/v1/customer-portal/document-grants/{grant.json()['id']}",
        headers=admin_headers,
    )
    assert revoked.status_code == 200
    client.post("/api/v1/auth/logout", headers=admin_headers)
    limiter.reset()
    sign_in(client, "portal-document-reader", PORTAL_PASSWORD)
    assert client.get("/api/v1/customer-portal/documents").json() == []
    assert (
        client.get(f"/api/v1/customer-portal/documents/{grant.json()['id']}/download").status_code
        == 404
    )

    with TestingSessionLocal() as db:
        history = db.scalars(
            select(CustomerPortalDocumentGrantHistory).where(
                CustomerPortalDocumentGrantHistory.grant_id == UUID(grant.json()["id"])
            )
        ).all()
        assert [event.action for event in history] == ["granted", "revoked"]


def test_customer_portal_request_thread_object_scope_admin_status_and_private_upload(
    client: TestClient, tmp_path, monkeypatch
):
    monkeypatch.setattr(get_settings(), "document_storage_path", tmp_path)
    admin_headers = sign_in(client)
    customer = create_customer(client, admin_headers, "Anfragetest")
    contact = create_contact(client, admin_headers, customer["id"])
    foreign_customer = create_customer(client, admin_headers, "Fremder Anfragetest")
    with TestingSessionLocal() as db:
        own_object = SecurityObject(
            customer_id=UUID(customer["id"]),
            code="REQ-OWN",
            name="Eigener Anfrage-Standort",
            status="active",
        )
        foreign_object = SecurityObject(
            customer_id=UUID(foreign_customer["id"]),
            code="REQ-FOREIGN",
            name="Fremder Anfrage-Standort",
            status="active",
        )
        db.add_all([own_object, foreign_object])
        db.commit()
        own_object_id = own_object.id
        foreign_object_id = foreign_object.id

    user_id = create_role_user("portal-requester")
    link = client.post(
        "/api/v1/customer-portal/links",
        headers=admin_headers,
        json={"user_id": str(user_id), "contact_id": contact["id"]},
    )
    assert link.status_code == 201
    client.post("/api/v1/auth/logout", headers=admin_headers)
    portal_headers = sign_in(client, "portal-requester", PORTAL_PASSWORD)
    assert client.get("/api/v1/customer-portal/admin/requests").status_code == 403
    denied = client.post(
        "/api/v1/customer-portal/requests",
        headers=portal_headers,
        json={
            "category": "complaint",
            "object_id": str(foreign_object_id),
            "title": "Fremdobjekt",
            "first_message": "Diese Anfrage darf nicht angenommen werden.",
        },
    )
    assert denied.status_code == 404

    created = client.post(
        "/api/v1/customer-portal/requests",
        headers=portal_headers,
        json={
            "category": "complaint",
            "object_id": str(own_object_id),
            "title": "Rückmeldung zum Standort",
            "first_message": "Bitte prüfen Sie den Zugang zum Haupteingang.",
        },
    )
    assert created.status_code == 201, created.text
    request_id = created.json()["id"]
    assert created.json()["status"] == "submitted"
    assert created.json()["messages"][0]["body"] == "Bitte prüfen Sie den Zugang zum Haupteingang."
    assert created.json()["history"][0]["action"] == "created"

    def scanner_unavailable(_content: bytes) -> None:
        raise MalwareScannerError("unavailable")

    with monkeypatch.context() as scanner_patch:
        scanner_patch.setattr("app.upload_scanning.scan_upload", scanner_unavailable)
        rejected = client.post(
            f"/api/v1/customer-portal/requests/{request_id}/attachments",
            headers=portal_headers,
            files={
                "file": ("nicht-gespeichert.pdf", b"%PDF-1.7\nsynthetic file", "application/pdf")
            },
        )
    assert rejected.status_code == 503
    assert list(tmp_path.iterdir()) == []

    uploaded = client.post(
        f"/api/v1/customer-portal/requests/{request_id}/attachments",
        headers=portal_headers,
        files={
            "file": ("hinweis.pdf", b"%PDF-1.7\nsynthetic customer attachment", "application/pdf")
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    attachment_id = uploaded.json()["id"]
    downloaded = client.get(
        f"/api/v1/customer-portal/requests/{request_id}/attachments/{attachment_id}/download",
        headers=portal_headers,
    )
    assert downloaded.status_code == 200
    assert downloaded.content == b"%PDF-1.7\nsynthetic customer attachment"
    assert downloaded.headers["cache-control"] == "private, no-store"
    assert (
        client.get(
            f"/api/v1/customer-portal/requests/{uuid4()}/attachments/{attachment_id}/download",
            headers=portal_headers,
        ).status_code
        == 404
    )

    message = client.post(
        f"/api/v1/customer-portal/requests/{request_id}/messages",
        headers=portal_headers,
        json={"body": "Ergänzende Kundenangabe."},
    )
    assert message.status_code == 201
    client.post("/api/v1/auth/logout", headers=portal_headers)

    admin_headers = sign_in(client)
    managed_list = client.get("/api/v1/customer-portal/admin/requests", headers=admin_headers)
    assert managed_list.status_code == 200, managed_list.text
    assert [item["id"] for item in managed_list.json()] == [request_id]
    admin_reply = client.post(
        f"/api/v1/customer-portal/admin/requests/{request_id}/messages",
        headers=admin_headers,
        json={"body": "Wir prüfen Ihre Meldung."},
    )
    assert admin_reply.status_code == 201
    status_update = client.patch(
        f"/api/v1/customer-portal/admin/requests/{request_id}/status",
        headers=admin_headers,
        json={"status": "in_progress"},
    )
    assert status_update.status_code == 200
    assert status_update.json()["status"] == "in_progress"
    admin_download = client.get(
        f"/api/v1/customer-portal/admin/requests/{request_id}/attachments/{attachment_id}/download",
        headers=admin_headers,
    )
    assert admin_download.status_code == 200
    assert admin_download.content == downloaded.content

    client.post("/api/v1/auth/logout", headers=admin_headers)
    portal_headers = sign_in(client, "portal-requester", PORTAL_PASSWORD)
    customer_view = client.get(f"/api/v1/customer-portal/requests/{request_id}")
    assert customer_view.status_code == 200
    assert [item["body"] for item in customer_view.json()["messages"]] == [
        "Bitte prüfen Sie den Zugang zum Haupteingang.",
        "Ergänzende Kundenangabe.",
        "Wir prüfen Ihre Meldung.",
    ]
    assert customer_view.json()["history"][-1]["new_status"] == "in_progress"
    assert client.get("/api/v1/incidents").status_code == 403

    with TestingSessionLocal() as db:
        actions = db.scalars(
            select(CustomerPortalRequestHistory.action)
            .where(CustomerPortalRequestHistory.request_id == UUID(request_id))
            .order_by(CustomerPortalRequestHistory.created_at)
        ).all()
        assert actions == [
            "created",
            "attachment_added",
            "message_added",
            "message_added",
            "status_changed",
        ]


def test_unlinked_customer_portal_role_has_no_portal_or_generic_access(client: TestClient):
    user_id = create_role_user("portal-unlinked")
    with TestingSessionLocal() as db:
        user = db.get(User, user_id)
        employee_role = db.scalar(select(Role).where(Role.code == "employee"))
        user.roles.append(employee_role)
        db.commit()
    session = client.post(
        "/api/v1/auth/login",
        json={"username": "portal-unlinked", "password": PORTAL_PASSWORD},
    )
    assert session.status_code == 200
    assert session.json()["user"]["permissions"] == ["customer_portal.access"]
    assert client.get("/api/v1/customer-portal/me").status_code == 403
    assert client.get("/api/v1/customers").status_code == 403
    assert client.get("/api/v1/employees").status_code == 403


def test_linked_account_stays_restricted_if_its_role_is_changed(client: TestClient):
    admin_headers = sign_in(client)
    customer = create_customer(client, admin_headers, "Rollenwechsel-Testkunde")
    contact = create_contact(client, admin_headers, customer["id"])
    user_id = create_role_user("portal-role-change")
    linked = client.post(
        "/api/v1/customer-portal/links",
        headers=admin_headers,
        json={"user_id": str(user_id), "contact_id": contact["id"]},
    )
    assert linked.status_code == 201

    with TestingSessionLocal() as db:
        user = db.get(User, user_id)
        employee_role = db.scalar(select(Role).where(Role.code == "employee"))
        user.roles = [employee_role]
        db.commit()

    client.post("/api/v1/auth/logout", headers=admin_headers)
    session = client.post(
        "/api/v1/auth/login",
        json={"username": "portal-role-change", "password": PORTAL_PASSWORD},
    )
    assert session.status_code == 200
    assert session.json()["user"]["roles"] == ["customer_portal"]
    assert session.json()["user"]["permissions"] == ["customer_portal.access"]
    assert client.get("/api/v1/customer-portal/me").status_code == 403
    assert client.get("/api/v1/employees").status_code == 403
