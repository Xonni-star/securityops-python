from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, sessionmaker

from app.auth import require_permission
from app.config import get_settings
from app.database import SessionLocal, get_db
from app.models import NotificationOutbox, NotificationWorkerHeartbeat

WORKER_NAME = "notification-outbox"
HEARTBEAT_INTERVAL_SECONDS = 30
HEARTBEAT_STALE_SECONDS = 90
MONITORING_PERMISSION = "system.monitoring.read"

router = APIRouter()


class WorkerStatus(BaseModel):
    status: Literal["healthy", "stale", "unknown"]
    last_heartbeat_at: datetime | None
    heartbeat_age_seconds: int | None
    stale_after_seconds: int


class OutboxMetrics(BaseModel):
    pending: int
    processing: int
    completed: int
    failed: int
    dead_letter: int
    stale_processing: int
    oldest_pending_at: datetime | None
    oldest_dead_letter_at: datetime | None


class NotificationMonitoringRead(BaseModel):
    status: Literal["healthy", "degraded", "unknown"]
    worker: WorkerStatus
    outbox: OutboxMetrics


def write_worker_heartbeat(
    session_factory: sessionmaker[Session] = SessionLocal,
) -> None:
    now = datetime.now(UTC)
    with session_factory() as db:
        statement_factory = {
            "postgresql": postgresql_insert,
            "sqlite": sqlite_insert,
        }.get(db.bind.dialect.name)
        if statement_factory is None:
            raise RuntimeError("Unsupported database dialect")
        db.execute(
            statement_factory(NotificationWorkerHeartbeat)
            .values(worker_name=WORKER_NAME, heartbeat_at=now)
            .on_conflict_do_update(
                index_elements=[NotificationWorkerHeartbeat.worker_name],
                set_={"heartbeat_at": now},
            )
        )
        db.commit()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def get_notification_monitoring(
    db: Session, *, now: datetime | None = None
) -> NotificationMonitoringRead:
    current_time = now or datetime.now(UTC)
    heartbeat_at = db.scalar(
        select(NotificationWorkerHeartbeat.heartbeat_at).where(
            NotificationWorkerHeartbeat.worker_name == WORKER_NAME
        )
    )
    if heartbeat_at is None:
        worker_status: Literal["healthy", "stale", "unknown"] = "unknown"
        heartbeat_age_seconds = None
    else:
        heartbeat_age_seconds = max(0, int((current_time - _as_utc(heartbeat_at)).total_seconds()))
        worker_status = "healthy" if heartbeat_age_seconds <= HEARTBEAT_STALE_SECONDS else "stale"

    grouped_counts = db.execute(
        select(NotificationOutbox.status, func.count()).group_by(NotificationOutbox.status)
    ).all()
    counts = {status: count for status, count in grouped_counts}
    stale_processing_before = current_time - timedelta(
        seconds=get_settings().notification_worker_lease_seconds
    )
    stale_processing = db.scalar(
        select(func.count())
        .select_from(NotificationOutbox)
        .where(
            NotificationOutbox.status == "processing",
            or_(
                NotificationOutbox.locked_at.is_(None),
                NotificationOutbox.locked_at <= stale_processing_before,
            ),
        )
    )
    oldest_pending_at = db.scalar(
        select(func.min(NotificationOutbox.created_at)).where(
            NotificationOutbox.status == "pending"
        )
    )
    oldest_dead_letter_at = db.scalar(
        select(func.min(NotificationOutbox.created_at)).where(
            NotificationOutbox.status == "dead_letter"
        )
    )
    outbox = OutboxMetrics(
        pending=counts.get("pending", 0),
        processing=counts.get("processing", 0),
        completed=counts.get("completed", 0),
        failed=counts.get("failed", 0),
        dead_letter=counts.get("dead_letter", 0),
        stale_processing=stale_processing or 0,
        oldest_pending_at=oldest_pending_at,
        oldest_dead_letter_at=oldest_dead_letter_at,
    )
    if worker_status == "unknown":
        overall_status: Literal["healthy", "degraded", "unknown"] = "unknown"
    elif worker_status == "stale" or outbox.failed or outbox.dead_letter or outbox.stale_processing:
        overall_status = "degraded"
    else:
        overall_status = "healthy"

    return NotificationMonitoringRead(
        status=overall_status,
        worker=WorkerStatus(
            status=worker_status,
            last_heartbeat_at=heartbeat_at,
            heartbeat_age_seconds=heartbeat_age_seconds,
            stale_after_seconds=HEARTBEAT_STALE_SECONDS,
        ),
        outbox=outbox,
    )


@router.get(
    "/monitoring/notifications",
    response_model=NotificationMonitoringRead,
    tags=["Monitoring"],
)
def notification_monitoring(
    response: Response,
    db: Session = Depends(get_db),
    _principal=Depends(require_permission(MONITORING_PERMISSION)),
) -> NotificationMonitoringRead:
    response.headers["Cache-Control"] = "no-store"
    return get_notification_monitoring(db)
