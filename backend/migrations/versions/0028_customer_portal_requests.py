"""Add customer-facing request threads and private attachments."""

from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert

revision: str = "0028_customer_portal_requests"
down_revision: str | None = "0027_customer_document_grants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MANAGE_PERMISSION = "customer_portal.requests.manage"


def stable_id(kind: str, code: str):
    return uuid5(NAMESPACE_URL, f"securityops:{kind}:{code}")


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "customer_portal_requests",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("customer_id", uuid, nullable=False),
        sa.Column("contact_id", uuid, nullable=False),
        sa.Column("object_id", uuid, nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="submitted"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "category IN ('request', 'question', 'complaint')",
            name="ck_customer_portal_requests_category",
        ),
        sa.CheckConstraint(
            "status IN ('submitted', 'in_progress', 'waiting_customer', 'resolved', 'closed')",
            name="ck_customer_portal_requests_status",
        ),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_customer_portal_requests_title"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["contact_id"], ["customer_contacts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["object_id"], ["objects.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_customer_portal_requests_customer_updated",
        "customer_portal_requests",
        ["customer_id", "updated_at"],
    )
    op.create_index(
        "ix_customer_portal_requests_status_updated",
        "customer_portal_requests",
        ["status", "updated_at"],
    )
    op.create_table(
        "customer_portal_request_messages",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("request_id", uuid, nullable=False),
        sa.Column("author_id", uuid, nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "length(trim(body)) > 0", name="ck_customer_portal_request_messages_body"
        ),
        sa.ForeignKeyConstraint(
            ["request_id"], ["customer_portal_requests.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_customer_portal_request_messages_request_created",
        "customer_portal_request_messages",
        ["request_id", "created_at"],
    )
    op.create_table(
        "customer_portal_request_attachments",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("request_id", uuid, nullable=False),
        sa.Column("storage_key", sa.String(32), nullable=False, unique=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("uploaded_by_id", uuid, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_customer_portal_request_attachments_size"),
        sa.CheckConstraint(
            "media_type IN ('application/pdf', 'image/png', 'image/jpeg')",
            name="ck_customer_portal_request_attachments_type",
        ),
        sa.ForeignKeyConstraint(
            ["request_id"], ["customer_portal_requests.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_customer_portal_request_attachments_request",
        "customer_portal_request_attachments",
        ["request_id", "created_at"],
    )
    op.create_table(
        "customer_portal_request_history",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("request_id", uuid, nullable=False),
        sa.Column("actor_id", uuid, nullable=True),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("old_status", sa.String(20), nullable=True),
        sa.Column("new_status", sa.String(20), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "action IN ('created', 'message_added', 'attachment_added', 'status_changed')",
            name="ck_customer_portal_request_history_action",
        ),
        sa.ForeignKeyConstraint(
            ["request_id"], ["customer_portal_requests.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_customer_portal_request_history_request_created",
        "customer_portal_request_history",
        ["request_id", "created_at"],
    )
    for table in (
        "customer_portal_request_messages",
        "customer_portal_request_attachments",
        "customer_portal_request_history",
    ):
        function_name = f"securityops_reject_{table}_mutation"
        op.execute(
            f"""
            CREATE FUNCTION {function_name}() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'Kundenanfrage-Verlauf ist unveränderlich'
                    USING ERRCODE = '55000';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION {function_name}()"
        )

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
            id=stable_id("permission", MANAGE_PERMISSION),
            code=MANAGE_PERMISSION,
            description="Kundenanfragen und Kundenrückmeldungen verwalten",
        )
        .on_conflict_do_nothing()
    )
    connection.execute(
        pg_insert(role_permissions)
        .values(
            role_id=stable_id("role", "administrator"),
            permission_id=stable_id("permission", MANAGE_PERMISSION),
        )
        .on_conflict_do_nothing()
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM customer_portal_requests) "
            "OR EXISTS (SELECT 1 FROM customer_portal_request_messages) "
            "OR EXISTS (SELECT 1 FROM customer_portal_request_attachments) "
            "OR EXISTS (SELECT 1 FROM customer_portal_request_history)"
        )
    ).scalar_one():
        raise RuntimeError(
            "Anfragen-Downgrade abgelehnt: Kundenanfragen und Verlauf zuerst sichern."
        )
    for table in (
        "customer_portal_request_history",
        "customer_portal_request_attachments",
        "customer_portal_request_messages",
    ):
        op.execute(f"DROP TRIGGER {table}_append_only ON {table}")
        op.execute(f"DROP FUNCTION securityops_reject_{table}_mutation()")
    for table in (
        "customer_portal_request_history",
        "customer_portal_request_attachments",
        "customer_portal_request_messages",
        "customer_portal_requests",
    ):
        op.drop_table(table)

    uuid = postgresql.UUID(as_uuid=True)
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", uuid),
        sa.column("permission_id", uuid),
    )
    permissions = sa.table("permissions", sa.column("id", uuid))
    connection.execute(
        sa.delete(role_permissions).where(
            role_permissions.c.permission_id == stable_id("permission", MANAGE_PERMISSION)
        )
    )
    connection.execute(
        sa.delete(permissions).where(permissions.c.id == stable_id("permission", MANAGE_PERMISSION))
    )
