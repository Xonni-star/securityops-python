"""Add object-scoped inventory assets and append-only lifecycle events."""

from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert

revision: str = "0030_inventory_management"
down_revision: str | None = "0029_audit_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = {
    "inventory.read": "Inventar und Inventarhistorien einsehen",
    "inventory.manage": "Inventarstammdaten verwalten",
    "inventory.move": "Inventar ausgeben, zurücknehmen und Vorgänge erfassen",
}
ROLE_PERMISSIONS = {
    "administrator": set(PERMISSIONS),
    "management": set(PERMISSIONS),
    "operations": set(PERMISSIONS),
    "object_manager": {"inventory.read", "inventory.move"},
}
ROLE_CODES = tuple(ROLE_PERMISSIONS)


def stable_id(kind: str, code: str):
    return uuid5(NAMESPACE_URL, f"securityops:{kind}:{code}")


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    timestamp = sa.DateTime(timezone=True)
    op.create_table(
        "inventory_assets",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("asset_number", sa.String(80), nullable=False, unique=True),
        sa.Column("serial_number", sa.String(120), nullable=True, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("condition", sa.String(20), nullable=False, server_default="good"),
        sa.Column("status", sa.String(20), nullable=False, server_default="available"),
        sa.Column("location", sa.String(200), nullable=False),
        sa.Column(
            "object_id", uuid, sa.ForeignKey("objects.id", ondelete="RESTRICT"), nullable=True
        ),
        sa.Column(
            "current_employee_id",
            uuid,
            sa.ForeignKey("employees.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "created_by_id", uuid, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("archived_at", timestamp, nullable=True),
        sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "category IN ('access_media', 'radio', 'smartphone', 'tablet', 'computer', "
            "'clothing', 'safety_equipment', 'vehicle', 'other')",
            name="ck_inventory_assets_category",
        ),
        sa.CheckConstraint(
            "condition IN ('new', 'good', 'used', 'worn', 'defective')",
            name="ck_inventory_assets_condition",
        ),
        sa.CheckConstraint(
            "status IN ('available', 'issued', 'maintenance', 'lost', 'damaged', 'archived')",
            name="ck_inventory_assets_status",
        ),
        sa.CheckConstraint("length(trim(asset_number)) > 0", name="ck_inventory_assets_number"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_inventory_assets_name"),
        sa.CheckConstraint("length(trim(location)) > 0", name="ck_inventory_assets_location"),
        sa.CheckConstraint(
            "serial_number IS NULL OR length(trim(serial_number)) > 0",
            name="ck_inventory_assets_serial",
        ),
        sa.CheckConstraint(
            "(status = 'issued' AND current_employee_id IS NOT NULL) "
            "OR (status != 'issued' AND current_employee_id IS NULL)",
            name="ck_inventory_assets_holder_status",
        ),
        sa.CheckConstraint(
            "(status = 'archived' AND archived_at IS NOT NULL) "
            "OR (status != 'archived' AND archived_at IS NULL)",
            name="ck_inventory_assets_archived_at",
        ),
    )
    op.create_index(
        "ix_inventory_assets_object_status",
        "inventory_assets",
        ["object_id", "status", "archived_at"],
    )
    op.create_index(
        "ix_inventory_assets_holder_status",
        "inventory_assets",
        ["current_employee_id", "status"],
    )
    op.create_index(
        "ix_inventory_assets_category_condition",
        "inventory_assets",
        ["category", "condition"],
    )

    op.create_table(
        "inventory_events",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "asset_id",
            uuid,
            sa.ForeignKey("inventory_assets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("object_id", uuid, sa.ForeignKey("objects.id", ondelete="RESTRICT")),
        sa.Column("from_object_id", uuid, sa.ForeignKey("objects.id", ondelete="RESTRICT")),
        sa.Column("to_object_id", uuid, sa.ForeignKey("objects.id", ondelete="RESTRICT")),
        sa.Column("from_employee_id", uuid, sa.ForeignKey("employees.id", ondelete="RESTRICT")),
        sa.Column("to_employee_id", uuid, sa.ForeignKey("employees.id", ondelete="RESTRICT")),
        sa.Column("actor_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("status_after", sa.String(20), nullable=False),
        sa.Column("condition_after", sa.String(20), nullable=False),
        sa.Column("location_after", sa.String(200), nullable=False),
        sa.Column("acknowledged_at", timestamp, nullable=True),
        sa.Column("acknowledgement_note", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "event_type IN ('created', 'updated', 'issued', 'returned', 'transferred', "
            "'lost', 'damaged', 'maintenance', 'repair', 'archived')",
            name="ck_inventory_events_type",
        ),
        sa.CheckConstraint(
            "status_after IN ('available', 'issued', 'maintenance', 'lost', 'damaged', 'archived')",
            name="ck_inventory_events_status",
        ),
        sa.CheckConstraint(
            "condition_after IN ('new', 'good', 'used', 'worn', 'defective')",
            name="ck_inventory_events_condition",
        ),
        sa.CheckConstraint(
            "event_type != 'issued' OR "
            "(to_employee_id IS NOT NULL AND acknowledged_at IS NOT NULL)",
            name="ck_inventory_events_issue_acknowledged",
        ),
        sa.CheckConstraint(
            "event_type != 'transferred' OR "
            "(from_employee_id IS NOT NULL AND to_employee_id IS NOT NULL "
            "AND acknowledged_at IS NOT NULL)",
            name="ck_inventory_events_transfer_acknowledged",
        ),
        sa.CheckConstraint(
            "(event_type = 'created' AND status_after = 'available') "
            "OR (event_type = 'updated' AND status_after IN "
            "('available', 'issued', 'maintenance', 'lost', 'damaged', 'archived')) "
            "OR (event_type = 'issued' AND status_after = 'issued') "
            "OR (event_type = 'returned' AND status_after = 'available') "
            "OR (event_type = 'transferred' AND status_after = 'issued') "
            "OR (event_type = 'lost' AND status_after = 'lost') "
            "OR (event_type = 'damaged' AND status_after = 'damaged') "
            "OR (event_type = 'maintenance' AND status_after = 'maintenance') "
            "OR (event_type = 'repair' AND status_after = 'available') "
            "OR (event_type = 'archived' AND status_after = 'archived')",
            name="ck_inventory_events_type_status",
        ),
        sa.CheckConstraint("length(trim(location_after)) > 0", name="ck_inventory_events_location"),
    )
    op.create_index(
        "ix_inventory_events_asset_created", "inventory_events", ["asset_id", "created_at"]
    )
    op.create_index(
        "ix_inventory_events_object_created", "inventory_events", ["object_id", "created_at"]
    )
    op.create_index(
        "ix_inventory_events_employee_created",
        "inventory_events",
        ["from_employee_id", "to_employee_id", "created_at"],
    )
    op.execute(
        """
        CREATE FUNCTION securityops_reject_inventory_event_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Inventarereignisse sind unveränderlich'
                USING ERRCODE = '55000';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER inventory_events_append_only BEFORE UPDATE OR DELETE ON inventory_events "
        "FOR EACH ROW EXECUTE FUNCTION securityops_reject_inventory_event_mutation()"
    )

    uuid_type = postgresql.UUID(as_uuid=True)
    permissions = sa.table(
        "permissions",
        sa.column("id", uuid_type),
        sa.column("code", sa.String(100)),
        sa.column("description", sa.String(300)),
    )
    role_permissions = sa.table(
        "role_permissions", sa.column("role_id", uuid_type), sa.column("permission_id", uuid_type)
    )
    connection = op.get_bind()
    connection.execute(
        pg_insert(permissions)
        .values(
            [
                {
                    "id": stable_id("permission", code),
                    "code": code,
                    "description": description,
                }
                for code, description in PERMISSIONS.items()
            ]
        )
        .on_conflict_do_nothing()
    )
    connection.execute(
        pg_insert(role_permissions)
        .values(
            [
                {
                    "role_id": stable_id("role", role_code),
                    "permission_id": stable_id("permission", permission_code),
                }
                for role_code, permission_codes in ROLE_PERMISSIONS.items()
                for permission_code in sorted(permission_codes)
            ]
        )
        .on_conflict_do_nothing()
    )


def downgrade() -> None:
    connection = op.get_bind()
    has_data = connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM inventory_events) "
            "OR EXISTS (SELECT 1 FROM inventory_assets)"
        )
    ).scalar_one()
    custom_role_permission = connection.execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM role_permissions rp
                JOIN roles r ON r.id = rp.role_id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE p.code IN ('inventory.read', 'inventory.manage', 'inventory.move')
                  AND r.code NOT IN ('administrator', 'management', 'operations', 'object_manager')
            )
            """
        )
    ).scalar_one()
    if has_data or custom_role_permission:
        raise RuntimeError(
            "Inventar-Downgrade abgelehnt: Inventar, Ereignisse oder benutzerdefinierte "
            "Berechtigungen zuerst sichern."
        )

    uuid = postgresql.UUID(as_uuid=True)
    permission_ids = [stable_id("permission", code) for code in PERMISSIONS]
    role_ids = [stable_id("role", code) for code in ROLE_CODES]
    role_permissions = sa.table(
        "role_permissions", sa.column("role_id", uuid), sa.column("permission_id", uuid)
    )
    permissions = sa.table("permissions", sa.column("id", uuid))
    connection.execute(
        sa.delete(role_permissions).where(
            role_permissions.c.permission_id.in_(permission_ids),
            role_permissions.c.role_id.in_(role_ids),
        )
    )
    connection.execute(sa.delete(permissions).where(permissions.c.id.in_(permission_ids)))
    op.execute("DROP TRIGGER inventory_events_append_only ON inventory_events")
    op.execute("DROP FUNCTION securityops_reject_inventory_event_mutation()")
    op.drop_index("ix_inventory_events_employee_created", table_name="inventory_events")
    op.drop_index("ix_inventory_events_object_created", table_name="inventory_events")
    op.drop_index("ix_inventory_events_asset_created", table_name="inventory_events")
    op.drop_table("inventory_events")
    op.drop_index("ix_inventory_assets_category_condition", table_name="inventory_assets")
    op.drop_index("ix_inventory_assets_holder_status", table_name="inventory_assets")
    op.drop_index("ix_inventory_assets_object_status", table_name="inventory_assets")
    op.drop_table("inventory_assets")
