import stat
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID

from conftest import ADMIN_PASSWORD, TestingSessionLocal
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import malware_scanner
from app.config import get_settings
from app.identity_api import password_hasher
from app.malware_scanner import MalwareDetected, MalwareScannerError
from app.models import (
    AuditLog,
    Contract,
    ContractHistory,
    Document,
    DocumentContractReminder,
    DocumentHistory,
    DocumentVersion,
    Role,
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


def create_test_user(username: str, role_code: str) -> UUID:
    with TestingSessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == role_code))
        assert role is not None
        user = User(
            username=username,
            email=f"{username}@example.com",
            full_name=f"Test {username}",
            password_hash=password_hasher.hash("documents-test-passwort-2026"),
            roles=[role],
        )
        db.add(user)
        db.commit()
        return user.id


def upload_pdf(client: TestClient, headers: dict[str, str], filename: str = "vertrag.pdf"):
    return client.post(
        "/api/v1/documents",
        headers=headers,
        data={
            "document_number": "D-2026-001",
            "title": "Testvertrag",
            "category": "Vertrag",
            "status": "active",
        },
        files={"file": (filename, b"%PDF-1.7\nprivate test document", "application/pdf")},
    )


def test_document_upload_validation_version_download_and_archive(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "document_storage_path", tmp_path)
    unauthenticated = client.get("/api/v1/documents")
    assert unauthenticated.status_code == 401
    headers = sign_in(client)

    invalid = client.post(
        "/api/v1/documents",
        headers=headers,
        data={"document_number": "D-BAD", "title": "Ungültig", "category": "Test"},
        files={"file": ("bad.pdf", b"kein PDF", "application/pdf")},
    )
    assert invalid.status_code == 415
    mismatch = client.post(
        "/api/v1/documents",
        headers=headers,
        data={"document_number": "D-MIME", "title": "MIME", "category": "Test"},
        files={"file": ("bild.png", b"%PDF-1.7\nwrong extension", "image/png")},
    )
    assert mismatch.status_code == 415

    created = upload_pdf(client, headers, "../../vertrag.pdf")
    assert created.status_code == 201, created.text
    document = created.json()
    assert document["latest_version"]["version"] == 1
    detail = client.get(f"/api/v1/documents/{document['id']}", headers=headers).json()
    version = detail["versions"][0]
    assert version["file_name"] == "vertrag.pdf"
    actual_files = list(tmp_path.iterdir())
    assert len(actual_files) == 1
    assert stat.S_IMODE(actual_files[0].stat().st_mode) == 0o600

    download = client.get(
        f"/api/v1/documents/{document['id']}/versions/{version['id']}/download",
        headers=headers,
    )
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF-")
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["cache-control"] == "private, no-store"
    assert download.headers["x-content-type-options"] == "nosniff"

    receipt = client.post(
        f"/api/v1/documents/versions/{version['id']}/read-receipt",
        headers=headers,
    )
    assert receipt.status_code == 200
    assert receipt.json()["version_id"] == version["id"]
    assert (
        client.post(
            f"/api/v1/documents/versions/{version['id']}/read-receipt",
            headers=headers,
        ).json()["id"]
        == receipt.json()["id"]
    )

    requested = client.post(
        f"/api/v1/documents/versions/{version['id']}/approvals",
        headers=headers,
    )
    assert requested.status_code == 201
    approval_id = requested.json()["id"]
    decision = client.patch(
        f"/api/v1/documents/approvals/{approval_id}",
        headers=headers,
        json={"status": "approved", "decision_note": "Geprüft"},
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "approved"

    added_version = client.post(
        f"/api/v1/documents/{document['id']}/versions",
        headers=headers,
        files={"file": ("version-2.pdf", b"%PDF-1.7\nupdated test content", "application/pdf")},
    )
    assert added_version.status_code == 201, added_version.text
    assert added_version.json()["version"] == 2

    archived = client.post(f"/api/v1/documents/{document['id']}/archive", headers=headers)
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert client.get("/api/v1/documents").json()["total"] == 0
    restored = client.post(f"/api/v1/documents/{document['id']}/restore", headers=headers)
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"

    with TestingSessionLocal() as db:
        history_actions = set(
            db.scalars(
                select(DocumentHistory.action).where(
                    DocumentHistory.document_id == UUID(document["id"])
                )
            ).all()
        )
        audit_actions = set(db.scalars(select(AuditLog.action)).all())
        assert {
            "created",
            "version_uploaded",
            "read_confirmed",
            "approval_requested",
            "approval_approved",
            "archived",
            "restored",
        } <= history_actions
        assert {"documents.uploaded", "documents.downloaded", "documents.archived"} <= audit_actions
        assert db.scalar(select(DocumentVersion).where(DocumentVersion.version == 2)) is not None
        assert db.scalar(select(Document).where(Document.id == UUID(document["id"]))) is not None


def test_documents_scope_and_role_permissions(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "document_storage_path", tmp_path)
    admin_headers = sign_in(client)
    created = upload_pdf(client, admin_headers)
    assert created.status_code == 201
    create_test_user("objektleitung-test", "object_manager")
    restricted_headers = sign_in(client, "objektleitung-test", "documents-test-passwort-2026")
    assert client.get("/api/v1/documents", headers=restricted_headers).json()["total"] == 0
    detail = client.get(
        f"/api/v1/documents/{created.json()['id']}",
        headers=restricted_headers,
    )
    assert detail.status_code == 404
    denied_download = client.get(
        f"/api/v1/documents/{created.json()['id']}/versions/"
        f"{created.json()['latest_version']['id']}/download",
        headers=restricted_headers,
    )
    assert denied_download.status_code == 404


def test_document_and_version_uploads_fail_closed_on_scan_rejection(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "document_storage_path", tmp_path)
    headers = sign_in(client)
    with TestingSessionLocal() as db:
        rejected_uploads_before = db.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "uploads.rejected")
        )

    def infected(_content: bytes) -> None:
        raise MalwareDetected

    monkeypatch.setattr("app.upload_scanning.scan_upload", infected)
    rejected = upload_pdf(client, headers)
    assert rejected.status_code == 422
    with TestingSessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Document)) == 0
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "uploads.rejected")
            )
            == rejected_uploads_before + 1
        )
    assert list(tmp_path.iterdir()) == []

    monkeypatch.setattr(get_settings(), "malware_scan_max_bytes", 5)
    monkeypatch.setattr("app.upload_scanning.scan_upload", malware_scanner.scan_upload)
    size_limited = upload_pdf(client, headers)
    assert size_limited.status_code == 413
    assert list(tmp_path.iterdir()) == []

    def unavailable(_content: bytes) -> None:
        raise MalwareScannerError("timeout")

    monkeypatch.setattr("app.upload_scanning.scan_upload", unavailable)
    failed = upload_pdf(client, headers)
    assert failed.status_code == 503
    assert list(tmp_path.iterdir()) == []

    monkeypatch.setattr("app.upload_scanning.scan_upload", lambda _content: None)
    created = upload_pdf(client, headers)
    assert created.status_code == 201
    document_id = created.json()["id"]

    monkeypatch.setattr("app.upload_scanning.scan_upload", unavailable)
    version = client.post(
        f"/api/v1/documents/{document_id}/versions",
        headers=headers,
        files={"file": ("version-2.pdf", b"%PDF-1.7\nversion", "application/pdf")},
    )
    assert version.status_code == 503
    with TestingSessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(DocumentVersion)
                .where(DocumentVersion.document_id == UUID(document_id))
            )
            == 1
        )
    assert len(list(tmp_path.iterdir())) == 1


def test_contract_history_and_idempotent_reminders(client: TestClient) -> None:
    headers = sign_in(client)
    customer_response = client.post(
        "/api/v1/customers",
        headers=headers,
        json={"company_name": "Testkunde Vertragsverwaltung"},
    )
    assert customer_response.status_code == 201
    customer_id = customer_response.json()["id"]
    today = date.today()
    contract_response = client.post(
        "/api/v1/contracts",
        headers=headers,
        json={
            "contract_number": "V-2026-001",
            "name": "Objektschutz",
            "contract_type": "customer",
            "counterparty": "Testpartner",
            "customer_id": customer_id,
            "starts_on": str(today),
            "ends_on": str(today + timedelta(days=200)),
            "notice_period_days": 30,
            "renewal_rule": "Verlängerung um zwölf Monate",
            "status": "active",
            "internal_notes": "Interne Testnotiz",
        },
    )
    assert contract_response.status_code == 201, contract_response.text
    contract_id = contract_response.json()["id"]
    assert contract_response.json()["history"][0]["action"] == "created"

    updated = client.patch(
        f"/api/v1/contracts/{contract_id}",
        headers=headers,
        json={"internal_notes": "Aktualisierte Testnotiz"},
    )
    assert updated.status_code == 200
    assert updated.json()["history"][0]["action"] == "updated"

    settings_response = client.put(
        "/api/v1/reminders/settings",
        headers=headers,
        json={"lead_days": [90, 30, 7]},
    )
    assert settings_response.status_code == 200
    assert settings_response.json()["lead_days"] == [90, 30, 7]
    generated = client.post("/api/v1/reminders/generate", headers=headers)
    assert generated.status_code == 200
    assert generated.json()["created"] == 9
    assert client.post("/api/v1/reminders/generate", headers=headers).json()["created"] == 0
    reminders = client.get("/api/v1/reminders", headers=headers).json()
    assert len(reminders) == 9
    assert {item["reminder_type"] for item in reminders} == {
        "contract_expiry",
        "contract_termination",
        "contract_renewal",
    }

    completed = client.patch(
        f"/api/v1/reminders/{reminders[0]['id']}",
        headers=headers,
        json={"status": "completed"},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert len(client.get("/api/v1/reminders", headers=headers).json()) == 8
    settings_response = client.put(
        "/api/v1/reminders/settings",
        headers=headers,
        json={"lead_days": [90, 30]},
    )
    assert settings_response.status_code == 200
    assert client.post("/api/v1/reminders/generate", headers=headers).json()["created"] == 0
    open_reminders = client.get("/api/v1/reminders", headers=headers).json()
    assert all(
        (date.fromisoformat(item["event_on"]) - date.fromisoformat(item["remind_on"])).days
        in {90, 30}
        for item in open_reminders
    )

    archived = client.post(f"/api/v1/contracts/{contract_id}/archive", headers=headers)
    assert archived.status_code == 200
    restored = client.post(f"/api/v1/contracts/{contract_id}/restore", headers=headers)
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"

    with TestingSessionLocal() as db:
        assert db.scalar(select(Contract).where(Contract.id == UUID(contract_id))) is not None
        history_actions = set(
            db.scalars(
                select(ContractHistory.action).where(
                    ContractHistory.contract_id == UUID(contract_id)
                )
            ).all()
        )
        assert {"created", "updated", "archived", "restored"} <= history_actions
        assert db.scalar(select(func.count()).select_from(DocumentContractReminder)) == 9
        assert (
            db.scalar(select(AuditLog).where(AuditLog.action == "contracts.reminders_generated"))
            is not None
        )


def test_contract_relation_constraints_are_declared() -> None:
    assert any(
        foreign_key.target_fullname == "customers.id"
        for foreign_key in Contract.__table__.foreign_keys
    )
    assert any(
        foreign_key.target_fullname == "documents.id"
        for foreign_key in Contract.__table__.foreign_keys
    )
    assert any(
        foreign_key.target_fullname == "documents.id"
        for foreign_key in DocumentVersion.__table__.foreign_keys
    )
