"""Add explicit customer document publication grants."""

from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert

revision: str = "0027_customer_document_grants"
down_revision: str | None = "0026_customer_portal_access"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MANAGE_PERMISSION = "customer_portal.documents.manage"


def stable_id(kind: str, code: str):
    return uuid5(NAMESPACE_URL, f"securityops:{kind}:{code}")


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.add_column(
        "customer_portal_links",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.drop_constraint(
        "ck_customer_portal_link_action", "customer_portal_link_history", type_="check"
    )
    op.create_check_constraint(
        "ck_customer_portal_link_action",
        "customer_portal_link_history",
        "action IN ('linked', 'unlinked', 'activated', 'deactivated')",
    )
    op.create_table(
        "customer_portal_document_grants",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("document_id", uuid, nullable=False),
        sa.Column("version_id", uuid, nullable=False),
        sa.Column("customer_id", uuid, nullable=False),
        sa.Column("granted_by_id", uuid, nullable=True),
        sa.Column(
            "granted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("revoked_by_id", uuid, nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["version_id"], ["document_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["granted_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revoked_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "(revoked_at IS NULL AND revoked_by_id IS NULL) OR "
            "(revoked_at IS NOT NULL AND revoked_by_id IS NOT NULL)",
            name="ck_customer_portal_document_grants_revocation",
        ),
    )
    op.create_index(
        "uq_customer_portal_document_grants_active",
        "customer_portal_document_grants",
        ["document_id", "version_id", "customer_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "ix_customer_portal_document_grants_customer",
        "customer_portal_document_grants",
        ["customer_id", "granted_at"],
    )
    op.create_table(
        "customer_portal_document_grant_history",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("grant_id", uuid, nullable=False),
        sa.Column("actor_id", uuid, nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["grant_id"], ["customer_portal_document_grants.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "action IN ('granted', 'revoked')", name="ck_portal_document_grant_action"
        ),
    )
    op.create_index(
        "ix_customer_portal_document_grant_history_created",
        "customer_portal_document_grant_history",
        ["created_at"],
    )
    op.execute(
        """
        CREATE FUNCTION securityops_reject_customer_portal_document_grant_history_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Kundenfreigabe-Historie ist unveränderlich'
                USING ERRCODE = '55000';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER customer_portal_document_grant_history_append_only "
        "BEFORE UPDATE OR DELETE ON customer_portal_document_grant_history "
        "FOR EACH ROW EXECUTE FUNCTION "
        "securityops_reject_customer_portal_document_grant_history_mutation()"
    )

    permissions = sa.table(
        "permissions",
        sa.column("id", uuid),
        sa.column("code", sa.String),
        sa.column("description", sa.String),
    )
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", uuid),
        sa.column("permission_id", uuid),
    )
    connection = op.get_bind()
    connection.execute(
        pg_insert(permissions)
        .values(
            id=stable_id("permission", MANAGE_PERMISSION),
            code=MANAGE_PERMISSION,
            description="Kundenbezogene Dokumente ausdrücklich veröffentlichen oder zurückziehen",
        )
        .on_conflict_do_nothing()
    )
    connection.execute(
        pg_insert(role_permissions)
        .values(
            role_id=stable_id("role", "administrator"),
            permission_id=stable_id("permission", MANAGE_PERMISSION),
        )
        .on_conflict_do_nothing()
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM customer_portal_link_history "
            "WHERE action IN ('activated', 'deactivated')) "
            "OR EXISTS (SELECT 1 FROM customer_portal_links WHERE is_active = false)"
        )
    ).scalar_one():
        raise RuntimeError(
            "Portalzugangs-Downgrade abgelehnt: Aktivierungshistorie zuerst sichern."
        )
    if connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM customer_portal_document_grants) "
            "OR EXISTS (SELECT 1 FROM customer_portal_document_grant_history)"
        )
    ).scalar_one():
        raise RuntimeError("Kundenfreigabe-Downgrade abgelehnt: Freigabehistorie zuerst sichern.")

    op.execute(
        "DROP TRIGGER customer_portal_document_grant_history_append_only "
        "ON customer_portal_document_grant_history"
    )
    op.execute("DROP FUNCTION securityops_reject_customer_portal_document_grant_history_mutation()")
    op.drop_index(
        "ix_customer_portal_document_grant_history_created",
        table_name="customer_portal_document_grant_history",
    )
    op.drop_table("customer_portal_document_grant_history")
    op.drop_index(
        "ix_customer_portal_document_grants_customer",
        table_name="customer_portal_document_grants",
    )
    op.drop_index(
        "uq_customer_portal_document_grants_active",
        table_name="customer_portal_document_grants",
    )
    op.drop_table("customer_portal_document_grants")

    uuid = postgresql.UUID(as_uuid=True)
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", uuid),
        sa.column("permission_id", uuid),
    )
    permissions = sa.table("permissions", sa.column("id", uuid))
    connection.execute(
        sa.delete(role_permissions).where(
            role_permissions.c.permission_id == stable_id("permission", MANAGE_PERMISSION)
        )
    )
    connection.execute(
        sa.delete(permissions).where(permissions.c.id == stable_id("permission", MANAGE_PERMISSION))
    )

    op.drop_constraint(
        "ck_customer_portal_link_action", "customer_portal_link_history", type_="check"
    )
    op.create_check_constraint(
        "ck_customer_portal_link_action",
        "customer_portal_link_history",
        "action IN ('linked', 'unlinked')",
    )
    op.drop_column("customer_portal_links", "is_active")
