"""Register acknowledged key issuance as an automation trigger."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040_key_issue_automation"
down_revision: str | None = "0039_unique_billing_corrections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_automation_rules_trigger_type", "automation_rules", type_="check")
    op.create_check_constraint(
        "ck_automation_rules_trigger_type",
        "automation_rules",
        "trigger_type IN ('task.assigned', 'task.status_changed', "
        "'owks.missed_control', 'owks.deviation_reported', "
        "'owks.offline_event_synced', 'billing.invoice_approved', 'key.issued')",
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM automation_rules WHERE trigger_type = 'key.issued') "
            "OR EXISTS (SELECT 1 FROM notification_outbox WHERE event_type = 'key.issued') "
            "OR EXISTS (SELECT 1 FROM automation_runs WHERE trigger_type = 'key.issued') "
            "OR EXISTS (SELECT 1 FROM notifications WHERE event_type = 'key.issued')"
        )
    ).scalar_one():
        raise RuntimeError(
            "Schlüsselregeln, -ereignisse und -benachrichtigungen müssen vor dem Downgrade "
            "gesichert oder entfernt werden."
        )

    op.drop_constraint("ck_automation_rules_trigger_type", "automation_rules", type_="check")
    op.create_check_constraint(
        "ck_automation_rules_trigger_type",
        "automation_rules",
        "trigger_type IN ('task.assigned', 'task.status_changed', "
        "'owks.missed_control', 'owks.deviation_reported', "
        "'owks.offline_event_synced', 'billing.invoice_approved')",
    )
