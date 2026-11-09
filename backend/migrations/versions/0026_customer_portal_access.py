"""Add isolated customer portal access and auditable contact links."""

from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert

revision: str = "0026_customer_portal_access"
down_revision: str | None = "0025_unique_incident_owks_event"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PORTAL_PERMISSION = "customer_portal.access"
MANAGE_PERMISSION = "customers.portal.manage"


def stable_id(kind: str, code: str):
    return uuid5(NAMESPACE_URL, f"securityops:{kind}:{code}")


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "customer_portal_links",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("user_id", uuid, nullable=False),
        sa.Column("contact_id", uuid, nullable=False),
        sa.Column("created_by_id", uuid, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["contact_id"], ["customer_contacts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("user_id", name="uq_customer_portal_links_user"),
        sa.UniqueConstraint("contact_id", name="uq_customer_portal_links_contact"),
    )
    op.create_table(
        "customer_portal_link_history",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("user_id", uuid, nullable=False),
        sa.Column("contact_id", uuid, nullable=False),
        sa.Column("actor_id", uuid, nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "action IN ('linked', 'unlinked')", name="ck_customer_portal_link_action"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["contact_id"], ["customer_contacts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_customer_portal_link_history_created",
        "customer_portal_link_history",
        ["created_at"],
    )
    op.execute(
        """
        CREATE FUNCTION securityops_reject_customer_portal_link_history_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Kundenportal-Verknüpfungshistorie ist unveränderlich'
                USING ERRCODE = '55000';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER customer_portal_link_history_append_only "
        "BEFORE UPDATE OR DELETE ON customer_portal_link_history "
        "FOR EACH ROW EXECUTE FUNCTION "
        "securityops_reject_customer_portal_link_history_mutation()"
    )

    permissions = sa.table(
        "permissions",
        sa.column("id", uuid),
        sa.column("code", sa.String),
        sa.column("description", sa.String),
    )
    roles = sa.table(
        "roles",
        sa.column("id", uuid),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
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
            [
                {
                    "id": stable_id("permission", PORTAL_PERMISSION),
                    "code": PORTAL_PERMISSION,
                    "description": "Eigene freigegebene Kundenportal-Daten einsehen",
                },
                {
                    "id": stable_id("permission", MANAGE_PERMISSION),
                    "code": MANAGE_PERMISSION,
                    "description": "Kundenportal-Konten manuell mit Kundenkontakten verknüpfen",
                },
            ]
        )
        .on_conflict_do_nothing()
    )
    connection.execute(
        pg_insert(roles)
        .values(
            id=stable_id("role", "customer_portal"),
            code="customer_portal",
            name="Kundenportal",
            description="Ausschließlich eigene, explizit freigegebene Kundeninformationen",
        )
        .on_conflict_do_nothing()
    )
    connection.execute(
        pg_insert(role_permissions)
        .values(
            [
                {
                    "role_id": stable_id("role", "customer_portal"),
                    "permission_id": stable_id("permission", PORTAL_PERMISSION),
                },
                {
                    "role_id": stable_id("role", "administrator"),
                    "permission_id": stable_id("permission", MANAGE_PERMISSION),
                },
            ]
        )
        .on_conflict_do_nothing()
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM customer_portal_link_history) "
            "OR EXISTS (SELECT 1 FROM customer_portal_links)"
        )
    ).scalar_one():
        raise RuntimeError("Kundenportal-Downgrade abgelehnt: Verknüpfungshistorie zuerst sichern.")
    if connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM user_roles ur "
            "JOIN roles r ON r.id = ur.role_id WHERE r.code = 'customer_portal')"
        )
    ).scalar_one():
        raise RuntimeError(
            "Kundenportal-Downgrade abgelehnt: Kundenportal-Rollen sind noch Benutzern zugewiesen."
        )
    if connection.execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM role_permissions rp
                JOIN roles r ON r.id = rp.role_id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE (p.code = :portal_permission AND r.code <> 'customer_portal')
                   OR (p.code = :manage_permission AND r.code <> 'administrator')
            )
            """
        ),
        {
            "portal_permission": PORTAL_PERMISSION,
            "manage_permission": MANAGE_PERMISSION,
        },
    ).scalar_one():
        raise RuntimeError(
            "Kundenportal-Downgrade abgelehnt: Portalrechte sind weiteren Rollen zugewiesen."
        )

    op.execute(
        "DROP TRIGGER customer_portal_link_history_append_only ON customer_portal_link_history"
    )
    op.execute("DROP FUNCTION securityops_reject_customer_portal_link_history_mutation()")
    op.drop_index(
        "ix_customer_portal_link_history_created", table_name="customer_portal_link_history"
    )
    op.drop_table("customer_portal_link_history")
    op.drop_table("customer_portal_links")

    uuid = postgresql.UUID(as_uuid=True)
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", uuid),
        sa.column("permission_id", uuid),
    )
    users = sa.table("user_roles", sa.column("role_id", uuid))
    permissions = sa.table("permissions", sa.column("id", uuid))
    roles = sa.table("roles", sa.column("id", uuid))
    connection.execute(
        sa.delete(role_permissions).where(
            role_permissions.c.permission_id.in_(
                [
                    stable_id("permission", PORTAL_PERMISSION),
                    stable_id("permission", MANAGE_PERMISSION),
                ]
            )
        )
    )
    connection.execute(
        sa.delete(users).where(users.c.role_id == stable_id("role", "customer_portal"))
    )
    connection.execute(sa.delete(roles).where(roles.c.id == stable_id("role", "customer_portal")))
    connection.execute(
        sa.delete(permissions).where(
            permissions.c.id.in_(
                [
                    stable_id("permission", PORTAL_PERMISSION),
                    stable_id("permission", MANAGE_PERMISSION),
                ]
            )
        )
    )
