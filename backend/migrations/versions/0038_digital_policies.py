"""Add immutable policy versions, assignments and acknowledgements."""

from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert

revision: str = "0038_digital_policies"
down_revision: str | None = "0037_object_qual_requirements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = (
    ("policies.manage", "Dienstanweisungen und Unterweisungen verwalten"),
    (
        "policies.read_own",
        "Eigene gültige Dienstanweisungen und Unterweisungen lesen und bestätigen",
    ),
)
MANAGER_ROLES = ("administrator", "management", "object_manager")


def stable_id(kind: str, code: str):
    return uuid5(NAMESPACE_URL, f"securityops:{kind}:{code}")


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "policy_items",
        sa.Column("id", uuid, nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("object_id", uuid, nullable=True),
        sa.Column("repeat_interval_days", sa.Integer(), nullable=True),
        sa.Column("reminder_days", sa.Integer(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", uuid, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("kind IN ('instruction', 'training')", name="ck_policy_items_kind"),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_policy_items_title"),
        sa.CheckConstraint(
            "repeat_interval_days IS NULL OR repeat_interval_days > 0",
            name="ck_policy_items_repeat_interval",
        ),
        sa.CheckConstraint(
            "reminder_days IS NULL OR reminder_days > 0",
            name="ck_policy_items_reminder_days",
        ),
        sa.CheckConstraint(
            "kind = 'training' OR repeat_interval_days IS NULL",
            name="ck_policy_items_instruction_repeat",
        ),
        sa.ForeignKeyConstraint(
            ["object_id"],
            ["objects.id"],
            ondelete="RESTRICT",
            name="fk_policy_items_object_id_objects",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_policy_items_created_by_id_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_policy_items"),
    )
    op.create_index(
        "ix_policy_items_scope_kind", "policy_items", ["object_id", "kind", "archived_at"]
    )
    op.create_table(
        "policy_versions",
        sa.Column("id", uuid, nullable=False),
        sa.Column("policy_item_id", uuid, nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", uuid, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("version_number > 0", name="ck_policy_versions_number"),
        sa.CheckConstraint("length(trim(content)) > 0", name="ck_policy_versions_content"),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until > valid_from",
            name="ck_policy_versions_validity",
        ),
        sa.ForeignKeyConstraint(
            ["policy_item_id"],
            ["policy_items.id"],
            ondelete="RESTRICT",
            name="fk_policy_versions_policy_item_id_policy_items",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_policy_versions_created_by_id_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_policy_versions"),
        sa.UniqueConstraint("policy_item_id", "version_number", name="uq_policy_versions_number"),
    )
    op.create_index(
        "ix_policy_versions_validity",
        "policy_versions",
        ["policy_item_id", "valid_from", "valid_until"],
    )
    op.create_table(
        "policy_version_closures",
        sa.Column("policy_version_id", uuid, nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_by_id", uuid, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["policy_version_id"],
            ["policy_versions.id"],
            ondelete="RESTRICT",
            name="fk_policy_version_closures_policy_version_id_policy_versions",
        ),
        sa.ForeignKeyConstraint(
            ["closed_by_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_policy_version_closures_closed_by_id_users",
        ),
        sa.PrimaryKeyConstraint("policy_version_id", name="pk_policy_version_closures"),
    )
    op.create_table(
        "policy_assignments",
        sa.Column("id", uuid, nullable=False),
        sa.Column("policy_version_id", uuid, nullable=False),
        sa.Column("employee_id", uuid, nullable=False),
        sa.Column("cycle_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_by_id", uuid, nullable=True),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("cycle_number > 0", name="ck_policy_assignments_cycle"),
        sa.ForeignKeyConstraint(
            ["policy_version_id"],
            ["policy_versions.id"],
            ondelete="RESTRICT",
            name="fk_policy_assignments_policy_version_id_policy_versions",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            ondelete="RESTRICT",
            name="fk_policy_assignments_employee_id_employees",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_policy_assignments_assigned_by_id_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_policy_assignments"),
        sa.UniqueConstraint(
            "employee_id",
            "policy_version_id",
            "cycle_number",
            name="uq_policy_assignments_cycle",
        ),
    )
    op.create_index(
        "ix_policy_assignments_employee_due", "policy_assignments", ["employee_id", "due_at"]
    )
    op.create_index(
        "ix_policy_assignments_version_employee",
        "policy_assignments",
        ["policy_version_id", "employee_id"],
    )
    op.create_table(
        "policy_receipts",
        sa.Column("id", uuid, nullable=False),
        sa.Column("assignment_id", uuid, nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("actor_id", uuid, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("action IN ('read', 'confirmed')", name="ck_policy_receipts_action"),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["policy_assignments.id"],
            ondelete="RESTRICT",
            name="fk_policy_receipts_assignment_id_policy_assignments",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_policy_receipts_actor_id_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_policy_receipts"),
        sa.UniqueConstraint("assignment_id", "action", name="uq_policy_receipts_assignment_action"),
    )
    op.create_index(
        "ix_policy_receipts_created", "policy_receipts", ["assignment_id", "created_at"]
    )
    op.execute(
        """
        CREATE FUNCTION reject_policy_history_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Policy history rows are append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in (
        "policy_versions",
        "policy_version_closures",
        "policy_assignments",
        "policy_receipts",
    ):
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_policy_history_mutation()"
        )

    permissions = sa.table(
        "permissions",
        sa.column("id", uuid),
        sa.column("code", sa.String),
        sa.column("description", sa.String),
    )
    role_permissions = sa.table(
        "role_permissions", sa.column("role_id", uuid), sa.column("permission_id", uuid)
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
                for code, description in PERMISSIONS
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
                    "permission_id": stable_id("permission", "policies.manage"),
                }
                for role_code in MANAGER_ROLES
            ]
            + [
                {
                    "role_id": stable_id("role", "employee"),
                    "permission_id": stable_id("permission", "policies.read_own"),
                }
            ]
        )
        .on_conflict_do_nothing()
    )


def downgrade() -> None:
    connection = op.get_bind()
    has_data = connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM policy_receipts) "
            "OR EXISTS (SELECT 1 FROM policy_assignments) "
            "OR EXISTS (SELECT 1 FROM policy_version_closures) "
            "OR EXISTS (SELECT 1 FROM policy_versions) "
            "OR EXISTS (SELECT 1 FROM policy_items)"
        )
    ).scalar_one()
    if has_data:
        raise RuntimeError(
            "Downgrade abgelehnt: Dienstanweisungen, Unterweisungen und Nachweise müssen "
            "vorher gesichert werden."
        )
    custom_roles = connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM role_permissions rp "
            "JOIN permissions p ON p.id = rp.permission_id "
            "JOIN roles r ON r.id = rp.role_id "
            "WHERE p.code IN ('policies.manage', 'policies.read_own') "
            "AND r.code NOT IN ('administrator', 'management', 'object_manager', 'employee'))"
        )
    ).scalar_one()
    if custom_roles:
        raise RuntimeError(
            "Downgrade abgelehnt: Die Berechtigungen wurden benutzerdefinierten Rollen zugewiesen."
        )
    uuid = postgresql.UUID(as_uuid=True)
    role_permissions = sa.table(
        "role_permissions", sa.column("role_id", uuid), sa.column("permission_id", uuid)
    )
    permissions = sa.table("permissions", sa.column("id", uuid))
    connection.execute(
        sa.delete(role_permissions).where(
            role_permissions.c.permission_id.in_(
                [stable_id("permission", code) for code, _ in PERMISSIONS]
            )
        )
    )
    connection.execute(
        sa.delete(permissions).where(
            permissions.c.id.in_([stable_id("permission", code) for code, _ in PERMISSIONS])
        )
    )
    for table in (
        "policy_receipts",
        "policy_assignments",
        "policy_version_closures",
        "policy_versions",
    ):
        op.execute(f"DROP TRIGGER {table}_append_only ON {table}")
    op.execute("DROP FUNCTION reject_policy_history_mutation()")
    op.drop_table("policy_receipts")
    op.drop_index("ix_policy_assignments_version_employee", table_name="policy_assignments")
    op.drop_index("ix_policy_assignments_employee_due", table_name="policy_assignments")
    op.drop_table("policy_assignments")
    op.drop_table("policy_version_closures")
    op.drop_index("ix_policy_versions_validity", table_name="policy_versions")
    op.drop_table("policy_versions")
    op.drop_index("ix_policy_items_scope_kind", table_name="policy_items")
    op.drop_table("policy_items")
