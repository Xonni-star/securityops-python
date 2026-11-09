import hashlib
from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.auth import add_audit_entry, require_permission
from app.database import get_db
from app.models import (
    Employee,
    EmployeeAbsence,
    EmployeeAvailabilityWindow,
    EmployeeQualification,
    ObjectAssignment,
    ScheduleAvailabilityRequest,
    ScheduleSettings,
    ScheduleShift,
    ScheduleShiftHistory,
    SecurityObject,
)
from app.schemas import (
    EmployeeAvailabilityUpdate,
    EmployeeAvailabilityWindowRead,
    ScheduleAvailabilityRequestCreate,
    ScheduleAvailabilityRequestRead,
    ScheduleAvailabilityRequestUpdate,
    ScheduleConflictRead,
    ScheduleReplacementCandidateRead,
    ScheduleSettingsRead,
    ScheduleSettingsUpdate,
    ScheduleShiftCreate,
    ScheduleShiftHistoryRead,
    ScheduleShiftRead,
    ScheduleShiftReplacementCreate,
    ScheduleShiftUpdate,
)

router = APIRouter()


def get_schedule_settings(db: Session) -> ScheduleSettings:
    settings = db.get(ScheduleSettings, 1)
    if settings is None:
        settings = ScheduleSettings(id=1, time_zone="Europe/Berlin", minimum_rest_hours=11)
        db.add(settings)
        db.flush()
    return settings


def get_zone(time_zone: str) -> ZoneInfo:
    try:
        return ZoneInfo(time_zone)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Die angegebene Zeitzone ist keine gültige IANA-Zeitzone.",
        ) from exc


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def local_to_utc(value: datetime, zone: ZoneInfo, fold: int) -> datetime:
    local = value.replace(tzinfo=None)
    zoned = local.replace(tzinfo=zone, fold=fold)
    if zoned.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != local:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Diese lokale Uhrzeit existiert wegen der Zeitumstellung nicht.",
        )
    return zoned.astimezone(UTC)


def local_day_start(value: date, zone: ZoneInfo) -> datetime:
    return local_to_utc(datetime.combine(value, time.min), zone, 0)


def shift_query():
    return select(ScheduleShift).options(
        joinedload(ScheduleShift.employee),
        joinedload(ScheduleShift.object),
    )


def visible_shift_query(principal):
    query = shift_query().join(Employee).join(SecurityObject)
    permissions = principal.permission_codes
    if "employees.read" not in permissions:
        query = query.where(Employee.user_id == principal.user.id)
    if "objects.read_all" not in permissions:
        query = query.where(
            SecurityObject.assignments.any(ObjectAssignment.user_id == principal.user.id)
        )
    return query


def get_shift_or_404(
    db: Session,
    shift_id: UUID,
    principal,
    *,
    for_update: bool = False,
) -> ScheduleShift:
    query = visible_shift_query(principal).where(ScheduleShift.id == shift_id)
    if for_update:
        query = query.with_for_update(of=ScheduleShift)
    shift = db.scalar(query)
    if shift is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dienst nicht gefunden")
    return shift


def get_employee_or_404(db: Session, employee_id) -> Employee:
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Mitarbeiter nicht gefunden"
        )
    return employee


def ensure_employee_schedule_access(employee: Employee, principal) -> None:
    permissions = principal.permission_codes
    if "scheduling.manage" in permissions or "employees.read" in permissions:
        return
    if employee.user_id != principal.user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mitarbeiter nicht gefunden",
        )


def get_assignable_object(db: Session, object_id, principal) -> SecurityObject:
    query = select(SecurityObject).where(
        SecurityObject.id == object_id,
        SecurityObject.status == "active",
        SecurityObject.archived_at.is_(None),
    )
    if "objects.manage_all" not in principal.permission_codes:
        query = query.where(
            SecurityObject.assignments.any(ObjectAssignment.user_id == principal.user.id)
        )
    obj = db.scalar(query)
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aktives oder zugewiesenes Objekt nicht gefunden",
        )
    return obj


def lock_employee_schedule(db: Session, employee_id) -> None:
    if db.get_bind().dialect.name != "postgresql":
        return
    key = int.from_bytes(
        hashlib.sha256(employee_id.bytes).digest()[:8],
        byteorder="big",
        signed=True,
    )
    db.execute(select(func.pg_advisory_xact_lock(key)))


def lock_employee_schedules(db: Session, employee_ids: set) -> None:
    for employee_id in sorted(employee_ids, key=str):
        lock_employee_schedule(db, employee_id)


def time_microseconds(value: time) -> int:
    return ((value.hour * 60 + value.minute) * 60 + value.second) * 1_000_000 + value.microsecond


def shift_fits_availability(
    db: Session,
    employee_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
    zone: ZoneInfo,
    windows: Sequence[tuple[int, time, time]] | None = None,
) -> bool:
    if windows is None:
        rows = db.scalars(
            select(EmployeeAvailabilityWindow).where(
                EmployeeAvailabilityWindow.employee_id == employee_id
            )
        ).all()
        windows = [(row.weekday, row.starts_at, row.ends_at) for row in rows]
    if not windows:
        return True

    windows_by_weekday: dict[int, list[tuple[int, int]]] = {}
    for weekday, starts_at_time, ends_at_time in windows:
        windows_by_weekday.setdefault(weekday, []).append(
            (time_microseconds(starts_at_time), time_microseconds(ends_at_time))
        )
    day = starts_at.astimezone(zone).date()
    last_day = (ends_at - timedelta(microseconds=1)).astimezone(zone).date()
    if (last_day - day).days > 7:
        return False
    while day <= last_day:
        day_start = local_day_start(day, zone)
        next_day_start = local_day_start(day + timedelta(days=1), zone)
        segment_start = max(starts_at, day_start).astimezone(zone).replace(tzinfo=None).time()
        segment_end_at = min(ends_at, next_day_start)
        if segment_end_at == next_day_start:
            segment_end = 24 * 60 * 60 * 1_000_000
        else:
            segment_end = time_microseconds(
                segment_end_at.astimezone(zone).replace(tzinfo=None).time()
            )
        cursor = time_microseconds(segment_start)
        day_windows = sorted(windows_by_weekday.get(day.weekday(), []))
        for window_start, window_end in day_windows:
            if window_end <= cursor:
                continue
            if window_start > cursor:
                break
            cursor = max(cursor, window_end)
            if cursor >= segment_end:
                break
        if cursor < segment_end:
            return False
        day += timedelta(days=1)
    return True


def check_conflicts(
    db: Session,
    *,
    employee: Employee,
    obj: SecurityObject,
    starts_at: datetime,
    ends_at: datetime,
    required_qualification: str | None,
    time_zone: str,
    minimum_rest_hours: int,
    exclude_shift_id=None,
) -> list[ScheduleConflictRead]:
    zone = get_zone(time_zone)
    start_day = starts_at.astimezone(zone).date()
    end_day = (ends_at - timedelta(microseconds=1)).astimezone(zone).date()
    conflicts: list[ScheduleConflictRead] = []

    if (
        employee.archived_at is not None
        or employee.employment_status != "active"
        or employee.hired_on > start_day
        or (employee.ended_on is not None and employee.ended_on < end_day)
    ):
        conflicts.append(
            ScheduleConflictRead(
                code="employee_unavailable",
                message="Der Mitarbeiter ist im ausgewählten Zeitraum nicht aktiv beschäftigt.",
            )
        )

    if employee.user_id is None or db.scalar(
        select(ObjectAssignment.id).where(
            ObjectAssignment.object_id == obj.id,
            ObjectAssignment.user_id == employee.user_id,
        )
    ) is None:
        conflicts.append(
            ScheduleConflictRead(
                code="object_assignment",
                message="Der Mitarbeiter ist dem ausgewählten Objekt nicht zugewiesen.",
            )
        )

    absence = db.scalar(
        select(EmployeeAbsence.id)
        .where(
            EmployeeAbsence.employee_id == employee.id,
            EmployeeAbsence.status.in_(("pending", "approved")),
            EmployeeAbsence.starts_on <= end_day,
            EmployeeAbsence.ends_on >= start_day,
        )
        .limit(1)
    )
    if absence is not None:
        conflicts.append(
            ScheduleConflictRead(
                code="employee_absence",
                message="Im Dienstzeitraum liegt eine offene oder genehmigte Abwesenheit.",
            )
        )

    if not shift_fits_availability(
        db,
        employee.id,
        starts_at,
        ends_at,
        zone,
    ):
        conflicts.append(
            ScheduleConflictRead(
                code="outside_availability",
                message="Der Dienst liegt teilweise oder vollständig außerhalb der regelmäßigen Verfügbarkeit.",
            )
        )

    blocked_request = db.scalar(
        select(ScheduleAvailabilityRequest.id)
        .where(
            ScheduleAvailabilityRequest.employee_id == employee.id,
            ScheduleAvailabilityRequest.kind == "blocked",
            ScheduleAvailabilityRequest.status.in_(("open", "accepted")),
            ScheduleAvailabilityRequest.starts_at < ends_at,
            ScheduleAvailabilityRequest.ends_at > starts_at,
        )
        .limit(1)
    )
    if blocked_request is not None:
        conflicts.append(
            ScheduleConflictRead(
                code="availability_blocked",
                message="Der Dienst überschneidet sich mit einer offenen oder bestätigten Sperrzeit.",
            )
        )

    required_qualifications: dict[str, tuple[str, str]] = {}
    if required_qualification:
        required_qualifications[required_qualification.casefold()] = (
            required_qualification,
            "qualification_missing",
        )
    for requirement in obj.qualification_requirements:
        required_qualifications.setdefault(
            requirement.casefold(),
            (requirement, "object_qualification_missing"),
        )
    for qualification_name, conflict_code in required_qualifications.values():
        matching_qualification = db.scalar(
            select(EmployeeQualification.id)
            .where(
                EmployeeQualification.employee_id == employee.id,
                EmployeeQualification.archived_at.is_(None),
                EmployeeQualification.valid_from.is_(None)
                | (EmployeeQualification.valid_from <= start_day),
                EmployeeQualification.expires_on.is_(None)
                | (EmployeeQualification.expires_on >= end_day),
                or_(
                    func.lower(EmployeeQualification.name) == qualification_name.lower(),
                    func.lower(EmployeeQualification.category) == qualification_name.lower(),
                ),
            )
            .limit(1)
        )
        if matching_qualification is None:
            conflicts.append(
                ScheduleConflictRead(
                    code=conflict_code,
                    message=(
                        f"Der gültige Qualifikationsnachweis „{qualification_name}“ "
                        + (
                            "für das Objekt fehlt."
                            if conflict_code == "object_qualification_missing"
                            else "fehlt."
                        )
                    ),
                )
            )

    overlap_query = select(ScheduleShift.id).where(
        ScheduleShift.employee_id == employee.id,
        ScheduleShift.status != "cancelled",
        ScheduleShift.starts_at < ends_at,
        ScheduleShift.ends_at > starts_at,
    )
    if exclude_shift_id is not None:
        overlap_query = overlap_query.where(ScheduleShift.id != exclude_shift_id)
    if db.scalar(overlap_query.limit(1)) is not None:
        conflicts.append(
            ScheduleConflictRead(
                code="time_overlap",
                message="Der Mitarbeiter ist in diesem Zeitraum bereits für einen Dienst eingeplant.",
            )
        )

    if minimum_rest_hours:
        rest_period = timedelta(hours=minimum_rest_hours)
        before_query = select(ScheduleShift).where(
            ScheduleShift.employee_id == employee.id,
            ScheduleShift.status != "cancelled",
            ScheduleShift.ends_at <= starts_at,
        )
        after_query = select(ScheduleShift).where(
            ScheduleShift.employee_id == employee.id,
            ScheduleShift.status != "cancelled",
            ScheduleShift.starts_at >= ends_at,
        )
        if exclude_shift_id is not None:
            before_query = before_query.where(ScheduleShift.id != exclude_shift_id)
            after_query = after_query.where(ScheduleShift.id != exclude_shift_id)
        previous = db.scalar(before_query.order_by(ScheduleShift.ends_at.desc()).limit(1))
        following = db.scalar(after_query.order_by(ScheduleShift.starts_at).limit(1))
        if (previous is not None and starts_at - as_utc(previous.ends_at) < rest_period) or (
            following is not None and as_utc(following.starts_at) - ends_at < rest_period
        ):
            conflicts.append(
                ScheduleConflictRead(
                    code="minimum_rest",
                    message=(
                        f"Der konfigurierte Mindestabstand von {minimum_rest_hours} Stunden "
                        "zwischen Diensten wird unterschritten."
                    ),
                )
            )
    return conflicts


def ensure_no_conflicts(conflicts: list[ScheduleConflictRead]) -> None:
    if conflicts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Der Dienst weist Besetzungs- oder Zeitkonflikte auf.",
                "conflicts": [conflict.model_dump() for conflict in conflicts],
            },
            headers={"X-Schedule-Conflicts": ",".join(conflict.code for conflict in conflicts)},
        )


def record_shift_event(
    db: Session,
    *,
    shift: ScheduleShift,
    actor_id,
    action: str,
    changed_fields: set[str],
    request: Request,
    details: dict[str, object] | None = None,
) -> None:
    fields = sorted(changed_fields)
    event_details = details or {}
    db.add(
        ScheduleShiftHistory(
            shift_id=shift.id,
            actor_id=actor_id,
            action=action,
            changed_fields=fields,
            details=event_details,
        )
    )
    add_audit_entry(
        db,
        actor_id=actor_id,
        action=f"scheduling.{action}",
        entity_type="schedule_shift",
        entity_id=str(shift.id),
        ip_address=request.client.host if request.client else None,
        details={"fields": fields, **event_details},
    )


def commit_schedule_transaction(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        db.rollback()
        if constraint == "ex_schedule_shifts_employee_time":
            detail = "Der Mitarbeiter wurde zeitgleich in einem anderen Vorgang eingeplant."
        else:
            detail = "Die Dienständerung verletzt eine Datenbankbedingung."
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc


def flush_schedule_transaction(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        db.rollback()
        if constraint == "ex_schedule_shifts_employee_time":
            detail = "Der Mitarbeiter wurde zeitgleich in einem anderen Vorgang eingeplant."
        else:
            detail = "Die Dienständerung verletzt eine Datenbankbedingung."
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc


def read_shift(shift: ScheduleShift, time_zone: str) -> ScheduleShiftRead:
    return ScheduleShiftRead(
        id=shift.id,
        employee_id=shift.employee_id,
        employee_number=shift.employee.employee_number,
        employee_name=shift.employee.full_name,
        object_id=shift.object_id,
        object_code=shift.object.code,
        object_name=shift.object.name,
        starts_at=as_utc(shift.starts_at),
        ends_at=as_utc(shift.ends_at),
        time_zone=time_zone,
        break_minutes=shift.break_minutes,
        required_qualification=shift.required_qualification,
        status=shift.status,
        created_by_id=shift.created_by_id,
        created_at=as_utc(shift.created_at),
        updated_at=as_utc(shift.updated_at),
    )


def read_availability_request(
    db: Session,
    item: ScheduleAvailabilityRequest,
    time_zone: str,
) -> ScheduleAvailabilityRequestRead:
    conflicting_shift_ids = []
    if item.kind == "blocked" and item.status != "rejected":
        conflicting_shift_ids = list(
            db.scalars(
                select(ScheduleShift.id)
                .where(
                    ScheduleShift.employee_id == item.employee_id,
                    ScheduleShift.status != "cancelled",
                    ScheduleShift.starts_at < item.ends_at,
                    ScheduleShift.ends_at > item.starts_at,
                )
                .order_by(ScheduleShift.starts_at, ScheduleShift.id)
            ).all()
        )
    return ScheduleAvailabilityRequestRead(
        id=item.id,
        employee_id=item.employee_id,
        employee_name=item.employee.full_name,
        employee_number=item.employee.employee_number,
        kind=item.kind,
        starts_at=as_utc(item.starts_at),
        ends_at=as_utc(item.ends_at),
        time_zone=time_zone,
        status=item.status,
        conflicting_shift_ids=conflicting_shift_ids,
        created_by_id=item.created_by_id,
        reviewed_by_id=item.reviewed_by_id,
        reviewed_at=as_utc(item.reviewed_at) if item.reviewed_at else None,
        created_at=as_utc(item.created_at),
        updated_at=as_utc(item.updated_at),
    )


@router.get("/scheduling/settings", response_model=ScheduleSettingsRead)
def get_scheduling_settings(
    db: Session = Depends(get_db),
    _principal=Depends(require_permission("scheduling.read")),
) -> ScheduleSettingsRead:
    settings = get_schedule_settings(db)
    get_zone(settings.time_zone)
    return ScheduleSettingsRead(
        time_zone=settings.time_zone,
        minimum_rest_hours=settings.minimum_rest_hours,
        updated_at=as_utc(settings.updated_at),
    )


@router.patch("/scheduling/settings", response_model=ScheduleSettingsRead)
def update_scheduling_settings(
    request: Request,
    payload: ScheduleSettingsUpdate,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("scheduling.manage")),
) -> ScheduleSettingsRead:
    settings = db.scalar(select(ScheduleSettings).where(ScheduleSettings.id == 1).with_for_update())
    if settings is None:
        settings = get_schedule_settings(db)
    get_zone(payload.time_zone)
    changed_fields = set()
    if settings.time_zone != payload.time_zone:
        settings.time_zone = payload.time_zone
        changed_fields.add("time_zone")
    if settings.minimum_rest_hours != payload.minimum_rest_hours:
        settings.minimum_rest_hours = payload.minimum_rest_hours
        changed_fields.add("minimum_rest_hours")
    if changed_fields:
        settings.updated_by_id = principal.user.id
        add_audit_entry(
            db,
            actor_id=principal.user.id,
            action="scheduling.settings_updated",
            entity_type="schedule_settings",
            entity_id="1",
            ip_address=request.client.host if request.client else None,
            details={"fields": sorted(changed_fields)},
        )
        commit_schedule_transaction(db)
    return ScheduleSettingsRead(
        time_zone=settings.time_zone,
        minimum_rest_hours=settings.minimum_rest_hours,
        updated_at=as_utc(settings.updated_at),
    )


@router.get(
    "/scheduling/employees/{employee_id}/availability",
    response_model=list[EmployeeAvailabilityWindowRead],
)
def list_employee_availability(
    employee_id: UUID,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("scheduling.read")),
) -> list[EmployeeAvailabilityWindowRead]:
    employee = get_employee_or_404(db, employee_id)
    ensure_employee_schedule_access(employee, principal)
    windows = db.scalars(
        select(EmployeeAvailabilityWindow)
        .where(EmployeeAvailabilityWindow.employee_id == employee.id)
        .order_by(
            EmployeeAvailabilityWindow.weekday,
            EmployeeAvailabilityWindow.starts_at,
            EmployeeAvailabilityWindow.id,
        )
    ).all()
    return [EmployeeAvailabilityWindowRead.model_validate(item) for item in windows]


@router.put(
    "/scheduling/employees/{employee_id}/availability",
    response_model=list[EmployeeAvailabilityWindowRead],
)
def replace_employee_availability(
    request: Request,
    employee_id: UUID,
    payload: EmployeeAvailabilityUpdate,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("scheduling.manage")),
) -> list[EmployeeAvailabilityWindowRead]:
    employee = get_employee_or_404(db, employee_id)
    lock_employee_schedule(db, employee.id)
    existing_shifts = db.scalars(
        select(ScheduleShift).where(
            ScheduleShift.employee_id == employee.id,
            ScheduleShift.status != "cancelled",
            ScheduleShift.ends_at > datetime.now(UTC),
        )
    ).all()
    settings = get_schedule_settings(db)
    zone = get_zone(settings.time_zone)
    windows = [(item.weekday, item.starts_at, item.ends_at) for item in payload.windows]
    conflicts = [
        str(shift.id)
        for shift in existing_shifts
        if not shift_fits_availability(
            db,
            employee.id,
            as_utc(shift.starts_at),
            as_utc(shift.ends_at),
            zone,
            windows,
        )
    ]
    if conflicts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Die Verfügbarkeit würde bestehenden Diensten widersprechen.",
                "conflicting_shift_ids": conflicts,
            },
        )
    old_windows = db.scalars(
        select(EmployeeAvailabilityWindow)
        .where(EmployeeAvailabilityWindow.employee_id == employee.id)
        .order_by(
            EmployeeAvailabilityWindow.weekday,
            EmployeeAvailabilityWindow.starts_at,
            EmployeeAvailabilityWindow.id,
        )
    ).all()
    old_values = [
        {
            "weekday": item.weekday,
            "starts_at": item.starts_at.isoformat(),
            "ends_at": item.ends_at.isoformat(),
        }
        for item in old_windows
    ]
    db.query(EmployeeAvailabilityWindow).filter(
        EmployeeAvailabilityWindow.employee_id == employee.id
    ).delete(synchronize_session=False)
    replacements = [
        EmployeeAvailabilityWindow(
            employee_id=employee.id,
            weekday=item.weekday,
            starts_at=item.starts_at,
            ends_at=item.ends_at,
            created_by_id=principal.user.id,
        )
        for item in payload.windows
    ]
    db.add_all(replacements)
    new_values = [
        {
            "weekday": item.weekday,
            "starts_at": item.starts_at.isoformat(),
            "ends_at": item.ends_at.isoformat(),
        }
        for item in payload.windows
    ]
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="scheduling.availability_updated",
        entity_type="employee_availability",
        entity_id=str(employee.id),
        ip_address=request.client.host if request.client else None,
        details={"before": old_values, "after": new_values},
    )
    commit_schedule_transaction(db)
    return [EmployeeAvailabilityWindowRead.model_validate(item) for item in replacements]


@router.get(
    "/scheduling/availability-requests",
    response_model=list[ScheduleAvailabilityRequestRead],
)
def list_schedule_availability_requests(
    from_date: date | None = None,
    to_date: date | None = None,
    employee_id: UUID | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal=Depends(require_permission("scheduling.read")),
) -> list[ScheduleAvailabilityRequestRead]:
    settings = get_schedule_settings(db)
    zone = get_zone(settings.time_zone)
    if (from_date is None) != (to_date is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Beginn und Ende des Filterzeitraums müssen gemeinsam angegeben werden.",
        )
    query = (
        select(ScheduleAvailabilityRequest)
        .join(Employee)
        .options(joinedload(ScheduleAvailabilityRequest.employee))
    )
    if "employees.read" not in principal.permission_codes and (
        "scheduling.manage" not in principal.permission_codes
    ):
        query = query.where(Employee.user_id == principal.user.id)
    if employee_id is not None:
        query = query.where(ScheduleAvailabilityRequest.employee_id == employee_id)
    if from_date is not None and to_date is not None:
        if to_date < from_date or (to_date - from_date).days > 366 or to_date == date.max:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Der Filterzeitraum ist ungültig oder umfasst mehr als 367 Kalendertage.",
            )
        starts_at = local_day_start(from_date, zone)
        ends_at = local_day_start(to_date + timedelta(days=1), zone)
        query = query.where(
            ScheduleAvailabilityRequest.starts_at < ends_at,
            ScheduleAvailabilityRequest.ends_at > starts_at,
        )
    items = db.scalars(
        query.order_by(
            ScheduleAvailabilityRequest.starts_at,
            ScheduleAvailabilityRequest.id,
        )
        .limit(limit)
        .offset(offset)
    ).all()
    return [read_availability_request(db, item, settings.time_zone) for item in items]


@router.post(
    "/scheduling/availability-requests",
    response_model=ScheduleAvailabilityRequestRead,
    status_code=status.HTTP_201_CREATED,
)
def create_schedule_availability_request(
    request: Request,
    payload: ScheduleAvailabilityRequestCreate,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("scheduling.availability.request")),
) -> ScheduleAvailabilityRequestRead:
    settings = get_schedule_settings(db)
    zone = get_zone(settings.time_zone)
    starts_at = local_to_utc(payload.starts_at_local, zone, payload.starts_at_fold)
    ends_at = local_to_utc(payload.ends_at_local, zone, payload.ends_at_fold)
    if ends_at <= starts_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Das Ende des Zeitraums muss nach der Umrechnung in UTC nach dem Beginn liegen.",
        )
    if ends_at - starts_at > timedelta(days=366):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Wunsch- und Sperrzeiträume dürfen höchstens 366 Tage umfassen.",
        )
    if "scheduling.manage" in principal.permission_codes:
        if payload.employee_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Für die Erfassung durch die Einsatzleitung muss ein Mitarbeiter gewählt werden.",
            )
        employee = get_employee_or_404(db, payload.employee_id)
    else:
        employee = db.scalar(select(Employee).where(Employee.user_id == principal.user.id))
        if employee is None or (
            payload.employee_id is not None and payload.employee_id != employee.id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mitarbeiter nicht gefunden",
            )
    if employee.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Für archivierte Mitarbeiter können keine Dienstwünsche eingereicht werden.",
        )
    lock_employee_schedule(db, employee.id)
    item = ScheduleAvailabilityRequest(
        employee_id=employee.id,
        kind=payload.kind,
        starts_at=starts_at,
        ends_at=ends_at,
        status="open",
        created_by_id=principal.user.id,
    )
    db.add(item)
    flush_schedule_transaction(db)
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="scheduling.availability_request_created",
        entity_type="schedule_availability_request",
        entity_id=str(item.id),
        ip_address=request.client.host if request.client else None,
        details={
            "employee_id": str(employee.id),
            "kind": item.kind,
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
        },
    )
    commit_schedule_transaction(db)
    return read_availability_request(db, item, settings.time_zone)


@router.patch(
    "/scheduling/availability-requests/{request_id}",
    response_model=ScheduleAvailabilityRequestRead,
)
def update_schedule_availability_request(
    request: Request,
    request_id: UUID,
    payload: ScheduleAvailabilityRequestUpdate,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("scheduling.manage")),
) -> ScheduleAvailabilityRequestRead:
    item = db.scalar(
        select(ScheduleAvailabilityRequest)
        .where(ScheduleAvailabilityRequest.id == request_id)
        .with_for_update()
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dienstwunsch nicht gefunden",
        )
    lock_employee_schedule(db, item.employee_id)
    if item.kind == "blocked" and payload.status == "accepted":
        conflicting_shift_ids = read_availability_request(
            db,
            item,
            get_schedule_settings(db).time_zone,
        ).conflicting_shift_ids
        if conflicting_shift_ids:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Die Sperrzeit überschneidet sich noch mit geplanten Diensten.",
                    "conflicting_shift_ids": [str(item_id) for item_id in conflicting_shift_ids],
                },
            )
    if item.status != payload.status:
        item.status = payload.status
        item.reviewed_by_id = principal.user.id
        item.reviewed_at = datetime.now(UTC)
        add_audit_entry(
            db,
            actor_id=principal.user.id,
            action="scheduling.availability_request_reviewed",
            entity_type="schedule_availability_request",
            entity_id=str(item.id),
            ip_address=request.client.host if request.client else None,
            details={"status": payload.status},
        )
        commit_schedule_transaction(db)
    settings = get_schedule_settings(db)
    return read_availability_request(db, item, settings.time_zone)


@router.get("/scheduling/shifts", response_model=list[ScheduleShiftRead])
def list_schedule_shifts(
    from_date: date | None = None,
    to_date: date | None = None,
    employee_id: UUID | None = None,
    object_id: UUID | None = None,
    include_cancelled: bool = False,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal=Depends(require_permission("scheduling.read")),
) -> list[ScheduleShiftRead]:
    settings = get_schedule_settings(db)
    zone = get_zone(settings.time_zone)
    if (from_date is None) != (to_date is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Beginn und Ende des Filterzeitraums müssen gemeinsam angegeben werden.",
        )
    if from_date is not None and to_date is not None:
        if to_date < from_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Das Ende des Filterzeitraums liegt vor dem Beginn.",
            )
        if to_date == date.max:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Das Ende des Filterzeitraums liegt außerhalb des unterstützten Bereichs.",
            )
        if (to_date - from_date).days > 366:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Der Filterzeitraum darf höchstens 367 Kalendertage umfassen.",
            )

    query = visible_shift_query(principal)
    if not include_cancelled:
        query = query.where(ScheduleShift.status != "cancelled")
    if from_date is not None and to_date is not None:
        starts_at = local_day_start(from_date, zone)
        ends_at = local_day_start(to_date + timedelta(days=1), zone)
        query = query.where(
            ScheduleShift.starts_at < ends_at,
            ScheduleShift.ends_at > starts_at,
        )
    if employee_id is not None:
        query = query.where(ScheduleShift.employee_id == employee_id)
    if object_id is not None:
        query = query.where(ScheduleShift.object_id == object_id)
    shifts = (
        db.scalars(
            query.order_by(ScheduleShift.starts_at, ScheduleShift.id).limit(limit).offset(offset)
        )
        .unique()
        .all()
    )
    return [read_shift(shift, settings.time_zone) for shift in shifts]


@router.post(
    "/scheduling/shifts",
    response_model=ScheduleShiftRead,
    status_code=status.HTTP_201_CREATED,
)
def create_schedule_shift(
    request: Request,
    payload: ScheduleShiftCreate,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("scheduling.manage")),
) -> ScheduleShiftRead:
    settings = get_schedule_settings(db)
    zone = get_zone(settings.time_zone)
    starts_at = local_to_utc(payload.starts_at_local, zone, payload.starts_at_fold)
    ends_at = local_to_utc(payload.ends_at_local, zone, payload.ends_at_fold)
    if ends_at <= starts_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Das Dienstende muss nach der Umrechnung in UTC nach dem Dienstbeginn liegen.",
        )
    if payload.break_minutes >= (ends_at - starts_at).total_seconds() / 60:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Die Pause muss kürzer als der Dienstzeitraum sein.",
        )
    lock_employee_schedule(db, payload.employee_id)
    employee = get_employee_or_404(db, payload.employee_id)
    obj = get_assignable_object(db, payload.object_id, principal)
    conflicts = check_conflicts(
        db,
        employee=employee,
        obj=obj,
        starts_at=starts_at,
        ends_at=ends_at,
        required_qualification=payload.required_qualification,
        time_zone=settings.time_zone,
        minimum_rest_hours=settings.minimum_rest_hours,
    )
    ensure_no_conflicts(conflicts)
    shift = ScheduleShift(
        employee_id=employee.id,
        object_id=obj.id,
        starts_at=starts_at,
        ends_at=ends_at,
        break_minutes=payload.break_minutes,
        required_qualification=payload.required_qualification,
        status="draft",
        created_by_id=principal.user.id,
    )
    db.add(shift)
    flush_schedule_transaction(db)
    record_shift_event(
        db,
        shift=shift,
        actor_id=principal.user.id,
        action="created",
        changed_fields={
            "employee_id",
            "object_id",
            "starts_at",
            "ends_at",
            "break_minutes",
            "required_qualification",
            "status",
        },
        request=request,
    )
    commit_schedule_transaction(db)
    return read_shift(shift, settings.time_zone)


@router.patch("/scheduling/shifts/{shift_id}", response_model=ScheduleShiftRead)
def update_schedule_shift(
    request: Request,
    shift_id: UUID,
    payload: ScheduleShiftUpdate,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("scheduling.manage")),
) -> ScheduleShiftRead:
    shift = get_shift_or_404(db, shift_id, principal, for_update=True)
    if shift.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Abgesagte Dienste können nicht mehr geändert werden.",
        )
    changes = payload.model_dump(exclude_unset=True)
    settings = get_schedule_settings(db)
    zone = get_zone(settings.time_zone)
    next_employee_id = changes.get("employee_id", shift.employee_id)
    lock_employee_schedules(db, {shift.employee_id, next_employee_id})
    next_object_id = changes.get("object_id", shift.object_id)
    employee = get_employee_or_404(db, next_employee_id)
    obj = get_assignable_object(db, next_object_id, principal)

    starts_at = as_utc(shift.starts_at)
    ends_at = as_utc(shift.ends_at)
    if "starts_at_local" in changes:
        starts_at = local_to_utc(
            changes["starts_at_local"],
            zone,
            changes.get("starts_at_fold", 0),
        )
    elif "starts_at_fold" in changes:
        local = starts_at.astimezone(zone).replace(tzinfo=None)
        starts_at = local_to_utc(local, zone, changes["starts_at_fold"])
    if "ends_at_local" in changes:
        ends_at = local_to_utc(
            changes["ends_at_local"],
            zone,
            changes.get("ends_at_fold", 0),
        )
    elif "ends_at_fold" in changes:
        local = ends_at.astimezone(zone).replace(tzinfo=None)
        ends_at = local_to_utc(local, zone, changes["ends_at_fold"])
    if ends_at <= starts_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Das Dienstende muss nach der Umrechnung in UTC nach dem Dienstbeginn liegen.",
        )

    values = {
        "employee_id": employee.id,
        "object_id": obj.id,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "break_minutes": changes.get("break_minutes", shift.break_minutes),
        "required_qualification": changes.get(
            "required_qualification", shift.required_qualification
        ),
    }
    if values["break_minutes"] >= (ends_at - starts_at).total_seconds() / 60:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Die Pause muss kürzer als der Dienstzeitraum sein.",
        )
    conflicts = check_conflicts(
        db,
        employee=employee,
        obj=obj,
        starts_at=starts_at,
        ends_at=ends_at,
        required_qualification=values["required_qualification"],
        time_zone=settings.time_zone,
        minimum_rest_hours=settings.minimum_rest_hours,
        exclude_shift_id=shift.id,
    )
    ensure_no_conflicts(conflicts)
    changed_fields = set()
    for field, value in values.items():
        if getattr(shift, field) != value:
            setattr(shift, field, value)
            changed_fields.add(field)
    shift.employee = employee
    shift.object = obj
    if changed_fields:
        record_shift_event(
            db,
            shift=shift,
            actor_id=principal.user.id,
            action="updated",
            changed_fields=changed_fields,
            request=request,
        )
        commit_schedule_transaction(db)
    return read_shift(shift, settings.time_zone)


@router.post(
    "/scheduling/shifts/{shift_id}/replacement",
    response_model=ScheduleShiftRead,
)
def replace_schedule_shift_employee(
    request: Request,
    shift_id: UUID,
    payload: ScheduleShiftReplacementCreate,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("scheduling.manage")),
) -> ScheduleShiftRead:
    shift = get_shift_or_404(db, shift_id, principal, for_update=True)
    if shift.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Abgesagte Dienste können nicht vertreten werden.",
        )
    if payload.employee_id == shift.employee_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Die Vertretung muss eine andere Person als der bisherige Mitarbeiter sein.",
        )
    lock_employee_schedules(db, {shift.employee_id, payload.employee_id})
    settings = get_schedule_settings(db)
    employee = get_employee_or_404(db, payload.employee_id)
    obj = get_assignable_object(db, shift.object_id, principal)
    starts_at = as_utc(shift.starts_at)
    ends_at = as_utc(shift.ends_at)
    ensure_no_conflicts(
        check_conflicts(
            db,
            employee=employee,
            obj=obj,
            starts_at=starts_at,
            ends_at=ends_at,
            required_qualification=shift.required_qualification,
            time_zone=settings.time_zone,
            minimum_rest_hours=settings.minimum_rest_hours,
            exclude_shift_id=shift.id,
        )
    )
    previous_employee_id = shift.employee_id
    shift.employee_id = employee.id
    shift.employee = employee
    record_shift_event(
        db,
        shift=shift,
        actor_id=principal.user.id,
        action="replaced",
        changed_fields={"employee_id"},
        request=request,
        details={
            "previous_employee_id": str(previous_employee_id),
            "replacement_employee_id": str(employee.id),
            "reason": payload.reason,
        },
    )
    commit_schedule_transaction(db)
    return read_shift(shift, settings.time_zone)


@router.get(
    "/scheduling/shifts/{shift_id}/replacement-candidates",
    response_model=list[ScheduleReplacementCandidateRead],
)
def list_schedule_shift_replacement_candidates(
    shift_id: UUID,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("scheduling.manage")),
) -> list[ScheduleReplacementCandidateRead]:
    shift = get_shift_or_404(db, shift_id, principal)
    if shift.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Abgesagte Dienste können nicht vertreten werden.",
        )
    settings = get_schedule_settings(db)
    employee_query = select(Employee).where(
        Employee.id != shift.employee_id,
        Employee.archived_at.is_(None),
        Employee.user_id.is_not(None),
        Employee.user_id.in_(
            select(ObjectAssignment.user_id).where(
                ObjectAssignment.object_id == shift.object_id,
            )
        ),
    )
    candidates = db.scalars(employee_query.order_by(Employee.full_name, Employee.id)).all()
    obj = get_assignable_object(db, shift.object_id, principal)
    required_qualifications: dict[str, str] = {}
    if shift.required_qualification:
        required_qualifications[shift.required_qualification.casefold()] = (
            shift.required_qualification
        )
    for requirement in obj.qualification_requirements:
        required_qualifications.setdefault(requirement.casefold(), requirement)
    requirements = list(required_qualifications.values())
    results = []
    for employee in candidates:
        conflicts = check_conflicts(
            db,
            employee=employee,
            obj=obj,
            starts_at=as_utc(shift.starts_at),
            ends_at=as_utc(shift.ends_at),
            required_qualification=shift.required_qualification,
            time_zone=settings.time_zone,
            minimum_rest_hours=settings.minimum_rest_hours,
            exclude_shift_id=shift.id,
        )
        is_eligible = not conflicts
        results.append(
            ScheduleReplacementCandidateRead(
                employee_id=employee.id,
                employee_number=employee.employee_number,
                employee_name=employee.full_name,
                is_eligible=is_eligible,
                eligibility_reasons=(
                    [
                        "Das Beschäftigungsverhältnis umfasst den gesamten Dienstzeitraum.",
                        "Die Person ist dem Objekt aktuell zugewiesen.",
                        (
                            "Gültige Qualifikationsnachweise für den gesamten Dienstzeitraum: "
                            + ", ".join(requirements)
                            + "."
                            if requirements
                            else "Für Objekt und Dienst sind keine zusätzlichen Qualifikationen hinterlegt."
                        ),
                        "Es liegt keine offene oder genehmigte Abwesenheit und keine offene oder bestätigte Sperrzeit im Dienstzeitraum vor.",
                        "Die regelmäßige Verfügbarkeit deckt den Dienst vollständig ab.",
                        (
                            "Es gibt keine Dienstüberschneidung; der konfigurierte Mindestabstand "
                            f"von {settings.minimum_rest_hours} Stunden wird eingehalten."
                        ),
                    ]
                    if is_eligible
                    else []
                ),
                exclusion_reasons=[conflict.message for conflict in conflicts],
            )
        )
    return results


@router.post("/scheduling/shifts/{shift_id}/publish", response_model=ScheduleShiftRead)
def publish_schedule_shift(
    request: Request,
    shift_id: UUID,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("scheduling.manage")),
) -> ScheduleShiftRead:
    shift = get_shift_or_404(db, shift_id, principal, for_update=True)
    if shift.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Abgesagte Dienste können nicht veröffentlicht werden.",
        )
    settings = get_schedule_settings(db)
    lock_employee_schedule(db, shift.employee_id)
    employee = get_employee_or_404(db, shift.employee_id)
    obj = get_assignable_object(db, shift.object_id, principal)
    ensure_no_conflicts(
        check_conflicts(
            db,
            employee=employee,
            obj=obj,
            starts_at=as_utc(shift.starts_at),
            ends_at=as_utc(shift.ends_at),
            required_qualification=shift.required_qualification,
            time_zone=settings.time_zone,
            minimum_rest_hours=settings.minimum_rest_hours,
            exclude_shift_id=shift.id,
        )
    )
    if shift.status != "published":
        shift.status = "published"
        record_shift_event(
            db,
            shift=shift,
            actor_id=principal.user.id,
            action="published",
            changed_fields={"status"},
            request=request,
        )
        commit_schedule_transaction(db)
    return read_shift(shift, settings.time_zone)


@router.post("/scheduling/shifts/{shift_id}/cancel", response_model=ScheduleShiftRead)
def cancel_schedule_shift(
    request: Request,
    shift_id: UUID,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("scheduling.manage")),
) -> ScheduleShiftRead:
    shift = get_shift_or_404(db, shift_id, principal, for_update=True)
    if shift.status != "cancelled":
        lock_employee_schedule(db, shift.employee_id)
        shift.status = "cancelled"
        record_shift_event(
            db,
            shift=shift,
            actor_id=principal.user.id,
            action="cancelled",
            changed_fields={"status"},
            request=request,
        )
        commit_schedule_transaction(db)
    settings = get_schedule_settings(db)
    return read_shift(shift, settings.time_zone)


@router.get(
    "/scheduling/shifts/{shift_id}/history",
    response_model=list[ScheduleShiftHistoryRead],
)
def list_schedule_shift_history(
    shift_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal=Depends(require_permission("scheduling.read")),
) -> list[ScheduleShiftHistoryRead]:
    shift = get_shift_or_404(db, shift_id, principal)
    history = db.scalars(
        select(ScheduleShiftHistory)
        .where(ScheduleShiftHistory.shift_id == shift.id)
        .order_by(ScheduleShiftHistory.created_at.desc(), ScheduleShiftHistory.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [ScheduleShiftHistoryRead.model_validate(item) for item in history]
