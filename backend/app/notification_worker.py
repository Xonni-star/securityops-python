import argparse
import asyncio
import json
import logging
import re
import signal
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.database import SessionLocal, engine
from app.models import (
    AutomationRule,
    AutomationRun,
    Notification,
    NotificationOutbox,
    NotificationOutboxAttempt,
)
from app.owks_scheduler import run_monitoring_scheduler

logger = logging.getLogger("app.notification_worker")

TASK_EVENTS = {"task.assigned", "task.status_changed"}
SUPPORTED_EVENTS = TASK_EVENTS | {"automation.notification"}
TASK_STATUSES = {"open", "in_progress", "blocked", "completed", "cancelled"}
BASE_RETRY_SECONDS = 5
MAX_RETRY_SECONDS = 60 * 60


@dataclass(frozen=True)
class ClaimedEvent:
    event_id: UUID
    lock_token: UUID


@dataclass(frozen=True)
class CycleResult:
    claimed: int = 0
    delivered: int = 0
    retried: int = 0
    dead_lettered: int = 0


class InvalidOutboxEvent(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class NotificationOutboxWorker:
    def __init__(
        self,
        session_factory: sessionmaker[Session] = SessionLocal,
        *,
        batch_size: int | None = None,
        lease_seconds: int | None = None,
        max_attempts: int | None = None,
    ) -> None:
        settings = get_settings()
        self.session_factory = session_factory
        self.batch_size = batch_size or settings.notification_worker_batch_size
        self.lease_seconds = lease_seconds or settings.notification_worker_lease_seconds
        self.max_attempts = max_attempts or settings.notification_worker_max_attempts

    def run_once(self) -> CycleResult:
        claimed = self._claim_batch()
        delivered = retried = dead_lettered = 0
        for event in claimed:
            outcome = self._process_claim(event)
            if outcome == "succeeded":
                delivered += 1
            elif outcome == "retry_scheduled":
                retried += 1
            elif outcome == "dead_lettered":
                dead_lettered += 1
        return CycleResult(len(claimed), delivered, retried, dead_lettered)

    def _claim_batch(self) -> list[ClaimedEvent]:
        now = datetime.now(UTC)
        expired_before = now - timedelta(seconds=self.lease_seconds)
        with self.session_factory() as db:
            rows = db.scalars(
                select(NotificationOutbox)
                .where(
                    or_(
                        (
                            (NotificationOutbox.status == "pending")
                            & (NotificationOutbox.available_at <= now)
                        ),
                        (
                            (NotificationOutbox.status == "processing")
                            & or_(
                                NotificationOutbox.locked_at.is_(None),
                                NotificationOutbox.locked_at <= expired_before,
                            )
                        ),
                    )
                )
                .order_by(NotificationOutbox.available_at, NotificationOutbox.created_at)
                .limit(self.batch_size)
                .with_for_update(skip_locked=True)
            ).all()
            claimed: list[ClaimedEvent] = []
            for row in rows:
                row.status = "processing"
                row.attempt_count += 1
                row.last_attempt_at = now
                row.locked_at = now
                row.lock_token = uuid4()
                db.add(
                    NotificationOutboxAttempt(
                        outbox_id=row.id,
                        attempt_number=row.attempt_count,
                        event="claimed",
                    )
                )
                claimed.append(ClaimedEvent(row.id, row.lock_token))
            db.commit()
        return claimed

    def _process_claim(self, claim: ClaimedEvent) -> str | None:
        try:
            with self.session_factory() as db:
                event = db.scalar(
                    select(NotificationOutbox)
                    .where(
                        NotificationOutbox.id == claim.event_id,
                        NotificationOutbox.status == "processing",
                        NotificationOutbox.lock_token == claim.lock_token,
                    )
                    .with_for_update()
                )
                if event is None:
                    return None
                self._deliver(db, event)
                now = datetime.now(UTC)
                event.status = "completed"
                event.processed_at = now
                event.last_error = None
                event.locked_at = None
                event.lock_token = None
                db.add(
                    NotificationOutboxAttempt(
                        outbox_id=event.id,
                        attempt_number=event.attempt_count,
                        event="succeeded",
                    )
                )
                db.commit()
                return "succeeded"
        except InvalidOutboxEvent as exc:
            return self._record_failure(claim, exc.code, permanent=True)
        except (SQLAlchemyError, ValueError, TypeError) as exc:
            error_code = _safe_error_code(exc)
            logger.error(
                "Notification-Outbox-Zustellung fehlgeschlagen: event_id=%s error_code=%s",
                claim.event_id,
                error_code,
            )
            return self._record_failure(claim, error_code, permanent=False)

    def _deliver(self, db: Session, event: NotificationOutbox) -> None:
        payload = event.payload
        if event.event_type not in SUPPORTED_EVENTS:
            raise InvalidOutboxEvent("unsupported_event")
        try:
            task_id = UUID(str(payload["task_id"]))
            recipients_raw = payload["recipient_ids"]
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise InvalidOutboxEvent("invalid_payload") from exc
        if not isinstance(recipients_raw, list):
            raise InvalidOutboxEvent("invalid_payload")
        if task_id != event.aggregate_id:
            raise InvalidOutboxEvent("invalid_payload")
        try:
            recipient_ids = {UUID(str(item)) for item in recipients_raw}
        except (TypeError, ValueError) as exc:
            raise InvalidOutboxEvent("invalid_recipient") from exc
        existing_notifications = db.execute(
            select(Notification.recipient_id, Notification.title, Notification.body).where(
                Notification.outbox_id == event.id
            )
        ).all()
        existing_recipient_ids = {row.recipient_id for row in existing_notifications}
        missing_recipient_ids = recipient_ids - existing_recipient_ids
        title = payload.get("title")
        body = payload.get("body")
        if not isinstance(title, str) or not title or len(title) > 200:
            title = existing_notifications[0].title if existing_notifications else None
        if not isinstance(body, str) or len(body) > 500:
            body = existing_notifications[0].body if existing_notifications else None
        if not isinstance(title, str) or not title or not isinstance(body, str):
            raise InvalidOutboxEvent("invalid_payload")

        statement_factory = {
            "postgresql": postgresql_insert,
            "sqlite": sqlite_insert,
        }.get(db.bind.dialect.name)
        if statement_factory is None:
            raise RuntimeError("Unsupported database dialect")
        for recipient_id in sorted(missing_recipient_ids, key=str):
            db.execute(
                statement_factory(Notification)
                .values(
                    id=uuid4(),
                    outbox_id=event.id,
                    recipient_id=recipient_id,
                    task_id=task_id,
                    event_type=event.event_type,
                    title=title,
                    body=body,
                )
                .on_conflict_do_nothing(index_elements=["outbox_id", "recipient_id"])
            )

        if event.event_type in TASK_EVENTS:
            event_status = payload.get("status")
            self._evaluate_automation_rules(
                db,
                event,
                task_id=task_id,
                event_status=event_status if isinstance(event_status, str) else None,
                recipient_ids=recipient_ids,
                body=body,
            )
        else:
            try:
                run_id = UUID(str(payload["automation_run_id"]))
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                raise InvalidOutboxEvent("invalid_payload") from exc
            run = db.scalar(
                select(AutomationRun).where(
                    AutomationRun.id == run_id,
                    AutomationRun.action_event_id == event.id,
                )
            )
            if run is None or run.status not in {"queued", "dead_letter"}:
                raise InvalidOutboxEvent("invalid_automation_run")
            run.status = "succeeded"
            run.last_error = None

    def _evaluate_automation_rules(
        self,
        db: Session,
        event: NotificationOutbox,
        *,
        task_id: UUID,
        event_status: str | None,
        recipient_ids: set[UUID],
        body: str,
    ) -> None:
        rules = db.scalars(
            select(AutomationRule)
            .where(
                AutomationRule.is_active.is_(True),
                AutomationRule.deleted_at.is_(None),
                AutomationRule.trigger_type == event.event_type,
            )
            .order_by(AutomationRule.id)
            .with_for_update()
        ).all()
        for rule in rules:
            existing_run = db.scalar(
                select(AutomationRun).where(
                    AutomationRun.rule_id == rule.id,
                    AutomationRun.source_event_id == event.id,
                )
            )
            if existing_run is not None:
                continue
            conditions = rule.conditions
            condition_status = conditions.get("status") if isinstance(conditions, dict) else None
            if (
                not isinstance(conditions, dict)
                or set(conditions) - {"status"}
                or (event_status is not None and event_status not in TASK_STATUSES)
                or event_status is None
                or (
                    "status" in conditions
                    and condition_status is not None
                    and (
                        not isinstance(condition_status, str)
                        or condition_status not in TASK_STATUSES
                    )
                )
                or rule.action_type != "notify_event_recipients"
            ):
                raise InvalidOutboxEvent("invalid_automation_rule")

            run_id = uuid4()
            matches = event_status is not None and condition_status in {None, event_status}
            run = AutomationRun(
                id=run_id,
                rule_id=rule.id,
                rule_name=rule.name,
                source_event_id=event.id,
                trigger_type=event.event_type,
                status=(
                    "condition_not_met"
                    if not matches
                    else "skipped_no_recipients"
                    if not recipient_ids
                    else "queued"
                ),
            )
            db.add(run)
            if not matches or not recipient_ids:
                continue

            action_event_id = uuid4()
            run.action_event_id = action_event_id
            db.add(
                NotificationOutbox(
                    id=action_event_id,
                    dedupe_key=f"automation:{rule.id}:{event.id}",
                    event_type="automation.notification",
                    aggregate_type="task",
                    aggregate_id=task_id,
                    payload={
                        "automation_run_id": str(run_id),
                        "task_id": str(task_id),
                        "recipient_ids": sorted(
                            str(recipient_id) for recipient_id in recipient_ids
                        ),
                        "title": f"Automatisierung: {rule.name}"[:200],
                        "body": body[:500],
                    },
                )
            )

    def _record_failure(
        self, claim: ClaimedEvent, error_code: str, *, permanent: bool
    ) -> str | None:
        with self.session_factory() as db:
            event = db.scalar(
                select(NotificationOutbox)
                .where(
                    NotificationOutbox.id == claim.event_id,
                    NotificationOutbox.status == "processing",
                    NotificationOutbox.lock_token == claim.lock_token,
                )
                .with_for_update()
            )
            if event is None:
                return None
            event.failure_count += 1
            terminal = permanent or event.failure_count >= self.max_attempts
            now = datetime.now(UTC)
            event.status = "dead_letter" if terminal else "pending"
            event.last_error = error_code
            event.available_at = (
                now
                if terminal
                else now + timedelta(seconds=retry_delay_seconds(event.attempt_count))
            )
            event.locked_at = None
            event.lock_token = None
            db.add(
                NotificationOutboxAttempt(
                    outbox_id=event.id,
                    attempt_number=event.attempt_count,
                    event="dead_lettered" if terminal else "retry_scheduled",
                    error_code=error_code,
                )
            )
            if event.event_type == "automation.notification":
                run = db.scalar(
                    select(AutomationRun).where(AutomationRun.action_event_id == event.id)
                )
                if run is not None:
                    run.last_error = error_code
                    if terminal:
                        run.status = "dead_letter"
            db.commit()
        return "dead_lettered" if terminal else "retry_scheduled"


def retry_delay_seconds(attempt_number: int) -> int:
    return min(MAX_RETRY_SECONDS, BASE_RETRY_SECONDS * 2 ** max(0, attempt_number - 1))


def _safe_error_code(exc: Exception) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", type(exc).__name__)[:100] or "unknown_error"


def _safe_stored_error_code(value: str | None) -> str:
    if value is not None and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,99}", value):
        return value
    return "legacy_or_invalid_error_code"


async def run_worker(
    stop: asyncio.Event,
    *,
    worker: NotificationOutboxWorker | None = None,
    poll_interval_seconds: float | None = None,
    run_cycle: Callable[[], CycleResult] | None = None,
) -> None:
    settings = get_settings()
    worker = worker or NotificationOutboxWorker()
    run_cycle = run_cycle or worker.run_once
    poll_interval_seconds = poll_interval_seconds or settings.notification_worker_poll_seconds
    monitor_task = asyncio.create_task(run_monitoring_scheduler(stop))
    try:
        while not stop.is_set():
            try:
                result = await asyncio.to_thread(run_cycle)
                logger.info(
                    "Notification-Outbox-Zyklus: beansprucht=%d zugestellt=%d wiederholt=%d "
                    "dead_letter=%d",
                    result.claimed,
                    result.delivered,
                    result.retried,
                    result.dead_lettered,
                )
            except (SQLAlchemyError, OSError, TimeoutError) as exc:
                logger.error(
                    "Notification-Outbox-Zyklus fehlgeschlagen: error_code=%s",
                    _safe_error_code(exc),
                )
            try:
                await asyncio.wait_for(stop.wait(), timeout=poll_interval_seconds)
            except TimeoutError:
                continue
    finally:
        stop.set()
        await monitor_task


def inspect_outbox(limit: int = 50) -> dict[str, object]:
    with SessionLocal() as db:
        counts = db.execute(
            select(NotificationOutbox.status, func.count())
            .group_by(NotificationOutbox.status)
            .order_by(NotificationOutbox.status)
        ).all()
        failed = db.scalars(
            select(NotificationOutbox)
            .where(NotificationOutbox.status.in_(("dead_letter", "failed")))
            .order_by(NotificationOutbox.created_at, NotificationOutbox.id)
            .limit(limit)
        ).all()
        attempts_by_event: dict[UUID, list[NotificationOutboxAttempt]] = {}
        if failed:
            for attempt in db.scalars(
                select(NotificationOutboxAttempt)
                .where(NotificationOutboxAttempt.outbox_id.in_([event.id for event in failed]))
                .order_by(
                    NotificationOutboxAttempt.outbox_id,
                    NotificationOutboxAttempt.attempt_number,
                    NotificationOutboxAttempt.created_at,
                )
            ).all():
                attempts_by_event.setdefault(attempt.outbox_id, []).append(attempt)
        return {
            "counts": {status: count for status, count in counts},
            "failed_events": [
                {
                    "id": str(event.id),
                    "event_type": event.event_type,
                    "aggregate_id": str(event.aggregate_id),
                    "status": event.status,
                    "attempt_count": event.attempt_count,
                    "last_error": _safe_stored_error_code(event.last_error),
                    "created_at": event.created_at.isoformat(),
                    "attempt_history": [
                        {
                            "attempt_number": attempt.attempt_number,
                            "event": attempt.event,
                            "error_code": attempt.error_code,
                            "created_at": attempt.created_at.isoformat(),
                        }
                        for attempt in attempts_by_event.get(event.id, [])
                    ],
                }
                for event in failed
            ],
        }


def check_worker_health() -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        connection.execute(select(func.count()).select_from(NotificationOutbox))


def main() -> int:
    parser = argparse.ArgumentParser(description="Persistierter In-App-Benachrichtigungs-Worker")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("run", help="Outbox-Ereignisse kontinuierlich zustellen")
    subparsers.add_parser("health", help="Datenbank und Outbox-Schema prüfen")
    inspect_parser = subparsers.add_parser("inspect", help="Status und fehlgeschlagene Events")
    inspect_parser.add_argument("--limit", type=int, default=50, choices=range(1, 101))
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if args.command == "health":
        try:
            check_worker_health()
        except SQLAlchemyError as exc:
            logger.error("Worker-Healthcheck fehlgeschlagen: error_code=%s", _safe_error_code(exc))
            return 1
        print(json.dumps({"status": "ready"}))
        return 0
    if args.command == "inspect":
        print(json.dumps(inspect_outbox(args.limit), ensure_ascii=False))
        return 0

    async def serve() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(signum, stop.set)
        try:
            await run_worker(stop)
        finally:
            engine.dispose()

    asyncio.run(serve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
