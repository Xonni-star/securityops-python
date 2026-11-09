from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.auth import add_audit_entry, require_permission
from app.database import get_db
from app.models import (
    Employee,
    KeyMovement,
    ObjectAssignment,
    PhysicalKey,
    SecurityObject,
    User,
)
from app.notifications_service import enqueue_key_issued_event
from app.schemas import (
    KeyEmployeeCandidate,
    KeyMovementCreate,
    KeyMovementPage,
    KeyMovementRead,
    KeyObjectCandidate,
    KeyStatus,
    PhysicalKeyCreate,
    PhysicalKeyPage,
    PhysicalKeyRead,
    PhysicalKeyUpdate,
)

router = APIRouter()


def has_object_assignment(db: Session, object_id: UUID, user_id: UUID) -> bool:
    return (
        db.scalar(
            select(ObjectAssignment.id).where(
                ObjectAssignment.object_id == object_id,
                ObjectAssignment.user_id == user_id,
            )
        )
        is not None
    )


def ensure_object_access(db: Session, object_id: UUID, principal) -> SecurityObject:
    obj = db.get(SecurityObject, object_id)
    if obj is None or (
        "objects.read_all" not in principal.permission_codes
        and "objects.manage_all" not in principal.permission_codes
        and not has_object_assignment(db, object_id, principal.user.id)
    ):
        raise HTTPException(status_code=404, detail="Objekt nicht gefunden")
    return obj


def ensure_object_management(db: Session, obj: SecurityObject, principal) -> None:
    if "objects.manage_all" in principal.permission_codes:
        return
    if "objects.manage" not in principal.permission_codes or not has_object_assignment(
        db, obj.id, principal.user.id
    ):
        raise HTTPException(status_code=403, detail="Keine Berechtigung für dieses Objekt")


def key_query():
    return select(PhysicalKey).options(
        joinedload(PhysicalKey.object),
        joinedload(PhysicalKey.current_employee),
    )


def get_key_or_404(
    db: Session,
    key_id: UUID,
    principal,
    *,
    for_update: bool = False,
) -> PhysicalKey:
    query = key_query().where(PhysicalKey.id == key_id)
    if not {"objects.read_all", "objects.manage_all"} & principal.permission_codes:
        query = query.where(
            PhysicalKey.object_id.in_(
                select(ObjectAssignment.object_id).where(
                    ObjectAssignment.user_id == principal.user.id
                )
            )
        )
    if for_update:
        query = query.with_for_update(of=PhysicalKey)
    key = db.scalar(query)
    if key is None:
        raise HTTPException(status_code=404, detail="Schlüssel nicht gefunden")
    return key


def key_read(key: PhysicalKey) -> PhysicalKeyRead:
    return PhysicalKeyRead(
        id=key.id,
        key_number=key.key_number,
        description=key.description,
        object_id=key.object_id,
        object_code=key.object.code,
        object_name=key.object.name,
        status=key.status,
        current_employee_id=key.current_employee_id,
        current_employee_name=key.current_employee.full_name if key.current_employee else None,
        archived_at=key.archived_at,
        created_at=key.created_at,
        updated_at=key.updated_at,
    )


@router.get("/keys/objects", response_model=list[KeyObjectCandidate])
def list_key_objects(
    db: Session = Depends(get_db),
    principal=Depends(require_permission("keys.read")),
) -> list[KeyObjectCandidate]:
    query = select(SecurityObject).where(SecurityObject.archived_at.is_(None))
    if not {"objects.read_all", "objects.manage_all"} & principal.permission_codes:
        query = query.where(
            SecurityObject.assignments.any(ObjectAssignment.user_id == principal.user.id)
        )
    objects = db.scalars(query.order_by(SecurityObject.name, SecurityObject.code)).all()
    return [KeyObjectCandidate(id=obj.id, code=obj.code, name=obj.name) for obj in objects]


def movement_read(movement: KeyMovement) -> KeyMovementRead:
    return KeyMovementRead(
        id=movement.id,
        key_id=movement.key_id,
        key_number=movement.key.key_number,
        object_id=movement.object_id,
        employee_id=movement.employee_id,
        employee_name=movement.employee.full_name if movement.employee else None,
        actor_id=movement.actor_id,
        actor_name=movement.actor.full_name,
        movement_type=movement.movement_type,
        key_status_after=movement.key_status_after,
        acknowledged_at=movement.acknowledged_at,
        acknowledgement_note=movement.acknowledgement_note,
        note=movement.note,
        created_at=movement.created_at,
    )


def commit_key_transaction(db: Session) -> None:
    try:
        db.flush()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Die Schlüsseländerung verletzt eine Datenbankbedingung",
        ) from exc


def flush_key_transaction(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Die Schlüsseländerung verletzt eine Datenbankbedingung",
        ) from exc


def record_key_audit(
    db: Session,
    *,
    principal,
    request: Request,
    action: str,
    key: PhysicalKey,
    details: dict[str, object] | None = None,
) -> None:
    audit_details = {"key_number": key.key_number}
    if details:
        audit_details.update(details)
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action=f"keys.{action}",
        entity_type="physical_key",
        entity_id=str(key.id),
        ip_address=request.client.host if request.client else None,
        details=audit_details,
    )


@router.get("/keys", response_model=PhysicalKeyPage)
def list_keys(
    q: str | None = Query(default=None, max_length=200),
    key_status: KeyStatus | None = Query(default=None, alias="status"),
    object_id: UUID | None = None,
    employee_id: UUID | None = None,
    include_archived: bool = False,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal=Depends(require_permission("keys.read")),
) -> PhysicalKeyPage:
    query = key_query()
    count_query = select(func.count()).select_from(PhysicalKey)
    filters = []
    if not include_archived and key_status != "archived":
        filters.append(PhysicalKey.archived_at.is_(None))
    if key_status is not None:
        filters.append(PhysicalKey.status == key_status)
    if object_id is not None:
        filters.append(PhysicalKey.object_id == object_id)
    if employee_id is not None:
        filters.append(PhysicalKey.current_employee_id == employee_id)
    if not {"objects.read_all", "objects.manage_all"} & principal.permission_codes:
        accessible_object_ids = select(ObjectAssignment.object_id).where(
            ObjectAssignment.user_id == principal.user.id
        )
        filters.append(PhysicalKey.object_id.in_(accessible_object_ids))
    if q and q.strip():
        term = f"%{q.strip()}%"
        filters.append(
            or_(
                PhysicalKey.key_number.ilike(term),
                PhysicalKey.description.ilike(term),
                PhysicalKey.object_id.in_(
                    select(SecurityObject.id).where(
                        or_(SecurityObject.code.ilike(term), SecurityObject.name.ilike(term))
                    )
                ),
            )
        )
    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)
    total = db.scalar(count_query) or 0
    keys = (
        db.scalars(query.order_by(PhysicalKey.key_number).limit(limit).offset(offset))
        .unique()
        .all()
    )
    return PhysicalKeyPage(
        items=[key_read(key) for key in keys], total=total, limit=limit, offset=offset
    )


@router.post("/keys", response_model=PhysicalKeyRead, status_code=status.HTTP_201_CREATED)
def create_key(
    payload: PhysicalKeyCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("keys.manage")),
) -> PhysicalKeyRead:
    obj = ensure_object_access(db, payload.object_id, principal)
    ensure_object_management(db, obj, principal)
    if obj.archived_at is not None:
        raise HTTPException(
            status_code=409, detail="Archivierte Objekte können keine Schlüssel erhalten"
        )
    key = PhysicalKey(
        key_number=payload.key_number,
        description=payload.description,
        object_id=obj.id,
        created_by_id=principal.user.id,
    )
    db.add(key)
    flush_key_transaction(db)
    record_key_audit(
        db,
        principal=principal,
        request=request,
        action="created",
        key=key,
        details={"fields": ["key_number", "description", "object_id"]},
    )
    commit_key_transaction(db)
    db.refresh(key)
    return key_read(key)


@router.patch("/keys/{key_id}", response_model=PhysicalKeyRead)
def update_key(
    key_id: UUID,
    payload: PhysicalKeyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("keys.manage")),
) -> PhysicalKeyRead:
    key = get_key_or_404(db, key_id, principal, for_update=True)
    obj = ensure_object_access(db, key.object_id, principal)
    ensure_object_management(db, obj, principal)
    if key.archived_at is not None:
        raise HTTPException(
            status_code=409, detail="Archivierte Schlüssel können nicht geändert werden"
        )
    key.description = payload.description
    record_key_audit(
        db,
        principal=principal,
        request=request,
        action="updated",
        key=key,
        details={"fields": ["description"]},
    )
    commit_key_transaction(db)
    db.refresh(key)
    return key_read(key)


@router.post("/keys/{key_id}/archive", response_model=PhysicalKeyRead)
def archive_key(
    key_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("keys.manage")),
) -> PhysicalKeyRead:
    key = get_key_or_404(db, key_id, principal, for_update=True)
    obj = ensure_object_access(db, key.object_id, principal)
    ensure_object_management(db, obj, principal)
    if key.archived_at is not None:
        raise HTTPException(status_code=409, detail="Der Schlüssel ist bereits archiviert")
    if key.status == "issued":
        raise HTTPException(
            status_code=409, detail="Ausgegebene Schlüssel müssen zuerst zurückgegeben werden"
        )
    key.status = "archived"
    key.archived_at = datetime.now(UTC)
    record_key_audit(db, principal=principal, request=request, action="archived", key=key)
    commit_key_transaction(db)
    db.refresh(key)
    return key_read(key)


@router.get("/keys/eligible-employees", response_model=list[KeyEmployeeCandidate])
def list_eligible_employees(
    object_id: UUID,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("keys.move")),
) -> list[KeyEmployeeCandidate]:
    ensure_object_access(db, object_id, principal)
    employees = (
        db.scalars(
            select(Employee)
            .join(User, Employee.user_id == User.id)
            .join(ObjectAssignment, ObjectAssignment.user_id == User.id)
            .where(
                ObjectAssignment.object_id == object_id,
                Employee.employment_status == "active",
                Employee.archived_at.is_(None),
                User.is_active.is_(True),
            )
            .order_by(Employee.full_name, Employee.employee_number)
        )
        .unique()
        .all()
    )
    return [
        KeyEmployeeCandidate(
            id=employee.id,
            employee_number=employee.employee_number,
            full_name=employee.full_name,
        )
        for employee in employees
    ]


@router.post(
    "/keys/{key_id}/movements",
    response_model=KeyMovementRead,
    status_code=status.HTTP_201_CREATED,
)
def create_key_movement(
    key_id: UUID,
    payload: KeyMovementCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("keys.move")),
) -> KeyMovementRead:
    key = get_key_or_404(db, key_id, principal, for_update=True)
    ensure_object_access(db, key.object_id, principal)
    if key.archived_at is not None or key.status == "archived":
        raise HTTPException(
            status_code=409, detail="Archivierte Schlüssel können nicht bewegt werden"
        )

    now = datetime.now(UTC)
    employee_id: UUID | None = None
    acknowledged_at = None
    acknowledgement_note = None
    if payload.movement_type == "issued":
        if key.status != "available":
            raise HTTPException(
                status_code=409, detail="Nur verfügbare Schlüssel können ausgegeben werden"
            )
        employee = db.scalar(
            select(Employee)
            .join(User, Employee.user_id == User.id)
            .join(ObjectAssignment, ObjectAssignment.user_id == User.id)
            .where(
                Employee.id == payload.employee_id,
                Employee.employment_status == "active",
                Employee.archived_at.is_(None),
                User.is_active.is_(True),
                ObjectAssignment.object_id == key.object_id,
            )
            .with_for_update(of=(Employee, User, ObjectAssignment))
        )
        if employee is None:
            raise HTTPException(
                status_code=422,
                detail="Der Mitarbeiter muss aktiv sein und dem Schlüsselobjekt zugewiesen sein",
            )
        employee_id = employee.id
        key.current_employee = employee
        acknowledged_at = now
        acknowledgement_note = payload.acknowledgement_note
        key.status = "issued"
        key.current_employee_id = employee.id
    elif payload.movement_type == "returned":
        if key.status != "issued" or key.current_employee_id is None:
            raise HTTPException(
                status_code=409, detail="Nur ausgegebene Schlüssel können zurückgenommen werden"
            )
        employee_id = key.current_employee_id
        movement_employee = key.current_employee
        key.current_employee = None
        key.current_employee_id = None
        key.status = "available"
    elif payload.movement_type == "lost":
        if key.status not in {"available", "issued"}:
            raise HTTPException(
                status_code=409, detail="Dieser Schlüssel kann nicht als verloren gemeldet werden"
            )
        if not payload.note:
            raise HTTPException(
                status_code=422, detail="Für eine Verlustmeldung ist eine Notiz erforderlich"
            )
        employee_id = key.current_employee_id
        movement_employee = key.current_employee
        key.current_employee = None
        key.current_employee_id = None
        key.status = "lost"
    elif payload.movement_type == "defective":
        if key.status not in {"available", "issued"}:
            raise HTTPException(
                status_code=409, detail="Dieser Schlüssel kann nicht als defekt gemeldet werden"
            )
        if not payload.note:
            raise HTTPException(
                status_code=422, detail="Für eine Defektmeldung ist eine Notiz erforderlich"
            )
        employee_id = key.current_employee_id
        movement_employee = key.current_employee
        key.current_employee = None
        key.current_employee_id = None
        key.status = "defective"
    elif payload.movement_type == "inventory":
        if key.status not in {"available", "issued"}:
            raise HTTPException(
                status_code=409, detail="Dieser Schlüssel kann nicht inventarisiert werden"
            )
        employee_id = key.current_employee_id
        movement_employee = key.current_employee

    if payload.movement_type == "issued":
        movement_employee = employee
    elif payload.movement_type == "inventory":
        movement_employee = key.current_employee

    movement = KeyMovement(
        key=key,
        object_id=key.object_id,
        employee_id=employee_id,
        employee=movement_employee,
        actor_id=principal.user.id,
        movement_type=payload.movement_type,
        key_status_after=key.status,
        acknowledged_at=acknowledged_at,
        acknowledgement_note=acknowledgement_note,
        note=payload.note,
        created_at=now,
    )
    db.add(movement)
    flush_key_transaction(db)
    enqueue_key_issued_event(db, movement)
    record_key_audit(
        db,
        principal=principal,
        request=request,
        action=payload.movement_type,
        key=key,
        details={
            "movement_id": str(movement.id),
            "status_after": key.status,
            "employee_id": str(employee_id) if employee_id else None,
        },
    )
    commit_key_transaction(db)
    db.refresh(movement)
    return movement_read(movement)


@router.get("/keys/{key_id}/movements", response_model=KeyMovementPage)
def list_key_movements(
    key_id: UUID,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal=Depends(require_permission("keys.read")),
) -> KeyMovementPage:
    key = get_key_or_404(db, key_id, principal)
    query = (
        select(KeyMovement)
        .options(
            joinedload(KeyMovement.key),
            joinedload(KeyMovement.employee),
            joinedload(KeyMovement.actor),
        )
        .where(KeyMovement.key_id == key.id)
    )
    total = (
        db.scalar(select(func.count()).select_from(KeyMovement).where(KeyMovement.key_id == key.id))
        or 0
    )
    movements = (
        db.scalars(
            query.order_by(KeyMovement.created_at.desc(), KeyMovement.id)
            .limit(limit)
            .offset(offset)
        )
        .unique()
        .all()
    )
    return KeyMovementPage(
        items=[movement_read(movement) for movement in movements],
        total=total,
        limit=limit,
        offset=offset,
    )
