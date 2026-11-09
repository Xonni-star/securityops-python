from datetime import UTC, date, datetime, time
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


user_roles = Table(
    "user_roles",
    Base.metadata,
    Column(
        "user_id", Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    ),
    Column(
        "role_id", Uuid(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    ),
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column(
        "role_id", Uuid(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    ),
    Column(
        "permission_id",
        Uuid(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    users: Mapped[list["User"]] = relationship(secondary=user_roles, back_populates="roles")
    permissions: Mapped[list["Permission"]] = relationship(
        secondary=role_permissions, back_populates="roles"
    )


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    roles: Mapped[list[Role]] = relationship(
        secondary=role_permissions, back_populates="permissions"
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("length(trim(username)) > 0", name="ck_users_username"),
        CheckConstraint("length(trim(full_name)) > 0", name="ck_users_full_name"),
        CheckConstraint(
            "mfa_enabled = false OR mfa_secret_encrypted IS NOT NULL",
            name="ck_users_mfa_secret",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    mfa_enabled: Mapped[bool] = mapped_column(
        default=False, server_default=text("false"), nullable=False
    )
    mfa_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    mfa_last_counter: Mapped[int | None] = mapped_column(nullable=True)
    force_password_change: Mapped[bool] = mapped_column(
        default=False, server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    roles: Mapped[list[Role]] = relationship(secondary=user_roles, back_populates="users")
    object_assignments: Mapped[list["ObjectAssignment"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="ObjectAssignment.user_id",
    )
    employee_record: Mapped["Employee | None"] = relationship(back_populates="user", uselist=False)
    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    mfa_recovery_codes: Mapped[list["UserMFARecoveryCode"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserSession(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (Index("ix_user_sessions_user_expires", "user_id", "expires_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    user: Mapped[User] = relationship(back_populates="sessions")


class UserMFARecoveryCode(Base):
    __tablename__ = "user_mfa_recovery_codes"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    user: Mapped[User] = relationship(back_populates="mfa_recovery_codes")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_entity_created", "entity_type", "entity_id", "created_at"),
        Index("ix_audit_logs_actor_created", "actor_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    details: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'urgent')", name="ck_tasks_priority"
        ),
        CheckConstraint(
            "status IN ('open', 'in_progress', 'blocked', 'completed', 'cancelled')",
            name="ck_tasks_status",
        ),
        CheckConstraint("length(trim(title)) > 0", name="ck_tasks_title"),
        Index("ix_tasks_assignee_status_due", "assigned_to_id", "status", "due_at"),
        Index("ix_tasks_object_status_due", "object_id", "status", "due_at"),
        Index("ix_tasks_customer_status_due", "customer_id", "status", "due_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    customer_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=True
    )
    object_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("objects.id", ondelete="RESTRICT"), nullable=True
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    priority: Mapped[str] = mapped_column(
        String(20), default="normal", server_default=text("'normal'"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="open", server_default=text("'open'"), nullable=False
    )
    completion_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    assignee: Mapped["User"] = relationship(foreign_keys=[assigned_to_id])
    creator: Mapped["User | None"] = relationship(foreign_keys=[created_by_id])
    customer: Mapped["Customer | None"] = relationship()
    object: Mapped["SecurityObject | None"] = relationship()
    comments: Mapped[list["TaskComment"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    history: Mapped[list["TaskHistory"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class TaskComment(Base):
    __tablename__ = "task_comments"
    __table_args__ = (
        CheckConstraint("length(trim(body)) > 0", name="ck_task_comments_body"),
        Index("ix_task_comments_task_created", "task_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    task: Mapped[Task] = relationship(back_populates="comments")
    author: Mapped["User | None"] = relationship()


class TaskHistory(Base):
    __tablename__ = "task_history"
    __table_args__ = (Index("ix_task_history_task_created", "task_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    changes: Mapped[dict[str, object]] = mapped_column(
        JSON, default=dict, server_default=text("'{}'"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    task: Mapped[Task] = relationship(back_populates="history")
    actor: Mapped["User | None"] = relationship()


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed', 'dead_letter')",
            name="ck_notification_outbox_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_notification_outbox_attempt_count"),
        CheckConstraint("failure_count >= 0", name="ck_notification_outbox_failure_count"),
        CheckConstraint(
            "manual_retry_count BETWEEN 0 AND 3",
            name="ck_notification_outbox_manual_retry_count",
        ),
        UniqueConstraint("dedupe_key", name="uq_notification_outbox_dedupe_key"),
        Index("ix_notification_outbox_status_available", "status", "available_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    dedupe_key: Mapped[str] = mapped_column(String(160), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default=text("'pending'"), nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(default=0, server_default=text("0"), nullable=False)
    failure_count: Mapped[int] = mapped_column(default=0, server_default=text("0"), nullable=False)
    manual_retry_count: Mapped[int] = mapped_column(
        default=0, server_default=text("0"), nullable=False
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lock_token: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class NotificationOutboxAttempt(Base):
    __tablename__ = "notification_outbox_attempts"
    __table_args__ = (
        CheckConstraint(
            "event IN ('claimed', 'succeeded', 'retry_scheduled', 'dead_lettered')",
            name="ck_notification_outbox_attempt_event",
        ),
        CheckConstraint("attempt_number > 0", name="ck_notification_outbox_attempt_number"),
        UniqueConstraint(
            "outbox_id", "attempt_number", "event", name="uq_notification_outbox_attempt_event"
        ),
        Index("ix_notification_outbox_attempts_outbox_created", "outbox_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    outbox_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("notification_outbox.id", ondelete="RESTRICT"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(nullable=False)
    event: Mapped[str] = mapped_column(String(30), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class AutomationRule(Base):
    __tablename__ = "automation_rules"
    __table_args__ = (
        CheckConstraint(
            "trigger_type IN ('task.assigned', 'task.status_changed', "
            "'owks.missed_control', 'owks.deviation_reported', "
            "'owks.offline_event_synced')",
            name="ck_automation_rules_trigger_type",
        ),
        CheckConstraint(
            "action_type = 'notify_event_recipients'",
            name="ck_automation_rules_action_type",
        ),
        CheckConstraint("length(trim(name)) > 0", name="ck_automation_rules_name"),
        Index("ix_automation_rules_trigger_active", "trigger_type", "is_active", "deleted_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(80), nullable=False)
    conditions: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    action_type: Mapped[str] = mapped_column(String(80), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        default=False, server_default=text("false"), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class AutomationRun(Base):
    __tablename__ = "automation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('condition_not_met', 'skipped_no_recipients', 'queued', "
            "'succeeded', 'dead_letter')",
            name="ck_automation_runs_status",
        ),
        CheckConstraint(
            "manual_retry_count BETWEEN 0 AND 3", name="ck_automation_runs_manual_retry_count"
        ),
        UniqueConstraint("rule_id", "source_event_id", name="uq_automation_runs_rule_source"),
        UniqueConstraint("action_event_id", name="uq_automation_runs_action_event"),
        Index("ix_automation_runs_created", "created_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    rule_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("automation_rules.id", ondelete="RESTRICT"), nullable=False
    )
    rule_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_event_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("notification_outbox.id", ondelete="RESTRICT"),
        nullable=False,
    )
    action_event_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("notification_outbox.id", ondelete="RESTRICT"),
        nullable=True,
    )
    trigger_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(100), nullable=True)
    manual_retry_count: Mapped[int] = mapped_column(
        default=0, server_default=text("0"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class NotificationWorkerHeartbeat(Base):
    __tablename__ = "notification_worker_heartbeats"

    worker_name: Mapped[str] = mapped_column(String(80), primary_key=True)
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "(task_id IS NOT NULL AND object_id IS NULL) "
            "OR (task_id IS NULL AND object_id IS NOT NULL)",
            name="ck_notifications_target",
        ),
        UniqueConstraint("outbox_id", "recipient_id", name="uq_notifications_event_recipient"),
        Index("ix_notifications_recipient_created", "recipient_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    outbox_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("notification_outbox.id", ondelete="RESTRICT"),
        nullable=False,
    )
    recipient_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=True
    )
    object_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("objects.id", ondelete="RESTRICT"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recipient: Mapped[User] = relationship()
    task: Mapped[Task | None] = relationship()
    object: Mapped["SecurityObject | None"] = relationship()
    outbox_event: Mapped[NotificationOutbox] = relationship()


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'inactive', 'lead')", name="ck_customers_status"),
        CheckConstraint(
            "contract_status IN ('none', 'draft', 'active', 'expired', 'terminated')",
            name="ck_customers_contract_status",
        ),
        CheckConstraint("length(trim(company_name)) > 0", name="ck_customers_company_name"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    customer_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    company_name: Mapped[str] = mapped_column(String(200), index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    legal_form: Mapped[str | None] = mapped_column(String(100), nullable=True)
    website: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    contract_status: Mapped[str] = mapped_column(String(20), default="none", nullable=False)
    vat_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tax_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    addresses: Mapped[list["CustomerAddress"]] = relationship(back_populates="customer")
    contacts: Mapped[list["CustomerContact"]] = relationship(back_populates="customer")
    objects: Mapped[list["SecurityObject"]] = relationship(back_populates="customer")

    @property
    def business_address(self) -> "CustomerAddress | None":
        return next((address for address in self.addresses if address.kind == "business"), None)

    @property
    def billing_address(self) -> "CustomerAddress | None":
        return next((address for address in self.addresses if address.kind == "billing"), None)


class CustomerAddress(Base):
    __tablename__ = "customer_addresses"
    __table_args__ = (
        UniqueConstraint("customer_id", "kind", name="uq_customer_addresses_customer_kind"),
        CheckConstraint("kind IN ('business', 'billing')", name="ck_customer_addresses_kind"),
        CheckConstraint(
            "length(trim(street)) > 0 AND length(trim(city)) > 0",
            name="ck_customer_addresses_required_fields",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    customer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    street: Mapped[str] = mapped_column(String(160), nullable=False)
    house_number: Mapped[str] = mapped_column(String(30), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), default="DE", nullable=False)
    customer: Mapped[Customer] = relationship(back_populates="addresses")


class CustomerContact(Base):
    __tablename__ = "customer_contacts"
    __table_args__ = (
        CheckConstraint(
            "length(trim(first_name)) > 0 AND length(trim(last_name)) > 0",
            name="ck_customer_contacts_name",
        ),
        Index("ix_customer_contacts_customer_name", "customer_id", "last_name", "first_name"),
        Index(
            "uq_customer_contacts_primary",
            "customer_id",
            unique=True,
            postgresql_where=text("is_primary"),
            sqlite_where=text("is_primary = 1"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    customer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    responsibility: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_primary: Mapped[bool] = mapped_column(default=False, nullable=False)
    customer: Mapped[Customer] = relationship(back_populates="contacts")


class CustomerPortalLink(Base):
    __tablename__ = "customer_portal_links"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_customer_portal_links_user"),
        UniqueConstraint("contact_id", name="uq_customer_portal_links_contact"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    contact_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customer_contacts.id", ondelete="RESTRICT"), nullable=False
    )
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CustomerPortalLinkHistory(Base):
    __tablename__ = "customer_portal_link_history"
    __table_args__ = (
        CheckConstraint(
            "action IN ('linked', 'unlinked', 'activated', 'deactivated')",
            name="ck_customer_portal_link_action",
        ),
        Index("ix_customer_portal_link_history_created", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    contact_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customer_contacts.id", ondelete="RESTRICT"), nullable=False
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class CustomerPortalDocumentGrant(Base):
    __tablename__ = "customer_portal_document_grants"
    __table_args__ = (
        CheckConstraint(
            "(revoked_at IS NULL AND revoked_by_id IS NULL) OR "
            "(revoked_at IS NOT NULL AND revoked_by_id IS NOT NULL)",
            name="ck_customer_portal_document_grants_revocation",
        ),
        Index(
            "uq_customer_portal_document_grants_active",
            "document_id",
            "version_id",
            "customer_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
        Index("ix_customer_portal_document_grants_customer", "customer_id", "granted_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False
    )
    version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("document_versions.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    granted_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    revoked_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CustomerPortalDocumentGrantHistory(Base):
    __tablename__ = "customer_portal_document_grant_history"
    __table_args__ = (
        CheckConstraint("action IN ('granted', 'revoked')", name="ck_portal_document_grant_action"),
        Index("ix_customer_portal_document_grant_history_created", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    grant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("customer_portal_document_grants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class EmployeePortalDocumentGrant(Base):
    __tablename__ = "employee_portal_document_grants"
    __table_args__ = (
        CheckConstraint(
            "(revoked_at IS NULL AND revoked_by_id IS NULL) OR "
            "(revoked_at IS NOT NULL AND revoked_by_id IS NOT NULL)",
            name="ck_employee_portal_document_grants_revocation",
        ),
        Index(
            "uq_employee_portal_document_grants_active",
            "qualification_document_id",
            "user_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
        Index(
            "ix_employee_portal_document_grants_employee",
            "employee_id",
            "granted_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    employee_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    qualification_document_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("employee_qualification_documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    granted_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    revoked_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmployeePortalDocumentGrantHistory(Base):
    __tablename__ = "employee_portal_document_grant_history"
    __table_args__ = (
        CheckConstraint(
            "action IN ('granted', 'revoked')",
            name="ck_employee_portal_document_grant_history_action",
        ),
        Index("ix_employee_portal_document_grant_history_created", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    grant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("employee_portal_document_grants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class CustomerPortalRequest(Base):
    __tablename__ = "customer_portal_requests"
    __table_args__ = (
        CheckConstraint(
            "category IN ('request', 'question', 'complaint')",
            name="ck_customer_portal_requests_category",
        ),
        CheckConstraint(
            "status IN ('submitted', 'in_progress', 'waiting_customer', 'resolved', 'closed')",
            name="ck_customer_portal_requests_status",
        ),
        CheckConstraint("length(trim(title)) > 0", name="ck_customer_portal_requests_title"),
        Index("ix_customer_portal_requests_customer_updated", "customer_id", "updated_at"),
        Index("ix_customer_portal_requests_status_updated", "status", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    customer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    contact_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customer_contacts.id", ondelete="RESTRICT"), nullable=False
    )
    object_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("objects.id", ondelete="RESTRICT"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="submitted", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class CustomerPortalRequestMessage(Base):
    __tablename__ = "customer_portal_request_messages"
    __table_args__ = (
        CheckConstraint("length(trim(body)) > 0", name="ck_customer_portal_request_messages_body"),
        Index(
            "ix_customer_portal_request_messages_request_created",
            "request_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("customer_portal_requests.id", ondelete="RESTRICT"),
        nullable=False,
    )
    author_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class CustomerPortalRequestAttachment(Base):
    __tablename__ = "customer_portal_request_attachments"
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="ck_customer_portal_request_attachments_size"),
        CheckConstraint(
            "media_type IN ('application/pdf', 'image/png', 'image/jpeg')",
            name="ck_customer_portal_request_attachments_type",
        ),
        Index("ix_customer_portal_request_attachments_request", "request_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("customer_portal_requests.id", ondelete="RESTRICT"),
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class CustomerPortalRequestHistory(Base):
    __tablename__ = "customer_portal_request_history"
    __table_args__ = (
        CheckConstraint(
            "action IN ('created', 'message_added', 'attachment_added', 'status_changed')",
            name="ck_customer_portal_request_history_action",
        ),
        Index("ix_customer_portal_request_history_request_created", "request_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("customer_portal_requests.id", ondelete="RESTRICT"),
        nullable=False,
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class CustomerHistory(Base):
    __tablename__ = "customer_history"
    __table_args__ = (Index("ix_customer_history_customer_created", "customer_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    customer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    changed_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class SecurityObject(Base):
    __tablename__ = "objects"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'inactive')", name="ck_objects_status"),
        CheckConstraint("length(trim(name)) > 0", name="ck_objects_name"),
        CheckConstraint("length(trim(code)) > 0", name="ck_objects_code"),
        Index("ix_objects_customer_status", "customer_id", "status", "archived_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    customer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    object_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    operating_hours: Mapped[str | None] = mapped_column(String(200), nullable=True)
    service_times: Mapped[str | None] = mapped_column(String(200), nullable=True)
    staffing_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    customer: Mapped[Customer] = relationship(back_populates="objects")
    address: Mapped["ObjectAddress | None"] = relationship(
        back_populates="object", cascade="all, delete-orphan"
    )
    contacts: Mapped[list["ObjectContact"]] = relationship(
        back_populates="object", cascade="all, delete-orphan"
    )
    history: Mapped[list["ObjectHistory"]] = relationship(
        back_populates="object", cascade="all, delete-orphan"
    )
    assignments: Mapped[list["ObjectAssignment"]] = relationship(
        back_populates="object", cascade="all, delete-orphan"
    )
    security_details: Mapped["ObjectSecurityDetails | None"] = relationship(
        back_populates="object", cascade="all, delete-orphan", uselist=False
    )

    @property
    def customer_name(self) -> str:
        return self.customer.company_name


class ObjectAddress(Base):
    __tablename__ = "object_addresses"
    __table_args__ = (
        UniqueConstraint("object_id", name="uq_object_addresses_object"),
        CheckConstraint(
            "length(trim(street)) > 0 AND length(trim(city)) > 0",
            name="ck_object_addresses_required_fields",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    object_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("objects.id", ondelete="RESTRICT"), nullable=False
    )
    street: Mapped[str] = mapped_column(String(160), nullable=False)
    house_number: Mapped[str] = mapped_column(String(30), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), default="DE", nullable=False)
    object: Mapped[SecurityObject] = relationship(back_populates="address")


class ObjectContact(Base):
    __tablename__ = "object_contacts"
    __table_args__ = (
        CheckConstraint(
            "length(trim(first_name)) > 0 AND length(trim(last_name)) > 0",
            name="ck_object_contacts_name",
        ),
        Index("ix_object_contacts_object_name", "object_id", "last_name", "first_name"),
        Index(
            "uq_object_contacts_primary",
            "object_id",
            unique=True,
            postgresql_where=text("is_primary"),
            sqlite_where=text("is_primary = 1"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    object_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("objects.id", ondelete="RESTRICT"), nullable=False
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_primary: Mapped[bool] = mapped_column(default=False, nullable=False)
    object: Mapped[SecurityObject] = relationship(back_populates="contacts")


class ObjectHistory(Base):
    __tablename__ = "object_history"
    __table_args__ = (Index("ix_object_history_object_created", "object_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    object_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("objects.id", ondelete="RESTRICT"), nullable=False
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    changed_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    object: Mapped[SecurityObject] = relationship(back_populates="history")


class ObjectAssignment(Base):
    __tablename__ = "object_assignments"
    __table_args__ = (
        UniqueConstraint("object_id", "user_id", name="uq_object_assignments_object_user"),
        Index("ix_object_assignments_user_object", "user_id", "object_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    object_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("objects.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    assigned_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    object: Mapped[SecurityObject] = relationship(back_populates="assignments")
    user: Mapped[User] = relationship(foreign_keys=[user_id], back_populates="object_assignments")


class ObjectSecurityDetails(Base):
    __tablename__ = "object_security_details"
    __table_args__ = (
        CheckConstraint(
            "security_requirements IS NULL OR length(trim(security_requirements)) > 0",
            name="ck_object_security_requirements_nonblank",
        ),
        CheckConstraint(
            "access_information IS NULL OR length(trim(access_information)) > 0",
            name="ck_object_access_information_nonblank",
        ),
    )

    object_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("objects.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    security_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_information: Mapped[str | None] = mapped_column(Text, nullable=True)
    emergency_contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    object: Mapped[SecurityObject] = relationship(back_populates="security_details")


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint(
            "employment_status IN ('active', 'inactive', 'leave', 'terminated')",
            name="ck_employees_employment_status",
        ),
        CheckConstraint("length(trim(employee_number)) > 0", name="ck_employees_number"),
        CheckConstraint("length(trim(full_name)) > 0", name="ck_employees_full_name"),
        CheckConstraint(
            "weekly_hours IS NULL OR (weekly_hours > 0 AND weekly_hours <= 168)",
            name="ck_employees_weekly_hours",
        ),
        CheckConstraint(
            "ended_on IS NULL OR ended_on >= hired_on",
            name="ck_employees_end_date",
        ),
        Index("ix_employees_status_name", "employment_status", "full_name"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    employee_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), unique=True, nullable=True
    )
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    employment_status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    hired_on: Mapped[date] = mapped_column(nullable=False)
    ended_on: Mapped[date | None] = mapped_column(nullable=True)
    contract_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    weekly_hours: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    user: Mapped[User | None] = relationship(back_populates="employee_record")
    qualifications: Mapped[list["EmployeeQualification"]] = relationship(back_populates="employee")
    absences: Mapped[list["EmployeeAbsence"]] = relationship(back_populates="employee")
    availability_windows: Mapped[list["EmployeeAvailabilityWindow"]] = relationship(
        back_populates="employee"
    )
    schedule_requests: Mapped[list["ScheduleAvailabilityRequest"]] = relationship(
        back_populates="employee"
    )
    history: Mapped[list["EmployeeHistory"]] = relationship(back_populates="employee")
    sensitive_details: Mapped["EmployeeSensitiveDetails | None"] = relationship(
        back_populates="employee", uselist=False
    )
    object_assignment_history: Mapped[list["EmployeeObjectAssignmentHistory"]] = relationship(
        back_populates="employee"
    )

    @property
    def assigned_objects(self) -> list[str]:
        if self.user is None:
            return []
        return [
            f"{assignment.object.name} ({assignment.object.code})"
            for assignment in sorted(
                self.user.object_assignments,
                key=lambda item: (item.object.name, item.object.code),
            )
        ]


class EmployeeQualification(Base):
    __tablename__ = "employee_qualifications"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_employee_qualifications_name"),
        CheckConstraint(
            "expires_on IS NULL OR valid_from IS NULL OR expires_on >= valid_from",
            name="ck_employee_qualifications_dates",
        ),
        Index("ix_employee_qualifications_expiry", "expires_on", "archived_at"),
        Index("ix_employee_qualifications_employee", "employee_id", "expires_on"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    employee_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(160), nullable=True)
    valid_from: Mapped[date | None] = mapped_column(nullable=True)
    expires_on: Mapped[date | None] = mapped_column(nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    employee: Mapped[Employee] = relationship(back_populates="qualifications")
    documents: Mapped[list["EmployeeQualificationDocument"]] = relationship(
        back_populates="qualification"
    )


class EmployeeQualificationDocument(Base):
    __tablename__ = "employee_qualification_documents"
    __table_args__ = (
        UniqueConstraint(
            "qualification_id", "version", name="uq_employee_qualification_documents_version"
        ),
        CheckConstraint("version > 0", name="ck_employee_qualification_documents_version"),
        CheckConstraint(
            "size_bytes > 0 AND size_bytes <= 10485760",
            name="ck_employee_qualification_documents_size",
        ),
        CheckConstraint(
            "media_type IN ('application/pdf', 'image/jpeg', 'image/png')",
            name="ck_employee_qualification_documents_media_type",
        ),
        CheckConstraint(
            "length(trim(file_name)) > 0",
            name="ck_employee_qualification_documents_name",
        ),
        CheckConstraint(
            "(storage_key IS NULL AND content IS NOT NULL) OR "
            "(storage_key IS NOT NULL AND content IS NULL)",
            name="ck_employee_qualification_documents_storage",
        ),
        UniqueConstraint("storage_key", name="uq_employee_qualification_documents_storage_key"),
        Index(
            "ix_employee_qualification_documents_qualification_created",
            "qualification_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    qualification_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("employee_qualifications.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(nullable=False)
    file_name: Mapped[str] = mapped_column(String(200), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    uploaded_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    qualification: Mapped[EmployeeQualification] = relationship(back_populates="documents")


class EmployeeObjectAssignmentHistory(Base):
    __tablename__ = "employee_object_assignment_history"
    __table_args__ = (
        Index(
            "ix_employee_object_assignment_history_employee_created",
            "employee_id",
            "created_at",
        ),
        Index(
            "ix_employee_object_assignment_history_object_created",
            "object_id",
            "created_at",
        ),
        CheckConstraint(
            "action IN ('assigned', 'ended')", name="ck_employee_object_assignment_action"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    employee_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    object_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("objects.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    employee: Mapped[Employee] = relationship(back_populates="object_assignment_history")


class PhysicalKey(Base):
    __tablename__ = "physical_keys"
    __table_args__ = (
        CheckConstraint(
            "status IN ('available', 'issued', 'lost', 'defective', 'archived')",
            name="ck_physical_keys_status",
        ),
        CheckConstraint("length(trim(key_number)) > 0", name="ck_physical_keys_number"),
        CheckConstraint("length(trim(description)) > 0", name="ck_physical_keys_description"),
        CheckConstraint(
            "(status = 'issued' AND current_employee_id IS NOT NULL) "
            "OR (status != 'issued' AND current_employee_id IS NULL)",
            name="ck_physical_keys_holder_status",
        ),
        CheckConstraint(
            "(status = 'archived' AND archived_at IS NOT NULL) "
            "OR (status != 'archived' AND archived_at IS NULL)",
            name="ck_physical_keys_archived_at",
        ),
        Index("ix_physical_keys_object_status", "object_id", "status", "archived_at"),
        Index("ix_physical_keys_holder_status", "current_employee_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    key_number: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    object_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("objects.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="available", server_default=text("'available'"), nullable=False
    )
    current_employee_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=True
    )
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    object: Mapped[SecurityObject] = relationship()
    current_employee: Mapped[Employee | None] = relationship(foreign_keys=[current_employee_id])
    movements: Mapped[list["KeyMovement"]] = relationship(
        back_populates="key", order_by="KeyMovement.created_at"
    )


class KeyMovement(Base):
    __tablename__ = "key_movements"
    __table_args__ = (
        CheckConstraint(
            "movement_type IN ('issued', 'returned', 'lost', 'defective', 'inventory')",
            name="ck_key_movements_type",
        ),
        CheckConstraint(
            "key_status_after IN ('available', 'issued', 'lost', 'defective')",
            name="ck_key_movements_status_after",
        ),
        CheckConstraint(
            "movement_type != 'issued' OR "
            "(employee_id IS NOT NULL AND acknowledged_at IS NOT NULL)",
            name="ck_key_movements_issue_acknowledged",
        ),
        CheckConstraint(
            "(movement_type = 'issued' AND key_status_after = 'issued') "
            "OR (movement_type = 'returned' AND key_status_after = 'available') "
            "OR (movement_type = 'lost' AND key_status_after = 'lost') "
            "OR (movement_type = 'defective' AND key_status_after = 'defective') "
            "OR (movement_type = 'inventory' AND key_status_after IN "
            "('available', 'issued'))",
            name="ck_key_movements_type_status",
        ),
        Index("ix_key_movements_key_created", "key_id", "created_at"),
        Index("ix_key_movements_object_created", "object_id", "created_at"),
        Index("ix_key_movements_employee_created", "employee_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    key_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("physical_keys.id", ondelete="RESTRICT"), nullable=False
    )
    object_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("objects.id", ondelete="RESTRICT"), nullable=False
    )
    employee_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=True
    )
    actor_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    movement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    key_status_after: Mapped[str] = mapped_column(String(20), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledgement_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    key: Mapped[PhysicalKey] = relationship(back_populates="movements")
    employee: Mapped[Employee | None] = relationship()
    actor: Mapped[User] = relationship()


class InventoryAsset(Base):
    __tablename__ = "inventory_assets"
    __table_args__ = (
        CheckConstraint(
            "category IN ('access_media', 'radio', 'smartphone', 'tablet', 'computer', "
            "'clothing', 'safety_equipment', 'vehicle', 'other')",
            name="ck_inventory_assets_category",
        ),
        CheckConstraint(
            "condition IN ('new', 'good', 'used', 'worn', 'defective')",
            name="ck_inventory_assets_condition",
        ),
        CheckConstraint(
            "status IN ('available', 'issued', 'maintenance', 'lost', 'damaged', 'archived')",
            name="ck_inventory_assets_status",
        ),
        CheckConstraint("length(trim(asset_number)) > 0", name="ck_inventory_assets_number"),
        CheckConstraint("length(trim(name)) > 0", name="ck_inventory_assets_name"),
        CheckConstraint("length(trim(location)) > 0", name="ck_inventory_assets_location"),
        CheckConstraint(
            "serial_number IS NULL OR length(trim(serial_number)) > 0",
            name="ck_inventory_assets_serial",
        ),
        CheckConstraint(
            "(status = 'issued' AND current_employee_id IS NOT NULL) "
            "OR (status != 'issued' AND current_employee_id IS NULL)",
            name="ck_inventory_assets_holder_status",
        ),
        CheckConstraint(
            "(status = 'archived' AND archived_at IS NOT NULL) "
            "OR (status != 'archived' AND archived_at IS NULL)",
            name="ck_inventory_assets_archived_at",
        ),
        Index("ix_inventory_assets_object_status", "object_id", "status", "archived_at"),
        Index("ix_inventory_assets_holder_status", "current_employee_id", "status"),
        Index("ix_inventory_assets_category_condition", "category", "condition"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    asset_number: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    condition: Mapped[str] = mapped_column(
        String(20), default="good", server_default=text("'good'"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="available", server_default=text("'available'"), nullable=False
    )
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    object_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("objects.id", ondelete="RESTRICT"), nullable=True
    )
    current_employee_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=True
    )
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    object: Mapped[SecurityObject | None] = relationship()
    current_employee: Mapped[Employee | None] = relationship(foreign_keys=[current_employee_id])
    events: Mapped[list["InventoryEvent"]] = relationship(
        back_populates="asset", order_by="InventoryEvent.created_at"
    )


class InventoryEvent(Base):
    __tablename__ = "inventory_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('created', 'updated', 'issued', 'returned', 'transferred', 'lost', "
            "'damaged', 'maintenance', 'repair', 'archived')",
            name="ck_inventory_events_type",
        ),
        CheckConstraint(
            "status_after IN ('available', 'issued', 'maintenance', 'lost', 'damaged', 'archived')",
            name="ck_inventory_events_status",
        ),
        CheckConstraint(
            "condition_after IN ('new', 'good', 'used', 'worn', 'defective')",
            name="ck_inventory_events_condition",
        ),
        CheckConstraint(
            "event_type != 'issued' OR "
            "(to_employee_id IS NOT NULL AND acknowledged_at IS NOT NULL)",
            name="ck_inventory_events_issue_acknowledged",
        ),
        CheckConstraint(
            "event_type != 'transferred' OR "
            "(from_employee_id IS NOT NULL AND to_employee_id IS NOT NULL "
            "AND acknowledged_at IS NOT NULL)",
            name="ck_inventory_events_transfer_acknowledged",
        ),
        CheckConstraint(
            "(event_type = 'created' AND status_after = 'available') "
            "OR (event_type = 'updated' AND status_after IN "
            "('available', 'issued', 'maintenance', 'lost', 'damaged', 'archived')) "
            "OR (event_type = 'issued' AND status_after = 'issued') "
            "OR (event_type = 'returned' AND status_after = 'available') "
            "OR (event_type = 'transferred' AND status_after = 'issued') "
            "OR (event_type = 'lost' AND status_after = 'lost') "
            "OR (event_type = 'damaged' AND status_after = 'damaged') "
            "OR (event_type = 'maintenance' AND status_after = 'maintenance') "
            "OR (event_type = 'repair' AND status_after = 'available') "
            "OR (event_type = 'archived' AND status_after = 'archived')",
            name="ck_inventory_events_type_status",
        ),
        CheckConstraint("length(trim(location_after)) > 0", name="ck_inventory_events_location"),
        Index("ix_inventory_events_asset_created", "asset_id", "created_at"),
        Index("ix_inventory_events_object_created", "object_id", "created_at"),
        Index(
            "ix_inventory_events_employee_created",
            "from_employee_id",
            "to_employee_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("inventory_assets.id", ondelete="RESTRICT"), nullable=False
    )
    object_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("objects.id", ondelete="RESTRICT"), nullable=True
    )
    from_object_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("objects.id", ondelete="RESTRICT"), nullable=True
    )
    to_object_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("objects.id", ondelete="RESTRICT"), nullable=True
    )
    from_employee_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=True
    )
    to_employee_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=True
    )
    actor_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status_after: Mapped[str] = mapped_column(String(20), nullable=False)
    condition_after: Mapped[str] = mapped_column(String(20), nullable=False)
    location_after: Mapped[str] = mapped_column(String(200), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledgement_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    asset: Mapped[InventoryAsset] = relationship(back_populates="events")
    object: Mapped[SecurityObject | None] = relationship(foreign_keys=[object_id])
    from_object: Mapped[SecurityObject | None] = relationship(foreign_keys=[from_object_id])
    to_object: Mapped[SecurityObject | None] = relationship(foreign_keys=[to_object_id])
    from_employee: Mapped[Employee | None] = relationship(foreign_keys=[from_employee_id])
    to_employee: Mapped[Employee | None] = relationship(foreign_keys=[to_employee_id])
    actor: Mapped[User] = relationship()


class EmployeeAbsence(Base):
    __tablename__ = "employee_absences"
    __table_args__ = (
        CheckConstraint(
            "absence_type IN ('vacation', 'sick_leave', 'other')",
            name="ck_employee_absences_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'withdrawn')",
            name="ck_employee_absences_status",
        ),
        CheckConstraint("ends_on >= starts_on", name="ck_employee_absences_dates"),
        Index("ix_employee_absences_employee_dates", "employee_id", "starts_on", "ends_on"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    employee_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    absence_type: Mapped[str] = mapped_column(String(20), nullable=False)
    starts_on: Mapped[date] = mapped_column(nullable=False)
    ends_on: Mapped[date] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    employee: Mapped[Employee] = relationship(back_populates="absences")


class EmployeeSensitiveDetails(Base):
    __tablename__ = "employee_sensitive_details"
    __table_args__ = (
        CheckConstraint(
            "address IS NULL OR length(trim(address)) > 0",
            name="ck_employee_sensitive_address",
        ),
        CheckConstraint(
            "emergency_contact IS NULL OR length(trim(emergency_contact)) > 0",
            name="ck_employee_sensitive_emergency_contact",
        ),
    )

    employee_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("employees.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    emergency_contact: Mapped[str | None] = mapped_column(String(300), nullable=True)
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    employee: Mapped[Employee] = relationship(back_populates="sensitive_details")


class EmployeeHistory(Base):
    __tablename__ = "employee_history"
    __table_args__ = (Index("ix_employee_history_employee_created", "employee_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    employee_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    changed_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    employee: Mapped[Employee] = relationship(back_populates="history")


class ScheduleSettings(Base):
    __tablename__ = "schedule_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_schedule_settings_singleton"),
        CheckConstraint(
            "minimum_rest_hours >= 0 AND minimum_rest_hours <= 168",
            name="ck_schedule_settings_rest_hours",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    time_zone: Mapped[str] = mapped_column(String(80), nullable=False, default="Europe/Berlin")
    minimum_rest_hours: Mapped[int] = mapped_column(default=11, nullable=False)
    updated_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class EmployeeAvailabilityWindow(Base):
    __tablename__ = "employee_availability_windows"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_employee_availability_weekday"),
        CheckConstraint(
            "ends_at > starts_at",
            name="ck_employee_availability_window_time_order",
        ),
        Index(
            "ix_employee_availability_windows_employee_weekday",
            "employee_id",
            "weekday",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    employee_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    weekday: Mapped[int] = mapped_column(nullable=False)
    starts_at: Mapped[time] = mapped_column(nullable=False)
    ends_at: Mapped[time] = mapped_column(nullable=False)
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    employee: Mapped[Employee] = relationship(back_populates="availability_windows")


class ScheduleAvailabilityRequest(Base):
    __tablename__ = "schedule_availability_requests"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('preferred', 'blocked')",
            name="ck_schedule_availability_requests_kind",
        ),
        CheckConstraint(
            "status IN ('open', 'accepted', 'rejected', 'withdrawn')",
            name="ck_schedule_availability_requests_status",
        ),
        CheckConstraint(
            "ends_at > starts_at",
            name="ck_schedule_availability_requests_time_order",
        ),
        Index(
            "ix_schedule_availability_requests_employee_time",
            "employee_id",
            "starts_at",
            "ends_at",
        ),
        Index(
            "ix_schedule_availability_requests_status_time",
            "status",
            "starts_at",
            "ends_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    employee_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    employee: Mapped[Employee] = relationship(back_populates="schedule_requests")


class ScheduleShift(Base):
    __tablename__ = "schedule_shifts"
    __table_args__ = (
        CheckConstraint(
            "ends_at > starts_at",
            name="ck_schedule_shifts_time_order",
        ),
        CheckConstraint(
            "break_minutes >= 0",
            name="ck_schedule_shifts_break_minutes",
        ),
        CheckConstraint(
            "status IN ('draft', 'published', 'cancelled')",
            name="ck_schedule_shifts_status",
        ),
        Index("ix_schedule_shifts_employee_time", "employee_id", "starts_at", "ends_at"),
        Index("ix_schedule_shifts_object_time", "object_id", "starts_at", "ends_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    employee_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    object_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("objects.id", ondelete="RESTRICT"), nullable=False
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    break_minutes: Mapped[int] = mapped_column(default=0, nullable=False)
    required_qualification: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    employee: Mapped[Employee] = relationship()
    object: Mapped[SecurityObject] = relationship()
    history: Mapped[list["ScheduleShiftHistory"]] = relationship(
        back_populates="shift", cascade="all, delete-orphan"
    )


class ScheduleShiftHistory(Base):
    __tablename__ = "schedule_shift_history"
    __table_args__ = (Index("ix_schedule_shift_history_shift_created", "shift_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    shift_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("schedule_shifts.id", ondelete="RESTRICT"), nullable=False
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    changed_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    shift: Mapped[ScheduleShift] = relationship(back_populates="history")


class TimeEntry(Base):
    __tablename__ = "time_entries"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'submitted', 'approved', 'rejected', "
            "'correction_requested', 'locked')",
            name="ck_time_entries_status",
        ),
        CheckConstraint(
            "ended_at IS NULL OR ended_at > started_at",
            name="ck_time_entries_time_order",
        ),
        UniqueConstraint("employee_id", "shift_id", name="uq_time_entries_employee_shift"),
        Index("ix_time_entries_employee_start", "employee_id", "started_at"),
        Index("ix_time_entries_object_start", "object_id", "started_at"),
        Index("ix_time_entries_status_start", "status", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    employee_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    object_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("objects.id", ondelete="RESTRICT"), nullable=False
    )
    shift_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("schedule_shifts.id", ondelete="RESTRICT"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="open", nullable=False)
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    employee: Mapped[Employee] = relationship()
    object: Mapped[SecurityObject] = relationship()
    shift: Mapped[ScheduleShift | None] = relationship()
    segments: Mapped[list["TimeEntrySegment"]] = relationship(
        back_populates="entry", cascade="all, delete-orphan", order_by="TimeEntrySegment.position"
    )
    corrections: Mapped[list["TimeEntryCorrection"]] = relationship(
        back_populates="entry", cascade="all, delete-orphan"
    )


class TimeEntrySegment(Base):
    __tablename__ = "time_entry_segments"
    __table_args__ = (
        CheckConstraint("kind IN ('work', 'break')", name="ck_time_entry_segments_kind"),
        CheckConstraint("position > 0", name="ck_time_entry_segments_position"),
        CheckConstraint(
            "ended_at IS NULL OR ended_at > started_at",
            name="ck_time_entry_segments_time_order",
        ),
        UniqueConstraint("entry_id", "position", name="uq_time_entry_segments_position"),
        Index("ix_time_entry_segments_entry", "entry_id", "position"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    entry_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("time_entries.id", ondelete="RESTRICT"), nullable=False
    )
    position: Mapped[int] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entry: Mapped[TimeEntry] = relationship(back_populates="segments")


class TimeEntryCorrection(Base):
    __tablename__ = "time_entry_corrections"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_time_entry_corrections_status",
        ),
        CheckConstraint(
            "length(trim(reason)) > 0",
            name="ck_time_entry_corrections_reason",
        ),
        Index("ix_time_entry_corrections_entry_created", "entry_id", "requested_at"),
        Index(
            "uq_time_entry_corrections_pending",
            "entry_id",
            unique=True,
            sqlite_where=text("status = 'pending'"),
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    entry_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("time_entries.id", ondelete="RESTRICT"), nullable=False
    )
    requested_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    previous_status: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entry: Mapped[TimeEntry] = relationship(back_populates="corrections")
    segments: Mapped[list["TimeEntryCorrectionSegment"]] = relationship(
        back_populates="correction",
        cascade="all, delete-orphan",
        order_by="TimeEntryCorrectionSegment.position",
    )


class TimeEntryCorrectionSegment(Base):
    __tablename__ = "time_entry_correction_segments"
    __table_args__ = (
        CheckConstraint("kind IN ('work', 'break')", name="ck_time_entry_correction_segments_kind"),
        CheckConstraint("position > 0", name="ck_time_entry_correction_segments_position"),
        CheckConstraint(
            "ended_at > started_at",
            name="ck_time_entry_correction_segments_time_order",
        ),
        UniqueConstraint("correction_id", "position", name="uq_time_entry_correction_segments_pos"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    correction_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("time_entry_corrections.id", ondelete="RESTRICT"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    correction: Mapped[TimeEntryCorrection] = relationship(back_populates="segments")


class TimeEntryHistory(Base):
    __tablename__ = "time_entry_history"
    __table_args__ = (Index("ix_time_entry_history_entry_created", "entry_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    entry_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("time_entries.id", ondelete="RESTRICT"), nullable=False
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class TimeTrackingSettings(Base):
    __tablename__ = "time_tracking_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_time_tracking_settings_singleton"),
        CheckConstraint(
            "federal_state IS NULL OR federal_state IN "
            "('BW', 'BY', 'BE', 'BB', 'HB', 'HH', 'HE', 'MV', 'NI', 'NW', 'RP', 'SL', 'SN', 'ST', 'SH', 'TH')",
            name="ck_time_tracking_settings_federal_state",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    federal_state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    updated_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class TimeSurchargeRule(Base):
    __tablename__ = "time_surcharge_rules"
    __table_args__ = (
        CheckConstraint(
            "category IN ('night', 'saturday', 'sunday', 'public_holiday', 'business')",
            name="ck_time_surcharge_rules_category",
        ),
        CheckConstraint(
            "calculation_type IN ('percentage', 'fixed')",
            name="ck_time_surcharge_rules_calculation_type",
        ),
        CheckConstraint("value > 0", name="ck_time_surcharge_rules_value"),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="ck_time_surcharge_rules_validity",
        ),
        CheckConstraint(
            "combination_mode IN ('exclusive', 'combine')",
            name="ck_time_surcharge_rules_combination",
        ),
        UniqueConstraint("code", name="uq_time_surcharge_rules_code"),
        Index("ix_time_surcharge_rules_validity", "valid_from", "valid_to"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    calculation_type: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    basis_description: Mapped[str] = mapped_column(String(240), nullable=False)
    valid_from: Mapped[date] = mapped_column(nullable=False)
    valid_to: Mapped[date | None] = mapped_column(nullable=True)
    priority: Mapped[int] = mapped_column(nullable=False, default=100)
    combination_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="exclusive")
    weekdays: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    starts_local: Mapped[str | None] = mapped_column(String(5), nullable=True)
    ends_local: Mapped[str | None] = mapped_column(String(5), nullable=True)
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class TimeSurchargeCalculation(Base):
    __tablename__ = "time_surcharge_calculations"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_time_surcharge_calculations_version"),
        CheckConstraint(
            "length(gross_work_seconds) > 0",
            name="ck_time_surcharge_calculations_work_seconds",
        ),
        UniqueConstraint("entry_id", "version", name="uq_time_surcharge_calculations_version"),
        Index("ix_time_surcharge_calculations_entry_created", "entry_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    entry_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("time_entries.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False)
    gross_work_seconds: Mapped[str] = mapped_column(String(32), nullable=False)
    time_zone: Mapped[str] = mapped_column(String(80), nullable=False)
    federal_state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    rule_snapshot: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    allocation_snapshot: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    source_segments: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False)
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class TimeTrackingPeriod(Base):
    __tablename__ = "time_tracking_periods"
    __table_args__ = (
        CheckConstraint("to_date >= from_date", name="ck_time_tracking_periods_date_order"),
        UniqueConstraint("from_date", "to_date", name="uq_time_tracking_periods_range"),
        Index("ix_time_tracking_periods_range", "from_date", "to_date"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    from_date: Mapped[date] = mapped_column(nullable=False)
    to_date: Mapped[date] = mapped_column(nullable=False)
    time_zone: Mapped[str] = mapped_column(String(80), nullable=False)
    federal_state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    locked_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    locked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'active', 'expired', 'archived')",
            name="ck_documents_status",
        ),
        CheckConstraint("length(trim(title)) > 0", name="ck_documents_title"),
        Index("ix_documents_status_expiry", "status", "expires_on"),
        Index("ix_documents_customer", "customer_id", "archived_at"),
        Index("ix_documents_object", "object_id", "archived_at"),
        Index("ix_documents_employee", "employee_id", "archived_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    document_number: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    customer_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=True
    )
    object_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("objects.id", ondelete="RESTRICT"), nullable=True
    )
    employee_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=True
    )
    expires_on: Mapped[date | None] = mapped_column(nullable=True)
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version", name="uq_document_versions_number"),
        CheckConstraint("version > 0", name="ck_document_versions_version"),
        CheckConstraint("size_bytes > 0", name="ck_document_versions_size"),
        CheckConstraint(
            "media_type IN ('application/pdf', 'image/png', 'image/jpeg', "
            "'application/vnd.openxmlformats-officedocument.wordprocessingml.document', "
            "'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')",
            name="ck_document_versions_media_type",
        ),
        Index("ix_document_versions_document_created", "document_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False)
    storage_key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class DocumentApproval(Base):
    __tablename__ = "document_approvals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_document_approvals_status",
        ),
        Index("ix_document_approvals_version_created", "version_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("document_versions.id", ondelete="RESTRICT"), nullable=False
    )
    requested_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DocumentReadReceipt(Base):
    __tablename__ = "document_read_receipts"
    __table_args__ = (
        UniqueConstraint("version_id", "user_id", name="uq_document_read_receipt_user_version"),
        Index("ix_document_read_receipts_version_read", "version_id", "read_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("document_versions.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class DocumentHistory(Base):
    __tablename__ = "document_history"
    __table_args__ = (Index("ix_document_history_document_created", "document_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    changed_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    details: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class Contract(Base):
    __tablename__ = "contracts"
    __table_args__ = (
        CheckConstraint(
            "contract_type IN ('customer', 'object', 'personnel', 'service', 'additional', 'other')",
            name="ck_contracts_type",
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'terminated', 'expired', 'archived')",
            name="ck_contracts_status",
        ),
        CheckConstraint("ends_on IS NULL OR ends_on >= starts_on", name="ck_contracts_dates"),
        CheckConstraint(
            "notice_period_days IS NULL OR notice_period_days BETWEEN 0 AND 3650",
            name="ck_contracts_notice_period",
        ),
        CheckConstraint("length(trim(name)) > 0", name="ck_contracts_name"),
        Index("ix_contracts_status_end", "status", "ends_on"),
        Index("ix_contracts_customer", "customer_id", "archived_at"),
        Index("ix_contracts_object", "object_id", "archived_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    contract_number: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    contract_type: Mapped[str] = mapped_column(String(30), nullable=False)
    counterparty: Mapped[str] = mapped_column(String(200), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    object_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("objects.id", ondelete="RESTRICT"), nullable=True
    )
    employee_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=True
    )
    starts_on: Mapped[date] = mapped_column(nullable=False)
    ends_on: Mapped[date | None] = mapped_column(nullable=True)
    notice_period_days: Mapped[int | None] = mapped_column(nullable=True)
    renewal_rule: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    document_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class ContractHistory(Base):
    __tablename__ = "contract_history"
    __table_args__ = (Index("ix_contract_history_contract_created", "contract_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    contract_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("contracts.id", ondelete="RESTRICT"), nullable=False
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    changed_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    details: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class BillingRate(Base):
    __tablename__ = "billing_rates"
    __table_args__ = (
        CheckConstraint("kind IN ('hourly', 'flat', 'surcharge')", name="ck_billing_rates_kind"),
        CheckConstraint("unit_price >= 0", name="ck_billing_rates_unit_price"),
        CheckConstraint("tax_rate >= 0 AND tax_rate <= 100", name="ck_billing_rates_tax_rate"),
        UniqueConstraint("code", name="uq_billing_rates_code"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    tax_code: Mapped[str] = mapped_column(String(40), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class BillingInvoice(Base):
    __tablename__ = "billing_invoices"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('invoice', 'correction', 'cancellation')", name="ck_billing_invoices_kind"
        ),
        CheckConstraint(
            "(kind = 'invoice' AND correction_of_id IS NULL) OR "
            "(kind IN ('correction', 'cancellation') AND correction_of_id IS NOT NULL)",
            name="ck_billing_invoices_correction_link",
        ),
        CheckConstraint(
            "status IN ('draft', 'approved', 'archived')", name="ck_billing_invoices_status"
        ),
        CheckConstraint(
            "payment_status IN ('open', 'partial', 'paid')",
            name="ck_billing_invoices_payment_status",
        ),
        CheckConstraint(
            "dunning_status IN ('none', 'reminder_1', 'reminder_2', 'final')",
            name="ck_billing_invoices_dunning_status",
        ),
        CheckConstraint("due_on >= issued_on", name="ck_billing_invoices_due_date"),
        CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)",
            name="ck_billing_invoices_currency",
        ),
        Index("ix_billing_invoices_customer_date", "customer_id", "issued_on"),
        Index("ix_billing_invoices_status_due", "status", "payment_status", "due_on"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    invoice_number: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    customer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    contract_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("contracts.id", ondelete="RESTRICT"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="invoice")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    payment_status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    dunning_status: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    issued_on: Mapped[date] = mapped_column(nullable=False)
    due_on: Mapped[date] = mapped_column(nullable=False)
    correction_of_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("billing_invoices.id", ondelete="RESTRICT"), nullable=True
    )
    correction_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    inputs_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    lines: Mapped[list["BillingInvoiceLine"]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="BillingInvoiceLine.position",
    )


class BillingInvoiceLine(Base):
    __tablename__ = "billing_invoice_lines"
    __table_args__ = (
        CheckConstraint("position > 0", name="ck_billing_invoice_lines_position"),
        CheckConstraint(
            "tax_rate >= 0 AND tax_rate <= 100", name="ck_billing_invoice_lines_tax_rate"
        ),
        UniqueConstraint("invoice_id", "position", name="uq_billing_invoice_lines_position"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("billing_invoices.id", ondelete="RESTRICT"), nullable=False
    )
    rate_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("billing_rates.id", ondelete="SET NULL"), nullable=True
    )
    position: Mapped[int] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(String(240), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    tax_code: Mapped[str] = mapped_column(String(40), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    inputs_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    invoice: Mapped[BillingInvoice] = relationship(back_populates="lines")


class BillingPayment(Base):
    __tablename__ = "billing_payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_billing_payments_amount"),
        UniqueConstraint("invoice_id", "idempotency_key", name="uq_billing_payments_idempotency"),
        Index("ix_billing_payments_invoice_date", "invoice_id", "paid_on"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("billing_invoices.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    paid_on: Mapped[date] = mapped_column(nullable=False)
    reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class BillingExport(Base):
    __tablename__ = "billing_exports"
    __table_args__ = (
        UniqueConstraint("invoice_id", "format_version", name="uq_billing_exports_invoice_version"),
        UniqueConstraint("idempotency_key", name="uq_billing_exports_idempotency"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("billing_invoices.id", ondelete="RESTRICT"), nullable=False
    )
    format_version: Mapped[str] = mapped_column(String(30), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class DocumentContractReminderSettings(Base):
    __tablename__ = "document_contract_reminder_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_doc_contract_reminder_settings_singleton"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    lead_days: Mapped[list[int]] = mapped_column(
        JSON, nullable=False, default=lambda: [90, 60, 30, 14, 7]
    )
    updated_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class DocumentContractReminder(Base):
    __tablename__ = "document_contract_reminders"
    __table_args__ = (
        CheckConstraint(
            "(document_id IS NOT NULL AND contract_id IS NULL) OR "
            "(document_id IS NULL AND contract_id IS NOT NULL)",
            name="ck_doc_contract_reminders_single_target",
        ),
        CheckConstraint(
            "reminder_type IN ('document_expiry', 'contract_expiry', 'contract_termination', "
            "'contract_renewal')",
            name="ck_doc_contract_reminders_type",
        ),
        CheckConstraint(
            "status IN ('open', 'completed', 'dismissed')",
            name="ck_doc_contract_reminders_status",
        ),
        UniqueConstraint("deduplication_key", name="uq_doc_contract_reminders_dedupe"),
        Index("ix_doc_contract_reminders_due_status", "remind_on", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="RESTRICT"), nullable=True
    )
    contract_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("contracts.id", ondelete="RESTRICT"), nullable=True
    )
    reminder_type: Mapped[str] = mapped_column(String(30), nullable=False)
    event_on: Mapped[date] = mapped_column(nullable=False)
    remind_on: Mapped[date] = mapped_column(nullable=False)
    deduplication_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class OWKSControlPoint(Base):
    __tablename__ = "owks_control_points"
    __table_args__ = (
        CheckConstraint("identifier_type IN ('qr', 'nfc')", name="ck_owks_control_point_type"),
        CheckConstraint("length(trim(name)) > 0", name="ck_owks_control_point_name"),
        Index("ix_owks_control_points_object_active", "object_id", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    object_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("objects.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    identifier_type: Mapped[str] = mapped_column(String(10), nullable=False)
    identifier_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class OWKSRoute(Base):
    __tablename__ = "owks_routes"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_owks_route_name"),
        CheckConstraint("interval_minutes > 0", name="ck_owks_route_interval"),
        Index("ix_owks_routes_object_active", "object_id", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    object_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("objects.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    interval_minutes: Mapped[int] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class OWKSRoutePoint(Base):
    __tablename__ = "owks_route_points"
    __table_args__ = (
        UniqueConstraint("route_id", "position", name="uq_owks_route_points_position"),
        UniqueConstraint("route_id", "control_point_id", name="uq_owks_route_points_point"),
        CheckConstraint("position >= 0", name="ck_owks_route_points_position"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    route_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("owks_routes.id", ondelete="RESTRICT"), nullable=False
    )
    control_point_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("owks_control_points.id", ondelete="RESTRICT"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(nullable=False)


class OWKSChallenge(Base):
    __tablename__ = "owks_challenges"
    __table_args__ = (Index("ix_owks_challenges_expires", "expires_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    object_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("objects.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class OWKSEvent(Base):
    __tablename__ = "owks_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('entry', 'handover', 'control', 'manipulation', 'deviation', 'missed', 'notification', 'correction')",
            name="ck_owks_events_type",
        ),
        CheckConstraint(
            "severity IN ('info', 'warning', 'critical')", name="ck_owks_events_severity"
        ),
        CheckConstraint("sync_status IN ('synced', 'conflict')", name="ck_owks_events_sync_status"),
        UniqueConstraint("actor_id", "client_event_id", name="uq_owks_events_idempotency"),
        Index("ix_owks_events_object_occurred", "object_id", "occurred_at"),
        Index("ix_owks_events_object_created", "object_id", "created_at"),
        Index(
            "uq_owks_missed_event_client_id",
            "client_event_id",
            unique=True,
            postgresql_where=text("event_type = 'missed'"),
            sqlite_where=text("event_type = 'missed'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    object_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("objects.id", ondelete="RESTRICT"), nullable=False
    )
    route_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("owks_routes.id", ondelete="RESTRICT"), nullable=True
    )
    control_point_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("owks_control_points.id", ondelete="RESTRICT"), nullable=True
    )
    corrects_event_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("owks_events.id", ondelete="RESTRICT"), nullable=True
    )
    employee_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=True
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    challenge_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("owks_challenges.id", ondelete="RESTRICT"), nullable=True
    )
    client_event_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="info", nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sync_status: Mapped[str] = mapped_column(String(20), default="synced", nullable=False)
    presence_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class OWKSEventStatus(Base):
    __tablename__ = "owks_event_statuses"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'in_progress', 'resolved')", name="ck_owks_event_status"
        ),
        CheckConstraint("sequence_no > 0", name="ck_owks_event_status_sequence"),
        UniqueConstraint("event_id", "sequence_no", name="uq_owks_event_status_sequence"),
        Index("ix_owks_event_statuses_event_created", "event_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("owks_events.id", ondelete="RESTRICT"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    actor_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class OWKSAttachment(Base):
    __tablename__ = "owks_attachments"
    __table_args__ = (
        CheckConstraint(
            "media_type IN ('application/pdf', 'image/jpeg', 'image/png')",
            name="ck_owks_attachments_media_type",
        ),
        CheckConstraint(
            "size_bytes > 0 AND size_bytes <= 10485760", name="ck_owks_attachments_size"
        ),
        CheckConstraint(
            "(storage_key IS NULL AND content IS NOT NULL) OR "
            "(storage_key IS NOT NULL AND content IS NULL)",
            name="ck_owks_attachments_storage",
        ),
        UniqueConstraint("storage_key", name="uq_owks_attachments_storage_key"),
        Index("ix_owks_attachments_event_created", "event_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("owks_events.id", ondelete="RESTRICT"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(200), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    uploaded_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint(
            "incident_type IN ('incident', 'accident', 'assault', 'property_damage', 'complaint', 'other')",
            name="ck_incidents_type",
        ),
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')", name="ck_incidents_severity"
        ),
        CheckConstraint(
            "status IN ('reported', 'investigating', 'action_required', 'closed')",
            name="ck_incidents_status",
        ),
        CheckConstraint("length(trim(title)) > 0", name="ck_incidents_title"),
        CheckConstraint("length(trim(report)) > 0", name="ck_incidents_report"),
        Index("ix_incidents_object_status_due", "object_id", "status", "due_at"),
        Index("ix_incidents_assignee_status", "assigned_to_id", "status"),
        Index(
            "uq_incidents_owks_event_id",
            "owks_event_id",
            unique=True,
            postgresql_where=text("owks_event_id IS NOT NULL"),
            sqlite_where=text("owks_event_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    report: Mapped[str] = mapped_column(Text, nullable=False)
    incident_type: Mapped[str] = mapped_column(String(30), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    object_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("objects.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), default="reported", server_default=text("'reported'"), nullable=False
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_to_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    owks_event_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("owks_events.id", ondelete="RESTRICT"), nullable=True
    )
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    object: Mapped[SecurityObject] = relationship()
    assignee: Mapped[User] = relationship(foreign_keys=[assigned_to_id])
    creator: Mapped[User | None] = relationship(foreign_keys=[created_by_id])


class IncidentSensitiveDetails(Base):
    __tablename__ = "incident_sensitive_details"

    incident_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("incidents.id", ondelete="RESTRICT"), primary_key=True
    )
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    closure_report: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class IncidentMeasure(Base):
    __tablename__ = "incident_measures"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'in_progress', 'completed')", name="ck_incident_measures_status"
        ),
        CheckConstraint("length(trim(title)) > 0", name="ck_incident_measures_title"),
        Index("ix_incident_measures_incident_status_due", "incident_id", "status", "due_at"),
        Index("ix_incident_measures_assignee_status", "assigned_to_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("incidents.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_to_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="open", server_default=text("'open'"), nullable=False
    )
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class IncidentPerson(Base):
    __tablename__ = "incident_people"
    __table_args__ = (
        CheckConstraint("role IN ('involved', 'witness')", name="ck_incident_people_role"),
        CheckConstraint("length(trim(name)) > 0", name="ck_incident_people_name"),
        Index("ix_incident_people_incident_created", "incident_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("incidents.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class IncidentAttachment(Base):
    __tablename__ = "incident_attachments"
    __table_args__ = (
        CheckConstraint(
            "media_type IN ('application/pdf', 'image/png', 'image/jpeg')",
            name="ck_incident_attachments_media_type",
        ),
        CheckConstraint(
            "size_bytes > 0 AND size_bytes <= 10485760", name="ck_incident_attachments_size"
        ),
        Index("ix_incident_attachments_incident_created", "incident_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("incidents.id", ondelete="RESTRICT"), nullable=False
    )
    storage_key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class IncidentHistory(Base):
    __tablename__ = "incident_history"
    __table_args__ = (Index("ix_incident_history_incident_created", "incident_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("incidents.id", ondelete="RESTRICT"), nullable=False
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    changes: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
