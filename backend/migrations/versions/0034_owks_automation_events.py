"""Register scoped OWKS automation events."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034_owks_automation_events"
down_revision: str | None = "0033_encrypted_document_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TRIGGERS = (
    "'task.assigned', 'task.status_changed', 'owks.missed_control', "
    "'owks.deviation_reported', 'owks.offline_event_synced'"
)


def upgrade() -> None:
    op.drop_constraint("ck_automation_rules_trigger_type", "automation_rules", type_="check")
    op.create_check_constraint(
        "ck_automation_rules_trigger_type",
        "automation_rules",
        f"trigger_type IN ({TRIGGERS})",
    )
    op.alter_column(
        "notifications",
        "task_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.add_column(
        "notifications",
        sa.Column(
            "object_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("objects.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_notifications_target",
        "notifications",
        "((task_id IS NOT NULL AND object_id IS NULL) "
        "OR (task_id IS NULL AND object_id IS NOT NULL))",
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM notifications WHERE object_id IS NOT NULL "
            "OR task_id IS NULL)"
        )
    ).scalar_one():
        raise RuntimeError(
            "OWKS-Benachrichtigungen müssen vor dem Downgrade gesichert oder entfernt werden."
        )

    op.drop_constraint("ck_notifications_target", "notifications", type_="check")
    op.drop_column("notifications", "object_id")
    op.alter_column(
        "notifications",
        "task_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.drop_constraint("ck_automation_rules_trigger_type", "automation_rules", type_="check")
    op.create_check_constraint(
        "ck_automation_rules_trigger_type",
        "automation_rules",
        "trigger_type IN ('task.assigned', 'task.status_changed')",
    )
