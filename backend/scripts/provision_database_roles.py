"""Provision least-privilege PostgreSQL roles before applying Alembic migrations."""

import os

import psycopg
from psycopg import sql

ADMIN_ROLE = os.environ.get("POSTGRES_ADMIN_USER", "securityops_admin")
MIGRATION_ROLE = "securityops_migrator"
RUNTIME_ROLE = "securityops_runtime"


def required_secret(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} muss gesetzt sein.")
    return value


def provision_roles() -> None:
    database = os.environ.get("POSTGRES_DB", "securityops")
    if ADMIN_ROLE in {MIGRATION_ROLE, RUNTIME_ROLE}:
        raise RuntimeError("Der Datenbank-Administrator muss eine eigene Rolle verwenden.")

    connection_options = {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": int(os.environ.get("POSTGRES_PORT", "5432")),
        "dbname": database,
        "user": ADMIN_ROLE,
        "password": required_secret("POSTGRES_ADMIN_PASSWORD"),
    }
    role_passwords = {
        MIGRATION_ROLE: required_secret("POSTGRES_MIGRATION_PASSWORD"),
        RUNTIME_ROLE: required_secret("POSTGRES_RUNTIME_PASSWORD"),
    }
    with psycopg.connect(**connection_options) as connection:
        if (
            connection.execute("SELECT current_setting('is_superuser') = 'on'").fetchone()[0]
            is not True
        ):
            raise RuntimeError(
                "POSTGRES_ADMIN_USER muss Superuser-Rechte für die Rollen-/Eigentümermigration haben."
            )
        for role, password in role_passwords.items():
            role_exists = connection.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s)", (role,)
            ).fetchone()[0]
            role_command = "ALTER ROLE" if role_exists else "CREATE ROLE"
            connection.execute(
                sql.SQL(
                    "{} {} WITH LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE "
                    "NOREPLICATION NOBYPASSRLS PASSWORD {}"
                ).format(
                    sql.SQL(role_command),
                    sql.Identifier(role),
                    sql.Literal(password),
                )
            )
            memberships = connection.execute(
                """
                SELECT granted_role.rolname
                FROM pg_auth_members AS membership
                JOIN pg_roles AS granted_role ON granted_role.oid = membership.roleid
                JOIN pg_roles AS member_role ON member_role.oid = membership.member
                WHERE member_role.rolname = %s
                """,
                (role,),
            ).fetchall()
            for (granted_role,) in memberships:
                connection.execute(
                    sql.SQL("REVOKE {} FROM {}").format(
                        sql.Identifier(granted_role), sql.Identifier(role)
                    )
                )

        connection.execute(
            sql.SQL("REASSIGN OWNED BY {} TO {}").format(
                sql.Identifier(ADMIN_ROLE), sql.Identifier(MIGRATION_ROLE)
            )
        )
        connection.execute(
            sql.SQL("ALTER DATABASE {} OWNER TO {}").format(
                sql.Identifier(database), sql.Identifier(MIGRATION_ROLE)
            )
        )
        connection.execute(
            sql.SQL("ALTER SCHEMA public OWNER TO {}").format(sql.Identifier(MIGRATION_ROLE))
        )
        connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        connection.execute(
            sql.SQL("REVOKE ALL ON DATABASE {} FROM {}").format(
                sql.Identifier(database), sql.Identifier(RUNTIME_ROLE)
            )
        )
        connection.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(database), sql.Identifier(RUNTIME_ROLE)
            )
        )
        connection.execute(
            sql.SQL("REVOKE ALL ON SCHEMA public FROM {}").format(sql.Identifier(RUNTIME_ROLE))
        )
        connection.execute(
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(RUNTIME_ROLE))
        )
        connection.execute(
            sql.SQL("REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {}").format(
                sql.Identifier(RUNTIME_ROLE)
            )
        )
        connection.execute(
            sql.SQL("REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM {}").format(
                sql.Identifier(RUNTIME_ROLE)
            )
        )
        connection.execute(
            sql.SQL(
                """
                ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public
                REVOKE ALL ON TABLES FROM {}
                """
            ).format(sql.Identifier(MIGRATION_ROLE), sql.Identifier(RUNTIME_ROLE))
        )
        connection.execute(
            sql.SQL(
                """
                ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public
                GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}
                """
            ).format(sql.Identifier(MIGRATION_ROLE), sql.Identifier(RUNTIME_ROLE))
        )
        connection.execute(
            sql.SQL(
                """
                ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public
                REVOKE ALL ON SEQUENCES FROM {}
                """
            ).format(sql.Identifier(MIGRATION_ROLE), sql.Identifier(RUNTIME_ROLE))
        )
        connection.execute(
            sql.SQL(
                """
                ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public
                GRANT USAGE, SELECT ON SEQUENCES TO {}
                """
            ).format(sql.Identifier(MIGRATION_ROLE), sql.Identifier(RUNTIME_ROLE))
        )

        tables = connection.execute(
            """
            SELECT relation.relname,
                   bool_or(trigger.tgname LIKE '%_append_only') AS append_only
            FROM pg_class AS relation
            JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
            LEFT JOIN pg_trigger AS trigger
                ON trigger.tgrelid = relation.oid AND NOT trigger.tgisinternal
            WHERE namespace.nspname = 'public'
              AND relation.relkind IN ('r', 'p')
              AND relation.relname NOT IN ('alembic_version', 'audit_log_integrity')
            GROUP BY relation.relname
            """
        ).fetchall()
        for table_name, append_only in tables:
            table = sql.Identifier("public", table_name)
            connection.execute(
                sql.SQL("GRANT SELECT, INSERT ON TABLE {} TO {}").format(
                    table, sql.Identifier(RUNTIME_ROLE)
                )
            )
            if not append_only and table_name != "audit_logs":
                connection.execute(
                    sql.SQL("GRANT UPDATE, DELETE ON TABLE {} TO {}").format(
                        table, sql.Identifier(RUNTIME_ROLE)
                    )
                )

        sequences = connection.execute(
            """
            SELECT relation.relname
            FROM pg_class AS relation
            JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = 'public' AND relation.relkind = 'S'
            """
        ).fetchall()
        for (sequence_name,) in sequences:
            connection.execute(
                sql.SQL("GRANT USAGE, SELECT ON SEQUENCE {} TO {}").format(
                    sql.Identifier("public", sequence_name), sql.Identifier(RUNTIME_ROLE)
                )
            )

        connection.commit()


if __name__ == "__main__":
    provision_roles()
