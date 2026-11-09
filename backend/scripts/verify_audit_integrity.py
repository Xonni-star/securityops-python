"""Verify the database-side audit hash chain and print its external checkpoint."""

import os
from typing import Any

import psycopg


def verify_audit_integrity(connection: psycopg.Connection[Any]) -> tuple[int, str | None]:
    result = connection.execute(
        """
        WITH RECURSIVE reachable(entry_hash) AS (
            SELECT entry_hash
            FROM public.audit_log_integrity
            WHERE previous_hash IS NULL
            UNION
            SELECT child.entry_hash
            FROM public.audit_log_integrity AS child
            JOIN reachable AS parent ON child.previous_hash = parent.entry_hash
        )
        SELECT
            count(audit.id) AS audit_count,
            count(integrity.audit_log_id) AS integrity_count,
            count(*) FILTER (
                WHERE audit.id IS NOT NULL
                  AND (
                    integrity.entry_hash IS NULL
                    OR public.securityops_audit_log_digest(audit, integrity.previous_hash)
                        <> integrity.entry_hash
                  )
            ) AS invalid_hashes,
            (SELECT count(*) FROM reachable) AS reachable_count,
            (SELECT count(*) FROM public.audit_log_integrity WHERE previous_hash IS NULL)
                AS root_count
        FROM public.audit_logs AS audit
        FULL OUTER JOIN public.audit_log_integrity AS integrity
            ON integrity.audit_log_id = audit.id
        """
    ).fetchone()
    audit_count, integrity_count, invalid_hashes, reachable_count, root_count = result
    tips = connection.execute(
        """
        SELECT encode(current_entry.entry_hash, 'hex')
        FROM public.audit_log_integrity AS current_entry
        WHERE NOT EXISTS (
            SELECT 1
            FROM public.audit_log_integrity AS successor
            WHERE successor.previous_hash = current_entry.entry_hash
        )
        """
    ).fetchall()
    valid_empty_chain = audit_count == integrity_count == reachable_count == root_count == 0
    valid_chain = (
        audit_count == integrity_count
        and invalid_hashes == 0
        and reachable_count == integrity_count
        and root_count == 1
        and len(tips) == 1
    )
    if not valid_empty_chain and not valid_chain:
        raise RuntimeError(
            "Audit-Integritätsprüfung fehlgeschlagen: "
            f"Einträge={audit_count}, Prüfsummen={integrity_count}, "
            f"ungültige Hashes={invalid_hashes}, erreichbar={reachable_count}, "
            f"Wurzeln={root_count}, Enden={len(tips)}."
        )
    return audit_count, tips[0][0] if tips else None


def main() -> None:
    options = {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": int(os.environ.get("POSTGRES_PORT", "5432")),
        "dbname": os.environ.get("POSTGRES_DB", "securityops"),
        "user": os.environ.get("POSTGRES_USER", "securityops_migrator"),
        "password": os.environ["POSTGRES_PASSWORD"],
    }
    with psycopg.connect(**options) as connection:
        count, tip = verify_audit_integrity(connection)
    print(f"Audit-Integrität gültig: {count} Einträge; Kettenende SHA-256: {tip or 'leer'}")


if __name__ == "__main__":
    main()
