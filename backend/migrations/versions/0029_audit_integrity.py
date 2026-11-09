"""Protect audit logs and add a tamper-evident integrity chain."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_audit_integrity"
down_revision: str | None = "0028_customer_portal_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("LOCK TABLE public.audit_logs IN ACCESS EXCLUSIVE MODE")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public")
    op.drop_constraint("audit_logs_actor_id_fkey", "audit_logs", type_="foreignkey")
    op.create_table(
        "audit_log_integrity",
        sa.Column(
            "audit_log_id",
            sa.UUID(),
            sa.ForeignKey("audit_logs.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("previous_hash", sa.LargeBinary(32), nullable=True, unique=True),
        sa.Column("entry_hash", sa.LargeBinary(32), nullable=False, unique=True),
        sa.CheckConstraint(
            "previous_hash IS NULL OR octet_length(previous_hash) = 32",
            name="ck_audit_log_integrity_previous_hash_length",
        ),
        sa.CheckConstraint(
            "octet_length(entry_hash) = 32", name="ck_audit_log_integrity_entry_hash_length"
        ),
    )
    op.execute(
        """
        CREATE FUNCTION public.securityops_audit_log_digest(
            p_log public.audit_logs,
            p_previous_hash bytea
        ) RETURNS bytea
        LANGUAGE plpgsql
        IMMUTABLE
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            payload jsonb;
        BEGIN
            payload := jsonb_build_object(
                'id', (p_log).id,
                'actor_id', (p_log).actor_id,
                'action', (p_log).action,
                'entity_type', (p_log).entity_type,
                'entity_id', (p_log).entity_id,
                'ip_address', (p_log).ip_address,
                'details', (p_log).details,
                'created_at', to_char(
                    (p_log).created_at AT TIME ZONE 'UTC',
                    'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                )
            );
            RETURN digest(
                COALESCE(p_previous_hash, decode(repeat('00', 32), 'hex'))
                    || convert_to(payload::text, 'UTF8'),
                'sha256'
            );
        END;
        $$
        """
    )
    op.execute(
        """
        DO $$
        DECLARE
            audit_row public.audit_logs;
            previous_hash bytea := NULL;
            entry_hash bytea;
        BEGIN
            FOR audit_row IN
                SELECT * FROM public.audit_logs ORDER BY created_at, id
            LOOP
                entry_hash := public.securityops_audit_log_digest(audit_row, previous_hash);
                INSERT INTO public.audit_log_integrity (
                    audit_log_id, previous_hash, entry_hash
                ) VALUES (audit_row.id, previous_hash, entry_hash);
                previous_hash := entry_hash;
            END LOOP;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.securityops_audit_log_integrity_insert()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            previous_hash bytea;
            head_count integer;
        BEGIN
            PERFORM pg_advisory_xact_lock(483, 29);
            SELECT count(*) INTO head_count
            FROM public.audit_log_integrity AS current_entry
            WHERE NOT EXISTS (
                SELECT 1
                FROM public.audit_log_integrity AS successor
                WHERE successor.previous_hash = current_entry.entry_hash
            );
            IF head_count > 1 THEN
                RAISE EXCEPTION 'Audit-Integritätskette hat mehrere Enden'
                    USING ERRCODE = '55000';
            ELSIF head_count = 1 THEN
                SELECT current_entry.entry_hash INTO previous_hash
                FROM public.audit_log_integrity AS current_entry
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM public.audit_log_integrity AS successor
                    WHERE successor.previous_hash = current_entry.entry_hash
                );
            END IF;

            INSERT INTO public.audit_log_integrity (
                audit_log_id, previous_hash, entry_hash
            ) VALUES (
                NEW.id,
                previous_hash,
                public.securityops_audit_log_digest(NEW, previous_hash)
            );
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.securityops_reject_audit_log_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
            RAISE EXCEPTION 'Audit-Einträge sind unveränderlich'
                USING ERRCODE = '55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.securityops_reject_audit_integrity_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
            RAISE EXCEPTION 'Audit-Integritätsdaten sind unveränderlich'
                USING ERRCODE = '55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_logs_append_only
        BEFORE UPDATE OR DELETE ON public.audit_logs
        FOR EACH ROW EXECUTE FUNCTION public.securityops_reject_audit_log_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_log_integrity_append_only
        BEFORE UPDATE OR DELETE ON public.audit_log_integrity
        FOR EACH ROW EXECUTE FUNCTION public.securityops_reject_audit_integrity_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_logs_integrity_chain
        AFTER INSERT ON public.audit_logs
        FOR EACH ROW EXECUTE FUNCTION public.securityops_audit_log_integrity_insert()
        """
    )
    op.execute("REVOKE ALL ON public.audit_logs FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT ON public.audit_logs TO securityops_runtime")
    op.execute(
        "REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON public.audit_logs "
        "FROM securityops_runtime"
    )
    op.execute("REVOKE ALL ON public.audit_log_integrity FROM PUBLIC, securityops_runtime")
    op.execute(
        "REVOKE EXECUTE ON FUNCTION public.securityops_audit_log_digest("
        "public.audit_logs, bytea) FROM PUBLIC, securityops_runtime"
    )
    op.execute(
        "REVOKE EXECUTE ON FUNCTION public.securityops_audit_log_integrity_insert() "
        "FROM PUBLIC, securityops_runtime"
    )
    op.execute(
        "REVOKE EXECUTE ON FUNCTION public.securityops_reject_audit_log_mutation() "
        "FROM PUBLIC, securityops_runtime"
    )
    op.execute(
        "REVOKE EXECUTE ON FUNCTION public.securityops_reject_audit_integrity_mutation() "
        "FROM PUBLIC, securityops_runtime"
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM public.audit_logs) "
            "OR EXISTS (SELECT 1 FROM public.audit_log_integrity)"
        )
    ).scalar_one():
        raise RuntimeError(
            "Audit-Downgrade abgelehnt: Audit-Einträge und Integritätskette zuerst sichern."
        )
    op.execute("DROP TRIGGER audit_logs_integrity_chain ON public.audit_logs")
    op.execute("DROP TRIGGER audit_log_integrity_append_only ON public.audit_log_integrity")
    op.execute("DROP TRIGGER audit_logs_append_only ON public.audit_logs")
    op.drop_table("audit_log_integrity")
    op.execute("DROP FUNCTION public.securityops_audit_log_integrity_insert()")
    op.execute("DROP FUNCTION public.securityops_reject_audit_integrity_mutation()")
    op.execute("DROP FUNCTION public.securityops_reject_audit_log_mutation()")
    op.execute("DROP FUNCTION public.securityops_audit_log_digest(public.audit_logs, bytea)")
    op.create_foreign_key(
        "audit_logs_actor_id_fkey",
        "audit_logs",
        "users",
        ["actor_id"],
        ["id"],
        ondelete="SET NULL",
    )
