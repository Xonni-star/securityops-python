"""Add immutable shift handovers and recipient confirmations."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0041_owks_shift_handovers"
down_revision: str | None = "0040_key_issue_automation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "owks_shift_handovers",
        sa.Column("id", uuid, nullable=False),
        sa.Column("event_id", uuid, nullable=False),
        sa.Column("object_id", uuid, nullable=False),
        sa.Column("shift_id", uuid, nullable=False),
        sa.Column("sender_employee_id", uuid, nullable=False),
        sa.Column("recipient_employee_id", uuid, nullable=False),
        sa.Column("handover_text", sa.Text(), nullable=False),
        sa.Column(
            "structured_items",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column("source_items", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("created_by_id", uuid, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("length(trim(handover_text)) > 0", name="ck_owks_shift_handovers_text"),
        sa.CheckConstraint(
            "sender_employee_id != recipient_employee_id",
            name="ck_owks_shift_handovers_distinct_employees",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["owks_events.id"],
            ondelete="RESTRICT",
            name="fk_owks_shift_handovers_event",
        ),
        sa.ForeignKeyConstraint(
            ["object_id"],
            ["objects.id"],
            ondelete="RESTRICT",
            name="fk_owks_shift_handovers_object",
        ),
        sa.ForeignKeyConstraint(
            ["shift_id"],
            ["schedule_shifts.id"],
            ondelete="RESTRICT",
            name="fk_owks_shift_handovers_shift",
        ),
        sa.ForeignKeyConstraint(
            ["sender_employee_id"],
            ["employees.id"],
            ondelete="RESTRICT",
            name="fk_owks_shift_handovers_sender",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_employee_id"],
            ["employees.id"],
            ondelete="RESTRICT",
            name="fk_owks_shift_handovers_recipient",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_owks_shift_handovers_created_by",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_owks_shift_handovers"),
        sa.UniqueConstraint("shift_id", name="uq_owks_shift_handovers_shift"),
        sa.UniqueConstraint("event_id", name="uq_owks_shift_handovers_event"),
    )
    op.create_index(
        "ix_owks_shift_handovers_object_created",
        "owks_shift_handovers",
        ["object_id", "created_at"],
    )
    op.create_index(
        "ix_owks_shift_handovers_recipient_created",
        "owks_shift_handovers",
        ["recipient_employee_id", "created_at"],
    )
    op.create_table(
        "owks_shift_handover_confirmations",
        sa.Column("id", uuid, nullable=False),
        sa.Column("handover_id", uuid, nullable=False),
        sa.Column("employee_id", uuid, nullable=False),
        sa.Column("actor_id", uuid, nullable=False),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(note)) <= 1000", name="ck_owks_shift_handover_confirmation_note"
        ),
        sa.ForeignKeyConstraint(
            ["handover_id"],
            ["owks_shift_handovers.id"],
            ondelete="RESTRICT",
            name="fk_owks_shift_handover_confirmations_handover",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            ondelete="RESTRICT",
            name="fk_owks_shift_handover_confirmations_employee",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_owks_shift_handover_confirmations_actor",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_owks_shift_handover_confirmations"),
        sa.UniqueConstraint("handover_id", name="uq_owks_shift_handover_confirmation"),
    )
    op.create_index(
        "ix_owks_shift_handover_confirmations_created",
        "owks_shift_handover_confirmations",
        ["handover_id", "created_at"],
    )
    op.execute(
        """
        CREATE FUNCTION reject_owks_handover_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'OWKS shift handover history rows are append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in ("owks_shift_handovers", "owks_shift_handover_confirmations"):
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_owks_handover_mutation()"
        )


def downgrade() -> None:
    connection = op.get_bind()
    has_data = connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM owks_shift_handover_confirmations) "
            "OR EXISTS (SELECT 1 FROM owks_shift_handovers)"
        )
    ).scalar_one()
    if has_data:
        raise RuntimeError(
            "Downgrade abgelehnt: Schichtübergaben und Empfangsnachweise müssen "
            "vorher gesichert werden."
        )
    for table in ("owks_shift_handover_confirmations", "owks_shift_handovers"):
        op.execute(f"DROP TRIGGER {table}_append_only ON {table}")
    op.execute("DROP FUNCTION reject_owks_handover_mutation()")
    op.drop_index(
        "ix_owks_shift_handover_confirmations_created",
        table_name="owks_shift_handover_confirmations",
    )
    op.drop_table("owks_shift_handover_confirmations")
    op.drop_index("ix_owks_shift_handovers_recipient_created", table_name="owks_shift_handovers")
    op.drop_index("ix_owks_shift_handovers_object_created", table_name="owks_shift_handovers")
    op.drop_table("owks_shift_handovers")
