"""Register invoice approval automation and scope its notifications."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0036_billing_approval_automation"
down_revision: str | None = "0035_worker_monitoring"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_automation_rules_trigger_type", "automation_rules", type_="check")
    op.create_check_constraint(
        "ck_automation_rules_trigger_type",
        "automation_rules",
        "trigger_type IN ('task.assigned', 'task.status_changed', "
        "'owks.missed_control', 'owks.deviation_reported', "
        "'owks.offline_event_synced', 'billing.invoice_approved')",
    )
    op.add_column(
        "notifications",
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("billing_invoices.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.drop_constraint("ck_notifications_target", "notifications", type_="check")
    op.create_check_constraint(
        "ck_notifications_target",
        "notifications",
        "((task_id IS NOT NULL AND object_id IS NULL AND invoice_id IS NULL) "
        "OR (task_id IS NULL AND object_id IS NOT NULL AND invoice_id IS NULL) "
        "OR (task_id IS NULL AND object_id IS NULL AND invoice_id IS NOT NULL))",
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM notifications WHERE invoice_id IS NOT NULL) "
            "OR EXISTS (SELECT 1 FROM automation_rules "
            "WHERE trigger_type = 'billing.invoice_approved') "
            "OR EXISTS (SELECT 1 FROM notification_outbox "
            "WHERE event_type = 'billing.invoice_approved')"
        )
    ).scalar_one():
        raise RuntimeError(
            "Rechnungsregeln, -ereignisse und -benachrichtigungen müssen vor dem Downgrade "
            "gesichert oder entfernt werden."
        )

    op.drop_constraint("ck_notifications_target", "notifications", type_="check")
    op.drop_column("notifications", "invoice_id")
    op.create_check_constraint(
        "ck_notifications_target",
        "notifications",
        "((task_id IS NOT NULL AND object_id IS NULL) "
        "OR (task_id IS NULL AND object_id IS NOT NULL))",
    )
    op.drop_constraint("ck_automation_rules_trigger_type", "automation_rules", type_="check")
    op.create_check_constraint(
        "ck_automation_rules_trigger_type",
        "automation_rules",
        "trigger_type IN ('task.assigned', 'task.status_changed', "
        "'owks.missed_control', 'owks.deviation_reported', "
        "'owks.offline_event_synced')",
    )
