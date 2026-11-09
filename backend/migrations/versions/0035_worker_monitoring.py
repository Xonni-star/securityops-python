"""Add notification worker heartbeat and operations monitoring permission."""

from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert

revision: str = "0035_worker_monitoring"
down_revision: str | None = "0034_owks_automation_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION_CODE = "system.monitoring.read"
ROLE_CODES = ("administrator", "operations")


def stable_id(kind: str, code: str):
    return uuid5(NAMESPACE_URL, f"securityops:{kind}:{code}")


def upgrade() -> None:
    op.create_table(
        "notification_worker_heartbeats",
        sa.Column("worker_name", sa.String(length=80), primary_key=True),
        sa.Column(
            "heartbeat_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    uuid = postgresql.UUID(as_uuid=True)
    permissions = sa.table(
        "permissions",
        sa.column("id", uuid),
        sa.column("code", sa.String),
        sa.column("description", sa.String),
    )
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", uuid),
        sa.column("permission_id", uuid),
    )
    connection = op.get_bind()
    connection.execute(
        pg_insert(permissions)
        .values(
            id=stable_id("permission", PERMISSION_CODE),
            code=PERMISSION_CODE,
            description="Technischen Status des Notification-Workers einsehen",
        )
        .on_conflict_do_nothing()
    )
    connection.execute(
        pg_insert(role_permissions)
        .values(
            [
                {
                    "role_id": stable_id("role", role_code),
                    "permission_id": stable_id("permission", PERMISSION_CODE),
                }
                for role_code in ROLE_CODES
            ]
        )
        .on_conflict_do_nothing()
    )


def downgrade() -> None:
    connection = op.get_bind()
    custom_role_permission = connection.execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM role_permissions rp
                JOIN roles r ON r.id = rp.role_id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE p.code = :permission_code
                  AND r.code NOT IN ('administrator', 'operations')
            )
            """
        ),
        {"permission_code": PERMISSION_CODE},
    ).scalar_one()
    if custom_role_permission:
        raise RuntimeError(
            "Monitoring-Downgrade abgelehnt: Die Berechtigung ist benutzerdefinierten Rollen "
            "zugewiesen."
        )

    permission_id = stable_id("permission", PERMISSION_CODE)
    uuid = postgresql.UUID(as_uuid=True)
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", uuid),
        sa.column("permission_id", uuid),
    )
    permissions = sa.table("permissions", sa.column("id", uuid))
    connection.execute(
        sa.delete(role_permissions).where(
            role_permissions.c.permission_id == permission_id,
            role_permissions.c.role_id.in_([stable_id("role", code) for code in ROLE_CODES]),
        )
    )
    connection.execute(sa.delete(permissions).where(permissions.c.id == permission_id))
    op.drop_table("notification_worker_heartbeats")
