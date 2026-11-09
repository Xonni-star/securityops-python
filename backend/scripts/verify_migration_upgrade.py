"""Verify the portal migration chain upgrades a database containing existing data."""

import os
import subprocess
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


def postgres_connection_options() -> dict[str, str | int]:
    return {
        "host": os.environ["POSTGRES_HOST"],
        "port": int(os.environ["POSTGRES_PORT"]),
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
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
    if script.get_heads() != [CUSTOMER_REQUESTS_REVISION]:
        raise RuntimeError(f"Unerwartete Alembic-Heads: {script.get_heads()}")


def run_migration(revision: str, database_name: str) -> None:
    environment = os.environ | {"POSTGRES_DB": database_name}
    subprocess.run(
        ["python", "-m", "alembic", "upgrade", revision],
        check=True,
        env=environment,
    )


def main() -> None:
    verify_revision_chain()
    options = postgres_connection_options()
    database_name = f"securityops_migration_data_{uuid4().hex}"
    with psycopg.connect(dbname="postgres", autocommit=True, **options) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))

    try:
        run_migration(BASE_REVISION, database_name)
        database_url = URL.create(
            "postgresql+psycopg",
            username=options["user"],
            password=options["password"],
            host=options["host"],
            port=options["port"],
            database=database_name,
        )
        engine = create_engine(database_url)
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
        engine.dispose()

        run_migration("head", database_name)
        engine = create_engine(database_url)
        with engine.connect() as connection:
            if (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                != CUSTOMER_REQUESTS_REVISION
            ):
                raise RuntimeError("Die Upgrade-Kette hat nicht bei 0028 geendet.")
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
        engine.dispose()
    finally:
        with psycopg.connect(dbname="postgres", autocommit=True, **options) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(database_name)
                )
            )


if __name__ == "__main__":
    main()
