"""Prevent multiple incidents from referencing the same OWKS event."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_unique_incident_owks_event"
down_revision: str | None = "0024_notification_outbox_worker"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    duplicate = (
        op.get_bind()
        .execute(
            sa.text(
                """
            SELECT owks_event_id
            FROM incidents
            WHERE owks_event_id IS NOT NULL
            GROUP BY owks_event_id
            HAVING count(*) > 1
            LIMIT 1
            """
            )
        )
        .first()
    )
    if duplicate is not None:
        raise RuntimeError(
            "Migration 0025 abgelehnt: Mehrere Vorfälle verweisen auf dasselbe "
            "OWKS-Ereignis. Vor der Migration müssen Duplikate nachvollziehbar "
            "bereinigt werden."
        )
    op.create_index(
        "uq_incidents_owks_event_id",
        "incidents",
        ["owks_event_id"],
        unique=True,
        postgresql_where=sa.text("owks_event_id IS NOT NULL"),
        sqlite_where=sa.text("owks_event_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_incidents_owks_event_id", table_name="incidents")
