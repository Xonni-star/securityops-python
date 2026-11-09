"""Prevent multiple correction documents for one original invoice."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039_unique_billing_corrections"
down_revision: str | None = "0038_digital_policies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    duplicate = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT correction_of_id FROM billing_invoices "
                "WHERE correction_of_id IS NOT NULL "
                "GROUP BY correction_of_id HAVING COUNT(*) > 1 LIMIT 1"
            )
        )
        .first()
    )
    if duplicate is not None:
        raise RuntimeError(
            "Billing-Migration abgelehnt: Für mindestens eine Originalrechnung existieren "
            "mehrere Korrektur- oder Stornobelege; diese Daten müssen vor der Migration "
            "fachlich geprüft werden."
        )
    op.create_index(
        "uq_billing_invoices_correction_of",
        "billing_invoices",
        ["correction_of_id"],
        unique=True,
        postgresql_where=sa.text("correction_of_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_billing_invoices_correction_of", table_name="billing_invoices")
