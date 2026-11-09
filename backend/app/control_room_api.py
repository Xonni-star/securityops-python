import csv
from datetime import UTC, date, datetime, time, timedelta
from io import StringIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.auth import AuthPrincipal, require_permission
from app.control_room_schemas import (
    ControlRoomAbsence,
    ControlRoomBillingApproval,
    ControlRoomIncident,
    ControlRoomObject,
    ControlRoomOWKSEvent,
    ControlRoomQualification,
    ControlRoomRead,
    ControlRoomShift,
    ControlRoomTask,
    ObjectOperationsReportItem,
    ObjectOperationsReportRead,
)
from app.database import get_db
from app.models import (
    BillingInvoice,
    Contract,
    Employee,
    EmployeeAbsence,
    EmployeeQualification,
    Incident,
    ObjectAssignment,
    ObjectQualificationRequirement,
    OWKSEvent,
    OWKSEventStatus,
    ScheduleSettings,
    ScheduleShift,
    SecurityObject,
    Task,
    User,
)
from app.qualification_checks import missing_qualification_requirements
from app.scheduling_api import as_utc, get_zone

router = APIRouter()
MAX_ITEMS = 100
MAX_REPORT_ITEMS = 100
MAX_REPORT_OFFSET = 10_000
OPEN_TASK_STATUSES = ("open", "in_progress", "blocked")
OPEN_INCIDENT_STATUSES = ("reported", "investigating", "action_required")
TASK_STATUSES = ("open", "in_progress", "blocked", "completed", "cancelled")


def _count(db: Session, query) -> int:
    return db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0


def _utc_range(day_start: date, day_end: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(day_start, time.min, tzinfo=UTC),
        datetime.combine(day_end + timedelta(days=1), time.min, tzinfo=UTC),
    )


def _assigned_employee_ids(db: Session, object_ids: list[UUID]) -> list[UUID]:
    if not object_ids:
        return []
    return list(
        db.scalars(
            select(Employee.id)
            .join(User, Employee.user_id == User.id)
            .join(ObjectAssignment, ObjectAssignment.user_id == User.id)
            .where(
                ObjectAssignment.object_id.in_(object_ids),
                Employee.archived_at.is_(None),
                Employee.employment_status == "active",
            )
            .distinct()
        ).all()
    )


@router.get(
    "/control-room",
    response_model=ControlRoomRead,
    response_model_exclude_none=True,
)
def get_control_room(
    object_id: UUID | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_permission("control_room.read")),
) -> ControlRoomRead:
    permissions = principal.permission_codes
    if "objects.read" not in permissions:
        raise HTTPException(403, "Keine Berechtigung für Objekte in der Leitstelle")

    now = datetime.now(UTC)
    start_day = from_date or (now.date() - timedelta(days=7))
    end_day = to_date or (now.date() + timedelta(days=30))
    if end_day < start_day:
        raise HTTPException(422, "Das Ende des Leitstellenzeitraums liegt vor dem Beginn.")
    if end_day == date.max:
        raise HTTPException(422, "Das Ende des Leitstellenzeitraums liegt außerhalb des Bereichs.")
    if (end_day - start_day).days > 366:
        raise HTTPException(422, "Der Leitstellenzeitraum darf höchstens 367 Tage umfassen.")
    range_start, range_end = _utc_range(start_day, end_day)

    object_query = select(SecurityObject).where(
        SecurityObject.status == "active",
        SecurityObject.archived_at.is_(None),
    )
    if "objects.read_all" not in permissions:
        object_query = object_query.where(
            SecurityObject.id.in_(
                select(ObjectAssignment.object_id).where(
                    ObjectAssignment.user_id == principal.user.id
                )
            )
        )
    allowed_objects = db.scalars(
        object_query.order_by(SecurityObject.name, SecurityObject.id)
    ).all()
    allowed_object_ids = [item.id for item in allowed_objects]
    if object_id is not None:
        if object_id not in allowed_object_ids:
            raise HTTPException(404, "Objekt nicht gefunden")
        scoped_object_ids = [object_id]
    else:
        scoped_object_ids = allowed_object_ids
    counts: dict[str, int] = {}
    objects = [
        ControlRoomObject(id=item.id, code=item.code, name=item.name) for item in allowed_objects
    ]
    counts["active_objects"] = len(objects)

    result: dict[str, object] = {
        "generated_at": now,
        "range_start": start_day,
        "range_end": end_day,
        "counts": counts,
        "objects": objects,
    }

    if "scheduling.read" in permissions:
        shifts_query = (
            select(ScheduleShift, Employee.full_name, SecurityObject.name)
            .join(Employee, ScheduleShift.employee_id == Employee.id)
            .join(SecurityObject, ScheduleShift.object_id == SecurityObject.id)
            .where(
                ScheduleShift.object_id.in_(scoped_object_ids),
                ScheduleShift.status == "published",
                ScheduleShift.starts_at <= now,
                ScheduleShift.ends_at > now,
            )
        )
        if "employees.read" not in permissions:
            shifts_query = shifts_query.where(Employee.user_id == principal.user.id)
        shifts_query = shifts_query.order_by(ScheduleShift.starts_at, ScheduleShift.id)
        shift_rows = db.execute(shifts_query.limit(MAX_ITEMS)).all()
        shifts_count = _count(db, shifts_query)
        counts["active_shifts"] = shifts_count
        result["shifts"] = [
            ControlRoomShift(
                id=shift.id,
                employee_id=shift.employee_id,
                employee_name=employee_name,
                object_id=shift.object_id,
                object_name=shift_object_name,
                starts_at=shift.starts_at,
                ends_at=shift.ends_at,
                status="published",
            )
            for shift, employee_name, shift_object_name in shift_rows
        ]

    if "owks.read" in permissions:
        latest_event_status = (
            select(OWKSEventStatus.status)
            .where(OWKSEventStatus.event_id == OWKSEvent.id)
            .order_by(OWKSEventStatus.sequence_no.desc())
            .limit(1)
            .correlate(OWKSEvent)
            .scalar_subquery()
        )
        events_query = (
            select(OWKSEvent, SecurityObject.name, latest_event_status)
            .join(SecurityObject, OWKSEvent.object_id == SecurityObject.id)
            .where(
                OWKSEvent.object_id.in_(scoped_object_ids),
                OWKSEvent.occurred_at >= range_start,
                OWKSEvent.occurred_at < range_end,
                or_(
                    OWKSEvent.event_type == "missed",
                    OWKSEvent.event_type.in_(("deviation", "manipulation", "notification"))
                    & OWKSEvent.severity.in_(("warning", "critical")),
                ),
                or_(
                    latest_event_status.is_(None),
                    latest_event_status.in_(("open", "in_progress")),
                ),
            )
            .order_by(
                case(
                    (OWKSEvent.severity == "critical", 0),
                    (OWKSEvent.severity == "warning", 1),
                    else_=2,
                ),
                OWKSEvent.occurred_at.desc(),
                OWKSEvent.id,
            )
        )
        event_rows = db.execute(events_query.limit(MAX_ITEMS)).all()
        counts["open_owks_events"] = _count(db, events_query)
        result["owks_events"] = [
            ControlRoomOWKSEvent(
                id=event.id,
                object_id=event.object_id,
                object_name=event_object_name,
                event_type=event.event_type,
                severity=event.severity,
                title=event.title,
                occurred_at=event.occurred_at,
                status=status_value or "open",
            )
            for event, event_object_name, status_value in event_rows
        ]

    if {"incidents.read", "incidents.read_all", "incidents.manage_all"} & permissions:
        incident_object_ids = scoped_object_ids
        if not {"incidents.read_all", "incidents.manage_all"} & permissions:
            assigned_object_ids = set(
                db.scalars(
                    select(ObjectAssignment.object_id).where(
                        ObjectAssignment.user_id == principal.user.id
                    )
                ).all()
            )
            incident_object_ids = [
                item_id for item_id in scoped_object_ids if item_id in assigned_object_ids
            ]
        incidents_query = (
            select(Incident, SecurityObject.name, User.full_name)
            .join(SecurityObject, Incident.object_id == SecurityObject.id)
            .join(User, Incident.assigned_to_id == User.id)
            .where(
                Incident.object_id.in_(incident_object_ids),
                Incident.status.in_(OPEN_INCIDENT_STATUSES),
            )
            .order_by(
                case(
                    (Incident.severity == "critical", 0),
                    (Incident.severity == "high", 1),
                    (Incident.severity == "medium", 2),
                    else_=3,
                ),
                Incident.due_at.asc().nulls_last(),
                Incident.created_at.desc(),
            )
        )
        incident_rows = db.execute(incidents_query.limit(MAX_ITEMS)).all()
        counts["open_incidents"] = _count(db, incidents_query)
        counts["overdue_incidents"] = _count(
            db,
            incidents_query.where(Incident.due_at < now),
        )
        result["incidents"] = [
            ControlRoomIncident(
                id=incident.id,
                title=incident.title,
                object_id=incident.object_id,
                object_name=incident_object_name,
                severity=incident.severity,
                status=incident.status,
                due_at=incident.due_at,
                assigned_to_name=assignee_name,
                created_at=incident.created_at,
            )
            for incident, incident_object_name, assignee_name in incident_rows
        ]

    task_read_permissions = {"tasks.read_own", "tasks.read_all", "tasks.manage_all"}
    if task_read_permissions & permissions:
        tasks_query = (
            select(Task, SecurityObject.name, User.full_name)
            .outerjoin(SecurityObject, Task.object_id == SecurityObject.id)
            .join(User, Task.assigned_to_id == User.id)
            .where(Task.status.in_(OPEN_TASK_STATUSES))
        )
        task_object_scope = Task.object_id.in_(scoped_object_ids)
        if object_id is None:
            task_object_scope = or_(
                task_object_scope,
                and_(
                    Task.object_id.is_(None),
                    or_(
                        Task.assigned_to_id == principal.user.id,
                        Task.created_by_id == principal.user.id,
                    ),
                ),
            )
        if not {"tasks.read_all", "tasks.manage_all"} & permissions:
            tasks_query = tasks_query.where(
                task_object_scope,
                or_(
                    Task.assigned_to_id == principal.user.id,
                    Task.created_by_id == principal.user.id,
                    Task.object_id.in_(
                        select(ObjectAssignment.object_id).where(
                            ObjectAssignment.user_id == principal.user.id
                        )
                    ),
                ),
            )
        else:
            tasks_query = tasks_query.where(task_object_scope)
        tasks_query = tasks_query.order_by(
            case(
                (Task.priority == "urgent", 0),
                (Task.priority == "high", 1),
                else_=2,
            ),
            Task.due_at.asc().nulls_last(),
            Task.created_at.desc(),
        )
        task_rows = db.execute(tasks_query.limit(MAX_ITEMS)).all()
        counts["open_tasks"] = _count(db, tasks_query)
        counts["urgent_tasks"] = _count(
            db,
            tasks_query.where((Task.priority == "urgent") | (Task.due_at < now)),
        )
        result["tasks"] = [
            ControlRoomTask(
                id=task.id,
                title=task.title,
                object_id=task.object_id,
                object_name=task_object_name,
                status=task.status,
                priority=task.priority,
                due_at=task.due_at,
                assigned_to_name=assignee_name,
                created_at=task.created_at,
            )
            for task, task_object_name, assignee_name in task_rows
        ]

    employee_ids = _assigned_employee_ids(db, scoped_object_ids)
    if "employees.absences.read" in permissions:
        absences_query = (
            select(EmployeeAbsence, Employee.full_name)
            .join(Employee, EmployeeAbsence.employee_id == Employee.id)
            .where(
                EmployeeAbsence.employee_id.in_(employee_ids),
                EmployeeAbsence.status.in_(("pending", "approved")),
                EmployeeAbsence.starts_on <= end_day,
                EmployeeAbsence.ends_on >= start_day,
            )
            .order_by(EmployeeAbsence.starts_on, EmployeeAbsence.id)
        )
        absence_rows = db.execute(absences_query.limit(MAX_ITEMS)).all()
        counts["active_absences"] = _count(db, absences_query)
        result["absences"] = [
            ControlRoomAbsence(
                employee_id=absence.employee_id,
                employee_name=employee_name,
                absence_type=absence.absence_type,
                status=absence.status,
                starts_on=absence.starts_on,
                ends_on=absence.ends_on,
            )
            for absence, employee_name in absence_rows
        ]

    if "employees.read" in permissions:
        qualifications_query = (
            select(EmployeeQualification, Employee.full_name)
            .join(Employee, EmployeeQualification.employee_id == Employee.id)
            .where(
                EmployeeQualification.employee_id.in_(employee_ids),
                EmployeeQualification.archived_at.is_(None),
                EmployeeQualification.expires_on.is_not(None),
                EmployeeQualification.expires_on <= end_day,
            )
            .order_by(EmployeeQualification.expires_on, EmployeeQualification.id)
        )
        qualification_rows = db.execute(qualifications_query.limit(MAX_ITEMS)).all()
        counts["qualification_problems"] = _count(db, qualifications_query)
        result["qualifications"] = [
            ControlRoomQualification(
                employee_id=qualification.employee_id,
                employee_name=employee_name,
                category=qualification.category,
                name=qualification.name,
                expires_on=qualification.expires_on,
            )
            for qualification, employee_name in qualification_rows
        ]

    if {"billing.invoices.read", "billing.invoices.approve"} <= permissions:
        approvals_query = (
            select(BillingInvoice, Contract.object_id, SecurityObject.name)
            .join(Contract, BillingInvoice.contract_id == Contract.id)
            .join(SecurityObject, Contract.object_id == SecurityObject.id)
            .where(
                BillingInvoice.kind == "invoice",
                BillingInvoice.status == "draft",
                BillingInvoice.archived_at.is_(None),
                Contract.object_id.in_(scoped_object_ids),
            )
            .order_by(BillingInvoice.created_at, BillingInvoice.id)
        )
        approval_rows = db.execute(approvals_query.limit(MAX_ITEMS)).all()
        counts["billing_approvals"] = _count(db, approvals_query)
        result["billing_approvals"] = [
            ControlRoomBillingApproval(
                id=invoice.id,
                invoice_number=invoice.invoice_number,
                object_name=invoice_object_name,
                issued_on=invoice.issued_on,
                created_at=invoice.created_at,
            )
            for invoice, _object_id, invoice_object_name in approval_rows
        ]

    return ControlRoomRead.model_validate(result)


def _object_operations_report(
    db: Session,
    principal: AuthPrincipal,
    *,
    object_id: UUID | None,
    from_date: date,
    to_date: date,
    limit: int,
    offset: int,
) -> ObjectOperationsReportRead:
    permissions = principal.permission_codes
    if "objects.read" not in permissions:
        raise HTTPException(403, "Keine Berechtigung für Objektberichte")
    if to_date < from_date:
        raise HTTPException(422, "Das Ende des Berichtszeitraums liegt vor dem Beginn.")
    if to_date == date.max or (to_date - from_date).days > 366:
        raise HTTPException(422, "Der Berichtszeitraum darf höchstens 367 Tage umfassen.")

    allowed_objects = select(SecurityObject.id).where(
        SecurityObject.status == "active",
        SecurityObject.archived_at.is_(None),
    )
    if "objects.read_all" not in permissions:
        allowed_objects = allowed_objects.where(
            SecurityObject.id.in_(
                select(ObjectAssignment.object_id).where(
                    ObjectAssignment.user_id == principal.user.id
                )
            )
        )
    if object_id is not None:
        allowed_objects = allowed_objects.where(SecurityObject.id == object_id)

    total = db.scalar(select(func.count()).select_from(allowed_objects.subquery())) or 0
    if object_id is not None and total == 0:
        raise HTTPException(404, "Objekt nicht gefunden")

    page_query = (
        select(SecurityObject)
        .where(SecurityObject.id.in_(allowed_objects))
        .order_by(SecurityObject.code, SecurityObject.id)
        .offset(offset)
        .limit(limit + 1)
    )
    page_objects = db.scalars(page_query).all()
    has_more = len(page_objects) > limit
    page_objects = page_objects[:limit]
    object_ids = [item.id for item in page_objects]

    range_start = datetime.combine(from_date, time.min, tzinfo=UTC)
    range_end = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=UTC)
    shift_counts: dict[UUID, int] = {}
    incident_counts: dict[UUID, int] = {}
    control_counts: dict[UUID, dict[str, int]] = {}
    task_counts: dict[UUID, dict[str, int]] = {
        item_id: dict.fromkeys(TASK_STATUSES, 0) for item_id in object_ids
    }
    qualification_conflict_counts: dict[UUID, int] = {}

    if object_ids:
        shift_counts = dict(
            db.execute(
                select(ScheduleShift.object_id, func.count())
                .where(
                    ScheduleShift.object_id.in_(object_ids),
                    ScheduleShift.status == "published",
                    ScheduleShift.starts_at < range_end,
                    ScheduleShift.ends_at > range_start,
                )
                .group_by(ScheduleShift.object_id)
            ).all()
        )
        incident_counts = dict(
            db.execute(
                select(Incident.object_id, func.count())
                .where(
                    Incident.object_id.in_(object_ids),
                    Incident.created_at >= range_start,
                    Incident.created_at < range_end,
                )
                .group_by(Incident.object_id)
            ).all()
        )
        for item_id, event_type, count in db.execute(
            select(OWKSEvent.object_id, OWKSEvent.event_type, func.count())
            .where(
                OWKSEvent.object_id.in_(object_ids),
                OWKSEvent.event_type.in_(("control", "missed")),
                OWKSEvent.occurred_at >= range_start,
                OWKSEvent.occurred_at < range_end,
            )
            .group_by(OWKSEvent.object_id, OWKSEvent.event_type)
        ).all():
            control_counts.setdefault(item_id, {})[event_type] = count
        for item_id, task_status, count in db.execute(
            select(Task.object_id, Task.status, func.count())
            .where(
                Task.object_id.in_(object_ids),
                Task.created_at >= range_start,
                Task.created_at < range_end,
            )
            .group_by(Task.object_id, Task.status)
        ).all():
            if task_status in TASK_STATUSES:
                task_counts[item_id][task_status] = count
        if "employees.read" in permissions:
            required_names: dict[UUID, list[str]] = {}
            for requirement_object_id, requirement_name in db.execute(
                select(
                    ObjectQualificationRequirement.object_id,
                    ObjectQualificationRequirement.name,
                ).where(ObjectQualificationRequirement.object_id.in_(object_ids))
            ).all():
                required_names.setdefault(requirement_object_id, []).append(requirement_name)

            now = datetime.now(UTC)
            shifts = db.execute(
                select(
                    ScheduleShift.object_id,
                    ScheduleShift.employee_id,
                    ScheduleShift.starts_at,
                    ScheduleShift.ends_at,
                    ScheduleShift.required_qualification,
                ).where(
                    ScheduleShift.object_id.in_(object_ids),
                    ScheduleShift.status == "published",
                    ScheduleShift.starts_at < range_end,
                    ScheduleShift.ends_at > range_start,
                    ScheduleShift.ends_at > now,
                    or_(
                        ScheduleShift.required_qualification.is_not(None),
                        ScheduleShift.object_id.in_(
                            select(ObjectQualificationRequirement.object_id).where(
                                ObjectQualificationRequirement.object_id.in_(object_ids)
                            )
                        ),
                    ),
                )
            ).all()
            employee_ids = {shift.employee_id for shift in shifts}
            qualifications_by_employee: dict[UUID, list[EmployeeQualification]] = {}
            if employee_ids:
                for qualification in db.scalars(
                    select(EmployeeQualification).where(
                        EmployeeQualification.employee_id.in_(employee_ids),
                        EmployeeQualification.archived_at.is_(None),
                    )
                ).all():
                    qualifications_by_employee.setdefault(qualification.employee_id, []).append(
                        qualification
                    )
            time_zone = (
                db.scalar(select(ScheduleSettings.time_zone).where(ScheduleSettings.id == 1))
                or "Europe/Berlin"
            )
            zone = get_zone(time_zone)
            for shift in shifts:
                start_day = as_utc(shift.starts_at).astimezone(zone).date()
                end_day = (
                    (as_utc(shift.ends_at) - timedelta(microseconds=1)).astimezone(zone).date()
                )
                if missing_qualification_requirements(
                    shift_requirement=shift.required_qualification,
                    object_requirements=required_names.get(shift.object_id, []),
                    qualifications=qualifications_by_employee.get(shift.employee_id, []),
                    starts_on=start_day,
                    ends_on=end_day,
                ):
                    qualification_conflict_counts[shift.object_id] = (
                        qualification_conflict_counts.get(shift.object_id, 0) + 1
                    )

    return ObjectOperationsReportRead(
        range_start=from_date,
        range_end=to_date,
        total=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
        items=[
            ObjectOperationsReportItem(
                object_id=item.id,
                object_code=item.code,
                object_name=item.name,
                published_assigned_shifts=shift_counts.get(item.id, 0),
                incidents_created=incident_counts.get(item.id, 0),
                control_events=control_counts.get(item.id, {}).get("control", 0),
                missed_controls=control_counts.get(item.id, {}).get("missed", 0),
                task_status_counts=task_counts[item.id],
                qualification_conflict_shifts=(
                    qualification_conflict_counts.get(item.id, 0)
                    if "employees.read" in permissions
                    else None
                ),
            )
            for item in page_objects
        ],
    )


@router.get(
    "/object-operations-report",
    response_model=ObjectOperationsReportRead,
)
def get_object_operations_report(
    object_id: UUID | None = None,
    from_date: date = Query(),
    to_date: date = Query(),
    limit: int = Query(50, ge=1, le=MAX_REPORT_ITEMS),
    offset: int = Query(0, ge=0, le=MAX_REPORT_OFFSET),
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_permission("control_room.read")),
) -> ObjectOperationsReportRead:
    return _object_operations_report(
        db,
        principal,
        object_id=object_id,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )


def _safe_csv_cell(value: object) -> str:
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{text}"
    return text


@router.get("/object-operations-report.csv")
def export_object_operations_report(
    object_id: UUID | None = None,
    from_date: date = Query(),
    to_date: date = Query(),
    limit: int = Query(50, ge=1, le=MAX_REPORT_ITEMS),
    offset: int = Query(0, ge=0, le=MAX_REPORT_OFFSET),
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_permission("control_room.read")),
) -> Response:
    report = _object_operations_report(
        db,
        principal,
        object_id=object_id,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )
    output = StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(
        (
            "Objektnummer",
            "Objekt",
            "Zeitraum von (UTC)",
            "Zeitraum bis (UTC)",
            "Veröffentlichte zugewiesene Schichten",
            "Erstellte Vorfälle",
            "Kontrollereignisse",
            "Versäumte Kontrollen",
            "Veröffentlichte Schichten mit Qualifikationslücken",
            "Aufgaben offen",
            "Aufgaben in Bearbeitung",
            "Aufgaben blockiert",
            "Aufgaben abgeschlossen",
            "Aufgaben abgebrochen",
        )
    )
    for item in report.items:
        writer.writerow(
            _safe_csv_cell(value)
            for value in (
                item.object_code,
                item.object_name,
                report.range_start.isoformat(),
                report.range_end.isoformat(),
                item.published_assigned_shifts,
                item.incidents_created,
                item.control_events,
                item.missed_controls,
                (
                    item.qualification_conflict_shifts
                    if item.qualification_conflict_shifts is not None
                    else ""
                ),
                *(item.task_status_counts[status] for status in TASK_STATUSES),
            )
        )
    return Response(
        content=f"\ufeff{output.getvalue()}",
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="objektbetriebsbericht.csv"'},
    )
