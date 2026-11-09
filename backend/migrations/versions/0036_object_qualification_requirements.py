"""Add normalized qualification requirements to security objects."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0036_object_qualification_requirements"
down_revision: str | None = "0035_worker_monitoring"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "object_qualification_requirements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("object_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_object_qualification_requirements_name",
        ),
        sa.ForeignKeyConstraint(
            ["object_id"],
            ["objects.id"],
            name="fk_object_qualification_requirements_object_id_objects",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "object_id",
            "name",
            name="uq_object_qualification_requirements_object_name",
        ),
    )


def downgrade() -> None:
    has_requirements = op.get_bind().execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM object_qualification_requirements)")
    ).scalar_one()
    if has_requirements:
        raise RuntimeError(
            "Objektqualifikations-Downgrade abgelehnt: Objektanforderungen würden verloren gehen."
        )
    op.drop_table("object_qualification_requirements")
