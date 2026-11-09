from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import AuthPrincipal, add_audit_entry, require_permission
from app.automation_schemas import (
    AutomationCondition,
    AutomationOutboxEventPage,
    AutomationOutboxEventRead,
    AutomationRuleCreate,
    AutomationRuleRead,
    AutomationRuleUpdate,
    AutomationRunPage,
    AutomationRunRead,
)
from app.database import get_db
from app.models import (
    AutomationRule,
    AutomationRun,
    NotificationOutbox,
    NotificationOutboxAttempt,
)
from app.notification_worker import SUPPORTED_EVENTS

router = APIRouter()
require_automation_admin = require_permission("automations.manage")
MAX_MANUAL_RETRIES = 3


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client is not None else None


def _get_rule(db: Session, rule_id: UUID) -> AutomationRule:
    rule = db.scalar(
        select(AutomationRule).where(
            AutomationRule.id == rule_id,
            AutomationRule.deleted_at.is_(None),
        )
    )
    if rule is None:
        raise HTTPException(status_code=404, detail="Automatisierungsregel nicht gefunden")
    return rule


def _record_rule_audit(
    db: Session,
    request: Request,
    principal: AuthPrincipal,
    action: str,
    rule: AutomationRule,
    details: dict[str, object] | None = None,
) -> None:
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action=action,
        entity_type="automation_rule",
        entity_id=str(rule.id),
        ip_address=_client_ip(request),
        details=details,
    )


def _attempts_by_outbox(
    db: Session, outbox_ids: set[UUID]
) -> dict[UUID, list[NotificationOutboxAttempt]]:
    if not outbox_ids:
        return {}
    attempts: dict[UUID, list[NotificationOutboxAttempt]] = {}
    for attempt in db.scalars(
        select(NotificationOutboxAttempt)
        .where(NotificationOutboxAttempt.outbox_id.in_(outbox_ids))
        .order_by(
            NotificationOutboxAttempt.outbox_id,
            NotificationOutboxAttempt.attempt_number,
            NotificationOutboxAttempt.created_at,
        )
    ).all():
        attempts.setdefault(attempt.outbox_id, []).append(attempt)
    return attempts


def _retry_outbox_event(
    db: Session,
    event: NotificationOutbox,
    request: Request,
    principal: AuthPrincipal,
) -> None:
    if event.status != "dead_letter":
        raise HTTPException(
            status_code=409,
            detail="Nur Ereignisse in der Fehlerablage können wiederholt werden.",
        )
    if event.event_type not in SUPPORTED_EVENTS:
        raise HTTPException(status_code=409, detail="Dieser Ereignistyp ist nicht wiederholbar.")
    if event.manual_retry_count >= MAX_MANUAL_RETRIES:
        raise HTTPException(
            status_code=409,
            detail="Die Höchstzahl manueller Wiederholungen wurde erreicht.",
        )

    if event.event_type == "automation.notification":
        run = db.scalar(select(AutomationRun).where(AutomationRun.action_event_id == event.id))
        if run is None or run.status != "dead_letter":
            raise HTTPException(
                status_code=409,
                detail="Der zugehörige Automatisierungslauf ist nicht wiederholbar.",
            )
        run.status = "queued"
        run.last_error = None
        run.manual_retry_count += 1

    event.status = "pending"
    event.available_at = datetime.now(UTC)
    event.failure_count = 0
    event.manual_retry_count += 1
    event.last_error = None
    event.locked_at = None
    event.lock_token = None
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="automation.outbox_retried",
        entity_type="notification_outbox",
        entity_id=str(event.id),
        ip_address=_client_ip(request),
        details={
            "event_type": event.event_type,
            "manual_retry_count": event.manual_retry_count,
        },
    )
    db.commit()


@router.get("/automations/rules", response_model=list[AutomationRuleRead])
def list_automation_rules(
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_automation_admin),
) -> list[AutomationRuleRead]:
    rules = db.scalars(
        select(AutomationRule)
        .where(AutomationRule.deleted_at.is_(None))
        .order_by(AutomationRule.created_at, AutomationRule.id)
    ).all()
    return [AutomationRuleRead.model_validate(rule) for rule in rules]


@router.post(
    "/automations/rules",
    response_model=AutomationRuleRead,
    status_code=status.HTTP_201_CREATED,
)
def create_automation_rule(
    payload: AutomationRuleCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_automation_admin),
) -> AutomationRuleRead:
    rule = AutomationRule(
        id=uuid4(),
        name=payload.name,
        description=payload.description,
        trigger_type=payload.trigger_type,
        conditions=payload.conditions.model_dump(exclude_none=True),
        action_type=payload.action_type,
        is_active=False,
        created_by_id=principal.user.id,
        updated_by_id=principal.user.id,
    )
    db.add(rule)
    _record_rule_audit(
        db,
        request,
        principal,
        "automation.rule_created",
        rule,
        {"trigger_type": rule.trigger_type, "action_type": rule.action_type},
    )
    db.commit()
    db.refresh(rule)
    return AutomationRuleRead.model_validate(rule)


@router.get("/automations/rules/{rule_id}", response_model=AutomationRuleRead)
def get_automation_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_automation_admin),
) -> AutomationRuleRead:
    return AutomationRuleRead.model_validate(_get_rule(db, rule_id))


@router.patch("/automations/rules/{rule_id}", response_model=AutomationRuleRead)
def update_automation_rule(
    rule_id: UUID,
    payload: AutomationRuleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_automation_admin),
) -> AutomationRuleRead:
    rule = _get_rule(db, rule_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Es wurden keine Änderungen angegeben.")
    for field in ("name", "trigger_type", "conditions", "action_type", "is_active"):
        if field in changes and changes[field] is None:
            raise HTTPException(status_code=422, detail="Änderungen dürfen nicht leer sein.")
    if "conditions" in changes:
        changes["conditions"] = AutomationCondition.model_validate(
            changes["conditions"]
        ).model_dump(exclude_none=True)
    for field, value in changes.items():
        setattr(rule, field, value)
    rule.updated_by_id = principal.user.id
    _record_rule_audit(
        db,
        request,
        principal,
        "automation.rule_updated",
        rule,
        {"fields": sorted(changes)},
    )
    db.commit()
    db.refresh(rule)
    return AutomationRuleRead.model_validate(rule)


@router.delete("/automations/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_automation_rule(
    rule_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_automation_admin),
) -> None:
    rule = _get_rule(db, rule_id)
    now = datetime.now(UTC)
    rule.is_active = False
    rule.deleted_at = now
    rule.updated_by_id = principal.user.id
    rule.updated_at = now
    _record_rule_audit(db, request, principal, "automation.rule_deleted", rule)
    db.commit()


@router.get("/automations/runs", response_model=AutomationRunPage)
def list_automation_runs(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_automation_admin),
) -> AutomationRunPage:
    total = db.scalar(select(func.count()).select_from(AutomationRun)) or 0
    runs = db.scalars(
        select(AutomationRun)
        .order_by(AutomationRun.created_at.desc(), AutomationRun.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    action_event_ids = {run.action_event_id or run.source_event_id for run in runs}
    attempts = _attempts_by_outbox(db, action_event_ids)
    return AutomationRunPage(
        items=[
            AutomationRunRead(
                id=run.id,
                rule_id=run.rule_id,
                rule_name=run.rule_name,
                source_event_id=run.source_event_id,
                action_event_id=run.action_event_id,
                trigger_type=run.trigger_type,
                status=run.status,
                last_error=run.last_error,
                manual_retry_count=run.manual_retry_count,
                created_at=run.created_at,
                updated_at=run.updated_at,
                attempt_history=attempts.get(run.action_event_id or run.source_event_id, []),
            )
            for run in runs
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/automations/outbox-events", response_model=AutomationOutboxEventPage)
def list_automation_dead_letters(
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    _principal: AuthPrincipal = Depends(require_automation_admin),
) -> AutomationOutboxEventPage:
    condition = (NotificationOutbox.status == "dead_letter") & NotificationOutbox.event_type.in_(
        SUPPORTED_EVENTS
    )
    total = db.scalar(select(func.count()).select_from(NotificationOutbox).where(condition)) or 0
    events = db.scalars(
        select(NotificationOutbox)
        .where(condition)
        .order_by(NotificationOutbox.created_at.desc(), NotificationOutbox.id.desc())
        .limit(limit)
    ).all()
    attempts = _attempts_by_outbox(db, {event.id for event in events})
    return AutomationOutboxEventPage(
        items=[
            AutomationOutboxEventRead(
                id=event.id,
                event_type=event.event_type,
                aggregate_id=event.aggregate_id,
                status="dead_letter",
                attempt_count=event.attempt_count,
                manual_retry_count=event.manual_retry_count,
                last_error=event.last_error,
                created_at=event.created_at,
                attempt_history=attempts.get(event.id, []),
            )
            for event in events
        ],
        total=total,
    )


@router.post("/automations/outbox-events/{event_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_automation_outbox_event(
    event_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_automation_admin),
) -> dict[str, str]:
    event = db.scalar(
        select(NotificationOutbox).where(NotificationOutbox.id == event_id).with_for_update()
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Ereignis nicht gefunden")
    _retry_outbox_event(db, event, request, principal)
    return {"status": "pending"}


@router.post("/automations/runs/{run_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_automation_run(
    run_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_automation_admin),
) -> dict[str, str]:
    run = db.scalar(select(AutomationRun).where(AutomationRun.id == run_id).with_for_update())
    if run is None:
        raise HTTPException(status_code=404, detail="Automatisierungslauf nicht gefunden")
    if run.action_event_id is None:
        raise HTTPException(
            status_code=409, detail="Dieser Lauf besitzt keine wiederholbare Aktion."
        )
    event = db.scalar(
        select(NotificationOutbox)
        .where(NotificationOutbox.id == run.action_event_id)
        .with_for_update()
    )
    if event is None:
        raise HTTPException(status_code=409, detail="Aktion nicht gefunden.")
    _retry_outbox_event(db, event, request, principal)
    return {"status": "pending"}
