import csv
import hashlib
import importlib
import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from threading import Barrier
from uuid import UUID

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from conftest import ADMIN_PASSWORD, TestingSessionLocal, app, test_engine
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from test_time_tracking import setup_tracking

from app.models import (
    AuditLog,
    BillingExport,
    BillingInvoice,
    BillingInvoiceLine,
    Notification,
    NotificationOutbox,
    Role,
    TimeEntry,
    TimeEntrySegment,
    User,
)
from app.notification_worker import NotificationOutboxWorker


def test_billing_corrections_migration_refuses_existing_duplicates() -> None:
    migration = importlib.import_module("migrations.versions.0039_unique_billing_corrections")
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE billing_invoices (correction_of_id TEXT)")
            connection.exec_driver_sql(
                "INSERT INTO billing_invoices (correction_of_id) VALUES ('original'), ('original')"
            )
            context = MigrationContext.configure(connection)
            with (
                Operations.context(context),
                pytest.raises(RuntimeError, match="mehrere Korrektur- oder Stornobelege"),
            ):
                migration.upgrade()
            assert connection.scalar(text("SELECT COUNT(*) FROM billing_invoices")) == 2
            assert not inspect(connection).get_indexes("billing_invoices")
    finally:
        engine.dispose()


def test_billing_corrections_migration_creates_partial_unique_index() -> None:
    migration = importlib.import_module("migrations.versions.0039_unique_billing_corrections")
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE billing_invoices (correction_of_id TEXT)")
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.upgrade()

        with engine.begin() as connection:
            index = inspect(connection).get_indexes("billing_invoices")[0]
            assert index["name"] == "uq_billing_invoices_correction_of"
            assert index["unique"] == 1
            assert "correction_of_id IS NOT NULL" in str(index["dialect_options"]["sqlite_where"])
            connection.exec_driver_sql(
                "INSERT INTO billing_invoices (correction_of_id) VALUES (NULL), (NULL), ('original')"
            )

        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO billing_invoices (correction_of_id) VALUES ('original')"
            )

        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text(
                        "SELECT COUNT(*) FROM billing_invoices WHERE correction_of_id = 'original'"
                    )
                )
                == 1
            )
    finally:
        engine.dispose()


def sign_in(client: TestClient, username: str = "admin", password: str = ADMIN_PASSWORD):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": client.cookies.get("securityops_csrf", "")}


def create_invoice(client: TestClient, headers: dict[str, str]):
    customer = client.post("/api/v1/customers", headers=headers, json={"company_name": "Testkunde"})
    assert customer.status_code == 201, customer.text
    rate = client.post(
        "/api/v1/billing/rates",
        headers=headers,
        json={
            "code": "STD-TEST",
            "name": "Testleistung",
            "kind": "hourly",
            "unit": "Stunde",
            "unit_price": "0.05",
            "tax_code": "TEST",
            "tax_rate": "10",
        },
    )
    assert rate.status_code == 201, rate.text
    response = client.post(
        "/api/v1/billing/invoices",
        headers=headers,
        json={
            "idempotency_key": "invoice-test-key-001",
            "customer_id": customer.json()["id"],
            "issued_on": "2026-11-08",
            "due_on": "2026-12-08",
            "lines": [{"rate_id": rate.json()["id"], "quantity": "1"}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_invoice_rounding_state_machine_correction_and_export(client: TestClient):
    headers = sign_in(client)
    invoice = create_invoice(client, headers)
    assert invoice["net_amount"] == "0.05"
    assert invoice["tax_amount"] == "0.01"
    assert invoice["gross_amount"] == "0.06"
    assert invoice["lines"][0]["tax_code"] == "TEST"
    assert client.get(f"/api/v1/billing/invoices/{invoice['id']}/pdf").status_code == 409
    draft_export = client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/exports",
        headers=headers,
        params={"idempotency_key": "draft-export-test-001"},
    )
    assert draft_export.status_code == 409
    draft_csv_export = client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/exports/csv",
        headers=headers,
        params={"idempotency_key": "draft-csv-export-001"},
    )
    assert draft_csv_export.status_code == 409

    repeated = client.post(
        "/api/v1/billing/invoices",
        headers=headers,
        json={
            "idempotency_key": "invoice-test-key-001",
            "customer_id": invoice["customer_id"],
            "issued_on": "2026-11-08",
            "due_on": "2026-12-08",
            "lines": [{"rate_id": invoice["lines"][0]["id"], "quantity": "1"}],
        },
    )
    assert repeated.status_code == 409

    approved = client.post(f"/api/v1/billing/invoices/{invoice['id']}/approve", headers=headers)
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert (
        client.post(
            f"/api/v1/billing/invoices/{invoice['id']}/approve", headers=headers
        ).status_code
        == 409
    )
    pdf = client.get(f"/api/v1/billing/invoices/{invoice['id']}/pdf")
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF-1.4")
    assert pdf.headers["cache-control"] == "private, no-store"
    assert pdf.headers["x-content-type-options"] == "nosniff"

    correction = client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/corrections",
        headers=headers,
        json={
            "idempotency_key": "correction-test-001",
            "reason": "Nachvollziehbarer Korrekturtest",
            "issued_on": "2026-11-09",
            "due_on": "2026-12-09",
        },
    )
    assert correction.status_code == 201, correction.text
    assert correction.json()["correction_of_id"] == invoice["id"]
    assert correction.json()["kind"] == "cancellation"
    assert correction.json()["gross_amount"] == "-0.06"
    correction_retry = client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/corrections",
        headers=headers,
        json={
            "idempotency_key": "correction-test-001",
            "reason": "Nachvollziehbarer Korrekturtest",
            "issued_on": "2026-11-09",
            "due_on": "2026-12-09",
        },
    )
    assert correction_retry.status_code == 201
    assert correction_retry.json()["id"] == correction.json()["id"]
    duplicate_correction = client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/corrections",
        headers=headers,
        json={
            "idempotency_key": "correction-test-002",
            "reason": "Zweiter Beleg darf die Originalrechnung nicht nochmals stornieren",
            "issued_on": "2026-11-09",
            "due_on": "2026-12-09",
        },
    )
    assert duplicate_correction.status_code == 409
    assert "bereits ein Korrektur- oder Stornobeleg" in duplicate_correction.json()["detail"]
    assert (
        client.post(
            f"/api/v1/billing/invoices/{invoice['id']}/archive",
            headers=headers,
            json={"reason": "Archivtest"},
        ).status_code
        == 200
    )

    exported = client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/exports",
        headers=headers,
        params={"idempotency_key": "export-test-key-001"},
    )
    assert exported.status_code == 201, exported.text
    exported_data = exported.json()
    assert exported_data["payload"]["schema_version"] == "securityops-accounting-v1"
    serialized_payload = json.dumps(
        exported_data["payload"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    expected_digest = hashlib.sha256(serialized_payload.encode("utf-8")).hexdigest()
    assert exported_data["payload_sha256"] == expected_digest
    duplicate_export = client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/exports",
        headers=headers,
        params={"idempotency_key": "export-test-key-001"},
    )
    assert duplicate_export.status_code == 201
    assert duplicate_export.json()["id"] == exported.json()["id"]

    payment = client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/payments",
        headers=headers,
        json={
            "idempotency_key": "payment-test-001",
            "amount": "0.06",
            "paid_on": "2026-11-09",
        },
    )
    assert payment.status_code == 201, payment.text
    listing = client.get("/api/v1/billing/invoices", headers=headers).json()
    assert next(item for item in listing if item["id"] == invoice["id"])["payment_status"] == "paid"
    with TestingSessionLocal() as db:
        stored = db.scalar(select(BillingInvoice).where(BillingInvoice.id == UUID(invoice["id"])))
        assert stored is not None
        assert (
            db.scalar(
                select(func.count())
                .select_from(BillingInvoice)
                .where(BillingInvoice.correction_of_id == UUID(invoice["id"]))
            )
            == 1
        )
        assert (
            db.scalar(
                select(BillingInvoiceLine).where(
                    BillingInvoiceLine.invoice_id == UUID(correction.json()["id"])
                )
            ).unit_price
            < 0
        )
        assert (
            db.scalar(
                select(AuditLog).where(
                    AuditLog.entity_type == "billing_invoice",
                    AuditLog.entity_id == invoice["id"],
                    AuditLog.action == "billing.invoice.approved",
                )
            )
            is not None
        )


@pytest.mark.skipif(
    test_engine.dialect.name != "postgresql",
    reason="PostgreSQL-Unique-Index unter parallelen Transaktionen",
)
def test_postgresql_prevents_concurrent_duplicate_invoice_corrections(client: TestClient):
    headers = sign_in(client)
    original = create_invoice(client, headers)
    approved = client.post(f"/api/v1/billing/invoices/{original['id']}/approve", headers=headers)
    assert approved.status_code == 200
    original_id = UUID(original["id"])
    barrier = Barrier(2)

    def create_correction(suffix: str) -> str | None:
        with TestingSessionLocal() as db:
            assert (
                db.scalar(
                    select(BillingInvoice.id).where(BillingInvoice.correction_of_id == original_id)
                )
                is None
            )
            barrier.wait(timeout=10)
            db.add(
                BillingInvoice(
                    invoice_number=f"R-2026-CONCURRENCY-{suffix}",
                    idempotency_key=f"billing-concurrent-correction-{suffix}",
                    customer_id=UUID(original["customer_id"]),
                    kind="cancellation",
                    status="draft",
                    payment_status="open",
                    dunning_status="none",
                    currency="EUR",
                    issued_on=date(2026, 11, 9),
                    due_on=date(2026, 12, 9),
                    correction_of_id=original_id,
                    correction_reason="Synthetischer Parallelitätstest",
                    customer_snapshot={},
                    inputs_snapshot={},
                    net_amount=0,
                    tax_amount=0,
                    gross_amount=0,
                )
            )
            try:
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                assert exc.orig.diag.constraint_name == "uq_billing_invoices_correction_of"
                return "duplicate"
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(create_correction, ("a", "b")))

    assert sorted(outcome or "created" for outcome in outcomes) == ["created", "duplicate"]
    with TestingSessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(BillingInvoice)
                .where(BillingInvoice.correction_of_id == original_id)
            )
            == 1
        )


@pytest.mark.skipif(
    test_engine.dialect.name != "postgresql",
    reason="PostgreSQL-parallele Rechnungs-Korrekturanfragen",
)
def test_postgresql_concurrent_correction_requests_create_one_followup(client: TestClient):
    headers = sign_in(client)
    original = create_invoice(client, headers)
    approved = client.post(f"/api/v1/billing/invoices/{original['id']}/approve", headers=headers)
    assert approved.status_code == 200
    barrier = Barrier(2)
    session_cookie = client.cookies.get("securityops_session")
    csrf_cookie = client.cookies.get("securityops_csrf")
    assert session_cookie and csrf_cookie

    def submit_correction(suffix: str) -> int:
        with TestClient(app) as concurrent_client:
            concurrent_client.cookies.set(
                "securityops_session", session_cookie, domain="testserver.local", path="/"
            )
            concurrent_client.cookies.set(
                "securityops_csrf", csrf_cookie, domain="testserver.local", path="/"
            )
            barrier.wait(timeout=10)
            response = concurrent_client.post(
                f"/api/v1/billing/invoices/{original['id']}/corrections",
                headers=headers,
                json={
                    "idempotency_key": f"parallel-correction-{suffix}-001",
                    "reason": "Synthetischer paralleler Anfragetest",
                    "issued_on": "2026-11-09",
                    "due_on": "2026-12-09",
                },
            )
            return response.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        status_codes = list(pool.map(submit_correction, ("a", "b")))

    assert sorted(status_codes) == [201, 409]
    with TestingSessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(BillingInvoice)
                .where(BillingInvoice.correction_of_id == UUID(original["id"]))
            )
            == 1
        )


def test_billing_routes_require_finance_permissions(client: TestClient):
    admin_headers = sign_in(client)
    invoice = create_invoice(client, admin_headers)
    headers = sign_in(client, "geschaeftsfuehrung", "management-test-passwort-2026")
    assert client.get("/api/v1/billing/invoices", headers=headers).status_code == 403
    assert (
        client.post(
            f"/api/v1/billing/invoices/{invoice['id']}/exports",
            headers=headers,
            params={"idempotency_key": "unauthorized-export-001"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/billing/invoices/{invoice['id']}/exports/csv",
            headers=headers,
            params={"idempotency_key": "unauthorized-csv-001"},
        ).status_code
        == 403
    )


def test_csv_export_uses_saved_snapshot_and_escapes_spreadsheet_formulas(
    client: TestClient,
):
    headers = sign_in(client)
    invoice = create_invoice(client, headers)
    invoice_id = UUID(invoice["id"])
    dangerous_name = "\t+SUM(1,1)"
    dangerous_description = (
        '\u00a0=HYPERLINK("https://example.invalid","Klick"), Zeile 1\r\nZeile 2'
    )
    with TestingSessionLocal() as db:
        stored_invoice = db.get(BillingInvoice, invoice_id)
        assert stored_invoice is not None
        stored_invoice.customer_snapshot = {
            **stored_invoice.customer_snapshot,
            "company_name": dangerous_name,
        }
        line = db.scalar(
            select(BillingInvoiceLine).where(BillingInvoiceLine.invoice_id == invoice_id)
        )
        assert line is not None
        line.description = dangerous_description
        db.commit()

    approved = client.post(f"/api/v1/billing/invoices/{invoice['id']}/approve", headers=headers)
    assert approved.status_code == 200
    snapshot = client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/exports",
        headers=headers,
        params={"idempotency_key": "existing-json-snapshot-001"},
    )
    assert snapshot.status_code == 201
    params = {"idempotency_key": "csv-snapshot-test-001"}
    response = client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/exports/csv",
        headers=headers,
        params=params,
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content.endswith(b"\r\n")
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8"), newline="")))
    assert len(rows) == 1
    row = rows[0]
    assert row["export_version"] == "securityops-accounting-csv-v1"
    assert row["invoice_number"] == invoice["invoice_number"]
    assert row["customer_name"] == f"'{dangerous_name}"
    assert row["description"] == f"'{dangerous_description}"
    assert row["quantity"] == "1.0000"
    assert row["unit_price"] == "0.0500"
    assert row["line_net_amount"] == "0.05"
    assert row["line_tax_amount"] == "0.01"
    assert row["line_gross_amount"] == "0.06"
    assert row["invoice_net_amount"] == "0.05"
    assert row["invoice_tax_amount"] == "0.01"
    assert row["invoice_gross_amount"] == "0.06"

    with TestingSessionLocal() as db:
        export = db.scalar(
            select(BillingExport).where(
                BillingExport.invoice_id == invoice_id,
                BillingExport.format_version == "securityops-accounting-v1",
            )
        )
        assert export is not None
        assert export.payload["customer"]["company_name"] == dangerous_name
        assert export.payload["lines"][0]["description"] == dangerous_description
        csv_audit = db.scalar(
            select(AuditLog)
            .where(
                AuditLog.entity_id == str(invoice_id),
                AuditLog.action == "billing.invoice.csv_exported",
            )
            .order_by(AuditLog.created_at.desc())
        )
        assert csv_audit is not None
        assert csv_audit.details["format_version"] == "securityops-accounting-csv-v1"
        assert csv_audit.details["source_payload_sha256"] == export.payload_sha256
        assert csv_audit.details["csv_sha256"] == hashlib.sha256(response.content).hexdigest()
        stored_invoice = db.get(BillingInvoice, invoice_id)
        assert stored_invoice is not None
        stored_invoice.customer_snapshot = {
            **stored_invoice.customer_snapshot,
            "company_name": "Später geänderter Livewert",
        }
        live_line = db.scalar(
            select(BillingInvoiceLine).where(BillingInvoiceLine.invoice_id == invoice_id)
        )
        assert live_line is not None
        live_line.description = "Später geänderter Livewert"
        db.commit()

    repeated = client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/exports/csv",
        headers=headers,
        params={"idempotency_key": "csv-repeat-request-002"},
    )
    assert repeated.status_code == 200
    assert repeated.content == response.content
    assert "Später geänderter Livewert" not in repeated.text


def test_csv_export_rejects_malformed_saved_snapshot(client: TestClient):
    headers = sign_in(client)
    invoice = create_invoice(client, headers)
    invoice_id = UUID(invoice["id"])
    approved = client.post(f"/api/v1/billing/invoices/{invoice['id']}/approve", headers=headers)
    assert approved.status_code == 200
    export = client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/exports",
        headers=headers,
        params={"idempotency_key": "csv-invalid-snapshot-001"},
    )
    assert export.status_code == 201
    with TestingSessionLocal() as db:
        stored_export = db.scalar(
            select(BillingExport).where(
                BillingExport.invoice_id == invoice_id,
                BillingExport.format_version == "securityops-accounting-v1",
            )
        )
        assert stored_export is not None
        stored_export.payload = {
            "customer": [],
            "totals": {},
            "lines": [{"position": "one"}],
        }
        db.commit()

    response = client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/exports/csv",
        headers=headers,
        params={"idempotency_key": "csv-invalid-snapshot-001"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Gespeicherter Rechnungsexport ist fehlerhaft."
    with TestingSessionLocal() as db:
        stored_export = db.scalar(
            select(BillingExport).where(
                BillingExport.invoice_id == invoice_id,
                BillingExport.format_version == "securityops-accounting-v1",
            )
        )
        assert stored_export is not None
        serialized = json.dumps(
            stored_export.payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        stored_export.payload_sha256 = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        db.commit()
    malformed_but_hashed = client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/exports/csv",
        headers=headers,
        params={"idempotency_key": "csv-invalid-snapshot-001"},
    )
    assert malformed_but_hashed.status_code == 409
    assert malformed_but_hashed.json()["detail"] == "Gespeicherter Rechnungsexport ist fehlerhaft."


def test_invoice_approval_emits_minimal_idempotent_notification(client: TestClient):
    headers = sign_in(client)
    invoice = create_invoice(client, headers)
    rule_response = client.post(
        "/api/v1/automations/rules",
        headers=headers,
        json={
            "name": "Vertrauliche Regelbezeichnung",
            "trigger_type": "billing.invoice_approved",
            "conditions": {},
            "action_type": "notify_event_recipients",
        },
    )
    assert rule_response.status_code == 201, rule_response.text
    rule = rule_response.json()
    assert (
        client.patch(
            f"/api/v1/automations/rules/{rule['id']}",
            headers=headers,
            json={"is_active": True},
        ).status_code
        == 200
    )

    management_headers = sign_in(client, "geschaeftsfuehrung", "management-test-passwort-2026")
    assert (
        client.post(
            f"/api/v1/billing/invoices/{invoice['id']}/approve",
            headers=management_headers,
        ).status_code
        == 403
    )
    headers = sign_in(client)
    approved = client.post(f"/api/v1/billing/invoices/{invoice['id']}/approve", headers=headers)
    assert approved.status_code == 200
    assert (
        client.post(
            f"/api/v1/billing/invoices/{invoice['id']}/approve", headers=headers
        ).status_code
        == 409
    )

    with TestingSessionLocal() as db:
        event = db.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.event_type == "billing.invoice_approved",
                NotificationOutbox.aggregate_id == UUID(invoice["id"]),
            )
        )
        assert event is not None
        assert set(event.payload) == {"schema_version", "invoice_id", "recipient_ids"}
        assert event.payload["schema_version"] == 1
        assert event.payload["invoice_id"] == invoice["id"]
        administrator = db.scalar(select(User).where(User.username == "admin"))
        management = db.scalar(select(User).where(User.username == "geschaeftsfuehrung"))
        assert administrator is not None and management is not None
        assert event.payload["recipient_ids"] == [str(administrator.id)]
        assert str(management.id) not in event.payload["recipient_ids"]
        event_id = event.id

    worker = NotificationOutboxWorker(TestingSessionLocal)
    assert worker.run_once().delivered == 1
    assert worker.run_once().delivered == 1
    assert worker.run_once().claimed == 0
    with TestingSessionLocal() as db:
        action_count = db.scalar(
            select(func.count())
            .select_from(NotificationOutbox)
            .where(
                NotificationOutbox.event_type == "automation.notification",
                NotificationOutbox.aggregate_id == UUID(invoice["id"]),
            )
        )
        notification = db.scalar(
            select(Notification).where(Notification.invoice_id == UUID(invoice["id"]))
        )
        assert action_count == 1
        assert notification is not None
        assert notification.outbox_id is not None
        assert notification.title == "Rechnungsfreigabe erfasst"
        assert notification.body == "Eine Rechnung wurde manuell freigegeben."
        assert "Vertrauliche Regelbezeichnung" not in notification.title + notification.body
        assert notification.task_id is None and notification.object_id is None
        source = db.get(NotificationOutbox, event_id)
        assert source is not None and source.status == "completed"
        stored_invoice = db.get(BillingInvoice, UUID(invoice["id"]))
        assert stored_invoice is not None
        assert stored_invoice.payment_status == "open"
        assert stored_invoice.dunning_status == "none"

    admin_headers = sign_in(client)
    visible = client.get("/api/v1/notifications", headers=admin_headers)
    assert visible.status_code == 200
    assert any(item["invoice_id"] == invoice["id"] for item in visible.json()["items"])
    management_headers = sign_in(client, "geschaeftsfuehrung", "management-test-passwort-2026")
    assert client.get("/api/v1/notifications", headers=management_headers).json()["total"] == 0


def test_invoice_approval_and_outbox_roll_back_together(client: TestClient, monkeypatch):
    headers = sign_in(client)
    invoice = create_invoice(client, headers)

    def fail_commit(_db, _message):
        raise HTTPException(status_code=409, detail="Testfehler vor Commit")

    monkeypatch.setattr("app.billing_api.commit_or_conflict", fail_commit)
    response = client.post(f"/api/v1/billing/invoices/{invoice['id']}/approve", headers=headers)
    assert response.status_code == 409
    with TestingSessionLocal() as db:
        stored = db.get(BillingInvoice, UUID(invoice["id"]))
        assert stored is not None and stored.status == "draft"
        assert (
            db.scalar(
                select(NotificationOutbox).where(
                    NotificationOutbox.event_type == "billing.invoice_approved",
                    NotificationOutbox.aggregate_id == UUID(invoice["id"]),
                )
            )
            is None
        )


def test_invoice_worker_rejects_invalid_versioned_payload(client: TestClient):
    headers = sign_in(client)
    invoice = create_invoice(client, headers)
    assert (
        client.post(
            f"/api/v1/billing/invoices/{invoice['id']}/approve", headers=headers
        ).status_code
        == 200
    )
    with TestingSessionLocal() as db:
        event = db.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.event_type == "billing.invoice_approved"
            )
        )
        assert event is not None
        event.payload = {**event.payload, "schema_version": 2, "amount": "0.01"}
        db.commit()

    result = NotificationOutboxWorker(TestingSessionLocal).run_once()
    assert result.dead_lettered == 1
    with TestingSessionLocal() as db:
        event = db.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.event_type == "billing.invoice_approved"
            )
        )
        assert event is not None
        assert event.status == "dead_letter"
        assert event.last_error == "invalid_payload"
        assert (
            db.scalar(select(Notification).where(Notification.invoice_id == UUID(invoice["id"])))
            is None
        )


def test_invoice_worker_rejects_recipient_after_billing_access_revoked(client: TestClient):
    headers = sign_in(client)
    invoice = create_invoice(client, headers)
    assert (
        client.post(
            f"/api/v1/billing/invoices/{invoice['id']}/approve", headers=headers
        ).status_code
        == 200
    )
    with TestingSessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "administrator"))
        assert role is not None
        role.permissions = [
            permission
            for permission in role.permissions
            if permission.code != "billing.invoices.read"
        ]
        db.commit()

    result = NotificationOutboxWorker(TestingSessionLocal).run_once()
    assert result.dead_lettered == 1
    with TestingSessionLocal() as db:
        source = db.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.event_type == "billing.invoice_approved"
            )
        )
        assert source is not None
        assert source.status == "dead_letter"
        assert source.last_error == "unauthorized_recipient"
        assert (
            db.scalar(select(Notification).where(Notification.invoice_id == UUID(invoice["id"])))
            is None
        )


def test_invoice_uses_approved_time_snapshot_and_prevents_double_billing(client: TestClient):
    employee, obj, csrf = setup_tracking(client, "Testkunde Rechnungswesen Zeit")
    start = datetime.now(UTC) - timedelta(hours=3)
    end = start + timedelta(minutes=90)
    with TestingSessionLocal() as db:
        entry = TimeEntry(
            employee_id=UUID(employee["id"]),
            object_id=UUID(obj["id"]),
            started_at=start,
            ended_at=end,
            status="approved",
            segments=[
                TimeEntrySegment(
                    position=1,
                    kind="work",
                    started_at=start,
                    ended_at=end,
                )
            ],
        )
        db.add(entry)
        db.commit()
        entry_id = entry.id

    rate = client.post(
        "/api/v1/billing/rates",
        headers={"X-CSRF-Token": csrf},
        json={
            "code": "TIME-TEST",
            "name": "Freigegebene Arbeitszeit",
            "kind": "hourly",
            "unit": "Stunde",
            "unit_price": "80",
            "tax_code": "TEST",
            "tax_rate": "0",
        },
    )
    assert rate.status_code == 201, rate.text
    response = client.post(
        "/api/v1/billing/invoices",
        headers={"X-CSRF-Token": csrf},
        json={
            "idempotency_key": "time-invoice-test-001",
            "customer_id": obj["customer_id"],
            "issued_on": "2026-11-08",
            "due_on": "2026-12-08",
            "lines": [
                {
                    "rate_id": rate.json()["id"],
                    "quantity": "99",
                    "source_time_entry_ids": [str(entry_id)],
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    invoice = response.json()
    assert invoice["lines"][0]["quantity"] == "1.5000"
    assert invoice["net_amount"] == "120.00"
    with TestingSessionLocal() as db:
        stored = db.scalar(select(BillingInvoice).where(BillingInvoice.id == UUID(invoice["id"])))
        assert stored is not None
        assert stored.inputs_snapshot["source_time_entries"][0]["time_entry_id"] == str(entry_id)
        assert len(stored.inputs_snapshot["source_time_entries"][0]["segments"]) == 1

    duplicate = client.post(
        "/api/v1/billing/invoices",
        headers={"X-CSRF-Token": csrf},
        json={
            "idempotency_key": "time-invoice-test-002",
            "customer_id": obj["customer_id"],
            "issued_on": "2026-11-08",
            "due_on": "2026-12-08",
            "lines": [
                {
                    "rate_id": rate.json()["id"],
                    "quantity": "1",
                    "source_time_entry_ids": [str(entry_id)],
                }
            ],
        },
    )
    assert duplicate.status_code == 409
