"""Add constrained task automation rules and execution tracking."""

from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert

revision: str = "0031_safe_automations"
down_revision: str | None = "0030_inventory_management"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION_CODE = "automations.manage"


def stable_id(kind: str, code: str):
    return uuid5(NAMESPACE_URL, f"securityops:{kind}:{code}")


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    timestamp = sa.DateTime(timezone=True)

    op.add_column(
        "notification_outbox",
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "notification_outbox",
        sa.Column("manual_retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(
        """
        UPDATE notification_outbox AS outbox_row
        SET failure_count = (
            SELECT count(*)
            FROM notification_outbox_attempts AS attempt
            WHERE attempt.outbox_id = outbox_row.id
              AND attempt.event IN ('retry_scheduled', 'dead_lettered')
        )
        """
    )
    op.create_check_constraint(
        "ck_notification_outbox_failure_count",
        "notification_outbox",
        "failure_count >= 0",
    )
    op.create_check_constraint(
        "ck_notification_outbox_manual_retry_count",
        "notification_outbox",
        "manual_retry_count BETWEEN 0 AND 3",
    )

    op.create_table(
        "automation_rules",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("trigger_type", sa.String(80), nullable=False),
        sa.Column("conditions", postgresql.JSON(), nullable=False, server_default="{}"),
        sa.Column("action_type", sa.String(80), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", timestamp, nullable=True),
        sa.Column(
            "created_by_id", uuid, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "updated_by_id", uuid, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "trigger_type IN ('task.assigned', 'task.status_changed')",
            name="ck_automation_rules_trigger_type",
        ),
        sa.CheckConstraint(
            "action_type = 'notify_event_recipients'",
            name="ck_automation_rules_action_type",
        ),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_automation_rules_name"),
    )
    op.create_index(
        "ix_automation_rules_trigger_active",
        "automation_rules",
        ["trigger_type", "is_active", "deleted_at"],
    )
    op.create_table(
        "automation_runs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "rule_id",
            uuid,
            sa.ForeignKey("automation_rules.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("rule_name", sa.String(100), nullable=False),
        sa.Column(
            "source_event_id",
            uuid,
            sa.ForeignKey("notification_outbox.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "action_event_id",
            uuid,
            sa.ForeignKey("notification_outbox.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("trigger_type", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("last_error", sa.String(100), nullable=True),
        sa.Column("manual_retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('condition_not_met', 'skipped_no_recipients', 'queued', "
            "'succeeded', 'dead_letter')",
            name="ck_automation_runs_status",
        ),
        sa.CheckConstraint(
            "manual_retry_count BETWEEN 0 AND 3",
            name="ck_automation_runs_manual_retry_count",
        ),
        sa.UniqueConstraint("rule_id", "source_event_id", name="uq_automation_runs_rule_source"),
        sa.UniqueConstraint("action_event_id", name="uq_automation_runs_action_event"),
    )
    op.create_index("ix_automation_runs_created", "automation_runs", ["created_at", "id"])

    permissions = sa.table(
        "permissions",
        sa.column("id", uuid),
        sa.column("code", sa.String(100)),
        sa.column("description", sa.String(300)),
    )
    role_permissions = sa.table(
        "role_permissions", sa.column("role_id", uuid), sa.column("permission_id", uuid)
    )
    permission_id = stable_id("permission", PERMISSION_CODE)
    op.get_bind().execute(
        pg_insert(permissions)
        .values(
            id=permission_id,
            code=PERMISSION_CODE,
            description="Automatisierungsregeln und Ausführungen verwalten",
        )
        .on_conflict_do_nothing()
    )
    op.get_bind().execute(
        pg_insert(role_permissions)
        .values(
            role_id=stable_id("role", "administrator"),
            permission_id=permission_id,
        )
        .on_conflict_do_nothing()
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM automation_runs) "
            "OR EXISTS (SELECT 1 FROM automation_rules)"
        )
    ).scalar_one():
        raise RuntimeError(
            "Automatisierungs-Downgrade abgelehnt: Regeln und Ausführungshistorie zuerst sichern."
        )

    uuid = postgresql.UUID(as_uuid=True)
    role_permissions = sa.table(
        "role_permissions", sa.column("role_id", uuid), sa.column("permission_id", uuid)
    )
    permissions = sa.table("permissions", sa.column("id", uuid))
    permission_id = stable_id("permission", PERMISSION_CODE)
    connection.execute(
        sa.delete(role_permissions).where(
            role_permissions.c.permission_id == permission_id,
            role_permissions.c.role_id == stable_id("role", "administrator"),
        )
    )
    connection.execute(sa.delete(permissions).where(permissions.c.id == permission_id))

    op.drop_index("ix_automation_runs_created", table_name="automation_runs")
    op.drop_table("automation_runs")
    op.drop_index("ix_automation_rules_trigger_active", table_name="automation_rules")
    op.drop_table("automation_rules")
    op.drop_constraint(
        "ck_notification_outbox_manual_retry_count",
        "notification_outbox",
        type_="check",
    )
    op.drop_constraint(
        "ck_notification_outbox_failure_count",
        "notification_outbox",
        type_="check",
    )
    op.drop_column("notification_outbox", "manual_retry_count")
    op.drop_column("notification_outbox", "failure_count")
