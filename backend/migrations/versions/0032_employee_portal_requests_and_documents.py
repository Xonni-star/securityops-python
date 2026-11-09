"""Add employee request withdrawal and explicit qualification document grants."""

from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert

revision: str = "0032_employee_portal"
down_revision: str | None = "0031_safe_automations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def stable_id(kind: str, code: str):
    return uuid5(NAMESPACE_URL, f"securityops:{kind}:{code}")


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    timestamp = sa.DateTime(timezone=True)

    op.drop_constraint("ck_employee_absences_status", "employee_absences", type_="check")
    op.create_check_constraint(
        "ck_employee_absences_status",
        "employee_absences",
        "status IN ('pending', 'approved', 'rejected', 'withdrawn')",
    )
    op.drop_constraint(
        "ck_schedule_availability_requests_status",
        "schedule_availability_requests",
        type_="check",
    )
    op.create_check_constraint(
        "ck_schedule_availability_requests_status",
        "schedule_availability_requests",
        "status IN ('open', 'accepted', 'rejected', 'withdrawn')",
    )

    op.create_table(
        "employee_portal_document_grants",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "employee_id",
            uuid,
            sa.ForeignKey("employees.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column(
            "qualification_document_id",
            uuid,
            sa.ForeignKey("employee_qualification_documents.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "granted_by_id",
            uuid,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("granted_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.Column(
            "revoked_by_id",
            uuid,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("revoked_at", timestamp, nullable=True),
        sa.CheckConstraint(
            "(revoked_at IS NULL AND revoked_by_id IS NULL) OR "
            "(revoked_at IS NOT NULL AND revoked_by_id IS NOT NULL)",
            name="ck_employee_portal_document_grants_revocation",
        ),
    )
    op.create_index(
        "uq_employee_portal_document_grants_active",
        "employee_portal_document_grants",
        ["qualification_document_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "ix_employee_portal_document_grants_employee",
        "employee_portal_document_grants",
        ["employee_id", "granted_at"],
    )
    op.create_table(
        "employee_portal_document_grant_history",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("grant_id", uuid, nullable=False),
        sa.Column("actor_id", uuid, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["grant_id"], ["employee_portal_document_grants.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "action IN ('granted', 'revoked')",
            name="ck_employee_portal_document_grant_history_action",
        ),
    )
    op.create_index(
        "ix_employee_portal_document_grant_history_created",
        "employee_portal_document_grant_history",
        ["created_at"],
    )
    op.execute(
        """
        CREATE FUNCTION securityops_reject_employee_portal_document_grant_history_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Mitarbeiterdokument-Freigabehistorie ist unveränderlich'
                USING ERRCODE = '55000';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER employee_portal_document_grant_history_append_only "
        "BEFORE UPDATE OR DELETE ON employee_portal_document_grant_history "
        "FOR EACH ROW EXECUTE FUNCTION "
        "securityops_reject_employee_portal_document_grant_history_mutation()"
    )

    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", uuid),
        sa.column("permission_id", uuid),
    )
    employee_role_id = stable_id("role", "employee")
    generic_document_permission_ids = [
        stable_id("permission", code) for code in ("documents.read", "documents.download")
    ]
    op.get_bind().execute(
        sa.delete(role_permissions).where(
            role_permissions.c.role_id == employee_role_id,
            role_permissions.c.permission_id.in_(generic_document_permission_ids),
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM employee_portal_document_grants) "
            "OR EXISTS (SELECT 1 FROM employee_portal_document_grant_history) "
            "OR EXISTS (SELECT 1 FROM employee_absences WHERE status = 'withdrawn') "
            "OR EXISTS (SELECT 1 FROM schedule_availability_requests WHERE status = 'withdrawn')"
        )
    ).scalar_one():
        raise RuntimeError(
            "Mitarbeiterportal-Downgrade abgelehnt: Freigabe- oder Rücknahmehistorie zuerst sichern."
        )

    op.execute(
        "DROP TRIGGER employee_portal_document_grant_history_append_only "
        "ON employee_portal_document_grant_history"
    )
    op.execute("DROP FUNCTION securityops_reject_employee_portal_document_grant_history_mutation()")
    op.drop_index(
        "ix_employee_portal_document_grant_history_created",
        table_name="employee_portal_document_grant_history",
    )
    op.drop_table("employee_portal_document_grant_history")
    op.drop_index(
        "ix_employee_portal_document_grants_employee",
        table_name="employee_portal_document_grants",
    )
    op.drop_index(
        "uq_employee_portal_document_grants_active",
        table_name="employee_portal_document_grants",
    )
    op.drop_table("employee_portal_document_grants")

    op.drop_constraint(
        "ck_schedule_availability_requests_status",
        "schedule_availability_requests",
        type_="check",
    )
    op.create_check_constraint(
        "ck_schedule_availability_requests_status",
        "schedule_availability_requests",
        "status IN ('open', 'accepted', 'rejected')",
    )
    op.drop_constraint("ck_employee_absences_status", "employee_absences", type_="check")
    op.create_check_constraint(
        "ck_employee_absences_status",
        "employee_absences",
        "status IN ('pending', 'approved', 'rejected')",
    )

    uuid = postgresql.UUID(as_uuid=True)
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", uuid),
        sa.column("permission_id", uuid),
    )
    connection.execute(
        pg_insert(role_permissions)
        .values(
            [
                {
                    "role_id": stable_id("role", "employee"),
                    "permission_id": stable_id("permission", code),
                }
                for code in ("documents.read", "documents.download")
            ]
        )
        .on_conflict_do_nothing()
    )
