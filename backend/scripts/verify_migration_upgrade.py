"""Verify the portal migration chain upgrades a database containing existing data."""

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
    if script.get_heads() != [AUDIT_REVISION]:
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
        engine.dispose()

        run_migration("head", database_name)
        engine = create_engine(database_url)
        with engine.connect() as connection:
            if (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                != AUDIT_REVISION
            ):
                raise RuntimeError("Die Upgrade-Kette hat nicht bei 0029 geendet.")
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
            ):
                if not connection.execute(
                    text("SELECT to_regclass(:table_name) IS NOT NULL"),
                    {"table_name": table_name},
                ).scalar_one():
                    raise RuntimeError(f"Portal-Tabelle {table_name} fehlt nach dem Upgrade.")
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
