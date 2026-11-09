from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Annotated
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth import AuthPrincipal, add_audit_entry, get_auth_principal, require_permission
from app.config import get_settings
from app.database import get_db
from app.document_storage import read_file, remove_file, sha256_hex, store_file, validate_upload
from app.incident_schemas import (
    IncidentAssigneeChoice,
    IncidentAttachmentRead,
    IncidentChoices,
    IncidentCreate,
    IncidentDetail,
    IncidentHistoryRead,
    IncidentMeasureCreate,
    IncidentMeasureRead,
    IncidentMeasureUpdate,
    IncidentObjectChoice,
    IncidentPage,
    IncidentPersonCreate,
    IncidentPersonRead,
    IncidentRead,
    IncidentSensitiveRead,
    IncidentSensitiveUpdate,
    IncidentStatusUpdate,
    IncidentUpdate,
)
from app.models import (
    Incident,
    IncidentAttachment,
    IncidentHistory,
    IncidentMeasure,
    IncidentPerson,
    IncidentSensitiveDetails,
    ObjectAssignment,
    OWKSEvent,
    SecurityObject,
    User,
)
from app.upload_scanning import scan_upload_or_reject

router = APIRouter(prefix="/incidents", tags=["Vorfall- und Beschwerdemanagement"])
GLOBAL_READ = {"incidents.read_all", "incidents.manage_all"}
GLOBAL_WRITE = {"incidents.manage_all"}
ALLOWED_ATTACHMENT_TYPES = {"application/pdf", "image/png", "image/jpeg"}
STATUS_TRANSITIONS = {
    "reported": {"investigating", "closed"},
    "investigating": {"action_required", "closed"},
    "action_required": {"investigating", "closed"},
    "closed": set(),
}


def _object_access_query(principal: AuthPrincipal, *, for_write: bool = False):
    query = select(SecurityObject).where(SecurityObject.archived_at.is_(None))
    global_permissions = GLOBAL_WRITE if for_write else GLOBAL_READ
    if not global_permissions.intersection(principal.permission_codes):
        assigned_object_ids = select(ObjectAssignment.object_id).where(
            ObjectAssignment.user_id == principal.user.id
        )
        query = query.where(SecurityObject.id.in_(assigned_object_ids))
    return query


def _get_object(
    db: Session,
    object_id: UUID,
    principal: AuthPrincipal,
    *,
    for_write: bool = False,
    missing_status: int = 404,
) -> SecurityObject:
    obj = db.scalar(
        _object_access_query(principal, for_write=for_write).where(SecurityObject.id == object_id)
    )
    if obj is None:
        raise HTTPException(missing_status, "Objekt nicht gefunden")
    return obj


def _require_incident_reader(principal: AuthPrincipal) -> None:
    if not {"incidents.read", *GLOBAL_READ}.intersection(principal.permission_codes):
        raise HTTPException(403, "Keine Berechtigung für Vorfälle")


def _require_incident_writer(principal: AuthPrincipal) -> None:
    if not {"incidents.update", *GLOBAL_WRITE}.intersection(principal.permission_codes):
        raise HTTPException(403, "Keine Berechtigung für Vorfalländerungen")


def _incident_query(principal: AuthPrincipal):
    query = select(Incident)
    if not GLOBAL_READ.intersection(principal.permission_codes):
        assigned_object_ids = select(ObjectAssignment.object_id).where(
            ObjectAssignment.user_id == principal.user.id
        )
        query = query.where(Incident.object_id.in_(assigned_object_ids))
    return query


def _get_incident(
    db: Session,
    incident_id: UUID,
    principal: AuthPrincipal,
    *,
    for_update: bool = False,
) -> Incident:
    query = _incident_query(principal).where(Incident.id == incident_id)
    if for_update:
        query = query.with_for_update()
    incident = db.scalar(query)
    if incident is None:
        raise HTTPException(404, "Vorfall nicht gefunden")
    return incident


def _has_object_assignment(db: Session, object_id: UUID, user_id: UUID) -> bool:
    return (
        db.scalar(
            select(ObjectAssignment.id).where(
                ObjectAssignment.object_id == object_id,
                ObjectAssignment.user_id == user_id,
            )
        )
        is not None
    )


def _validate_assignee(
    db: Session, object_id: UUID, assignee_id: UUID, principal: AuthPrincipal
) -> User:
    assignee = db.scalar(select(User).where(User.id == assignee_id, User.is_active.is_(True)))
    if assignee is None:
        raise HTTPException(422, "Die verantwortliche Person ist nicht aktiv oder nicht verfügbar.")
    if not GLOBAL_WRITE.intersection(principal.permission_codes) and not _has_object_assignment(
        db, object_id, assignee_id
    ):
        raise HTTPException(422, "Die verantwortliche Person ist dem Objekt nicht zugeordnet.")
    return assignee


def _incident_read(db: Session, incident: Incident) -> IncidentRead:
    obj = db.get(SecurityObject, incident.object_id)
    assignee = db.get(User, incident.assigned_to_id)
    if obj is None or assignee is None:
        raise HTTPException(409, "Vorfallbezüge sind nicht verfügbar.")
    return IncidentRead(
        id=incident.id,
        title=incident.title,
        report=incident.report,
        incident_type=incident.incident_type,
        severity=incident.severity,
        object_id=incident.object_id,
        object_name=obj.name,
        status=incident.status,
        due_at=incident.due_at,
        assigned_to_id=incident.assigned_to_id,
        assigned_to_name=assignee.full_name,
        owks_event_id=incident.owks_event_id,
        created_by_id=incident.created_by_id,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
    )


def _record_history(
    db: Session, incident: Incident, principal: AuthPrincipal, action: str, changes: dict
) -> None:
    db.add(
        IncidentHistory(
            incident_id=incident.id,
            actor_id=principal.user.id,
            action=action,
            changes=changes,
        )
    )


def _audit_incident(
    db: Session,
    request: Request,
    principal: AuthPrincipal,
    incident: Incident,
    action: str,
    details: dict | None = None,
) -> None:
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action=f"incidents.{action}",
        entity_type="incident",
        entity_id=str(incident.id),
        ip_address=request.client.host if request.client else None,
        details=details,
    )


def _commit_incident(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        _raise_incident_integrity_error(db, exc)


def _raise_incident_integrity_error(db: Session, exc: IntegrityError) -> None:
    db.rollback()
    constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    if constraint_name == "uq_incidents_owks_event_id" or (
        "UNIQUE constraint failed: incidents.owks_event_id" in str(exc.orig)
    ):
        raise HTTPException(
            409,
            "Dieses OWKS-Ereignis ist bereits mit einem Vorgang verknüpft.",
        ) from exc
    raise HTTPException(409, "Die Vorfalländerung kollidiert mit vorhandenen Daten.") from exc


def _incident_detail(db: Session, incident: Incident, principal: AuthPrincipal) -> IncidentDetail:
    can_read_sensitive = "incidents.sensitive.read" in principal.permission_codes
    details = db.get(IncidentSensitiveDetails, incident.id) if can_read_sensitive else None
    people = (
        db.scalars(
            select(IncidentPerson)
            .where(IncidentPerson.incident_id == incident.id)
            .order_by(IncidentPerson.created_at, IncidentPerson.id)
        ).all()
        if can_read_sensitive
        else []
    )
    attachments = (
        db.scalars(
            select(IncidentAttachment)
            .where(IncidentAttachment.incident_id == incident.id)
            .order_by(IncidentAttachment.created_at, IncidentAttachment.id)
        ).all()
        if can_read_sensitive
        else []
    )
    measures = db.scalars(
        select(IncidentMeasure)
        .where(IncidentMeasure.incident_id == incident.id)
        .order_by(IncidentMeasure.due_at.asc().nulls_last(), IncidentMeasure.created_at)
    ).all()
    history = db.scalars(
        select(IncidentHistory)
        .where(IncidentHistory.incident_id == incident.id)
        .order_by(IncidentHistory.created_at, IncidentHistory.id)
    ).all()
    return IncidentDetail(
        **_incident_read(db, incident).model_dump(),
        sensitive_details=(
            IncidentSensitiveRead(
                narrative=details.narrative if details else None,
                closure_report=details.closure_report if details else None,
                updated_by_id=details.updated_by_id if details else None,
                updated_at=details.updated_at if details else None,
            )
            if can_read_sensitive
            else None
        ),
        people=[IncidentPersonRead.model_validate(person) for person in people],
        attachments=[IncidentAttachmentRead.model_validate(item) for item in attachments],
        measures=[IncidentMeasureRead.model_validate(item) for item in measures],
        history=[IncidentHistoryRead.model_validate(item) for item in history],
    )


@router.get("/choices", response_model=IncidentChoices)
def get_incident_choices(
    object_id: UUID | None = None,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_auth_principal),
) -> IncidentChoices:
    can_create = "incidents.create" in principal.permission_codes
    can_read = bool({"incidents.read", *GLOBAL_READ}.intersection(principal.permission_codes))
    if not can_create and not can_read:
        raise HTTPException(403, "Keine Berechtigung für Vorfälle")
    objects_query = _object_access_query(principal, for_write=can_create).order_by(
        SecurityObject.name, SecurityObject.id
    )
    if object_id is not None:
        _get_object(db, object_id, principal, for_write=can_create)
        objects_query = objects_query.where(SecurityObject.id == object_id)
    objects = db.scalars(objects_query).all()
    if object_id is None:
        return IncidentChoices(
            objects=[
                IncidentObjectChoice(id=item.id, name=item.name, code=item.code) for item in objects
            ],
            assignees=[],
        )
    assignees_query = select(User).where(User.is_active.is_(True))
    if not GLOBAL_WRITE.intersection(principal.permission_codes):
        assignee_ids = select(ObjectAssignment.user_id).where(
            ObjectAssignment.object_id == object_id
        )
        assignees_query = assignees_query.where(User.id.in_(assignee_ids))
    assignees = db.scalars(assignees_query.order_by(User.full_name, User.id).limit(250)).all()
    return IncidentChoices(
        objects=[
            IncidentObjectChoice(id=item.id, name=item.name, code=item.code) for item in objects
        ],
        assignees=[
            IncidentAssigneeChoice(id=item.id, full_name=item.full_name) for item in assignees
        ],
        linked_owks_event_ids=(
            db.scalars(
                select(Incident.owks_event_id)
                .where(
                    Incident.object_id == object_id,
                    Incident.owks_event_id.is_not(None),
                )
                .order_by(Incident.owks_event_id)
            ).all()
            if can_create
            else []
        ),
    )


@router.get("", response_model=IncidentPage)
def list_incidents(
    status_filter: str | None = Query(default=None, alias="status"),
    object_id: UUID | None = None,
    overdue: bool = False,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_auth_principal),
) -> IncidentPage:
    _require_incident_reader(principal)
    filters = []
    if status_filter is not None:
        if status_filter not in STATUS_TRANSITIONS:
            raise HTTPException(422, "Der Vorfallstatus ist ungültig.")
        filters.append(Incident.status == status_filter)
    if object_id is not None:
        _get_object(db, object_id, principal)
        filters.append(Incident.object_id == object_id)
    if overdue:
        filters.extend((Incident.due_at < datetime.now(UTC), Incident.status != "closed"))
    query = _incident_query(principal).where(*filters)
    items = db.scalars(
        query.order_by(Incident.due_at.asc().nulls_last(), Incident.created_at.desc(), Incident.id)
        .limit(limit)
        .offset(offset)
    ).all()
    total = db.scalar(
        select(func.count()).select_from(_incident_query(principal).where(*filters).subquery())
    )
    return IncidentPage(
        items=[_incident_read(db, item) for item in items],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=IncidentRead, status_code=201)
def create_incident(
    payload: IncidentCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_permission("incidents.create")),
) -> IncidentRead:
    obj = _get_object(db, payload.object_id, principal, for_write=True, missing_status=403)
    assigned_to_id = payload.assigned_to_id or principal.user.id
    assignee = _validate_assignee(db, obj.id, assigned_to_id, principal)
    if payload.owks_event_id is not None:
        event = db.get(OWKSEvent, payload.owks_event_id)
        if event is None or event.object_id != obj.id:
            raise HTTPException(422, "Die OWKS-Meldung gehört nicht zum gewählten Objekt.")
    due_at = payload.due_at
    if due_at is not None:
        due_at = due_at.replace(tzinfo=UTC) if due_at.tzinfo is None else due_at.astimezone(UTC)
    incident = Incident(
        id=uuid4(),
        title=payload.title,
        report=payload.report,
        incident_type=payload.incident_type,
        severity=payload.severity,
        object_id=obj.id,
        due_at=due_at,
        assigned_to_id=assignee.id,
        owks_event_id=payload.owks_event_id,
        created_by_id=principal.user.id,
    )
    db.add(incident)
    try:
        db.flush()
        _record_history(db, incident, principal, "created", {"fields": ["report", "title"]})
        _audit_incident(db, request, principal, incident, "created", {"object_id": str(obj.id)})
        _commit_incident(db)
    except IntegrityError as exc:
        _raise_incident_integrity_error(db, exc)
    return _incident_read(db, incident)


@router.get("/{incident_id}", response_model=IncidentDetail)
def get_incident(
    incident_id: UUID,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_auth_principal),
) -> IncidentDetail:
    _require_incident_reader(principal)
    return _incident_detail(db, _get_incident(db, incident_id, principal), principal)


@router.patch("/{incident_id}", response_model=IncidentRead)
def update_incident(
    incident_id: UUID,
    payload: IncidentUpdate,
    request: Request,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_auth_principal),
) -> IncidentRead:
    _require_incident_writer(principal)
    incident = _get_incident(db, incident_id, principal, for_update=True)
    if incident.status == "closed":
        raise HTTPException(409, "Abgeschlossene Vorfälle können nicht mehr geändert werden.")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, "Es wurden keine Änderungen übermittelt.")
    for field in ("title", "report", "incident_type", "severity", "assigned_to_id"):
        if field in changes and changes[field] is None:
            raise HTTPException(422, f"{field} darf nicht leer sein.")
    if "assigned_to_id" in changes:
        _validate_assignee(db, incident.object_id, changes["assigned_to_id"], principal)
    after: dict[str, object] = {}
    for field, value in changes.items():
        old_value = getattr(incident, field)
        if field == "due_at":
            new_value = (
                value.replace(tzinfo=UTC)
                if value is not None and value.tzinfo is None
                else value.astimezone(UTC)
                if value is not None
                else None
            )
            old_record = old_value.isoformat() if old_value is not None else None
            new_record = new_value.isoformat() if new_value is not None else None
        else:
            new_value = value
            old_record = str(old_value) if isinstance(old_value, UUID) else old_value
            new_record = str(new_value) if isinstance(new_value, UUID) else new_value
        if old_record != new_record:
            after[field] = new_record
            setattr(incident, field, new_value)
    if not after:
        raise HTTPException(422, "Es wurden keine Änderungen übermittelt.")
    incident.updated_at = datetime.now(UTC)
    _record_history(db, incident, principal, "updated", {"fields": sorted(after)})
    _audit_incident(db, request, principal, incident, "updated", {"fields": sorted(after)})
    _commit_incident(db)
    return _incident_read(db, incident)


@router.post("/{incident_id}/status", response_model=IncidentRead)
def change_incident_status(
    incident_id: UUID,
    payload: IncidentStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_auth_principal),
) -> IncidentRead:
    _require_incident_writer(principal)
    incident = _get_incident(db, incident_id, principal, for_update=True)
    if payload.status not in STATUS_TRANSITIONS[incident.status]:
        raise HTTPException(422, "Dieser Statusübergang ist nicht zulässig.")
    if payload.status == "closed":
        if "incidents.sensitive.manage" not in principal.permission_codes:
            raise HTTPException(
                403, "Zum Abschließen ist die Berechtigung für sensible Vorfalldaten erforderlich."
            )
        details = db.get(IncidentSensitiveDetails, incident.id)
        if details is None or not details.closure_report:
            raise HTTPException(422, "Zum Abschließen ist ein Abschlussbericht erforderlich.")
        outstanding_measures = db.scalar(
            select(func.count())
            .select_from(IncidentMeasure)
            .where(
                IncidentMeasure.incident_id == incident.id,
                IncidentMeasure.status != "completed",
            )
        )
        if outstanding_measures:
            raise HTTPException(409, "Offene Maßnahmen müssen vor dem Abschluss erledigt werden.")
    old_status = incident.status
    incident.status = payload.status
    incident.updated_at = datetime.now(UTC)
    action = "closed" if payload.status == "closed" else "status_changed"
    _record_history(
        db,
        incident,
        principal,
        action,
        {"from": old_status, "to": payload.status},
    )
    _audit_incident(
        db,
        request,
        principal,
        incident,
        action,
        {"from": old_status, "to": payload.status},
    )
    _commit_incident(db)
    return _incident_read(db, incident)


@router.patch("/{incident_id}/sensitive", response_model=IncidentSensitiveRead)
def update_sensitive_details(
    incident_id: UUID,
    payload: IncidentSensitiveUpdate,
    request: Request,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_permission("incidents.sensitive.manage")),
) -> IncidentSensitiveRead:
    _require_incident_writer(principal)
    incident = _get_incident(db, incident_id, principal, for_update=True)
    if incident.status == "closed":
        raise HTTPException(409, "Abgeschlossene Vorfälle können nicht mehr geändert werden.")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, "Es wurden keine Änderungen übermittelt.")
    details = db.get(IncidentSensitiveDetails, incident.id)
    if details is None:
        details = IncidentSensitiveDetails(
            incident_id=incident.id,
            updated_by_id=principal.user.id,
            updated_at=datetime.now(UTC),
        )
        db.add(details)
    fields = []
    for field, value in changes.items():
        if value != getattr(details, field):
            setattr(details, field, value)
            fields.append(field)
    if not fields:
        raise HTTPException(422, "Es wurden keine Änderungen übermittelt.")
    details.updated_by_id = principal.user.id
    details.updated_at = datetime.now(UTC)
    _record_history(db, incident, principal, "sensitive_updated", {"fields": sorted(fields)})
    _audit_incident(
        db, request, principal, incident, "sensitive_updated", {"fields": sorted(fields)}
    )
    _commit_incident(db)
    return IncidentSensitiveRead(
        narrative=details.narrative,
        closure_report=details.closure_report,
        updated_by_id=details.updated_by_id,
        updated_at=details.updated_at,
    )


@router.post("/{incident_id}/measures", response_model=IncidentMeasureRead, status_code=201)
def create_incident_measure(
    incident_id: UUID,
    payload: IncidentMeasureCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_auth_principal),
) -> IncidentMeasureRead:
    _require_incident_writer(principal)
    incident = _get_incident(db, incident_id, principal, for_update=True)
    if incident.status == "closed":
        raise HTTPException(
            409, "Abgeschlossenen Vorfällen können keine Maßnahmen hinzugefügt werden."
        )
    _validate_assignee(db, incident.object_id, payload.assigned_to_id, principal)
    due_at = payload.due_at
    if due_at is not None:
        due_at = due_at.replace(tzinfo=UTC) if due_at.tzinfo is None else due_at.astimezone(UTC)
    measure = IncidentMeasure(
        incident_id=incident.id,
        title=payload.title,
        description=payload.description,
        due_at=due_at,
        assigned_to_id=payload.assigned_to_id,
        created_by_id=principal.user.id,
    )
    db.add(measure)
    db.flush()
    _record_history(db, incident, principal, "measure_created", {"measure_id": str(measure.id)})
    _audit_incident(db, request, principal, incident, "measure_created")
    _commit_incident(db)
    return IncidentMeasureRead.model_validate(measure)


@router.patch("/{incident_id}/measures/{measure_id}", response_model=IncidentMeasureRead)
def update_incident_measure(
    incident_id: UUID,
    measure_id: UUID,
    payload: IncidentMeasureUpdate,
    request: Request,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_auth_principal),
) -> IncidentMeasureRead:
    _require_incident_writer(principal)
    incident = _get_incident(db, incident_id, principal, for_update=True)
    if incident.status == "closed":
        raise HTTPException(409, "Abgeschlossene Vorfälle können nicht mehr geändert werden.")
    measure = db.scalar(
        select(IncidentMeasure).where(
            IncidentMeasure.id == measure_id,
            IncidentMeasure.incident_id == incident.id,
        )
    )
    if measure is None:
        raise HTTPException(404, "Maßnahme nicht gefunden")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, "Es wurden keine Änderungen übermittelt.")
    for field in ("title", "status"):
        if field in changes and changes[field] is None:
            raise HTTPException(422, f"{field} darf nicht leer sein.")
    if "assigned_to_id" in changes:
        if changes["assigned_to_id"] is None:
            raise HTTPException(422, "Die verantwortliche Person darf nicht leer sein.")
        _validate_assignee(db, incident.object_id, changes["assigned_to_id"], principal)
    after: dict[str, object] = {}
    status_transition: dict[str, str] | None = None
    for field, value in changes.items():
        old_value = getattr(measure, field)
        new_value = value
        if field == "due_at":
            new_value = (
                value.replace(tzinfo=UTC)
                if value is not None and value.tzinfo is None
                else value.astimezone(UTC)
                if value is not None
                else None
            )
            old_record = old_value.isoformat() if old_value is not None else None
            new_record = new_value.isoformat() if new_value is not None else None
        else:
            old_record = str(old_value) if isinstance(old_value, UUID) else old_value
            new_record = str(new_value) if isinstance(new_value, UUID) else new_value
        if old_record != new_record:
            after[field] = new_record
            setattr(measure, field, new_value)
            if field == "status":
                status_transition = {"from": old_value, "to": new_value}
    if not after:
        raise HTTPException(422, "Es wurden keine Änderungen übermittelt.")
    measure.updated_at = datetime.now(UTC)
    history_changes: dict[str, object] = {"fields": sorted(after)}
    if status_transition is not None:
        history_changes["status_transition"] = status_transition
    _record_history(db, incident, principal, "measure_updated", history_changes)
    _audit_incident(
        db,
        request,
        principal,
        incident,
        "measure_updated",
        {"measure_id": str(measure.id), **history_changes},
    )
    _commit_incident(db)
    return IncidentMeasureRead.model_validate(measure)


@router.post("/{incident_id}/people", response_model=IncidentPersonRead, status_code=201)
def add_incident_person(
    incident_id: UUID,
    payload: IncidentPersonCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_permission("incidents.sensitive.manage")),
) -> IncidentPersonRead:
    _require_incident_writer(principal)
    incident = _get_incident(db, incident_id, principal, for_update=True)
    if incident.status == "closed":
        raise HTTPException(
            409, "Abgeschlossenen Vorfällen können keine Personen hinzugefügt werden."
        )
    person = IncidentPerson(
        incident_id=incident.id,
        name=payload.name,
        role=payload.role,
        notes=payload.notes,
        created_by_id=principal.user.id,
    )
    db.add(person)
    _record_history(db, incident, principal, "person_added", {"role": payload.role})
    _audit_incident(db, request, principal, incident, "person_added", {"role": payload.role})
    _commit_incident(db)
    return IncidentPersonRead.model_validate(person)


@router.post("/{incident_id}/attachments", response_model=IncidentAttachmentRead, status_code=201)
def upload_incident_attachment(
    incident_id: UUID,
    request: Request,
    file: Annotated[UploadFile, File()],
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_auth_principal),
) -> IncidentAttachmentRead:
    _require_incident_writer(principal)
    if "incidents.sensitive.manage" not in principal.permission_codes:
        raise HTTPException(403, "Keine Berechtigung für sensible Vorfalldateien.")
    incident = _get_incident(db, incident_id, principal, for_update=True)
    if incident.status == "closed":
        raise HTTPException(
            409, "Abgeschlossenen Vorfällen können keine Dateien hinzugefügt werden."
        )
    maximum = get_settings().document_max_upload_bytes
    if maximum <= 0:
        raise RuntimeError("DOCUMENT_MAX_UPLOAD_BYTES muss größer als 0 sein.")
    if file.size is not None and file.size > min(maximum, 10 * 1024 * 1024):
        raise HTTPException(413, "Die Datei überschreitet das Limit von 10 MiB.")
    content = file.file.read(min(maximum, 10 * 1024 * 1024) + 1)
    if len(content) > min(maximum, 10 * 1024 * 1024):
        raise HTTPException(413, "Die Datei überschreitet das Limit von 10 MiB.")
    safe_name, media_type = validate_upload(file.filename, file.content_type, content)
    if media_type not in ALLOWED_ATTACHMENT_TYPES:
        raise HTTPException(415, "Für Vorfalldateien sind nur PDF- und Bilddateien zugelassen.")
    scan_upload_or_reject(
        db,
        request,
        content=content,
        actor_id=principal.user.id,
        surface="incident_attachment",
    )
    storage_key = uuid4().hex
    attachment = IncidentAttachment(
        incident_id=incident.id,
        storage_key=storage_key,
        file_name=safe_name,
        media_type=media_type,
        size_bytes=len(content),
        sha256=sha256_hex(content),
        uploaded_by_id=principal.user.id,
    )
    db.add(attachment)
    _record_history(db, incident, principal, "attachment_added", {"media_type": media_type})
    _audit_incident(
        db,
        request,
        principal,
        incident,
        "attachment_added",
        {"size_bytes": len(content), "sha256": attachment.sha256},
    )
    stored = False
    try:
        store_file(storage_key, content)
        stored = True
        _commit_incident(db)
    except HTTPException:
        if stored:
            remove_file(storage_key)
        raise
    except OSError as exc:
        db.rollback()
        if stored:
            remove_file(storage_key)
        raise HTTPException(500, "Datei konnte nicht sicher gespeichert werden.") from exc
    except SQLAlchemyError:
        db.rollback()
        if stored:
            remove_file(storage_key)
        raise
    return IncidentAttachmentRead.model_validate(attachment)


@router.get("/{incident_id}/attachments/{attachment_id}/download")
def download_incident_attachment(
    incident_id: UUID,
    attachment_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_permission("incidents.sensitive.read")),
) -> Response:
    _require_incident_reader(principal)
    incident = _get_incident(db, incident_id, principal)
    attachment = db.scalar(
        select(IncidentAttachment).where(
            IncidentAttachment.id == attachment_id,
            IncidentAttachment.incident_id == incident.id,
        )
    )
    if attachment is None:
        raise HTTPException(404, "Vorfall-Datei nicht gefunden")
    try:
        content = read_file(attachment.storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(503, "Die Vorfalldatei ist nicht verfügbar.") from exc
    except OSError as exc:
        raise HTTPException(503, "Der private Dokumentenspeicher ist nicht verfügbar.") from exc
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="incidents.attachment_downloaded",
        entity_type="incident",
        entity_id=str(incident.id),
        ip_address=request.client.host if request.client else None,
        details={"attachment_id": str(attachment.id), "sha256": attachment.sha256},
    )
    db.commit()
    safe_name = PurePosixPath(attachment.file_name.replace("\\", "/")).name
    return Response(
        content=content,
        media_type=attachment.media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_name, safe='')}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
