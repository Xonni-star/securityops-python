"""Verify the migration chain upgrades a database containing existing data."""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import psycopg
from alembic.config import Config
from alembic.script import ScriptDirectory
from psycopg import sql
from sqlalchemy import URL, create_engine, text

BASE_REVISION = "0024_notification_outbox_worker"
INCIDENT_REVISION = "0025_unique_incident_owks_event"
PORTAL_REVISION = "0026_customer_portal_access"
DOCUMENT_GRANTS_REVISION = "0027_customer_document_grants"
CUSTOMER_REQUESTS_REVISION = "0028_customer_portal_requests"
AUDIT_REVISION = "0029_audit_integrity"
INVENTORY_REVISION = "0030_inventory_management"
AUTOMATION_REVISION = "0031_safe_automations"
EMPLOYEE_PORTAL_REVISION = "0032_employee_portal"
DOCUMENT_STORAGE_REVISION = "0033_encrypted_document_storage"
OWKS_AUTOMATION_REVISION = "0034_owks_automation_events"
MONITORING_REVISION = "0035_worker_monitoring"
BILLING_AUTOMATION_REVISION = "0036_billing_approval_automation"
OBJECT_QUALIFICATION_REVISION = "0037_object_qual_requirements"
DIGITAL_POLICIES_REVISION = "0038_digital_policies"
BILLING_CORRECTIONS_REVISION = "0039_unique_billing_corrections"


def admin_connection_options() -> dict[str, str | int]:
    return {
        "host": os.environ["POSTGRES_HOST"],
        "port": int(os.environ["POSTGRES_PORT"]),
        "user": os.environ["POSTGRES_ADMIN_USER"],
        "password": os.environ["POSTGRES_ADMIN_PASSWORD"],
    }


def migration_connection_options() -> dict[str, str | int]:
    return {
        "host": os.environ["POSTGRES_HOST"],
        "port": int(os.environ["POSTGRES_PORT"]),
        "user": "securityops_migrator",
        "password": os.environ["POSTGRES_MIGRATION_PASSWORD"],
    }


def verify_revision_chain() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    incident_revision = script.get_revision(INCIDENT_REVISION)
    portal_revision = script.get_revision(PORTAL_REVISION)
    if incident_revision is None or incident_revision.down_revision != BASE_REVISION:
        raise RuntimeError(f"{INCIDENT_REVISION} folgt nicht auf {BASE_REVISION}.")
    if portal_revision is None or portal_revision.down_revision != INCIDENT_REVISION:
        raise RuntimeError(f"{PORTAL_REVISION} folgt nicht auf {INCIDENT_REVISION}.")
    grants_revision = script.get_revision(DOCUMENT_GRANTS_REVISION)
    if grants_revision is None or grants_revision.down_revision != PORTAL_REVISION:
        raise RuntimeError(f"{DOCUMENT_GRANTS_REVISION} folgt nicht auf {PORTAL_REVISION}.")
    requests_revision = script.get_revision(CUSTOMER_REQUESTS_REVISION)
    if requests_revision is None or requests_revision.down_revision != DOCUMENT_GRANTS_REVISION:
        raise RuntimeError(
            f"{CUSTOMER_REQUESTS_REVISION} folgt nicht auf {DOCUMENT_GRANTS_REVISION}."
        )
    audit_revision = script.get_revision(AUDIT_REVISION)
    if audit_revision is None or audit_revision.down_revision != CUSTOMER_REQUESTS_REVISION:
        raise RuntimeError(f"{AUDIT_REVISION} folgt nicht auf {CUSTOMER_REQUESTS_REVISION}.")
    inventory_revision = script.get_revision(INVENTORY_REVISION)
    if inventory_revision is None or inventory_revision.down_revision != AUDIT_REVISION:
        raise RuntimeError(f"{INVENTORY_REVISION} folgt nicht auf {AUDIT_REVISION}.")
    automation_revision = script.get_revision(AUTOMATION_REVISION)
    if automation_revision is None or automation_revision.down_revision != INVENTORY_REVISION:
        raise RuntimeError(f"{AUTOMATION_REVISION} folgt nicht auf {INVENTORY_REVISION}.")
    employee_portal_revision = script.get_revision(EMPLOYEE_PORTAL_REVISION)
    if (
        employee_portal_revision is None
        or employee_portal_revision.down_revision != AUTOMATION_REVISION
    ):
        raise RuntimeError(f"{EMPLOYEE_PORTAL_REVISION} folgt nicht auf {AUTOMATION_REVISION}.")
    document_storage_revision = script.get_revision(DOCUMENT_STORAGE_REVISION)
    if (
        document_storage_revision is None
        or document_storage_revision.down_revision != EMPLOYEE_PORTAL_REVISION
    ):
        raise RuntimeError(
            f"{DOCUMENT_STORAGE_REVISION} folgt nicht auf {EMPLOYEE_PORTAL_REVISION}."
        )
    owks_automation_revision = script.get_revision(OWKS_AUTOMATION_REVISION)
    if (
        owks_automation_revision is None
        or owks_automation_revision.down_revision != DOCUMENT_STORAGE_REVISION
    ):
        raise RuntimeError(
            f"{OWKS_AUTOMATION_REVISION} folgt nicht auf {DOCUMENT_STORAGE_REVISION}."
        )
    monitoring_revision = script.get_revision(MONITORING_REVISION)
    if monitoring_revision is None or monitoring_revision.down_revision != OWKS_AUTOMATION_REVISION:
        raise RuntimeError(f"{MONITORING_REVISION} folgt nicht auf {OWKS_AUTOMATION_REVISION}.")
    billing_automation_revision = script.get_revision(BILLING_AUTOMATION_REVISION)
    if (
        billing_automation_revision is None
        or billing_automation_revision.down_revision != MONITORING_REVISION
    ):
        raise RuntimeError(f"{BILLING_AUTOMATION_REVISION} folgt nicht auf {MONITORING_REVISION}.")
    object_qualification_revision = script.get_revision(OBJECT_QUALIFICATION_REVISION)
    if (
        object_qualification_revision is None
        or object_qualification_revision.down_revision != BILLING_AUTOMATION_REVISION
    ):
        raise RuntimeError(
            f"{OBJECT_QUALIFICATION_REVISION} folgt nicht auf {BILLING_AUTOMATION_REVISION}."
        )
    digital_policies_revision = script.get_revision(DIGITAL_POLICIES_REVISION)
    if (
        digital_policies_revision is None
        or digital_policies_revision.down_revision != OBJECT_QUALIFICATION_REVISION
    ):
        raise RuntimeError(
            f"{DIGITAL_POLICIES_REVISION} folgt nicht auf {OBJECT_QUALIFICATION_REVISION}."
        )
    billing_corrections_revision = script.get_revision(BILLING_CORRECTIONS_REVISION)
    if (
        billing_corrections_revision is None
        or billing_corrections_revision.down_revision != DIGITAL_POLICIES_REVISION
    ):
        raise RuntimeError(
            f"{BILLING_CORRECTIONS_REVISION} folgt nicht auf {DIGITAL_POLICIES_REVISION}."
        )
    if script.get_heads() != [BILLING_CORRECTIONS_REVISION]:
        raise RuntimeError(f"Unerwartete Alembic-Heads: {script.get_heads()}")


def run_migration(revision: str, database_name: str) -> None:
    environment = os.environ | {
        "POSTGRES_DB": database_name,
        "POSTGRES_USER": "securityops_migrator",
        "POSTGRES_PASSWORD": os.environ["POSTGRES_MIGRATION_PASSWORD"],
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        check=True,
        env=environment,
    )


def main() -> None:
    verify_revision_chain()
    admin_options = admin_connection_options()
    migration_options = migration_connection_options()
    database_name = f"securityops_migration_data_{uuid4().hex}"
    with psycopg.connect(dbname="postgres", autocommit=True, **admin_options) as connection:
        connection.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(database_name), sql.Identifier("securityops_migrator")
            )
        )

    try:
        run_migration(BASE_REVISION, database_name)
        database_url = URL.create(
            "postgresql+psycopg",
            username=migration_options["user"],
            password=migration_options["password"],
            host=migration_options["host"],
            port=migration_options["port"],
            database=database_name,
        )
        engine = create_engine(database_url)
        audit_id = uuid4()
        outbox_id = uuid4()
        with engine.begin() as connection:
            customer_id = connection.execute(
                text(
                    "INSERT INTO customers "
                    "(customer_number, company_name, contract_status) "
                    "VALUES ("
                    "'CI-MIGRATION-EXISTING-DATA', "
                    "'Synthetischer Migrationskunde', "
                    "'none'"
                    ") "
                    "RETURNING id"
                )
            ).scalar_one()
            contact_id = connection.execute(
                text(
                    "INSERT INTO customer_contacts "
                    "(id, customer_id, first_name, last_name) "
                    "VALUES (gen_random_uuid(), :customer_id, 'Test', 'Kontakt') "
                    "RETURNING id"
                ),
                {"customer_id": customer_id},
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO audit_logs "
                    "(id, action, entity_type, entity_id, details) "
                    "VALUES (:id, 'ci.migration_fixture', 'migration_test', "
                    "'preserved', '{}'::json)"
                ),
                {"id": audit_id},
            )
            connection.execute(
                text(
                    "INSERT INTO notification_outbox "
                    "(id, dedupe_key, event_type, aggregate_type, aggregate_id, payload, "
                    "status, attempt_count, available_at) "
                    "VALUES (:id, :dedupe_key, 'task.assigned', 'task', :aggregate_id, "
                    "'{}'::json, 'pending', 2, now())"
                ),
                {
                    "id": outbox_id,
                    "dedupe_key": f"ci-migration:{outbox_id}",
                    "aggregate_id": uuid4(),
                },
            )
            for attempt_number in (1, 2):
                connection.execute(
                    text(
                        "INSERT INTO notification_outbox_attempts "
                        "(id, outbox_id, attempt_number, event) "
                        "VALUES (:id, :outbox_id, :attempt_number, 'claimed'), "
                        "(:retry_id, :outbox_id, :attempt_number, 'retry_scheduled')"
                    ),
                    {
                        "id": uuid4(),
                        "retry_id": uuid4(),
                        "outbox_id": outbox_id,
                        "attempt_number": attempt_number,
                    },
                )
        engine.dispose()

        run_migration("head", database_name)
        engine = create_engine(database_url)
        with engine.connect() as connection:
            if (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                != BILLING_CORRECTIONS_REVISION
            ):
                raise RuntimeError("Die Upgrade-Kette hat nicht beim aktuellen Head geendet.")
            if (
                connection.execute(
                    text("SELECT company_name FROM customers WHERE id = :id"),
                    {"id": customer_id},
                ).scalar_one()
                != "Synthetischer Migrationskunde"
            ):
                raise RuntimeError("Vorhandene Kundendaten wurden beim Upgrade verändert.")
            if (
                connection.execute(
                    text("SELECT customer_id FROM customer_contacts WHERE id = :id"),
                    {"id": contact_id},
                ).scalar_one()
                != customer_id
            ):
                raise RuntimeError("Vorhandene Kontaktdaten wurden beim Upgrade verändert.")
            if (
                connection.execute(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM pg_indexes "
                        "WHERE indexname = 'uq_incidents_owks_event_id')"
                    )
                ).scalar_one()
                is not True
            ):
                raise RuntimeError("Der eindeutige OWKS-Vorfallindex wurde nicht angelegt.")
            for table_name in (
                "customer_portal_links",
                "customer_portal_link_history",
                "customer_portal_document_grants",
                "customer_portal_document_grant_history",
                "customer_portal_requests",
                "customer_portal_request_messages",
                "customer_portal_request_attachments",
                "customer_portal_request_history",
                "employee_portal_document_grants",
                "employee_portal_document_grant_history",
            ):
                if not connection.execute(
                    text("SELECT to_regclass(:table_name) IS NOT NULL"),
                    {"table_name": table_name},
                ).scalar_one():
                    raise RuntimeError(f"Portal-Tabelle {table_name} fehlt nach dem Upgrade.")
            for table_name in (
                "employee_qualification_documents",
                "owks_attachments",
            ):
                if (
                    connection.execute(
                        text(
                            "SELECT count(*) FROM information_schema.columns "
                            "WHERE table_schema = 'public' AND table_name = :table_name "
                            "AND column_name = 'storage_key' AND is_nullable = 'YES'"
                        ),
                        {"table_name": table_name},
                    ).scalar_one()
                    != 1
                ):
                    raise RuntimeError(f"Verschlüsselte Dateireferenz fehlt in {table_name}.")
            for table_name in ("inventory_assets", "inventory_events"):
                if not connection.execute(
                    text("SELECT to_regclass(:table_name) IS NOT NULL"),
                    {"table_name": table_name},
                ).scalar_one():
                    raise RuntimeError(f"Inventartabelle {table_name} fehlt nach dem Upgrade.")
            if not connection.execute(
                text("SELECT to_regclass('notification_worker_heartbeats') IS NOT NULL")
            ).scalar_one():
                raise RuntimeError("Die Notification-Worker-Heartbeat-Tabelle fehlt.")
            if (
                connection.execute(
                    text(
                        "SELECT count(*) FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'notifications' "
                        "AND column_name = 'invoice_id' AND is_nullable = 'YES'"
                    )
                ).scalar_one()
                != 1
            ):
                raise RuntimeError("Der optionale Rechnungsbezug für Benachrichtigungen fehlt.")
            if (
                connection.execute(
                    text(
                        "SELECT count(*) FROM pg_constraint "
                        "WHERE conname = 'ck_automation_rules_trigger_type' "
                        "AND pg_get_constraintdef(oid) LIKE '%billing.invoice_approved%'"
                    )
                ).scalar_one()
                != 1
            ):
                raise RuntimeError("Der Rechnungsfreigabe-Auslöser ist nicht registriert.")
            inventory_permissions = connection.execute(
                text(
                    "SELECT count(*) FROM permissions "
                    "WHERE code IN ('inventory.read', 'inventory.manage', 'inventory.move')"
                )
            ).scalar_one()
            if inventory_permissions != 3:
                raise RuntimeError("Inventarberechtigungen wurden nicht angelegt.")
            monitoring_roles = (
                connection.execute(
                    text(
                        "SELECT r.code FROM role_permissions rp "
                        "JOIN roles r ON r.id = rp.role_id "
                        "JOIN permissions p ON p.id = rp.permission_id "
                        "WHERE p.code = 'system.monitoring.read' ORDER BY r.code"
                    )
                )
                .scalars()
                .all()
            )
            if monitoring_roles != ["administrator", "operations"]:
                raise RuntimeError("Die Monitoring-Berechtigung ist falschen Rollen zugewiesen.")
            if (
                connection.execute(
                    text(
                        "SELECT count(*) FROM pg_trigger "
                        "WHERE tgname = 'inventory_events_append_only' AND NOT tgisinternal"
                    )
                ).scalar_one()
                != 1
            ):
                raise RuntimeError("Der Inventar-Append-only-Trigger wurde nicht angelegt.")
            for table_name in ("automation_rules", "automation_runs"):
                if not connection.execute(
                    text("SELECT to_regclass(:table_name) IS NOT NULL"),
                    {"table_name": table_name},
                ).scalar_one():
                    raise RuntimeError(f"Automatisierungstabelle {table_name} fehlt.")
            if (
                connection.execute(
                    text(
                        "SELECT count(*) FROM role_permissions rp "
                        "JOIN roles r ON r.id = rp.role_id "
                        "JOIN permissions p ON p.id = rp.permission_id "
                        "WHERE r.code = 'employee' "
                        "AND p.code IN ('documents.read', 'documents.download')"
                    )
                ).scalar_one()
                != 0
            ):
                raise RuntimeError(
                    "Die Mitarbeiterrolle besitzt weiterhin generische Dokumentrechte."
                )
            if (
                connection.execute(
                    text(
                        "SELECT count(*) FROM pg_trigger "
                        "WHERE tgname = 'employee_portal_document_grant_history_append_only' "
                        "AND NOT tgisinternal"
                    )
                ).scalar_one()
                != 1
            ):
                raise RuntimeError("Der Mitarbeiterdokument-Freigabeverlauf ist nicht append-only.")
            if (
                connection.execute(
                    text("SELECT count(*) FROM permissions WHERE code = 'automations.manage'")
                ).scalar_one()
                != 1
            ):
                raise RuntimeError("Die Automatisierungsberechtigung wurde nicht angelegt.")
            if (
                connection.execute(
                    text(
                        "SELECT count(*) FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'notification_outbox' "
                        "AND column_name IN ('failure_count', 'manual_retry_count')"
                    )
                ).scalar_one()
                != 2
            ):
                raise RuntimeError("Die Outbox-Wiederholungszähler fehlen.")
            if (
                connection.execute(
                    text("SELECT failure_count FROM notification_outbox WHERE id = :id"),
                    {"id": outbox_id},
                ).scalar_one()
                != 2
            ):
                raise RuntimeError("Bestehende Outbox-Fehlversuche wurden nicht übernommen.")
            if (
                connection.execute(
                    text("SELECT action FROM audit_logs WHERE id = :id"),
                    {"id": audit_id},
                ).scalar_one()
                != "ci.migration_fixture"
            ):
                raise RuntimeError("Der vorhandene Audit-Eintrag wurde beim Upgrade verändert.")
            if (
                connection.execute(
                    text("SELECT count(*) FROM audit_log_integrity WHERE audit_log_id = :id"),
                    {"id": audit_id},
                ).scalar_one()
                != 1
            ):
                raise RuntimeError("Der bestehende Audit-Eintrag wurde nicht verkettet.")
            if (
                connection.execute(
                    text(
                        "SELECT count(*) FROM pg_trigger "
                        "WHERE tgname IN ('audit_logs_append_only', 'audit_logs_integrity_chain') "
                        "AND NOT tgisinternal"
                    )
                ).scalar_one()
                != 2
            ):
                raise RuntimeError("Audit-Append-only- und Integritätstrigger fehlen.")
        engine.dispose()

        runtime_options = {
            **admin_options,
            "dbname": database_name,
            "user": "securityops_runtime",
            "password": os.environ["POSTGRES_RUNTIME_PASSWORD"],
        }
        with psycopg.connect(**runtime_options) as connection:
            if connection.execute(
                "SELECT has_table_privilege('securityops_runtime', 'owks_attachments', 'UPDATE')"
            ).fetchone()[0]:
                raise RuntimeError("Die Laufzeitrolle darf OWKS-Anhänge nicht aktualisieren.")
            runtime_audit_id = uuid4()
            connection.execute(
                """
                INSERT INTO audit_logs (id, action, entity_type, entity_id, details)
                VALUES (%s, 'ci.runtime_fixture', 'runtime_test', 'insert', '{}'::json)
                """,
                (runtime_audit_id,),
            )
            if (
                connection.execute(
                    "SELECT action FROM audit_logs WHERE id = %s", (runtime_audit_id,)
                ).fetchone()[0]
                != "ci.runtime_fixture"
            ):
                raise RuntimeError("Die Laufzeitrolle kann Audit-Einträge nicht lesen.")
            for operation in (
                "UPDATE audit_logs SET action = 'changed' WHERE id = %s",
                "DELETE FROM audit_logs WHERE id = %s",
            ):
                connection.execute("SAVEPOINT audit_write_rejection")
                try:
                    connection.execute(operation, (runtime_audit_id,))
                except psycopg.Error as error:
                    if error.sqlstate not in {"42501", "55000"}:
                        raise
                    connection.execute("ROLLBACK TO SAVEPOINT audit_write_rejection")
                else:
                    raise RuntimeError(
                        f"Die Laufzeitrolle durfte eine Audit-Änderung ausführen: {operation}"
                    )
                connection.execute("RELEASE SAVEPOINT audit_write_rejection")
            connection.commit()

        barrier = Barrier(2)

        def insert_concurrently() -> None:
            with psycopg.connect(**runtime_options) as connection:
                barrier.wait()
                connection.execute(
                    """
                    INSERT INTO audit_logs (id, action, entity_type, entity_id, details)
                    VALUES (%s, 'ci.concurrent_fixture', 'runtime_test', 'concurrent', '{}'::json)
                    """,
                    (uuid4(),),
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(insert_concurrently) for _ in range(2)]
            for future in futures:
                future.result()

        from scripts.verify_audit_integrity import verify_audit_integrity

        with psycopg.connect(
            dbname=database_name,
            **migration_options,
        ) as connection:
            count, tip = verify_audit_integrity(connection)
            if count != 4 or tip is None:
                raise RuntimeError("Audit-Integrität oder parallele Runtime-Inserts sind ungültig.")
    finally:
        with psycopg.connect(dbname="postgres", autocommit=True, **admin_options) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(database_name)
                )
            )


if __name__ == "__main__":
    main()
