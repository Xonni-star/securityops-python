import hashlib
from datetime import UTC, date, datetime, timedelta
from pathlib import PurePosixPath
from typing import Literal
from urllib.parse import quote
from uuid import UUID, uuid4

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
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.assignment_history import record_employee_object_assignment_event
from app.auth import AuthPrincipal, add_audit_entry, get_auth_principal, require_permission
from app.database import get_db
from app.document_storage import read_attachment, remove_file, store_file
from app.models import (
    Employee,
    EmployeeAbsence,
    EmployeeHistory,
    EmployeeObjectAssignmentHistory,
    EmployeePortalDocumentGrant,
    EmployeeQualification,
    EmployeeQualificationDocument,
    EmployeeSensitiveDetails,
    ObjectAssignment,
    ObjectHistory,
    Role,
    SecurityObject,
    User,
)
from app.schemas import (
    EmployeeAbsenceCreate,
    EmployeeAbsenceRead,
    EmployeeAbsenceUpdate,
    EmployeeAccountCandidateRead,
    EmployeeCreate,
    EmployeeHistoryRead,
    EmployeeObjectAssignmentHistoryRead,
    EmployeeObjectAssignmentRead,
    EmployeeObjectCandidateRead,
    EmployeePage,
    EmployeeQualificationCreate,
    EmployeeQualificationDocumentRead,
    EmployeeQualificationExpiringRead,
    EmployeeQualificationRead,
    EmployeeQualificationUpdate,
    EmployeeRead,
    EmployeeSensitiveRead,
    EmployeeSensitiveUpdate,
    EmployeeStatus,
    EmployeeUpdate,
)
from app.upload_scanning import scan_upload_or_reject

router = APIRouter()
MAX_QUALIFICATION_DOCUMENT_SIZE = 10 * 1024 * 1024
QUALIFICATION_DOCUMENT_TYPES = {
    ".pdf": ("application/pdf", b"%PDF-"),
    ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
    ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
}


def employee_query():
    return select(Employee).options(
        selectinload(Employee.user)
        .selectinload(User.object_assignments)
        .selectinload(ObjectAssignment.object)
    )


def visible_object_ids(db: Session, principal) -> set[UUID] | None:
    if "objects.read_all" in principal.permission_codes:
        return None
    return set(
        db.scalars(
            select(ObjectAssignment.object_id).where(ObjectAssignment.user_id == principal.user.id)
        ).all()
    )


def employee_read(
    employee: Employee,
    accessible_object_ids: set[UUID] | None,
) -> EmployeeRead:
    result = EmployeeRead.model_validate(employee)
    if accessible_object_ids is not None:
        assigned_objects = []
        if employee.user is not None:
            assigned_objects = [
                f"{assignment.object.name} ({assignment.object.code})"
                for assignment in employee.user.object_assignments
                if assignment.object_id in accessible_object_ids
            ]
        result = result.model_copy(update={"assigned_objects": assigned_objects})
    return result


def accessible_object_filter(principal):
    if "objects.read_all" in principal.permission_codes:
        return None
    return SecurityObject.assignments.any(ObjectAssignment.user_id == principal.user.id)


def get_employee_or_404(db: Session, employee_id: UUID) -> Employee:
    employee = db.scalar(employee_query().where(Employee.id == employee_id))
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Mitarbeiter nicht gefunden"
        )
    return employee


def ensure_employee_is_active(employee: Employee) -> None:
    if employee.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Archivierte Mitarbeiter müssen vor Änderungen reaktiviert werden",
        )


def validate_linked_user(db: Session, user_id: UUID | None) -> User | None:
    if user_id is None:
        return None
    user = db.scalar(
        select(User)
        .options(selectinload(User.roles))
        .where(User.id == user_id, User.is_active.is_(True))
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Das verknüpfte Benutzerkonto muss vorhanden und aktiv sein",
        )
    if not any(role.code in {"employee", "object_manager"} for role in user.roles):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Das verknüpfte Konto benötigt eine Mitarbeiter- oder Objektleitungsrolle",
        )
    return user


def record_employee_event(
    db: Session,
    *,
    employee: Employee,
    actor_id: UUID,
    action: str,
    changed_fields: set[str],
    ip_address: str | None,
) -> None:
    sorted_fields = sorted(changed_fields)
    db.add(
        EmployeeHistory(
            employee_id=employee.id,
            actor_id=actor_id,
            action=action,
            changed_fields=sorted_fields,
        )
    )
    add_audit_entry(
        db,
        actor_id=actor_id,
        action=f"employees.{action}",
        entity_type="employee",
        entity_id=str(employee.id),
        ip_address=ip_address,
        details={"fields": sorted_fields},
    )


def commit_employee_transaction(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Die Personaländerung verletzt eine Datenbankbedingung",
        ) from exc


def flush_employee_transaction(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Die Personaländerung verletzt eine Datenbankbedingung",
        ) from exc


def validate_employee_dates(hired_on: date, ended_on: date | None) -> None:
    if ended_on is not None and ended_on < hired_on:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Das Austrittsdatum darf nicht vor dem Eintrittsdatum liegen",
        )


def employee_absence_query(employee_id: UUID):
    return select(EmployeeAbsence).where(EmployeeAbsence.employee_id == employee_id)


def get_employee_qualification_or_404(
    db: Session,
    employee_id: UUID,
    qualification_id: UUID,
) -> EmployeeQualification:
    qualification = db.scalar(
        select(EmployeeQualification).where(
            EmployeeQualification.id == qualification_id,
            EmployeeQualification.employee_id == employee_id,
        )
    )
    if qualification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Qualifikationsnachweis nicht gefunden",
        )
    return qualification


def require_object_assignment_access(
    principal=Depends(require_permission("employees.manage")),
):
    if "objects.assign" not in principal.permission_codes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Objektzuweisungen dürfen nicht verwaltet werden",
        )
    return principal


def get_assignable_object(
    db: Session,
    object_id: UUID,
    principal,
    *,
    active_only: bool = True,
) -> SecurityObject:
    query = select(SecurityObject).where(SecurityObject.id == object_id)
    if active_only:
        query = query.where(SecurityObject.archived_at.is_(None))
    if "objects.manage_all" not in principal.permission_codes:
        query = query.where(
            SecurityObject.assignments.any(ObjectAssignment.user_id == principal.user.id)
        )
    obj = db.scalar(query)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Objekt nicht gefunden")
    return obj


def record_object_assignment_event(
    db: Session,
    *,
    employee: Employee,
    obj: SecurityObject,
    actor_id: UUID,
    action: Literal["assigned", "ended"],
    ip_address: str | None,
) -> None:
    if employee.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Für Objektzuweisungen muss ein Benutzerkonto verknüpft sein",
        )
    record_employee_object_assignment_event(
        db,
        employee_id=employee.id,
        object_id=obj.id,
        user_id=employee.user_id,
        actor_id=actor_id,
        action=action,
        ip_address=ip_address,
    )
    db.add(
        ObjectHistory(
            object_id=obj.id,
            actor_id=actor_id,
            action=f"employee_{action}",
            changed_fields=["assignments"],
        )
    )


def end_employee_object_assignments(
    db: Session,
    *,
    employee: Employee,
    actor_id: UUID,
    ip_address: str | None,
) -> int:
    if employee.user_id is None:
        return 0
    assignments = db.execute(
        select(ObjectAssignment, SecurityObject)
        .join(SecurityObject, SecurityObject.id == ObjectAssignment.object_id)
        .where(ObjectAssignment.user_id == employee.user_id)
        .with_for_update()
    ).all()
    for assignment, obj in assignments:
        record_object_assignment_event(
            db,
            employee=employee,
            obj=obj,
            actor_id=actor_id,
            action="ended",
            ip_address=ip_address,
        )
        db.delete(assignment)
    return len(assignments)


def safe_qualification_filename(filename: str | None, extension: str) -> str:
    raw_name = (filename or "").replace("\\", "/").split("/")[-1]
    safe_name = "".join(
        character for character in raw_name if ord(character) >= 32 and ord(character) != 127
    ).strip()
    safe_name = safe_name[:200]
    if not safe_name or PurePosixPath(safe_name).suffix.lower() != extension:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Der Dateiname muss zur unterstützten Dateiendung passen",
        )
    return safe_name


@router.get("/employees", response_model=EmployeePage)
def list_employees(
    q: str | None = Query(default=None, max_length=200),
    employment_status: EmployeeStatus | None = Query(default=None, alias="status"),
    include_archived: bool = False,
    sort_by: Literal["employee_number", "full_name", "hired_on", "employment_status"] = "full_name",
    sort_order: Literal["asc", "desc"] = "asc",
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal=Depends(require_permission("employees.read")),
) -> EmployeePage:
    query = employee_query()
    count_query = select(func.count()).select_from(Employee)
    filters = []
    if not include_archived:
        filters.append(Employee.archived_at.is_(None))
    if employment_status is not None:
        filters.append(Employee.employment_status == employment_status)
    if q and q.strip():
        term = f"%{q.strip()}%"
        filters.append(
            or_(
                Employee.employee_number.ilike(term),
                Employee.full_name.ilike(term),
                Employee.email.ilike(term),
                Employee.phone.ilike(term),
                Employee.job_title.ilike(term),
            )
        )
    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)
    sort_columns = {
        "employee_number": Employee.employee_number,
        "full_name": Employee.full_name,
        "hired_on": Employee.hired_on,
        "employment_status": Employee.employment_status,
    }
    ordering = sort_columns[sort_by].asc() if sort_order == "asc" else sort_columns[sort_by].desc()
    employees = db.scalars(
        query.order_by(ordering, Employee.employee_number).limit(limit).offset(offset)
    ).all()
    object_ids = visible_object_ids(db, principal)
    return EmployeePage(
        items=[employee_read(employee, object_ids) for employee in employees],
        total=db.scalar(count_query) or 0,
        limit=limit,
        offset=offset,
    )


@router.post("/employees", response_model=EmployeeRead, status_code=status.HTTP_201_CREATED)
def create_employee(
    request: Request,
    payload: EmployeeCreate,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("employees.manage")),
) -> EmployeeRead:
    validate_employee_dates(payload.hired_on, payload.ended_on)
    validate_linked_user(db, payload.user_id)
    if (
        db.scalar(select(Employee.id).where(Employee.employee_number == payload.employee_number))
        is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Die Personalnummer ist bereits vergeben",
        )
    employee = Employee(
        employee_number=payload.employee_number,
        user_id=payload.user_id,
        full_name=payload.full_name,
        email=str(payload.email).lower() if payload.email else None,
        phone=payload.phone,
        job_title=payload.job_title,
        employment_status=payload.employment_status,
        hired_on=payload.hired_on,
        ended_on=payload.ended_on,
        contract_type=payload.contract_type,
        weekly_hours=payload.weekly_hours,
    )
    db.add(employee)
    flush_employee_transaction(db)
    record_employee_event(
        db,
        employee=employee,
        actor_id=principal.user.id,
        action="created",
        changed_fields={
            field for field, value in payload.model_dump().items() if value is not None
        },
        ip_address=request.client.host if request.client else None,
    )
    commit_employee_transaction(db)
    employee = get_employee_or_404(db, employee.id)
    return employee_read(employee, visible_object_ids(db, principal))


@router.get(
    "/employees/qualifications/expiring", response_model=list[EmployeeQualificationExpiringRead]
)
def list_expiring_qualifications(
    days: int = Query(default=30, ge=0, le=365),
    db: Session = Depends(get_db),
    _principal=Depends(require_permission("employees.read")),
) -> list[EmployeeQualificationExpiringRead]:
    today = date.today()
    rows = db.execute(
        select(EmployeeQualification, Employee.employee_number, Employee.full_name)
        .join(Employee, Employee.id == EmployeeQualification.employee_id)
        .where(
            Employee.archived_at.is_(None),
            Employee.employment_status != "terminated",
            EmployeeQualification.archived_at.is_(None),
            EmployeeQualification.expires_on.is_not(None),
            EmployeeQualification.expires_on <= today + timedelta(days=days),
        )
        .order_by(EmployeeQualification.expires_on, Employee.full_name)
    ).all()
    return [
        EmployeeQualificationExpiringRead(
            **EmployeeQualificationRead.model_validate(qualification).model_dump(),
            employee_number=employee_number,
            employee_name=employee_name,
            days_until_expiry=(qualification.expires_on - today).days,
        )
        for qualification, employee_number, employee_name in rows
    ]


@router.get(
    "/employees/linked-user-candidates",
    response_model=list[EmployeeAccountCandidateRead],
)
def list_employee_linked_user_candidates(
    employee_id: UUID | None = None,
    db: Session = Depends(get_db),
    _principal=Depends(require_permission("employees.manage")),
) -> list[EmployeeAccountCandidateRead]:
    if employee_id is not None:
        get_employee_or_404(db, employee_id)
    linked_elsewhere = select(Employee.id).where(Employee.user_id == User.id)
    if employee_id is not None:
        linked_elsewhere = linked_elsewhere.where(Employee.id != employee_id)
    users = db.scalars(
        select(User)
        .where(
            User.is_active.is_(True),
            User.roles.any(Role.code.in_(("employee", "object_manager"))),
            ~linked_elsewhere.exists(),
        )
        .order_by(User.full_name, User.username)
    ).all()
    return [
        EmployeeAccountCandidateRead(id=user.id, username=user.username, full_name=user.full_name)
        for user in users
    ]


@router.get(
    "/employees/object-assignment-candidates",
    response_model=list[EmployeeObjectCandidateRead],
)
def list_employee_object_assignment_candidates(
    db: Session = Depends(get_db),
    principal=Depends(require_object_assignment_access),
) -> list[EmployeeObjectCandidateRead]:
    query = select(SecurityObject).where(SecurityObject.archived_at.is_(None))
    if "objects.manage_all" not in principal.permission_codes:
        query = query.where(
            SecurityObject.assignments.any(ObjectAssignment.user_id == principal.user.id)
        )
    objects = db.scalars(query.order_by(SecurityObject.name, SecurityObject.code)).all()
    return [
        EmployeeObjectCandidateRead(
            object_id=obj.id,
            object_code=obj.code,
            object_name=obj.name,
        )
        for obj in objects
    ]


@router.get("/employees/{employee_id}", response_model=EmployeeRead)
def get_employee(
    employee_id: UUID,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("employees.read")),
) -> EmployeeRead:
    employee = get_employee_or_404(db, employee_id)
    return employee_read(employee, visible_object_ids(db, principal))


@router.get(
    "/employees/{employee_id}/objects",
    response_model=list[EmployeeObjectAssignmentRead],
)
def list_employee_object_assignments(
    employee_id: UUID,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("employees.read")),
) -> list[EmployeeObjectAssignmentRead]:
    employee = get_employee_or_404(db, employee_id)
    if employee.user_id is None:
        return []
    query = (
        select(ObjectAssignment, SecurityObject)
        .join(SecurityObject, SecurityObject.id == ObjectAssignment.object_id)
        .where(ObjectAssignment.user_id == employee.user_id)
        .order_by(SecurityObject.name, SecurityObject.code)
    )
    object_filter = accessible_object_filter(principal)
    if object_filter is not None:
        query = query.where(object_filter)
    rows = db.execute(query).all()
    return [
        EmployeeObjectAssignmentRead(
            object_id=obj.id,
            object_code=obj.code,
            object_name=obj.name,
            assigned_at=assignment.assigned_at,
        )
        for assignment, obj in rows
    ]


@router.get(
    "/employees/{employee_id}/object-assignment-history",
    response_model=list[EmployeeObjectAssignmentHistoryRead],
)
def list_employee_object_assignment_history(
    employee_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal=Depends(require_permission("employees.read")),
) -> list[EmployeeObjectAssignmentHistoryRead]:
    get_employee_or_404(db, employee_id)
    query = (
        select(EmployeeObjectAssignmentHistory, SecurityObject)
        .join(
            SecurityObject,
            SecurityObject.id == EmployeeObjectAssignmentHistory.object_id,
        )
        .where(EmployeeObjectAssignmentHistory.employee_id == employee_id)
        .order_by(
            EmployeeObjectAssignmentHistory.created_at.desc(),
            EmployeeObjectAssignmentHistory.id,
        )
        .limit(limit)
        .offset(offset)
    )
    object_filter = accessible_object_filter(principal)
    if object_filter is not None:
        query = query.where(object_filter)
    rows = db.execute(query).all()
    return [
        EmployeeObjectAssignmentHistoryRead(
            id=history.id,
            object_id=obj.id,
            object_code=obj.code,
            object_name=obj.name,
            action=history.action,
            actor_id=history.actor_id,
            created_at=history.created_at,
        )
        for history, obj in rows
    ]


@router.post(
    "/employees/{employee_id}/objects/{object_id}",
    response_model=list[EmployeeObjectAssignmentRead],
    status_code=status.HTTP_201_CREATED,
)
def assign_employee_to_object(
    request: Request,
    employee_id: UUID,
    object_id: UUID,
    db: Session = Depends(get_db),
    principal=Depends(require_object_assignment_access),
) -> list[EmployeeObjectAssignmentRead]:
    employee = get_employee_or_404(db, employee_id)
    ensure_employee_is_active(employee)
    if employee.employment_status == "terminated":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ausgeschiedene Mitarbeiter können keinem Objekt zugewiesen werden",
        )
    if employee.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vor einer Objektzuweisung muss ein Benutzerkonto verknüpft werden",
        )
    obj = get_assignable_object(db, object_id, principal)
    if db.scalar(
        select(ObjectAssignment.id).where(
            ObjectAssignment.object_id == obj.id,
            ObjectAssignment.user_id == employee.user_id,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Der Mitarbeiter ist diesem Objekt bereits zugewiesen",
        )
    db.add(
        ObjectAssignment(
            object_id=obj.id,
            user_id=employee.user_id,
            assigned_by_id=principal.user.id,
        )
    )
    record_object_assignment_event(
        db,
        employee=employee,
        obj=obj,
        actor_id=principal.user.id,
        action="assigned",
        ip_address=request.client.host if request.client else None,
    )
    commit_employee_transaction(db)
    return list_employee_object_assignments(employee.id, db, principal)


@router.delete(
    "/employees/{employee_id}/objects/{object_id}",
    response_model=list[EmployeeObjectAssignmentRead],
)
def end_employee_object_assignment(
    request: Request,
    employee_id: UUID,
    object_id: UUID,
    db: Session = Depends(get_db),
    principal=Depends(require_object_assignment_access),
) -> list[EmployeeObjectAssignmentRead]:
    employee = get_employee_or_404(db, employee_id)
    if employee.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Zuweisung nicht gefunden"
        )
    obj = get_assignable_object(db, object_id, principal, active_only=False)
    assignment = db.scalar(
        select(ObjectAssignment).where(
            ObjectAssignment.object_id == obj.id,
            ObjectAssignment.user_id == employee.user_id,
        )
    )
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Zuweisung nicht gefunden"
        )
    record_object_assignment_event(
        db,
        employee=employee,
        obj=obj,
        actor_id=principal.user.id,
        action="ended",
        ip_address=request.client.host if request.client else None,
    )
    db.delete(assignment)
    commit_employee_transaction(db)
    return list_employee_object_assignments(employee.id, db, principal)


@router.patch("/employees/{employee_id}", response_model=EmployeeRead)
def update_employee(
    request: Request,
    employee_id: UUID,
    payload: EmployeeUpdate,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("employees.manage")),
) -> EmployeeRead:
    employee = get_employee_or_404(db, employee_id)
    ensure_employee_is_active(employee)
    changes = payload.model_dump(exclude_unset=True)
    hired_on = changes.get("hired_on", employee.hired_on)
    ended_on = changes.get("ended_on", employee.ended_on)
    validate_employee_dates(hired_on, ended_on)
    if "user_id" in changes:
        validate_linked_user(db, changes["user_id"])
        if (
            changes["user_id"] != employee.user_id
            and employee.user_id is not None
            and db.scalar(
                select(func.count())
                .select_from(ObjectAssignment)
                .where(ObjectAssignment.user_id == employee.user_id)
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Das Benutzerkonto kann bei aktiven Objektzuweisungen nicht geändert werden",
            )
    if (
        "employee_number" in changes
        and changes["employee_number"] != employee.employee_number
        and db.scalar(
            select(Employee.id).where(
                Employee.employee_number == changes["employee_number"],
                Employee.id != employee.id,
            )
        )
        is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Die Personalnummer ist bereits vergeben",
        )

    changed_fields = set()
    for field, value in changes.items():
        if field == "email" and value is not None:
            value = str(value).lower()
        if getattr(employee, field) != value:
            setattr(employee, field, value)
            changed_fields.add(field)
    if changed_fields:
        if employee.employment_status == "terminated":
            end_employee_object_assignments(
                db,
                employee=employee,
                actor_id=principal.user.id,
                ip_address=request.client.host if request.client else None,
            )
        record_employee_event(
            db,
            employee=employee,
            actor_id=principal.user.id,
            action="updated",
            changed_fields=changed_fields,
            ip_address=request.client.host if request.client else None,
        )
        commit_employee_transaction(db)
    employee = get_employee_or_404(db, employee.id)
    return employee_read(employee, visible_object_ids(db, principal))


@router.post("/employees/{employee_id}/archive", response_model=EmployeeRead)
def archive_employee(
    request: Request,
    employee_id: UUID,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("employees.manage")),
) -> EmployeeRead:
    employee = get_employee_or_404(db, employee_id)
    if employee.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Mitarbeiter ist bereits archiviert",
        )
    employee.archived_at = datetime.now(UTC)
    end_employee_object_assignments(
        db,
        employee=employee,
        actor_id=principal.user.id,
        ip_address=request.client.host if request.client else None,
    )
    record_employee_event(
        db,
        employee=employee,
        actor_id=principal.user.id,
        action="archived",
        changed_fields={"archived_at"},
        ip_address=request.client.host if request.client else None,
    )
    commit_employee_transaction(db)
    employee = get_employee_or_404(db, employee.id)
    return employee_read(employee, visible_object_ids(db, principal))


@router.post("/employees/{employee_id}/reactivate", response_model=EmployeeRead)
def reactivate_employee(
    request: Request,
    employee_id: UUID,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("employees.manage")),
) -> EmployeeRead:
    employee = get_employee_or_404(db, employee_id)
    if employee.archived_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Mitarbeiter ist nicht archiviert",
        )
    employee.archived_at = None
    record_employee_event(
        db,
        employee=employee,
        actor_id=principal.user.id,
        action="reactivated",
        changed_fields={"archived_at"},
        ip_address=request.client.host if request.client else None,
    )
    commit_employee_transaction(db)
    employee = get_employee_or_404(db, employee.id)
    return employee_read(employee, visible_object_ids(db, principal))


@router.get("/employees/{employee_id}/sensitive", response_model=EmployeeSensitiveRead)
def get_employee_sensitive_details(
    employee_id: UUID,
    db: Session = Depends(get_db),
    _principal=Depends(require_permission("employees.sensitive.read")),
) -> EmployeeSensitiveRead:
    employee = get_employee_or_404(db, employee_id)
    details = db.get(EmployeeSensitiveDetails, employee.id)
    return EmployeeSensitiveRead(
        employee_id=employee.id,
        address=details.address if details else None,
        emergency_contact=details.emergency_contact if details else None,
        internal_notes=details.internal_notes if details else None,
        updated_at=details.updated_at if details else None,
    )


@router.patch("/employees/{employee_id}/sensitive", response_model=EmployeeSensitiveRead)
def update_employee_sensitive_details(
    request: Request,
    employee_id: UUID,
    payload: EmployeeSensitiveUpdate,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("employees.sensitive.manage")),
) -> EmployeeSensitiveRead:
    employee = get_employee_or_404(db, employee_id)
    ensure_employee_is_active(employee)
    changes = payload.model_dump(exclude_unset=True)
    details = db.get(EmployeeSensitiveDetails, employee.id)
    changed_fields = {
        field for field, value in changes.items() if details is None and value is not None
    }
    if details is None and changed_fields:
        details = EmployeeSensitiveDetails(employee_id=employee.id)
        db.add(details)
        flush_employee_transaction(db)
    if details is not None:
        for field, value in changes.items():
            if getattr(details, field) != value:
                setattr(details, field, value)
                changed_fields.add(field)
    if changed_fields:
        record_employee_event(
            db,
            employee=employee,
            actor_id=principal.user.id,
            action="sensitive_updated",
            changed_fields=changed_fields,
            ip_address=request.client.host if request.client else None,
        )
        commit_employee_transaction(db)
    details = db.get(EmployeeSensitiveDetails, employee.id)
    return EmployeeSensitiveRead(
        employee_id=employee.id,
        address=details.address if details else None,
        emergency_contact=details.emergency_contact if details else None,
        internal_notes=details.internal_notes if details else None,
        updated_at=details.updated_at if details else None,
    )


@router.get(
    "/employees/{employee_id}/qualifications", response_model=list[EmployeeQualificationRead]
)
def list_employee_qualifications(
    employee_id: UUID,
    include_archived: bool = False,
    db: Session = Depends(get_db),
    _principal=Depends(require_permission("employees.read")),
) -> list[EmployeeQualificationRead]:
    get_employee_or_404(db, employee_id)
    query = select(EmployeeQualification).where(EmployeeQualification.employee_id == employee_id)
    if not include_archived:
        query = query.where(EmployeeQualification.archived_at.is_(None))
    qualifications = db.scalars(
        query.order_by(EmployeeQualification.expires_on, EmployeeQualification.name)
    ).all()
    return [EmployeeQualificationRead.model_validate(item) for item in qualifications]


@router.post(
    "/employees/{employee_id}/qualifications",
    response_model=EmployeeQualificationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_employee_qualification(
    request: Request,
    employee_id: UUID,
    payload: EmployeeQualificationCreate,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("employees.manage")),
) -> EmployeeQualificationRead:
    employee = get_employee_or_404(db, employee_id)
    ensure_employee_is_active(employee)
    qualification = EmployeeQualification(employee_id=employee.id, **payload.model_dump())
    db.add(qualification)
    flush_employee_transaction(db)
    record_employee_event(
        db,
        employee=employee,
        actor_id=principal.user.id,
        action="qualification_created",
        changed_fields={"qualifications"},
        ip_address=request.client.host if request.client else None,
    )
    commit_employee_transaction(db)
    return EmployeeQualificationRead.model_validate(qualification)


@router.patch(
    "/employees/{employee_id}/qualifications/{qualification_id}",
    response_model=EmployeeQualificationRead,
)
def update_employee_qualification(
    request: Request,
    employee_id: UUID,
    qualification_id: UUID,
    payload: EmployeeQualificationUpdate,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("employees.manage")),
) -> EmployeeQualificationRead:
    employee = get_employee_or_404(db, employee_id)
    ensure_employee_is_active(employee)
    qualification = db.scalar(
        select(EmployeeQualification).where(
            EmployeeQualification.id == qualification_id,
            EmployeeQualification.employee_id == employee_id,
        )
    )
    if qualification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Qualifikationsnachweis nicht gefunden",
        )
    if qualification.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Archivierte Nachweise können nicht geändert werden",
        )
    changes = payload.model_dump(exclude_unset=True)
    valid_from = changes.get("valid_from", qualification.valid_from)
    expires_on = changes.get("expires_on", qualification.expires_on)
    if valid_from is not None and expires_on is not None and expires_on < valid_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Das Ablaufdatum darf nicht vor dem Gültigkeitsbeginn liegen",
        )
    changed_fields = set()
    for field, value in changes.items():
        if getattr(qualification, field) != value:
            setattr(qualification, field, value)
            changed_fields.add(field)
    if changed_fields:
        record_employee_event(
            db,
            employee=employee,
            actor_id=principal.user.id,
            action="qualification_updated",
            changed_fields={"qualifications"},
            ip_address=request.client.host if request.client else None,
        )
        commit_employee_transaction(db)
    return EmployeeQualificationRead.model_validate(qualification)


@router.post(
    "/employees/{employee_id}/qualifications/{qualification_id}/archive",
    response_model=EmployeeQualificationRead,
)
def archive_employee_qualification(
    request: Request,
    employee_id: UUID,
    qualification_id: UUID,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("employees.manage")),
) -> EmployeeQualificationRead:
    employee = get_employee_or_404(db, employee_id)
    ensure_employee_is_active(employee)
    qualification = db.scalar(
        select(EmployeeQualification).where(
            EmployeeQualification.id == qualification_id,
            EmployeeQualification.employee_id == employee_id,
        )
    )
    if qualification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Qualifikationsnachweis nicht gefunden",
        )
    if qualification.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Qualifikationsnachweis ist bereits archiviert",
        )
    qualification.archived_at = datetime.now(UTC)
    record_employee_event(
        db,
        employee=employee,
        actor_id=principal.user.id,
        action="qualification_archived",
        changed_fields={"qualifications"},
        ip_address=request.client.host if request.client else None,
    )
    commit_employee_transaction(db)
    return EmployeeQualificationRead.model_validate(qualification)


@router.get(
    "/employees/{employee_id}/qualification-documents",
    response_model=list[EmployeeQualificationDocumentRead],
)
def list_employee_qualification_documents(
    employee_id: UUID,
    db: Session = Depends(get_db),
    _principal=Depends(require_permission("employees.documents.read")),
) -> list[EmployeeQualificationDocumentRead]:
    get_employee_or_404(db, employee_id)
    documents = db.scalars(
        select(EmployeeQualificationDocument)
        .join(
            EmployeeQualification,
            EmployeeQualification.id == EmployeeQualificationDocument.qualification_id,
        )
        .where(EmployeeQualification.employee_id == employee_id)
        .order_by(
            EmployeeQualificationDocument.created_at.desc(),
            EmployeeQualificationDocument.version.desc(),
        )
    ).all()
    return [EmployeeQualificationDocumentRead.model_validate(item) for item in documents]


@router.post(
    "/employees/{employee_id}/qualifications/{qualification_id}/documents",
    response_model=EmployeeQualificationDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
def upload_employee_qualification_document(
    request: Request,
    employee_id: UUID,
    qualification_id: UUID,
    document: UploadFile = File(),
    db: Session = Depends(get_db),
    principal=Depends(require_permission("employees.documents.manage")),
) -> EmployeeQualificationDocumentRead:
    employee = get_employee_or_404(db, employee_id)
    ensure_employee_is_active(employee)
    qualification = get_employee_qualification_or_404(db, employee_id, qualification_id)
    if qualification.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Für archivierte Qualifikationen können keine Dateien hinzugefügt werden",
        )
    extension = PurePosixPath((document.filename or "").replace("\\", "/")).suffix.lower()
    allowed_type = QUALIFICATION_DOCUMENT_TYPES.get(extension)
    if allowed_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Erlaubt sind PDF-, PNG- und JPEG-Dateien",
        )
    media_type, signature = allowed_type
    declared_media_type = (document.content_type or "").split(";", maxsplit=1)[0].lower()
    if declared_media_type != media_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Dateiendung und Dateityp stimmen nicht überein",
        )
    content = document.file.read(MAX_QUALIFICATION_DOCUMENT_SIZE + 1)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Die Datei darf nicht leer sein",
        )
    if len(content) > MAX_QUALIFICATION_DOCUMENT_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Die Datei darf höchstens 10 MiB groß sein",
        )
    if not content.startswith(signature):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Der Dateiinhalt passt nicht zum angegebenen Dateityp",
        )
    filename = safe_qualification_filename(document.filename, extension)
    scan_upload_or_reject(
        db,
        request,
        content=content,
        actor_id=principal.user.id,
        surface="personnel_qualification",
    )
    version = (
        db.scalar(
            select(func.max(EmployeeQualificationDocument.version)).where(
                EmployeeQualificationDocument.qualification_id == qualification.id
            )
        )
        or 0
    ) + 1
    document_id = uuid4()
    storage_key = document_id.hex
    stored = EmployeeQualificationDocument(
        id=document_id,
        qualification_id=qualification.id,
        version=version,
        file_name=filename,
        media_type=media_type,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        storage_key=storage_key,
        content=None,
        uploaded_by_id=principal.user.id,
    )
    file_created = False
    commit_attempted = False
    try:
        db.add(stored)
        db.add(
            EmployeeHistory(
                employee_id=employee.id,
                actor_id=principal.user.id,
                action="qualification_document_uploaded",
                changed_fields=["qualification_documents"],
            )
        )
        db.flush()
        store_file(storage_key, content)
        file_created = True
        add_audit_entry(
            db,
            actor_id=principal.user.id,
            action="employees.qualification_document_uploaded",
            entity_type="employee",
            entity_id=str(employee.id),
            ip_address=request.client.host if request.client else None,
            details={
                "qualification_id": str(qualification.id),
                "document_id": str(stored.id),
                "version": version,
            },
        )
        commit_attempted = True
        commit_employee_transaction(db)
    except Exception as exc:
        db.rollback()
        if file_created and (
            not commit_attempted or (isinstance(exc, HTTPException) and exc.status_code == 409)
        ):
            remove_file(storage_key)
        raise
    return EmployeeQualificationDocumentRead.model_validate(stored)


@router.get(
    "/employees/{employee_id}/qualifications/{qualification_id}/documents/{document_id}",
)
def get_employee_qualification_document(
    request: Request,
    employee_id: UUID,
    qualification_id: UUID,
    document_id: UUID,
    download: bool = Query(default=False),
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_auth_principal),
) -> Response:
    can_read_personnel_documents = "employees.documents.read" in principal.permission_codes
    if not can_read_personnel_documents and (
        principal.customer_portal_restricted or "employee" not in principal.role_codes
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung für diese Aktion",
        )
    employee = get_employee_or_404(db, employee_id)
    if not can_read_personnel_documents:
        if (
            employee.user_id != principal.user.id
            or employee.employment_status != "active"
            or employee.archived_at is not None
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Qualifikationsdokument nicht gefunden",
            )
        qualification = db.scalar(
            select(EmployeeQualification).where(
                EmployeeQualification.id == qualification_id,
                EmployeeQualification.employee_id == employee.id,
                EmployeeQualification.archived_at.is_(None),
            )
        )
        if qualification is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Qualifikationsdokument nicht gefunden",
            )
        stored = db.scalar(
            select(EmployeeQualificationDocument).where(
                EmployeeQualificationDocument.id == document_id,
                EmployeeQualificationDocument.qualification_id == qualification.id,
            )
        )
        grant_id = db.scalar(
            select(EmployeePortalDocumentGrant.id).where(
                EmployeePortalDocumentGrant.employee_id == employee.id,
                EmployeePortalDocumentGrant.user_id == principal.user.id,
                EmployeePortalDocumentGrant.qualification_document_id == document_id,
                EmployeePortalDocumentGrant.revoked_at.is_(None),
            )
        )
        if stored is None or grant_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Qualifikationsdokument nicht gefunden",
            )
        add_audit_entry(
            db,
            actor_id=principal.user.id,
            action="employee_portal.document_downloaded",
            entity_type="employee_qualification_document",
            entity_id=str(stored.id),
            ip_address=request.client.host if request.client else None,
            details={"version": stored.version, "grant_id": str(grant_id)},
        )
        db.commit()
    else:
        stored = db.scalar(
            select(EmployeeQualificationDocument)
            .join(
                EmployeeQualification,
                EmployeeQualification.id == EmployeeQualificationDocument.qualification_id,
            )
            .where(
                EmployeeQualification.employee_id == employee_id,
                EmployeeQualification.id == qualification_id,
                EmployeeQualificationDocument.id == document_id,
            )
        )
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Qualifikationsdokument nicht gefunden",
        )
    disposition = "attachment" if download else "inline"
    encoded_filename = quote(stored.file_name, safe="")
    fallback_filename = f"nachweis{PurePosixPath(stored.file_name).suffix.lower()}"
    return Response(
        content=read_attachment(stored.storage_key, stored.content),
        media_type=stored.media_type,
        headers={
            "Content-Disposition": (
                f'{disposition}; filename="{fallback_filename}"; '
                f"filename*=UTF-8''{encoded_filename}"
            ),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'",
        },
    )


@router.get(
    "/employees/{employee_id}/absences",
    response_model=list[EmployeeAbsenceRead],
)
def list_employee_absences(
    employee_id: UUID,
    db: Session = Depends(get_db),
    _principal=Depends(require_permission("employees.absences.read")),
) -> list[EmployeeAbsenceRead]:
    get_employee_or_404(db, employee_id)
    absences = db.scalars(
        employee_absence_query(employee_id).order_by(
            EmployeeAbsence.starts_on.desc(), EmployeeAbsence.created_at.desc()
        )
    ).all()
    return [EmployeeAbsenceRead.model_validate(item) for item in absences]


@router.post(
    "/employees/{employee_id}/absences",
    response_model=EmployeeAbsenceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_employee_absence(
    request: Request,
    employee_id: UUID,
    payload: EmployeeAbsenceCreate,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("employees.absences.manage")),
) -> EmployeeAbsenceRead:
    employee = get_employee_or_404(db, employee_id)
    ensure_employee_is_active(employee)
    absence = EmployeeAbsence(
        employee_id=employee.id,
        created_by_id=principal.user.id,
        **payload.model_dump(),
    )
    db.add(absence)
    flush_employee_transaction(db)
    record_employee_event(
        db,
        employee=employee,
        actor_id=principal.user.id,
        action="absence_created",
        changed_fields={"absences"},
        ip_address=request.client.host if request.client else None,
    )
    commit_employee_transaction(db)
    return EmployeeAbsenceRead.model_validate(absence)


@router.patch(
    "/employees/{employee_id}/absences/{absence_id}",
    response_model=EmployeeAbsenceRead,
)
def update_employee_absence(
    request: Request,
    employee_id: UUID,
    absence_id: UUID,
    payload: EmployeeAbsenceUpdate,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("employees.absences.manage")),
) -> EmployeeAbsenceRead:
    employee = get_employee_or_404(db, employee_id)
    ensure_employee_is_active(employee)
    absence = db.scalar(employee_absence_query(employee_id).where(EmployeeAbsence.id == absence_id))
    if absence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Abwesenheit nicht gefunden",
        )
    changes = payload.model_dump(exclude_unset=True)
    starts_on = changes.get("starts_on", absence.starts_on)
    ends_on = changes.get("ends_on", absence.ends_on)
    if ends_on < starts_on:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Das Abwesenheitsende darf nicht vor dem Beginn liegen",
        )
    changed_fields = set()
    for field, value in changes.items():
        if getattr(absence, field) != value:
            setattr(absence, field, value)
            changed_fields.add(field)
    if changed_fields:
        record_employee_event(
            db,
            employee=employee,
            actor_id=principal.user.id,
            action="absence_updated",
            changed_fields={"absences"},
            ip_address=request.client.host if request.client else None,
        )
        commit_employee_transaction(db)
    return EmployeeAbsenceRead.model_validate(absence)


@router.get("/employees/{employee_id}/history", response_model=list[EmployeeHistoryRead])
def list_employee_history(
    employee_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _principal=Depends(require_permission("employees.read")),
) -> list[EmployeeHistoryRead]:
    get_employee_or_404(db, employee_id)
    history = db.scalars(
        select(EmployeeHistory)
        .where(EmployeeHistory.employee_id == employee_id)
        .order_by(EmployeeHistory.created_at.desc(), EmployeeHistory.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [EmployeeHistoryRead.model_validate(item) for item in history]
