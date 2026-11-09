"""Move OWKS and qualification document payloads to private file storage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033_encrypted_document_storage"
down_revision: str | None = "0032_employee_portal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("employee_qualification_documents", "owks_attachments"):
        op.add_column(table, sa.Column("storage_key", sa.String(length=32), nullable=True))
        op.alter_column(table, "content", existing_type=sa.LargeBinary(), nullable=True)
        op.create_unique_constraint(f"uq_{table}_storage_key", table, ["storage_key"])
        op.create_check_constraint(
            f"ck_{table}_storage",
            table,
            "(storage_key IS NULL AND content IS NOT NULL) OR "
            "(storage_key IS NOT NULL AND content IS NULL)",
        )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION securityops_reject_owks_mutation() RETURNS trigger AS $$
        BEGIN
            IF TG_TABLE_NAME = 'owks_attachments' THEN
                IF TG_OP = 'UPDATE'
                    AND current_user = 'securityops_migrator'
                    AND OLD.content IS NOT NULL
                    AND NEW.content IS NULL
                    AND NEW.storage_key = replace(OLD.id::text, '-', '')
                    AND (to_jsonb(OLD) - 'content' - 'storage_key')
                        = (to_jsonb(NEW) - 'content' - 'storage_key') THEN
                    RETURN NEW;
                END IF;
            END IF;
            RAISE EXCEPTION 'OWKS-Datensätze sind unveränderlich; Korrekturen müssen angehängt werden'
                USING ERRCODE = '55000';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute("REVOKE UPDATE, DELETE ON TABLE owks_attachments FROM securityops_runtime")


def downgrade() -> None:
    connection = op.get_bind()
    for table in ("employee_qualification_documents", "owks_attachments"):
        if connection.execute(
            sa.text(f"SELECT EXISTS (SELECT 1 FROM {table} WHERE storage_key IS NOT NULL)")
        ).scalar_one():
            raise RuntimeError(
                f"Downgrade abgelehnt: verschlüsselte Dateien aus {table} zuerst sichern."
            )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION securityops_reject_owks_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'OWKS-Datensätze sind unveränderlich; Korrekturen müssen angehängt werden'
                USING ERRCODE = '55000';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in ("employee_qualification_documents", "owks_attachments"):
        op.drop_constraint(f"ck_{table}_storage", table, type_="check")
        op.drop_constraint(f"uq_{table}_storage_key", table, type_="unique")
        op.drop_column(table, "storage_key")
        op.alter_column(table, "content", existing_type=sa.LargeBinary(), nullable=False)
