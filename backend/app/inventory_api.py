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
    InventoryAsset,
    InventoryEvent,
    ObjectAssignment,
    SecurityObject,
    User,
)
from app.schemas import (
    InventoryAssetCreate,
    InventoryAssetPage,
    InventoryAssetRead,
    InventoryAssetUpdate,
    InventoryCategory,
    InventoryCondition,
    InventoryEmployeeCandidate,
    InventoryEventCreate,
    InventoryEventPage,
    InventoryEventRead,
    InventoryObjectCandidate,
    InventoryStatus,
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


def lock_object_assignment(db: Session, object_id: UUID, user_id: UUID) -> bool:
    return (
        db.scalar(
            select(ObjectAssignment.id)
            .where(
                ObjectAssignment.object_id == object_id,
                ObjectAssignment.user_id == user_id,
            )
            .with_for_update()
        )
        is not None
    )


def has_global_object_access(principal) -> bool:
    return bool({"objects.read_all", "objects.manage_all"} & principal.permission_codes)


def ensure_object_access(db: Session, object_id: UUID | None, principal) -> SecurityObject | None:
    if object_id is None:
        if not has_global_object_access(principal):
            raise HTTPException(status_code=404, detail="Inventar nicht gefunden")
        return None
    obj = db.get(SecurityObject, object_id)
    if obj is None or (
        not has_global_object_access(principal)
        and not has_object_assignment(db, object_id, principal.user.id)
    ):
        raise HTTPException(status_code=404, detail="Objekt nicht gefunden")
    return obj


def ensure_object_management(db: Session, obj: SecurityObject | None, principal) -> None:
    if obj is None:
        if "objects.manage_all" not in principal.permission_codes:
            raise HTTPException(status_code=403, detail="Keine Berechtigung für dieses Inventar")
        return
    if "objects.manage_all" in principal.permission_codes:
        return
    if "objects.manage" not in principal.permission_codes or not lock_object_assignment(
        db, obj.id, principal.user.id
    ):
        raise HTTPException(status_code=403, detail="Keine Berechtigung für dieses Objekt")


def ensure_object_move_access(db: Session, object_id: UUID | None, principal) -> None:
    if object_id is None:
        if "objects.manage_all" not in principal.permission_codes:
            raise HTTPException(status_code=403, detail="Keine Berechtigung für dieses Inventar")
        return
    if "objects.manage_all" in principal.permission_codes:
        return
    if not lock_object_assignment(db, object_id, principal.user.id):
        raise HTTPException(status_code=403, detail="Keine Berechtigung für dieses Objekt")


def asset_query():
    return select(InventoryAsset).options(
        joinedload(InventoryAsset.object),
        joinedload(InventoryAsset.current_employee),
    )


def get_asset_or_404(
    db: Session,
    asset_id: UUID,
    principal,
    *,
    for_update: bool = False,
) -> InventoryAsset:
    query = asset_query().where(InventoryAsset.id == asset_id)
    if not has_global_object_access(principal):
        query = query.where(
            InventoryAsset.object_id.in_(
                select(ObjectAssignment.object_id).where(
                    ObjectAssignment.user_id == principal.user.id
                )
            )
        )
    if for_update:
        query = query.with_for_update(of=InventoryAsset)
    asset = db.scalar(query)
    if asset is None:
        raise HTTPException(status_code=404, detail="Inventar nicht gefunden")
    return asset


def asset_read(asset: InventoryAsset) -> InventoryAssetRead:
    return InventoryAssetRead(
        id=asset.id,
        asset_number=asset.asset_number,
        serial_number=asset.serial_number,
        name=asset.name,
        category=asset.category,
        condition=asset.condition,
        status=asset.status,
        location=asset.location,
        object_id=asset.object_id,
        object_code=asset.object.code if asset.object else None,
        object_name=asset.object.name if asset.object else None,
        current_employee_id=asset.current_employee_id,
        current_employee_name=asset.current_employee.full_name if asset.current_employee else None,
        archived_at=asset.archived_at,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


def event_read(event: InventoryEvent) -> InventoryEventRead:
    return InventoryEventRead(
        id=event.id,
        asset_id=event.asset_id,
        asset_number=event.asset.asset_number,
        object_id=event.object_id,
        object_name=event.object.name if event.object else None,
        from_object_id=event.from_object_id,
        from_object_name=event.from_object.name if event.from_object else None,
        to_object_id=event.to_object_id,
        to_object_name=event.to_object.name if event.to_object else None,
        from_employee_id=event.from_employee_id,
        from_employee_name=event.from_employee.full_name if event.from_employee else None,
        to_employee_id=event.to_employee_id,
        to_employee_name=event.to_employee.full_name if event.to_employee else None,
        actor_id=event.actor_id,
        actor_name=event.actor.full_name,
        event_type=event.event_type,
        status_after=event.status_after,
        condition_after=event.condition_after,
        location_after=event.location_after,
        acknowledged_at=event.acknowledged_at,
        acknowledgement_note=event.acknowledgement_note,
        note=event.note,
        created_at=event.created_at,
    )


def commit_inventory_transaction(db: Session) -> None:
    try:
        db.flush()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Die Inventaränderung verletzt eine Datenbankbedingung",
        ) from exc


def flush_inventory_transaction(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Die Inventaränderung verletzt eine Datenbankbedingung",
        ) from exc


def record_inventory_audit(
    db: Session,
    *,
    principal,
    request: Request,
    action: str,
    asset: InventoryAsset,
    details: dict[str, object] | None = None,
) -> None:
    audit_details = {"asset_number": asset.asset_number}
    if details:
        audit_details.update(details)
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action=f"inventory.{action}",
        entity_type="inventory_asset",
        entity_id=str(asset.id),
        ip_address=request.client.host if request.client else None,
        details=audit_details,
    )


def append_event(
    db: Session,
    *,
    asset: InventoryAsset,
    actor_id: UUID,
    event_type: str,
    now: datetime,
    from_employee_id: UUID | None = None,
    to_employee_id: UUID | None = None,
    from_object_id: UUID | None = None,
    to_object_id: UUID | None = None,
    acknowledged_at: datetime | None = None,
    acknowledgement_note: str | None = None,
    note: str | None = None,
) -> InventoryEvent:
    event = InventoryEvent(
        asset=asset,
        object_id=asset.object_id,
        from_object_id=from_object_id,
        to_object_id=to_object_id,
        from_employee_id=from_employee_id,
        to_employee_id=to_employee_id,
        actor_id=actor_id,
        event_type=event_type,
        status_after=asset.status,
        condition_after=asset.condition,
        location_after=asset.location,
        acknowledged_at=acknowledged_at,
        acknowledgement_note=acknowledgement_note,
        note=note,
        created_at=now,
    )
    db.add(event)
    return event


def require_active_employee(db: Session, employee_id: UUID, object_id: UUID | None) -> Employee:
    query = (
        select(Employee)
        .join(User, Employee.user_id == User.id)
        .where(
            Employee.id == employee_id,
            Employee.employment_status == "active",
            Employee.archived_at.is_(None),
            User.is_active.is_(True),
        )
        .with_for_update(of=(Employee, User))
    )
    if object_id is not None:
        query = (
            query.join(ObjectAssignment, ObjectAssignment.user_id == User.id)
            .where(ObjectAssignment.object_id == object_id)
            .with_for_update(of=(Employee, User, ObjectAssignment))
        )
    employee = db.scalar(query)
    if employee is None:
        raise HTTPException(
            status_code=422,
            detail="Der Mitarbeiter muss aktiv und dem Zielobjekt zugewiesen sein",
        )
    return employee


def event_options():
    return (
        joinedload(InventoryEvent.asset),
        joinedload(InventoryEvent.object),
        joinedload(InventoryEvent.from_object),
        joinedload(InventoryEvent.to_object),
        joinedload(InventoryEvent.from_employee),
        joinedload(InventoryEvent.to_employee),
        joinedload(InventoryEvent.actor),
    )


@router.get("/inventory/objects", response_model=list[InventoryObjectCandidate])
def list_inventory_objects(
    db: Session = Depends(get_db),
    principal=Depends(require_permission("inventory.read")),
) -> list[InventoryObjectCandidate]:
    query = select(SecurityObject).where(SecurityObject.archived_at.is_(None))
    if not has_global_object_access(principal):
        query = query.where(
            SecurityObject.assignments.any(ObjectAssignment.user_id == principal.user.id)
        )
    objects = db.scalars(query.order_by(SecurityObject.name, SecurityObject.code)).all()
    return [InventoryObjectCandidate(id=obj.id, code=obj.code, name=obj.name) for obj in objects]


@router.get("/inventory/eligible-employees", response_model=list[InventoryEmployeeCandidate])
def list_eligible_inventory_employees(
    object_id: UUID | None = None,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("inventory.move")),
) -> list[InventoryEmployeeCandidate]:
    ensure_object_access(db, object_id, principal)
    ensure_object_move_access(db, object_id, principal)
    query = (
        select(Employee)
        .join(User, Employee.user_id == User.id)
        .where(
            Employee.employment_status == "active",
            Employee.archived_at.is_(None),
            User.is_active.is_(True),
        )
    )
    if object_id is not None:
        query = query.join(ObjectAssignment, ObjectAssignment.user_id == User.id).where(
            ObjectAssignment.object_id == object_id
        )
    employees = (
        db.scalars(query.order_by(Employee.full_name, Employee.employee_number)).unique().all()
    )
    return [
        InventoryEmployeeCandidate(
            id=employee.id,
            employee_number=employee.employee_number,
            full_name=employee.full_name,
        )
        for employee in employees
    ]


@router.get("/inventory/employees", response_model=list[InventoryEmployeeCandidate])
def list_inventory_employees(
    db: Session = Depends(get_db),
    principal=Depends(require_permission("inventory.read")),
) -> list[InventoryEmployeeCandidate]:
    query = (
        select(Employee)
        .join(InventoryAsset, InventoryAsset.current_employee_id == Employee.id)
        .where(InventoryAsset.archived_at.is_(None))
    )
    if not has_global_object_access(principal):
        query = query.where(
            InventoryAsset.object_id.in_(
                select(ObjectAssignment.object_id).where(
                    ObjectAssignment.user_id == principal.user.id
                )
            )
        )
    employees = db.scalars(
        query.distinct().order_by(Employee.full_name, Employee.employee_number)
    ).all()
    return [
        InventoryEmployeeCandidate(
            id=employee.id,
            employee_number=employee.employee_number,
            full_name=employee.full_name,
        )
        for employee in employees
    ]


@router.get("/inventory/assets", response_model=InventoryAssetPage)
def list_inventory_assets(
    q: str | None = Query(default=None, max_length=200),
    category: InventoryCategory | None = None,
    condition: InventoryCondition | None = None,
    asset_status: InventoryStatus | None = Query(default=None, alias="status"),
    object_id: UUID | None = None,
    employee_id: UUID | None = None,
    include_archived: bool = False,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal=Depends(require_permission("inventory.read")),
) -> InventoryAssetPage:
    query = asset_query()
    count_query = select(func.count()).select_from(InventoryAsset)
    filters = []
    if not include_archived and asset_status != "archived":
        filters.append(InventoryAsset.archived_at.is_(None))
    if asset_status is not None:
        filters.append(InventoryAsset.status == asset_status)
    if category is not None:
        filters.append(InventoryAsset.category == category)
    if condition is not None:
        filters.append(InventoryAsset.condition == condition)
    if object_id is not None:
        filters.append(InventoryAsset.object_id == object_id)
    if employee_id is not None:
        filters.append(InventoryAsset.current_employee_id == employee_id)
    if not has_global_object_access(principal):
        accessible_object_ids = select(ObjectAssignment.object_id).where(
            ObjectAssignment.user_id == principal.user.id
        )
        filters.append(InventoryAsset.object_id.in_(accessible_object_ids))
    if q and q.strip():
        term = f"%{q.strip()}%"
        filters.append(
            or_(
                InventoryAsset.asset_number.ilike(term),
                InventoryAsset.serial_number.ilike(term),
                InventoryAsset.name.ilike(term),
                InventoryAsset.location.ilike(term),
                InventoryAsset.object_id.in_(
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
    assets = (
        db.scalars(query.order_by(InventoryAsset.asset_number).limit(limit).offset(offset))
        .unique()
        .all()
    )
    return InventoryAssetPage(
        items=[asset_read(asset) for asset in assets], total=total, limit=limit, offset=offset
    )


@router.post(
    "/inventory/assets",
    response_model=InventoryAssetRead,
    status_code=status.HTTP_201_CREATED,
)
def create_inventory_asset(
    payload: InventoryAssetCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("inventory.manage")),
) -> InventoryAssetRead:
    obj = ensure_object_access(db, payload.object_id, principal)
    ensure_object_management(db, obj, principal)
    if obj is not None and obj.archived_at is not None:
        raise HTTPException(
            status_code=409, detail="Archivierte Objekte können kein Inventar erhalten"
        )
    now = datetime.now(UTC)
    asset = InventoryAsset(
        asset_number=payload.asset_number,
        serial_number=payload.serial_number,
        name=payload.name,
        category=payload.category,
        condition=payload.condition,
        status="available",
        location=payload.location,
        object_id=payload.object_id,
        created_by_id=principal.user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(asset)
    flush_inventory_transaction(db)
    event = append_event(
        db,
        asset=asset,
        actor_id=principal.user.id,
        event_type="created",
        now=now,
        to_object_id=asset.object_id,
    )
    flush_inventory_transaction(db)
    record_inventory_audit(
        db,
        principal=principal,
        request=request,
        action="created",
        asset=asset,
        details={"event_id": str(event.id)},
    )
    commit_inventory_transaction(db)
    db.refresh(asset)
    return asset_read(asset)


@router.patch("/inventory/assets/{asset_id}", response_model=InventoryAssetRead)
def update_inventory_asset(
    asset_id: UUID,
    payload: InventoryAssetUpdate,
    request: Request,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("inventory.manage")),
) -> InventoryAssetRead:
    asset = get_asset_or_404(db, asset_id, principal, for_update=True)
    obj = ensure_object_access(db, asset.object_id, principal)
    ensure_object_management(db, obj, principal)
    if asset.archived_at is not None:
        raise HTTPException(
            status_code=409, detail="Archiviertes Inventar kann nicht geändert werden"
        )
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status_code=422, detail="Mindestens ein Inventarfeld muss geändert werden"
        )
    for field, value in changes.items():
        setattr(asset, field, value)
    now = datetime.now(UTC)
    event = append_event(
        db,
        asset=asset,
        actor_id=principal.user.id,
        event_type="updated",
        now=now,
        note=f"Stammdaten geändert: {', '.join(sorted(changes))}",
    )
    flush_inventory_transaction(db)
    record_inventory_audit(
        db,
        principal=principal,
        request=request,
        action="updated",
        asset=asset,
        details={"event_id": str(event.id), "fields": sorted(changes)},
    )
    commit_inventory_transaction(db)
    db.refresh(asset)
    return asset_read(asset)


@router.post("/inventory/assets/{asset_id}/archive", response_model=InventoryAssetRead)
def archive_inventory_asset(
    asset_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("inventory.manage")),
) -> InventoryAssetRead:
    asset = get_asset_or_404(db, asset_id, principal, for_update=True)
    obj = ensure_object_access(db, asset.object_id, principal)
    ensure_object_management(db, obj, principal)
    if asset.archived_at is not None:
        raise HTTPException(status_code=409, detail="Das Inventar ist bereits archiviert")
    if asset.status in {"issued", "maintenance"}:
        raise HTTPException(
            status_code=409,
            detail="Ausgegebenes oder in Wartung befindliches Inventar kann nicht archiviert werden",
        )
    now = datetime.now(UTC)
    asset.status = "archived"
    asset.archived_at = now
    event = append_event(
        db,
        asset=asset,
        actor_id=principal.user.id,
        event_type="archived",
        now=now,
        from_object_id=asset.object_id,
    )
    flush_inventory_transaction(db)
    record_inventory_audit(
        db,
        principal=principal,
        request=request,
        action="archived",
        asset=asset,
        details={"event_id": str(event.id)},
    )
    commit_inventory_transaction(db)
    db.refresh(asset)
    return asset_read(asset)


@router.post(
    "/inventory/assets/{asset_id}/events",
    response_model=InventoryEventRead,
    status_code=status.HTTP_201_CREATED,
)
def create_inventory_event(
    asset_id: UUID,
    payload: InventoryEventCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("inventory.move")),
) -> InventoryEventRead:
    asset = get_asset_or_404(db, asset_id, principal, for_update=True)
    asset_object = ensure_object_access(db, asset.object_id, principal)
    ensure_object_move_access(db, asset.object_id, principal)
    if asset.status == "archived" or asset.archived_at is not None:
        raise HTTPException(
            status_code=409, detail="Archiviertes Inventar kann nicht bewegt werden"
        )
    now = datetime.now(UTC)
    from_employee_id = asset.current_employee_id
    from_object_id = asset.object_id
    to_employee_id: UUID | None = None
    to_object_id: UUID | None = asset.object_id
    acknowledged_at = None
    if payload.event_type == "issued":
        if asset.status != "available":
            raise HTTPException(
                status_code=409, detail="Nur verfügbares Inventar kann ausgegeben werden"
            )
        if asset_object is not None and asset_object.archived_at is not None:
            raise HTTPException(
                status_code=409, detail="Archivierte Objekte erhalten keine Ausgaben"
            )
        employee = require_active_employee(db, payload.employee_id, asset.object_id)
        to_employee_id = employee.id
        asset.current_employee_id = employee.id
        asset.status = "issued"
        acknowledged_at = now
    elif payload.event_type == "returned":
        if asset.status != "issued" or asset.current_employee_id is None:
            raise HTTPException(
                status_code=409, detail="Nur ausgegebenes Inventar kann zurückgenommen werden"
            )
        asset.current_employee_id = None
        asset.status = "available"
    elif payload.event_type == "transferred":
        if asset.status != "issued" or asset.current_employee_id is None:
            raise HTTPException(
                status_code=409, detail="Nur ausgegebenes Inventar kann übergeben werden"
            )
        target_object_id = (
            payload.object_id if "object_id" in payload.model_fields_set else asset.object_id
        )
        target_object = ensure_object_access(db, target_object_id, principal)
        if target_object_id != asset.object_id:
            if "inventory.manage" not in principal.permission_codes:
                raise HTTPException(
                    status_code=403,
                    detail="Objektwechsel erfordert die Berechtigung zur Inventarverwaltung",
                )
            source_object = asset_object
            for scope_object in sorted(
                (source_object, target_object),
                key=lambda obj: str(obj.id) if obj is not None else "",
            ):
                ensure_object_management(db, scope_object, principal)
        if target_object is not None and target_object.archived_at is not None:
            raise HTTPException(
                status_code=409, detail="Archivierte Objekte können kein Inventar erhalten"
            )
        employee = require_active_employee(db, payload.employee_id, target_object_id)
        if employee.id == asset.current_employee_id:
            raise HTTPException(
                status_code=422, detail="Die Übergabe benötigt einen anderen Mitarbeiter"
            )
        to_employee_id = employee.id
        to_object_id = target_object_id
        asset.object_id = target_object_id
        asset.current_employee_id = employee.id
        acknowledged_at = now
    elif payload.event_type == "lost":
        if asset.status not in {"available", "issued"}:
            raise HTTPException(
                status_code=409, detail="Dieses Inventar kann nicht als verloren gemeldet werden"
            )
        asset.current_employee_id = None
        asset.status = "lost"
    elif payload.event_type == "damaged":
        if asset.status not in {"available", "issued"}:
            raise HTTPException(
                status_code=409, detail="Dieses Inventar kann nicht als beschädigt gemeldet werden"
            )
        asset.current_employee_id = None
        asset.status = "damaged"
        asset.condition = "defective"
    elif payload.event_type == "maintenance":
        if asset.status != "available":
            raise HTTPException(
                status_code=409, detail="Nur verfügbares Inventar kann in Wartung genommen werden"
            )
        asset.status = "maintenance"
    elif payload.event_type == "repair":
        if asset.status not in {"maintenance", "damaged"}:
            raise HTTPException(
                status_code=409,
                detail="Eine Reparatur kann nur für beschädigtes oder in Wartung befindliches Inventar abgeschlossen werden",
            )
        if payload.condition is None:
            raise HTTPException(
                status_code=422, detail="Der Zustand nach der Reparatur ist erforderlich"
            )
        asset.status = "available"
        asset.condition = payload.condition
    if payload.location is not None:
        asset.location = payload.location
    event = append_event(
        db,
        asset=asset,
        actor_id=principal.user.id,
        event_type=payload.event_type,
        now=now,
        from_employee_id=from_employee_id,
        to_employee_id=to_employee_id,
        from_object_id=from_object_id if payload.event_type == "transferred" else None,
        to_object_id=to_object_id if payload.event_type in {"issued", "transferred"} else None,
        acknowledged_at=acknowledged_at,
        acknowledgement_note=payload.acknowledgement_note,
        note=payload.note,
    )
    flush_inventory_transaction(db)
    record_inventory_audit(
        db,
        principal=principal,
        request=request,
        action=payload.event_type,
        asset=asset,
        details={
            "event_id": str(event.id),
            "status_after": asset.status,
            "from_employee_id": str(from_employee_id) if from_employee_id else None,
            "to_employee_id": str(to_employee_id) if to_employee_id else None,
        },
    )
    commit_inventory_transaction(db)
    persisted_event = db.scalar(
        select(InventoryEvent).options(*event_options()).where(InventoryEvent.id == event.id)
    )
    return event_read(persisted_event)


@router.get(
    "/inventory/assets/{asset_id}/events",
    response_model=InventoryEventPage,
)
def list_inventory_events(
    asset_id: UUID,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal=Depends(require_permission("inventory.read")),
) -> InventoryEventPage:
    asset = get_asset_or_404(db, asset_id, principal)
    query = (
        select(InventoryEvent).options(*event_options()).where(InventoryEvent.asset_id == asset.id)
    )
    count_query = (
        select(func.count()).select_from(InventoryEvent).where(InventoryEvent.asset_id == asset.id)
    )
    if not has_global_object_access(principal):
        accessible_object_ids = select(ObjectAssignment.object_id).where(
            ObjectAssignment.user_id == principal.user.id
        )
        event_scope = InventoryEvent.object_id.in_(accessible_object_ids)
        event_scope &= or_(
            InventoryEvent.from_object_id.is_(None),
            InventoryEvent.from_object_id.in_(accessible_object_ids),
        )
        event_scope &= or_(
            InventoryEvent.to_object_id.is_(None),
            InventoryEvent.to_object_id.in_(accessible_object_ids),
        )
        query = query.where(event_scope)
        count_query = count_query.where(event_scope)
    total = db.scalar(count_query) or 0
    events = (
        db.scalars(
            query.order_by(InventoryEvent.created_at.desc(), InventoryEvent.id)
            .limit(limit)
            .offset(offset)
        )
        .unique()
        .all()
    )
    return InventoryEventPage(
        items=[event_read(event) for event in events], total=total, limit=limit, offset=offset
    )
