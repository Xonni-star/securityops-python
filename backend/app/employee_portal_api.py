from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.auth import AuthPrincipal, add_audit_entry, get_auth_principal
from app.database import get_db
from app.employee_portal_schemas import (
    EmployeePortalAbsenceCreate,
    EmployeePortalAbsenceRead,
    EmployeePortalAbsenceUpdate,
    EmployeePortalAvailabilityCreate,
    EmployeePortalAvailabilityRead,
    EmployeePortalAvailabilityUpdate,
    EmployeePortalNotificationRead,
    EmployeePortalProfileRead,
    EmployeePortalQualificationRead,
    EmployeePortalRequestHistoryRead,
    EmployeePortalShiftRead,
    EmployeePortalTaskRead,
    EmployeePortalTimeEntryRead,
    EmployeePortalTimeOverviewRead,
)
from app.models import (
    AuditLog,
    Employee,
    EmployeeAbsence,
    EmployeeQualification,
    Notification,
    ObjectAssignment,
    ScheduleAvailabilityRequest,
    ScheduleShift,
    SecurityObject,
    Task,
    TimeEntry,
)
from app.scheduling_api import (
    as_utc,
    get_schedule_settings,
    get_zone,
    local_to_utc,
    lock_employee_schedule,
)

router = APIRouter()
PortalSession = Annotated[Session, Depends(get_db)]
PortalPrincipal = Annotated[AuthPrincipal, Depends(get_auth_principal)]


def current_employee(
    db: PortalSession,
    principal: PortalPrincipal,
) -> Employee:
    if "employee" not in principal.role_codes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Das Mitarbeiterportal ist nur für Mitarbeitende verfügbar.",
        )
    employee = db.scalar(
        select(Employee).where(
            Employee.user_id == principal.user.id,
            Employee.employment_status == "active",
            Employee.archived_at.is_(None),
        )
    )
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aktives Mitarbeiterprofil nicht gefunden.",
        )
    return employee


CurrentEmployee = Annotated[Employee, Depends(current_employee)]


def commit_portal_request(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Der Antrag konnte wegen eines Datenkonflikts nicht gespeichert werden.",
        ) from exc


def flush_portal_request(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Der Antrag verletzt eine Datenbankbedingung.",
        ) from exc


def request_history(
    db: Session,
    *,
    entity_type: str,
    entity_id: UUID,
    created_at: datetime,
    kind: str,
) -> list[EmployeePortalRequestHistoryRead]:
    logs = db.scalars(
        select(AuditLog)
        .where(
            AuditLog.entity_type == entity_type,
            AuditLog.entity_id == str(entity_id),
        )
        .order_by(AuditLog.created_at, AuditLog.id)
    ).all()
    history = []
    for item in logs:
        event = None
        if item.action in {
            "employee_portal.absence_requested",
            "employee_portal.availability_requested",
            "scheduling.availability_request_created",
        }:
            event = "requested"
        elif item.action in {
            "employee_portal.absence_updated",
            "employee_portal.availability_updated",
        }:
            event = "updated"
        elif item.action == "scheduling.availability_request_reviewed" and kind == "availability":
            decision = item.details.get("status")
            event = decision if decision in {"accepted", "rejected"} else None
        if event is not None:
            history.append(
                EmployeePortalRequestHistoryRead(event=event, occurred_at=item.created_at)
            )
    if not any(item.event == "requested" for item in history):
        history.insert(
            0,
            EmployeePortalRequestHistoryRead(event="requested", occurred_at=created_at),
        )
    return history


def read_absence(db: Session, absence: EmployeeAbsence) -> EmployeePortalAbsenceRead:
    return EmployeePortalAbsenceRead(
        id=absence.id,
        absence_type=absence.absence_type,
        starts_on=absence.starts_on,
        ends_on=absence.ends_on,
        status=absence.status,
        created_at=absence.created_at,
        updated_at=absence.updated_at,
        history=request_history(
            db,
            entity_type="employee_absence",
            entity_id=absence.id,
            created_at=absence.created_at,
            kind="absence",
        ),
    )


def read_availability_request(
    db: Session,
    item: ScheduleAvailabilityRequest,
    time_zone: str,
) -> EmployeePortalAvailabilityRead:
    return EmployeePortalAvailabilityRead(
        id=item.id,
        kind=item.kind,
        starts_at=item.starts_at,
        ends_at=item.ends_at,
        time_zone=time_zone,
        status=item.status,
        created_at=item.created_at,
        updated_at=item.updated_at,
        reviewed_at=item.reviewed_at,
        history=request_history(
            db,
            entity_type="schedule_availability_request",
            entity_id=item.id,
            created_at=item.created_at,
            kind="availability",
        ),
    )


def actual_work_seconds(entry: TimeEntry) -> float:
    segments = [segment for segment in entry.segments if segment.kind == "work"]
    now = datetime.now(UTC)
    total = sum(
        (
            (as_utc(segment.ended_at) if segment.ended_at is not None else now)
            - as_utc(segment.started_at)
        ).total_seconds()
        for segment in segments
    )
    if segments:
        return total
    if entry.ended_at is None:
        return 0
    return (as_utc(entry.ended_at) - as_utc(entry.started_at)).total_seconds()


@router.get("/employee-portal/me", response_model=EmployeePortalProfileRead)
def read_employee_portal_profile(
    employee: CurrentEmployee,
) -> EmployeePortalProfileRead:
    return EmployeePortalProfileRead(full_name=employee.full_name, job_title=employee.job_title)


@router.get("/employee-portal/me/shifts", response_model=list[EmployeePortalShiftRead])
def list_employee_shifts(
    db: PortalSession,
    employee: CurrentEmployee,
) -> list[EmployeePortalShiftRead]:
    shifts = db.scalars(
        select(ScheduleShift)
        .options(joinedload(ScheduleShift.object))
        .where(
            ScheduleShift.employee_id == employee.id,
            ScheduleShift.status == "published",
            SecurityObject.assignments.any(ObjectAssignment.user_id == employee.user_id),
        )
        .join(SecurityObject, ScheduleShift.object_id == SecurityObject.id)
        .order_by(ScheduleShift.starts_at, ScheduleShift.id)
    ).all()
    return [
        EmployeePortalShiftRead(
            id=shift.id,
            object_code=shift.object.code,
            object_name=shift.object.name,
            starts_at=shift.starts_at,
            ends_at=shift.ends_at,
            break_minutes=shift.break_minutes,
        )
        for shift in shifts
    ]


@router.get(
    "/employee-portal/me/shifts/{shift_id}",
    response_model=EmployeePortalShiftRead,
)
def read_employee_shift(
    shift_id: UUID,
    db: PortalSession,
    employee: CurrentEmployee,
) -> EmployeePortalShiftRead:
    shift = db.scalar(
        select(ScheduleShift)
        .options(joinedload(ScheduleShift.object))
        .where(
            ScheduleShift.id == shift_id,
            ScheduleShift.employee_id == employee.id,
            ScheduleShift.status == "published",
            SecurityObject.assignments.any(ObjectAssignment.user_id == employee.user_id),
        )
        .join(SecurityObject, ScheduleShift.object_id == SecurityObject.id)
    )
    if shift is None:
        raise HTTPException(status_code=404, detail="Veröffentlichter Dienst nicht gefunden.")
    return EmployeePortalShiftRead(
        id=shift.id,
        object_code=shift.object.code,
        object_name=shift.object.name,
        starts_at=shift.starts_at,
        ends_at=shift.ends_at,
        break_minutes=shift.break_minutes,
    )


@router.get("/employee-portal/me/tasks", response_model=list[EmployeePortalTaskRead])
def list_employee_tasks(
    db: PortalSession,
    employee: CurrentEmployee,
) -> list[EmployeePortalTaskRead]:
    tasks = db.scalars(
        select(Task)
        .where(Task.assigned_to_id == employee.user_id)
        .order_by(Task.due_at.asc().nulls_last(), Task.created_at.desc(), Task.id)
    ).all()
    return [EmployeePortalTaskRead.model_validate(task) for task in tasks]


@router.get(
    "/employee-portal/me/notifications",
    response_model=list[EmployeePortalNotificationRead],
)
def list_employee_notifications(
    db: PortalSession,
    _employee: CurrentEmployee,
    principal: PortalPrincipal,
) -> list[EmployeePortalNotificationRead]:
    notifications = db.scalars(
        select(Notification)
        .where(Notification.recipient_id == principal.user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(100)
    ).all()
    return [EmployeePortalNotificationRead.model_validate(item) for item in notifications]


@router.patch(
    "/employee-portal/me/notifications/{notification_id}/read",
    response_model=EmployeePortalNotificationRead,
)
def mark_employee_notification_read(
    notification_id: UUID,
    db: PortalSession,
    _employee: CurrentEmployee,
    principal: PortalPrincipal,
) -> EmployeePortalNotificationRead:
    notification = db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.recipient_id == principal.user.id,
        )
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="Benachrichtigung nicht gefunden.")
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        db.commit()
    return EmployeePortalNotificationRead.model_validate(notification)


@router.get(
    "/employee-portal/me/qualifications",
    response_model=list[EmployeePortalQualificationRead],
)
def list_employee_qualifications(
    db: PortalSession,
    employee: CurrentEmployee,
) -> list[EmployeePortalQualificationRead]:
    qualifications = db.scalars(
        select(EmployeeQualification)
        .where(
            EmployeeQualification.employee_id == employee.id,
            EmployeeQualification.archived_at.is_(None),
        )
        .order_by(EmployeeQualification.expires_on, EmployeeQualification.name)
    ).all()
    return [
        EmployeePortalQualificationRead.model_validate(qualification)
        for qualification in qualifications
    ]


@router.get(
    "/employee-portal/me/time-entries",
    response_model=EmployeePortalTimeOverviewRead,
)
def list_employee_time_entries(
    db: PortalSession,
    employee: CurrentEmployee,
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> EmployeePortalTimeOverviewRead:
    query = (
        select(TimeEntry)
        .join(SecurityObject, TimeEntry.object_id == SecurityObject.id)
        .where(
            TimeEntry.employee_id == employee.id,
            SecurityObject.assignments.any(ObjectAssignment.user_id == employee.user_id),
        )
    )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    entries = db.scalars(
        query.options(selectinload(TimeEntry.segments))
        .order_by(TimeEntry.started_at.desc(), TimeEntry.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    items = [
        EmployeePortalTimeEntryRead(
            id=entry.id,
            started_at=entry.started_at,
            ended_at=entry.ended_at,
            status=entry.status,
            actual_work_seconds=actual_work_seconds(entry),
        )
        for entry in entries
    ]
    return EmployeePortalTimeOverviewRead(
        items=items,
        total=total,
        total_work_seconds=sum(item.actual_work_seconds for item in items),
        limit=limit,
        offset=offset,
    )


@router.get("/employee-portal/me/absences", response_model=list[EmployeePortalAbsenceRead])
def list_employee_absences(
    db: PortalSession,
    employee: CurrentEmployee,
) -> list[EmployeePortalAbsenceRead]:
    absences = db.scalars(
        select(EmployeeAbsence)
        .where(EmployeeAbsence.employee_id == employee.id)
        .order_by(EmployeeAbsence.starts_on.desc(), EmployeeAbsence.id)
    ).all()
    return [read_absence(db, absence) for absence in absences]


@router.patch(
    "/employee-portal/me/absences/{absence_id}",
    response_model=EmployeePortalAbsenceRead,
)
def update_employee_absence_request(
    absence_id: UUID,
    payload: EmployeePortalAbsenceUpdate,
    request: Request,
    db: PortalSession,
    employee: CurrentEmployee,
    principal: PortalPrincipal,
) -> EmployeePortalAbsenceRead:
    absence = db.scalar(
        select(EmployeeAbsence)
        .where(
            EmployeeAbsence.id == absence_id,
            EmployeeAbsence.employee_id == employee.id,
        )
        .with_for_update()
    )
    if absence is None:
        raise HTTPException(status_code=404, detail="Abwesenheitsantrag nicht gefunden.")
    if absence.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nur noch nicht entschiedene Abwesenheitsanträge können geändert werden.",
        )
    changes = payload.model_dump(exclude_unset=True)
    starts_on = changes.get("starts_on", absence.starts_on)
    ends_on = changes.get("ends_on", absence.ends_on)
    if ends_on < starts_on:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Das Abwesenheitsende darf nicht vor dem Beginn liegen.",
        )
    for field, value in changes.items():
        setattr(absence, field, value)
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="employee_portal.absence_updated",
        entity_type="employee_absence",
        entity_id=str(absence.id),
        ip_address=request.client.host if request.client else None,
        details={"fields": sorted(changes)},
    )
    commit_portal_request(db)
    return read_absence(db, absence)


@router.post(
    "/employee-portal/me/absences",
    response_model=EmployeePortalAbsenceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_employee_absence(
    payload: EmployeePortalAbsenceCreate,
    request: Request,
    db: PortalSession,
    employee: CurrentEmployee,
    principal: PortalPrincipal,
) -> EmployeePortalAbsenceRead:
    absence = EmployeeAbsence(
        employee_id=employee.id,
        absence_type=payload.absence_type,
        starts_on=payload.starts_on,
        ends_on=payload.ends_on,
        status="pending",
        created_by_id=principal.user.id,
    )
    db.add(absence)
    flush_portal_request(db)
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="employee_portal.absence_requested",
        entity_type="employee_absence",
        entity_id=str(absence.id),
        ip_address=request.client.host if request.client else None,
        details={"fields": ["absence_type", "starts_on", "ends_on", "status"]},
    )
    commit_portal_request(db)
    return read_absence(db, absence)


@router.get(
    "/employee-portal/me/availability-requests",
    response_model=list[EmployeePortalAvailabilityRead],
)
def list_employee_availability_requests(
    db: PortalSession,
    employee: CurrentEmployee,
) -> list[EmployeePortalAvailabilityRead]:
    settings = get_schedule_settings(db)
    requests = db.scalars(
        select(ScheduleAvailabilityRequest)
        .where(ScheduleAvailabilityRequest.employee_id == employee.id)
        .order_by(ScheduleAvailabilityRequest.starts_at.desc(), ScheduleAvailabilityRequest.id)
    ).all()
    return [read_availability_request(db, item, settings.time_zone) for item in requests]


@router.post(
    "/employee-portal/me/availability-requests",
    response_model=EmployeePortalAvailabilityRead,
    status_code=status.HTTP_201_CREATED,
)
def create_employee_availability_request(
    payload: EmployeePortalAvailabilityCreate,
    request: Request,
    db: PortalSession,
    employee: CurrentEmployee,
    principal: PortalPrincipal,
) -> EmployeePortalAvailabilityRead:
    settings = get_schedule_settings(db)
    zone = get_zone(settings.time_zone)
    starts_at = local_to_utc(payload.starts_at_local, zone, payload.starts_at_fold)
    ends_at = local_to_utc(payload.ends_at_local, zone, payload.ends_at_fold)
    if ends_at <= starts_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Das Ende des Zeitraums muss nach der Umrechnung nach dem Beginn liegen.",
        )
    if ends_at - starts_at > timedelta(days=366):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Wunsch- und Sperrzeiträume dürfen höchstens 366 Tage umfassen.",
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
    flush_portal_request(db)
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="employee_portal.availability_requested",
        entity_type="schedule_availability_request",
        entity_id=str(item.id),
        ip_address=request.client.host if request.client else None,
        details={"fields": ["kind", "starts_at", "ends_at", "status"]},
    )
    commit_portal_request(db)
    return read_availability_request(db, item, settings.time_zone)


@router.patch(
    "/employee-portal/me/availability-requests/{request_id}",
    response_model=EmployeePortalAvailabilityRead,
)
def update_employee_availability_request(
    request_id: UUID,
    payload: EmployeePortalAvailabilityUpdate,
    request: Request,
    db: PortalSession,
    employee: CurrentEmployee,
    principal: PortalPrincipal,
) -> EmployeePortalAvailabilityRead:
    item = db.scalar(
        select(ScheduleAvailabilityRequest)
        .where(
            ScheduleAvailabilityRequest.id == request_id,
            ScheduleAvailabilityRequest.employee_id == employee.id,
        )
        .with_for_update()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Verfügbarkeitsantrag nicht gefunden.")
    if item.status != "open":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nur noch nicht entschiedene Verfügbarkeitsanträge können geändert werden.",
        )
    settings = get_schedule_settings(db)
    zone = get_zone(settings.time_zone)
    changes = payload.model_dump(exclude_unset=True)
    existing_start = as_utc(item.starts_at)
    existing_end = as_utc(item.ends_at)
    starts_at = existing_start
    ends_at = existing_end
    if payload.starts_at_local is not None:
        existing_local_start = existing_start.astimezone(zone).replace(tzinfo=None)
        if payload.starts_at_local != existing_local_start:
            starts_at = local_to_utc(payload.starts_at_local, zone, payload.starts_at_fold)
    if payload.ends_at_local is not None:
        existing_local_end = existing_end.astimezone(zone).replace(tzinfo=None)
        if payload.ends_at_local != existing_local_end:
            ends_at = local_to_utc(payload.ends_at_local, zone, payload.ends_at_fold)
    if ends_at <= starts_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Das Ende des Zeitraums muss nach der Umrechnung nach dem Beginn liegen.",
        )
    if ends_at - starts_at > timedelta(days=366):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Wunsch- und Sperrzeiträume dürfen höchstens 366 Tage umfassen.",
        )
    lock_employee_schedule(db, employee.id)
    changed_fields = []
    if "kind" in changes and changes["kind"] != item.kind:
        item.kind = changes["kind"]
        changed_fields.append("kind")
    if starts_at != as_utc(item.starts_at):
        item.starts_at = starts_at
        changed_fields.append("starts_at")
    if ends_at != as_utc(item.ends_at):
        item.ends_at = ends_at
        changed_fields.append("ends_at")
    if changed_fields:
        add_audit_entry(
            db,
            actor_id=principal.user.id,
            action="employee_portal.availability_updated",
            entity_type="schedule_availability_request",
            entity_id=str(item.id),
            ip_address=request.client.host if request.client else None,
            details={"fields": sorted(changed_fields)},
        )
        commit_portal_request(db)
    return read_availability_request(db, item, settings.time_zone)
