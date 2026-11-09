import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError


def test_runtime_role_can_only_insert_and_read_audit_entries(client) -> None:
    database_url = os.environ.get("SECURITYOPS_RUNTIME_DATABASE_URL")
    if not database_url:
        pytest.skip("PostgreSQL-Laufzeitrolle ist nur in der PostgreSQL-CI eingerichtet.")
    parsed_url = make_url(database_url)
    if (
        parsed_url.drivername != "postgresql+psycopg"
        or parsed_url.host not in {"localhost", "127.0.0.1"}
        or parsed_url.database != "securityops_test"
        or parsed_url.username != "securityops_runtime"
    ):
        raise RuntimeError("Die Laufzeitrollen-Tests sind nur auf securityops_test zulässig.")

    engine = create_engine(database_url)
    audit_id = uuid4()
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            role = connection.execute(
                text(
                    "SELECT rolsuper, rolcreatedb, rolcreaterole "
                    "FROM pg_roles WHERE rolname = current_user"
                )
            ).one()
            assert role == (False, False, False)
            assert (
                connection.execute(
                    text(
                        "SELECT has_database_privilege(current_user, current_database(), 'CREATE')"
                    )
                ).scalar_one()
                is False
            )
            assert (
                connection.execute(
                    text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
                ).scalar_one()
                is False
            )
            assert (
                connection.execute(
                    text("SELECT has_table_privilege(current_user, 'audit_logs', 'UPDATE')")
                ).scalar_one()
                is False
            )
            connection.execute(
                text(
                    "INSERT INTO audit_logs "
                    "(id, action, entity_type, entity_id, details, created_at) "
                    "VALUES (:id, 'ci.runtime_test', 'runtime_test', 'insert', '{}'::json, now())"
                ),
                {"id": audit_id},
            )
            assert (
                connection.execute(
                    text("SELECT action FROM audit_logs WHERE id = :id"), {"id": audit_id}
                ).scalar_one()
                == "ci.runtime_test"
            )
            for name, statement in (
                ("update", "UPDATE audit_logs SET action = 'changed' WHERE id = :id"),
                ("delete", "DELETE FROM audit_logs WHERE id = :id"),
            ):
                connection.exec_driver_sql(f"SAVEPOINT audit_{name}")
                with pytest.raises(DBAPIError):
                    connection.execute(text(statement), {"id": audit_id})
                connection.exec_driver_sql(f"ROLLBACK TO SAVEPOINT audit_{name}")
                connection.exec_driver_sql(f"RELEASE SAVEPOINT audit_{name}")
            transaction.rollback()
    finally:
        engine.dispose()
