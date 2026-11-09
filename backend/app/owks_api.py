import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from urllib.parse import quote
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import AuthPrincipal, add_audit_entry, get_auth_principal, require_permission
from app.database import get_db
from app.document_storage import read_attachment, remove_file, store_file
from app.models import (
    Employee,
    ObjectAssignment,
    OWKSAttachment,
    OWKSChallenge,
    OWKSControlPoint,
    OWKSEvent,
    OWKSEventStatus,
    OWKSRoute,
    OWKSRoutePoint,
    SecurityObject,
)
from app.schemas import (
    OWKSAttachmentRead,
    OWKSChallengeRead,
    OWKSControlPointCreate,
    OWKSControlPointRead,
    OWKSEventCorrectionCreate,
    OWKSEventCreate,
    OWKSEventRead,
    OWKSEventStateUpdate,
    OWKSRouteCreate,
    OWKSRouteRead,
    OWKSScanCreate,
    OWKSSyncEventCreate,
    OWKSSyncResult,
)
from app.upload_scanning import scan_upload_or_reject

router = APIRouter(prefix="/owks", tags=["OWKS-Wachbuch"])
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024
ATTACHMENT_TYPES = {
    ".pdf": ("application/pdf", b"%PDF-"),
    ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
    ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
}
READ_PERMISSION = Depends(require_permission("owks.read"))
MONITOR_ADVISORY_LOCK_KEY = 731942681


def now_utc() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def can_manage(principal) -> bool:
    return "owks.manage" in principal.permission_codes


def get_object_or_404(
    db: Session, object_id: UUID, principal, *, for_write: bool = False
) -> SecurityObject:
    global_permission = "objects.manage_all" if for_write else "objects.read_all"
    query = select(SecurityObject).where(SecurityObject.id == object_id)
    if global_permission not in principal.permission_codes:
        query = query.where(
            SecurityObject.assignments.any(ObjectAssignment.user_id == principal.user.id)
        )
    obj = db.scalar(query)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Objekt nicht gefunden")
    if obj.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Das Objekt ist archiviert")
    return obj


def require_write_access(principal) -> None:
    if not ({"owks.write", "owks.manage"} & principal.permission_codes):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Keine Berechtigung für OWKS-Schreibzugriffe"
        )


def require_owks_write(principal=Depends(get_auth_principal)) -> AuthPrincipal:
    require_write_access(principal)
    return principal


def get_active_employee(db: Session, user_id: UUID) -> Employee:
    employee = db.scalar(
        select(Employee).where(
            Employee.user_id == user_id,
            Employee.archived_at.is_(None),
            Employee.employment_status == "active",
        )
    )
    if employee is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Für den angemeldeten Benutzer ist keine aktive Personalakte verknüpft",
        )
    return employee


def commit_or_conflict(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Die OWKS-Änderung kollidiert mit einem bestehenden Datensatz",
        ) from exc


def latest_status(db: Session, event_id: UUID) -> str:
    return (
        db.scalar(
            select(OWKSEventStatus.status)
            .where(OWKSEventStatus.event_id == event_id)
            .order_by(OWKSEventStatus.sequence_no.desc())
            .limit(1)
        )
        or "open"
    )


def event_read(db: Session, event: OWKSEvent) -> OWKSEventRead:
    return OWKSEventRead(
        id=event.id,
        object_id=event.object_id,
        route_id=event.route_id,
        control_point_id=event.control_point_id,
        corrects_event_id=event.corrects_event_id,
        employee_id=event.employee_id,
        actor_id=event.actor_id,
        client_event_id=event.client_event_id,
        event_type=event.event_type,
        severity=event.severity,
        title=event.title,
        description=event.description,
        occurred_at=as_utc(event.occurred_at),
        sync_status=event.sync_status,
        presence_verified=event.presence_verified,
        status=latest_status(db, event.id),  # type: ignore[arg-type]
        created_at=as_utc(event.created_at),
    )


def create_event(
    db: Session,
    *,
    object_id: UUID,
    employee_id: UUID | None,
    actor_id: UUID | None,
    event_type: str,
    title: str,
    description: str,
    severity: str,
    occurred_at: datetime,
    presence_verified: bool = False,
    client_event_id: UUID | None = None,
    sync_status: str = "synced",
    route_id: UUID | None = None,
    control_point_id: UUID | None = None,
    challenge_id: UUID | None = None,
    corrects_event_id: UUID | None = None,
    request: Request | None = None,
) -> OWKSEvent:
    event = OWKSEvent(
        object_id=object_id,
        route_id=route_id,
        control_point_id=control_point_id,
        corrects_event_id=corrects_event_id,
        employee_id=employee_id,
        actor_id=actor_id,
        challenge_id=challenge_id,
        client_event_id=client_event_id,
        event_type=event_type,
        severity=severity,
        title=title,
        description=description,
        occurred_at=occurred_at.astimezone(UTC),
        sync_status=sync_status,
        presence_verified=presence_verified,
    )
    db.add(event)
    db.flush()
    db.add(
        OWKSEventStatus(
            event_id=event.id,
            sequence_no=1,
            status="resolved" if presence_verified else "open",
            note="",
            actor_id=actor_id,
        )
    )
    add_audit_entry(
        db,
        actor_id=actor_id,
        action=f"owks.{event_type}",
        entity_type="owks_event",
        entity_id=str(event.id),
        ip_address=request.client.host if request and request.client else None,
        details={
            "object_id": str(object_id),
            "severity": severity,
            "sync_status": sync_status,
            "event_id": str(event.id),
        },
    )
    return event


def log_manipulation(
    db: Session, *, object_id: UUID, actor_id: UUID, title: str, request: Request
) -> None:
    create_event(
        db,
        object_id=object_id,
        employee_id=None,
        actor_id=actor_id,
        event_type="manipulation",
        title=title,
        description="Ein Kontrollversuch konnte nicht sicher verifiziert werden.",
        severity="critical",
        occurred_at=now_utc(),
        request=request,
    )
    commit_or_conflict(db)


def monitor_due_routes(
    db: Session,
    *,
    current_time: datetime | None = None,
    route_id: UUID | None = None,
    actor_id: UUID | None = None,
    request: Request | None = None,
    acquire_lock: bool = False,
) -> list[OWKSEvent]:
    if acquire_lock and db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": MONITOR_ADVISORY_LOCK_KEY},
        )
    checked_at = as_utc(current_time or now_utc())
    query = select(OWKSRoute).where(OWKSRoute.is_active.is_(True))
    if route_id is not None:
        query = query.where(OWKSRoute.id == route_id)
    routes = db.scalars(query.order_by(OWKSRoute.id)).all()
    generated: list[OWKSEvent] = []
    for route in routes:
        interval = timedelta(minutes=route.interval_minutes)
        point_ids = db.scalars(
            select(OWKSRoutePoint.control_point_id)
            .where(OWKSRoutePoint.route_id == route.id)
            .order_by(OWKSRoutePoint.position)
        ).all()
        for point_id in point_ids:
            latest_control = db.scalar(
                select(OWKSEvent)
                .where(
                    OWKSEvent.route_id == route.id,
                    OWKSEvent.control_point_id == point_id,
                    OWKSEvent.event_type == "control",
                    OWKSEvent.sync_status == "synced",
                    OWKSEvent.presence_verified.is_(True),
                )
                .order_by(OWKSEvent.occurred_at.desc())
                .limit(1)
            )
            latest_missed = db.scalar(
                select(OWKSEvent)
                .where(
                    OWKSEvent.route_id == route.id,
                    OWKSEvent.control_point_id == point_id,
                    OWKSEvent.event_type == "missed",
                )
                .order_by(OWKSEvent.occurred_at.desc())
                .limit(1)
            )
            recorded_times = [as_utc(route.created_at)]
            recorded_times.extend(
                as_utc(event.occurred_at)
                for event in (latest_control, latest_missed)
                if event is not None
            )
            last_recorded_at = max(recorded_times)
            due_at = last_recorded_at + interval
            if due_at > checked_at:
                continue
            client_event_id = uuid5(
                NAMESPACE_URL,
                f"securityops:owks:missed:{route.id}:{point_id}:{due_at.isoformat()}",
            )
            if db.scalar(
                select(OWKSEvent.id).where(
                    OWKSEvent.client_event_id == client_event_id,
                    OWKSEvent.event_type == "missed",
                )
            ):
                continue
            point = db.get(OWKSControlPoint, point_id)
            generated.append(
                create_event(
                    db,
                    object_id=route.object_id,
                    employee_id=None,
                    actor_id=actor_id,
                    event_type="missed",
                    title=f"Versäumte Kontrolle: {point.name if point else 'Kontrollpunkt'}",
                    description=(
                        f"Die Route „{route.name}“ wurde bis {due_at.isoformat()} "
                        "nicht kontrolliert."
                    ),
                    severity="warning",
                    occurred_at=due_at,
                    client_event_id=client_event_id,
                    route_id=route.id,
                    control_point_id=point_id,
                    request=request,
                )
            )
    return generated


@router.get("/objects")
def list_owks_objects(
    db: Session = Depends(get_db),
    principal=Depends(require_permission("owks.read")),
) -> list[dict[str, object]]:
    query = select(SecurityObject).where(SecurityObject.archived_at.is_(None))
    if "objects.read_all" not in principal.permission_codes:
        query = query.where(
            SecurityObject.assignments.any(ObjectAssignment.user_id == principal.user.id)
        )
    return [
        {"id": obj.id, "code": obj.code, "name": obj.name}
        for obj in db.scalars(query.order_by(SecurityObject.name)).all()
    ]


@router.get(
    "/objects/{object_id}/control-points",
    response_model=list[OWKSControlPointRead],
    response_model_exclude_none=True,
)
def list_control_points(
    object_id: UUID,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("owks.read")),
) -> list[OWKSControlPointRead]:
    get_object_or_404(db, object_id, principal)
    points = db.scalars(
        select(OWKSControlPoint)
        .where(OWKSControlPoint.object_id == object_id, OWKSControlPoint.is_active.is_(True))
        .order_by(OWKSControlPoint.name)
    ).all()
    return [
        OWKSControlPointRead(
            id=point.id,
            object_id=point.object_id,
            name=point.name,
            identifier_type=point.identifier_type,
            is_active=point.is_active,
            created_at=as_utc(point.created_at),
        )
        for point in points
    ]


@router.post(
    "/objects/{object_id}/control-points",
    response_model=OWKSControlPointRead,
    status_code=status.HTTP_201_CREATED,
)
def create_control_point(
    object_id: UUID,
    payload: OWKSControlPointCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("owks.manage")),
) -> OWKSControlPointRead:
    get_object_or_404(db, object_id, principal, for_write=True)
    credential = secrets.token_urlsafe(32)
    point = OWKSControlPoint(
        object_id=object_id,
        name=payload.name,
        identifier_type=payload.identifier_type,
        identifier_hash=hashlib.sha256(credential.encode()).hexdigest(),
        created_by_id=principal.user.id,
    )
    db.add(point)
    db.flush()
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="owks.control_point_created",
        entity_type="owks_control_point",
        entity_id=str(point.id),
        ip_address=request.client.host if request.client else None,
        details={"object_id": str(object_id), "identifier_type": point.identifier_type},
    )
    commit_or_conflict(db)
    return OWKSControlPointRead.model_validate({**point.__dict__, "credential": credential})


@router.get("/objects/{object_id}/routes", response_model=list[OWKSRouteRead])
def list_routes(
    object_id: UUID,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("owks.read")),
) -> list[OWKSRouteRead]:
    get_object_or_404(db, object_id, principal)
    routes = db.scalars(
        select(OWKSRoute)
        .where(OWKSRoute.object_id == object_id, OWKSRoute.is_active.is_(True))
        .order_by(OWKSRoute.name)
    ).all()
    result = []
    for route in routes:
        point_ids = db.scalars(
            select(OWKSRoutePoint.control_point_id)
            .where(OWKSRoutePoint.route_id == route.id)
            .order_by(OWKSRoutePoint.position)
        ).all()
        result.append(
            OWKSRouteRead(
                id=route.id,
                object_id=route.object_id,
                name=route.name,
                interval_minutes=route.interval_minutes,
                is_active=route.is_active,
                control_point_ids=point_ids,
                created_at=as_utc(route.created_at),
            )
        )
    return result


@router.post(
    "/objects/{object_id}/routes",
    response_model=OWKSRouteRead,
    status_code=status.HTTP_201_CREATED,
)
def create_route(
    object_id: UUID,
    payload: OWKSRouteCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("owks.manage")),
) -> OWKSRouteRead:
    get_object_or_404(db, object_id, principal, for_write=True)
    points = db.scalars(
        select(OWKSControlPoint).where(
            OWKSControlPoint.id.in_(payload.control_point_ids),
            OWKSControlPoint.object_id == object_id,
            OWKSControlPoint.is_active.is_(True),
        )
    ).all()
    if len(points) != len(payload.control_point_ids):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Ungültiger Kontrollpunkt für das Objekt"
        )
    route = OWKSRoute(
        object_id=object_id,
        name=payload.name.strip(),
        interval_minutes=payload.interval_minutes,
        created_by_id=principal.user.id,
    )
    db.add(route)
    db.flush()
    db.add_all(
        OWKSRoutePoint(route_id=route.id, control_point_id=point_id, position=position)
        for position, point_id in enumerate(payload.control_point_ids)
    )
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="owks.route_created",
        entity_type="owks_route",
        entity_id=str(route.id),
        ip_address=request.client.host if request.client else None,
        details={
            "object_id": str(object_id),
            "control_point_ids": [str(i) for i in payload.control_point_ids],
        },
    )
    commit_or_conflict(db)
    return OWKSRouteRead(
        id=route.id,
        object_id=route.object_id,
        name=route.name,
        interval_minutes=route.interval_minutes,
        is_active=route.is_active,
        control_point_ids=payload.control_point_ids,
        created_at=as_utc(route.created_at),
    )


@router.post("/objects/{object_id}/challenges", response_model=OWKSChallengeRead)
def create_challenge(
    object_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    principal=Depends(require_owks_write),
) -> OWKSChallengeRead:
    get_object_or_404(db, object_id, principal)
    challenge = OWKSChallenge(
        object_id=object_id,
        user_id=principal.user.id,
        expires_at=now_utc() + timedelta(minutes=5),
    )
    db.add(challenge)
    db.flush()
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="owks.challenge_issued",
        entity_type="owks_challenge",
        entity_id=str(challenge.id),
        ip_address=request.client.host if request.client else None,
        details={"object_id": str(object_id)},
    )
    db.commit()
    return OWKSChallengeRead(
        id=challenge.id,
        object_id=challenge.object_id,
        expires_at=as_utc(challenge.expires_at),
    )


@router.post("/scans", response_model=OWKSEventRead, status_code=status.HTTP_201_CREATED)
def record_scan(
    payload: OWKSScanCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal=Depends(require_owks_write),
) -> OWKSEventRead:
    employee = get_active_employee(db, principal.user.id)
    existing = db.scalar(
        select(OWKSEvent).where(
            OWKSEvent.actor_id == principal.user.id,
            OWKSEvent.client_event_id == payload.client_event_id,
        )
    )
    if existing is not None:
        get_object_or_404(db, existing.object_id, principal)
        point = db.scalar(
            select(OWKSControlPoint).where(
                OWKSControlPoint.identifier_hash
                == hashlib.sha256(payload.credential.encode()).hexdigest(),
                OWKSControlPoint.is_active.is_(True),
            )
        )
        if (
            existing.challenge_id == payload.challenge_id
            and existing.event_type == "control"
            and existing.control_point_id == (point.id if point is not None else None)
            and existing.route_id == payload.route_id
            and (
                payload.occurred_at is None
                or as_utc(existing.occurred_at) == payload.occurred_at.astimezone(UTC)
            )
        ):
            return event_read(db, existing)
        raise HTTPException(status.HTTP_409_CONFLICT, "Idempotenzschlüssel wurde bereits verwendet")

    challenge = db.scalar(
        select(OWKSChallenge)
        .where(OWKSChallenge.id == payload.challenge_id, OWKSChallenge.user_id == principal.user.id)
        .with_for_update()
    )
    if challenge is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kontrollanforderung nicht gefunden")
    get_object_or_404(db, challenge.object_id, principal)
    current_time = now_utc()
    if challenge.consumed_at is not None:
        log_manipulation(
            db,
            object_id=challenge.object_id,
            actor_id=principal.user.id,
            title="Wiederverwendung einer Kontrollanforderung",
            request=request,
        )
        raise HTTPException(status.HTTP_409_CONFLICT, "Kontrollanforderung wurde bereits verwendet")
    if as_utc(challenge.expires_at) <= current_time:
        log_manipulation(
            db,
            object_id=challenge.object_id,
            actor_id=principal.user.id,
            title="Abgelaufene Kontrollanforderung",
            request=request,
        )
        raise HTTPException(status.HTTP_409_CONFLICT, "Kontrollanforderung ist abgelaufen")

    credential_hash = hashlib.sha256(payload.credential.encode()).hexdigest()
    point = db.scalar(
        select(OWKSControlPoint).where(
            OWKSControlPoint.identifier_hash == credential_hash,
            OWKSControlPoint.is_active.is_(True),
        )
    )
    if point is None or point.object_id != challenge.object_id:
        log_manipulation(
            db,
            object_id=challenge.object_id,
            actor_id=principal.user.id,
            title="Unbekannter Kontrollpunkt oder fremdes Objekt",
            request=request,
        )
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Kontrollpunkt ist ungültig oder gehört zu einem anderen Objekt",
        )

    if payload.route_id is not None:
        route_point = db.scalar(
            select(OWKSRoutePoint)
            .join(OWKSRoute, OWKSRoute.id == OWKSRoutePoint.route_id)
            .where(
                OWKSRoute.id == payload.route_id,
                OWKSRoute.object_id == challenge.object_id,
                OWKSRoute.is_active.is_(True),
                OWKSRoutePoint.control_point_id == point.id,
            )
        )
        if route_point is None:
            log_manipulation(
                db,
                object_id=challenge.object_id,
                actor_id=principal.user.id,
                title="Kontrollpunkt außerhalb der angegebenen Route",
                request=request,
            )
            raise HTTPException(status.HTTP_409_CONFLICT, "Kontrollpunkt gehört nicht zur Route")

    occurred_at = payload.occurred_at or current_time
    if abs((current_time - occurred_at.astimezone(UTC)).total_seconds()) > 300:
        log_manipulation(
            db,
            object_id=challenge.object_id,
            actor_id=principal.user.id,
            title="Abweichender Kontrollzeitstempel",
            request=request,
        )
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Kontrollzeitstempel liegt außerhalb des zulässigen Zeitfensters",
        )

    late = False
    if payload.route_id is not None:
        route = db.get(OWKSRoute, payload.route_id)
        previous_scan = db.scalar(
            select(OWKSEvent)
            .where(
                OWKSEvent.route_id == payload.route_id,
                OWKSEvent.control_point_id == point.id,
                OWKSEvent.event_type == "control",
                OWKSEvent.sync_status == "synced",
                OWKSEvent.presence_verified.is_(True),
            )
            .order_by(OWKSEvent.occurred_at.desc())
            .limit(1)
        )
        due_at = (
            as_utc(previous_scan.occurred_at) + timedelta(minutes=route.interval_minutes)
            if previous_scan is not None
            else as_utc(route.created_at) + timedelta(minutes=route.interval_minutes)
        )
        late = as_utc(occurred_at) > due_at

    challenge.consumed_at = current_time
    event = create_event(
        db,
        object_id=challenge.object_id,
        employee_id=employee.id,
        actor_id=principal.user.id,
        event_type="control",
        title=f"{'Verspätete Kennung' if late else 'Kennung erkannt'}: {point.name}",
        description=(
            f"{point.identifier_type.upper()}-Kennung wurde vom Server mit der aktiven Challenge abgeglichen. "
            "Die physische Anwesenheit ist nicht bestätigt. "
            f"{'Die Kennung wurde nach dem vorgesehenen Zeitfenster eingereicht.' if late else ''}"
        ),
        severity="warning" if late else "info",
        occurred_at=occurred_at,
        client_event_id=payload.client_event_id,
        route_id=payload.route_id,
        control_point_id=point.id,
        challenge_id=challenge.id,
        presence_verified=False,
        request=request,
    )
    commit_or_conflict(db)
    return event_read(db, event)


@router.get("/objects/{object_id}/events", response_model=list[OWKSEventRead])
def list_events(
    object_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal=Depends(require_permission("owks.read")),
) -> list[OWKSEventRead]:
    get_object_or_404(db, object_id, principal)
    events = db.scalars(
        select(OWKSEvent)
        .where(OWKSEvent.object_id == object_id)
        .order_by(OWKSEvent.occurred_at.desc(), OWKSEvent.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [event_read(db, event) for event in events]


@router.get("/events/{event_id}", response_model=OWKSEventRead)
def get_event(
    event_id: UUID,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("owks.read")),
) -> OWKSEventRead:
    event = db.get(OWKSEvent, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wachbuchereignis nicht gefunden")
    get_object_or_404(db, event.object_id, principal)
    return event_read(db, event)


@router.post("/routes/{route_id}/monitor", response_model=list[OWKSEventRead])
def monitor_route(
    route_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("owks.manage")),
) -> list[OWKSEventRead]:
    route = db.get(OWKSRoute, route_id)
    if route is None or not route.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kontrollroute nicht gefunden")
    get_object_or_404(db, route.object_id, principal, for_write=True)
    generated = monitor_due_routes(
        db,
        route_id=route.id,
        actor_id=principal.user.id,
        request=request,
        acquire_lock=True,
    )
    commit_or_conflict(db)
    return [event_read(db, event) for event in generated]


def validate_event_writer(db: Session, object_id: UUID, principal) -> Employee | None:
    require_write_access(principal)
    get_object_or_404(db, object_id, principal, for_write=True)
    if not can_manage(principal):
        return get_active_employee(db, principal.user.id)
    return db.scalar(
        select(Employee).where(
            Employee.user_id == principal.user.id,
            Employee.archived_at.is_(None),
            Employee.employment_status == "active",
        )
    )


@router.post("/events", response_model=OWKSEventRead, status_code=status.HTTP_201_CREATED)
def create_log_event(
    payload: OWKSEventCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal=Depends(require_owks_write),
) -> OWKSEventRead:
    employee = validate_event_writer(db, payload.object_id, principal)
    existing = db.scalar(
        select(OWKSEvent).where(
            OWKSEvent.actor_id == principal.user.id,
            OWKSEvent.client_event_id == payload.client_event_id,
        )
    )
    if existing is not None:
        if (
            existing.object_id == payload.object_id
            and existing.event_type == payload.event_type
            and existing.title == payload.title
            and existing.description == payload.description
            and existing.severity == payload.severity
            and (
                payload.occurred_at is None
                or as_utc(existing.occurred_at) == payload.occurred_at.astimezone(UTC)
            )
        ):
            return event_read(db, existing)
        raise HTTPException(status.HTTP_409_CONFLICT, "Idempotenzschlüssel wurde bereits verwendet")
    event = create_event(
        db,
        object_id=payload.object_id,
        employee_id=employee.id if employee is not None else None,
        actor_id=principal.user.id,
        event_type=payload.event_type,
        title=payload.title,
        description=payload.description,
        severity=payload.severity,
        occurred_at=payload.occurred_at or now_utc(),
        client_event_id=payload.client_event_id,
        request=request,
    )
    commit_or_conflict(db)
    return event_read(db, event)


@router.post("/events/sync", response_model=list[OWKSSyncResult])
def sync_offline_events(
    payload: list[OWKSSyncEventCreate],
    request: Request,
    db: Session = Depends(get_db),
    principal=Depends(require_owks_write),
) -> list[OWKSSyncResult]:
    if len(payload) > 100:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "Pro Synchronisierung sind höchstens 100 Ereignisse erlaubt",
        )
    results: list[OWKSSyncResult] = []
    for item in payload:
        employee = validate_event_writer(db, item.object_id, principal)
        existing = db.scalar(
            select(OWKSEvent).where(
                OWKSEvent.actor_id == principal.user.id,
                OWKSEvent.client_event_id == item.client_event_id,
            )
        )
        if existing is not None:
            expected_type = "deviation" if item.event_type == "control" else item.event_type
            expected_title = (
                f"Offline nicht verifizierte Kontrolle: {item.title}"
                if item.event_type == "control"
                else item.title
            )
            expected_description = (
                f"Offline-Kontrolle nicht verifiziert. Sichtbare Konfliktbehandlung erforderlich. {item.description}"
                if item.event_type == "control"
                else item.description
            )
            expected_severity = "warning" if item.event_type == "control" else item.severity
            same_payload = (
                existing.object_id == item.object_id
                and existing.title == expected_title
                and existing.description == expected_description
                and existing.severity == expected_severity
                and existing.event_type == expected_type
                and as_utc(existing.occurred_at) == item.occurred_at.astimezone(UTC)
                and existing.sync_status
                == ("conflict" if item.event_type == "control" else "synced")
            )
            if same_payload:
                results.append(
                    OWKSSyncResult(
                        client_event_id=item.client_event_id,
                        status="duplicate",
                        event=event_read(db, existing),
                    )
                )
            else:
                results.append(
                    OWKSSyncResult(
                        client_event_id=item.client_event_id,
                        status="conflict",
                        detail="Idempotenzschlüssel wurde mit abweichenden Daten erneut verwendet.",
                    )
                )
            continue
        is_unverified_control = item.event_type == "control"
        event = create_event(
            db,
            object_id=item.object_id,
            employee_id=employee.id if employee is not None else None,
            actor_id=principal.user.id,
            event_type="deviation" if is_unverified_control else item.event_type,
            title=f"Offline nicht verifizierte Kontrolle: {item.title}"
            if is_unverified_control
            else item.title,
            description=(
                f"Offline-Kontrolle nicht verifiziert. Sichtbare Konfliktbehandlung erforderlich. {item.description}"
                if is_unverified_control
                else item.description
            ),
            severity="warning" if is_unverified_control else item.severity,
            occurred_at=item.occurred_at,
            client_event_id=item.client_event_id,
            sync_status="conflict" if is_unverified_control else "synced",
            request=request,
        )
        results.append(
            OWKSSyncResult(
                client_event_id=item.client_event_id,
                status="conflict" if is_unverified_control else "synced",
                event=event_read(db, event),
                detail="Offline-Kontrollen müssen vor Ort mit einer frischen Serveranforderung verifiziert werden."
                if is_unverified_control
                else None,
            )
        )
    commit_or_conflict(db)
    return results


@router.post("/events/{event_id}/status", response_model=OWKSEventRead)
def update_event_status(
    event_id: UUID,
    payload: OWKSEventStateUpdate,
    request: Request,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("owks.manage")),
) -> OWKSEventRead:
    event = db.scalar(select(OWKSEvent).where(OWKSEvent.id == event_id).with_for_update())
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wachbuchereignis nicht gefunden")
    get_object_or_404(db, event.object_id, principal, for_write=True)
    last_sequence = (
        db.scalar(
            select(func.max(OWKSEventStatus.sequence_no)).where(
                OWKSEventStatus.event_id == event.id
            )
        )
        or 0
    )
    db.add(
        OWKSEventStatus(
            event_id=event.id,
            sequence_no=last_sequence + 1,
            status=payload.status,
            note=payload.note.strip(),
            actor_id=principal.user.id,
        )
    )
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="owks.event_status_changed",
        entity_type="owks_event",
        entity_id=str(event.id),
        ip_address=request.client.host if request.client else None,
        details={"status": payload.status},
    )
    commit_or_conflict(db)
    return event_read(db, event)


@router.post("/events/{event_id}/corrections", response_model=OWKSEventRead, status_code=201)
def correct_event(
    event_id: UUID,
    payload: OWKSEventCorrectionCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("owks.manage")),
) -> OWKSEventRead:
    original = db.scalar(select(OWKSEvent).where(OWKSEvent.id == event_id))
    if original is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wachbuchereignis nicht gefunden")
    get_object_or_404(db, original.object_id, principal, for_write=True)
    existing = db.scalar(
        select(OWKSEvent).where(
            OWKSEvent.actor_id == principal.user.id,
            OWKSEvent.client_event_id == payload.client_event_id,
        )
    )
    if existing is not None:
        if (
            existing.event_type == "correction"
            and existing.corrects_event_id == original.id
            and existing.description == payload.reason
        ):
            return event_read(db, existing)
        raise HTTPException(status.HTTP_409_CONFLICT, "Idempotenzschlüssel wurde bereits verwendet")
    correction = create_event(
        db,
        object_id=original.object_id,
        employee_id=None,
        actor_id=principal.user.id,
        event_type="correction",
        title=f"Korrektur zu {original.title}",
        description=payload.reason,
        severity=original.severity,
        occurred_at=now_utc(),
        client_event_id=payload.client_event_id,
        corrects_event_id=original.id,
        request=request,
    )
    commit_or_conflict(db)
    return event_read(db, correction)


@router.post("/events/{event_id}/attachments", response_model=OWKSAttachmentRead, status_code=201)
def upload_attachment(
    event_id: UUID,
    request: Request,
    document: UploadFile = File(),
    db: Session = Depends(get_db),
    principal=Depends(require_owks_write),
) -> OWKSAttachmentRead:
    event = db.scalar(select(OWKSEvent).where(OWKSEvent.id == event_id))
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wachbuchereignis nicht gefunden")
    require_write_access(principal)
    get_object_or_404(db, event.object_id, principal, for_write=True)
    extension = PurePosixPath((document.filename or "").replace("\\", "/")).suffix.lower()
    allowed = ATTACHMENT_TYPES.get(extension)
    declared = (document.content_type or "").split(";", maxsplit=1)[0].lower()
    if allowed is None or declared != allowed[0]:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Erlaubt sind PDF-, PNG- und JPEG-Dateien"
        )
    content = document.file.read(MAX_ATTACHMENT_SIZE + 1)
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Die Datei darf nicht leer sein")
    if len(content) > MAX_ATTACHMENT_SIZE:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, "Die Datei darf höchstens 10 MiB groß sein"
        )
    if not content.startswith(allowed[1]):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Dateiinhalt und Dateityp stimmen nicht überein"
        )
    file_name = PurePosixPath((document.filename or "").replace("\\", "/")).name
    if not file_name or len(file_name) > 200 or any(ord(char) < 32 for char in file_name):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Ungültiger Dateiname")
    scan_upload_or_reject(
        db, request, content=content, actor_id=principal.user.id, surface="owks_attachment"
    )
    attachment_id = uuid4()
    storage_key = attachment_id.hex
    attachment = OWKSAttachment(
        id=attachment_id,
        event_id=event.id,
        file_name=file_name,
        media_type=allowed[0],
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        storage_key=storage_key,
        content=None,
        uploaded_by_id=principal.user.id,
    )
    file_created = False
    commit_attempted = False
    try:
        db.add(attachment)
        db.flush()
        store_file(storage_key, content)
        file_created = True
        add_audit_entry(
            db,
            actor_id=principal.user.id,
            action="owks.attachment_uploaded",
            entity_type="owks_event",
            entity_id=str(event.id),
            ip_address=request.client.host if request.client else None,
            details={"attachment_id": str(attachment.id), "size_bytes": len(content)},
        )
        commit_attempted = True
        commit_or_conflict(db)
    except Exception as exc:
        db.rollback()
        if file_created and (
            not commit_attempted or (isinstance(exc, HTTPException) and exc.status_code == 409)
        ):
            remove_file(storage_key)
        raise
    return OWKSAttachmentRead(
        id=attachment.id,
        event_id=attachment.event_id,
        file_name=attachment.file_name,
        media_type=attachment.media_type,
        size_bytes=attachment.size_bytes,
        sha256=attachment.sha256,
        uploaded_by_id=attachment.uploaded_by_id,
        created_at=as_utc(attachment.created_at),
    )


@router.get("/events/{event_id}/attachments", response_model=list[OWKSAttachmentRead])
def list_attachments(
    event_id: UUID,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("owks.read")),
) -> list[OWKSAttachmentRead]:
    event = db.scalar(select(OWKSEvent).where(OWKSEvent.id == event_id))
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wachbuchereignis nicht gefunden")
    get_object_or_404(db, event.object_id, principal)
    attachments = db.scalars(
        select(OWKSAttachment)
        .where(OWKSAttachment.event_id == event.id)
        .order_by(OWKSAttachment.created_at)
    ).all()
    return [
        OWKSAttachmentRead(
            id=item.id,
            event_id=item.event_id,
            file_name=item.file_name,
            media_type=item.media_type,
            size_bytes=item.size_bytes,
            sha256=item.sha256,
            uploaded_by_id=item.uploaded_by_id,
            created_at=as_utc(item.created_at),
        )
        for item in attachments
    ]


@router.get("/events/{event_id}/attachments/{attachment_id}")
def get_attachment(
    event_id: UUID,
    attachment_id: UUID,
    download: bool = Query(default=False),
    db: Session = Depends(get_db),
    principal=Depends(require_permission("owks.read")),
) -> Response:
    stored = db.scalar(
        select(OWKSAttachment)
        .join(OWKSEvent, OWKSEvent.id == OWKSAttachment.event_id)
        .where(OWKSAttachment.id == attachment_id, OWKSAttachment.event_id == event_id)
    )
    if stored is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anlage nicht gefunden")
    get_object_or_404(db, stored_event_object_id(db, event_id), principal)
    disposition = "attachment" if download else "inline"
    filename = PurePosixPath(stored.file_name).suffix.lower()
    return Response(
        content=read_attachment(stored.storage_key, stored.content),
        media_type=stored.media_type,
        headers={
            "Content-Disposition": f"{disposition}; filename=\"anlage{filename}\"; filename*=UTF-8''{quote(stored.file_name, safe='')}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'",
        },
    )


def stored_event_object_id(db: Session, event_id: UUID) -> UUID:
    object_id = db.scalar(select(OWKSEvent.object_id).where(OWKSEvent.id == event_id))
    if object_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wachbuchereignis nicht gefunden")
    return object_id
