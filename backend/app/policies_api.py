import csv
import io
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import AuthPrincipal, add_audit_entry, require_permission
from app.database import get_db
from app.models import (
    Employee,
    ObjectAssignment,
    PolicyAssignment,
    PolicyItem,
    PolicyReceipt,
    PolicyVersion,
    PolicyVersionClosure,
    SecurityObject,
)
from app.policy_schemas import (
    PolicyAssignmentCreate,
    PolicyAssignmentRead,
    PolicyCreate,
    PolicyEmployeeOption,
    PolicyHistoryRead,
    PolicyObjectOption,
    PolicyRead,
    PolicyVersionCreate,
    PolicyVersionRead,
)

router = APIRouter()


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def managed_object_ids(db: Session, principal: AuthPrincipal) -> set[UUID] | None:
    permissions = principal.permission_codes
    if "objects.manage_all" in permissions:
        return None
    if "objects.manage" not in permissions:
        return set()
    return set(
        db.scalars(
            select(ObjectAssignment.object_id).where(ObjectAssignment.user_id == principal.user.id)
        ).all()
    )


def require_policy_access(
    db: Session, principal: AuthPrincipal, policy: PolicyItem
) -> SecurityObject | None:
    if policy.archived_at is not None:
        raise HTTPException(status_code=404, detail="Anweisung oder Unterweisung nicht gefunden")
    if policy.object_id is None:
        if "objects.manage_all" not in principal.permission_codes:
            raise HTTPException(status_code=403, detail="Keine globale Verwaltungsberechtigung")
        return None
    obj = db.get(SecurityObject, policy.object_id)
    if obj is None or obj.archived_at is not None:
        raise HTTPException(status_code=404, detail="Objekt nicht gefunden")
    if "objects.manage_all" not in principal.permission_codes and (
        "objects.manage" not in principal.permission_codes
        or db.scalar(
            select(ObjectAssignment.id).where(
                ObjectAssignment.object_id == obj.id,
                ObjectAssignment.user_id == principal.user.id,
            )
        )
        is None
    ):
        raise HTTPException(status_code=404, detail="Anweisung oder Unterweisung nicht gefunden")
    return obj


def get_policy_or_404(db: Session, policy_id: UUID) -> PolicyItem:
    policy = db.get(PolicyItem, policy_id)
    if policy is None or policy.archived_at is not None:
        raise HTTPException(status_code=404, detail="Anweisung oder Unterweisung nicht gefunden")
    return policy


def policy_read(db: Session, policy: PolicyItem) -> PolicyRead:
    obj = db.get(SecurityObject, policy.object_id) if policy.object_id else None
    versions = db.scalars(
        select(PolicyVersion)
        .where(PolicyVersion.policy_item_id == policy.id)
        .order_by(PolicyVersion.version_number.desc())
    ).all()
    return PolicyRead(
        id=policy.id,
        kind=policy.kind,
        title=policy.title,
        object_id=policy.object_id,
        object_name=obj.name if obj else None,
        repeat_interval_days=policy.repeat_interval_days,
        reminder_days=policy.reminder_days,
        versions=[policy_version_read(db, version) for version in versions],
    )


def effective_version_end(db: Session, version: PolicyVersion) -> datetime | None:
    closure = db.get(PolicyVersionClosure, version.id)
    if closure is None:
        return version.valid_until
    closure_end = as_utc(closure.valid_until)
    stored_end = as_utc(version.valid_until) if version.valid_until else None
    if stored_end is None or closure_end < stored_end:
        return closure.valid_until
    return version.valid_until


def policy_version_read(db: Session, version: PolicyVersion) -> PolicyVersionRead:
    valid_until = effective_version_end(db, version)
    return PolicyVersionRead(
        id=version.id,
        version_number=version.version_number,
        content=version.content,
        valid_from=as_utc(version.valid_from),
        valid_until=as_utc(valid_until) if valid_until else None,
        created_by_id=version.created_by_id,
        created_at=as_utc(version.created_at),
    )


def current_employee(db: Session, principal: AuthPrincipal) -> Employee:
    employee = db.scalar(
        select(Employee).where(
            Employee.user_id == principal.user.id,
            Employee.archived_at.is_(None),
            Employee.employment_status == "active",
        )
    )
    if employee is None:
        raise HTTPException(status_code=403, detail="Kein aktiver Mitarbeiterzugang vorhanden")
    return employee


def ensure_employee_object_access(db: Session, employee: Employee, policy: PolicyItem) -> None:
    if policy.object_id is None:
        return
    obj = db.get(SecurityObject, policy.object_id)
    if obj is None or obj.archived_at is not None or obj.status != "active":
        raise HTTPException(status_code=404, detail="Objekt nicht gefunden")
    if (
        employee.user_id is None
        or db.scalar(
            select(ObjectAssignment.id).where(
                ObjectAssignment.object_id == policy.object_id,
                ObjectAssignment.user_id == employee.user_id,
            )
        )
        is None
    ):
        raise HTTPException(status_code=404, detail="Anweisung oder Unterweisung nicht gefunden")


def active_version(db: Session, version: PolicyVersion, now: datetime) -> bool:
    valid_until = effective_version_end(db, version)
    return as_utc(version.valid_from) <= now and (valid_until is None or as_utc(valid_until) > now)


def get_assignment_for_employee(
    db: Session, assignment_id: UUID, employee: Employee
) -> tuple[PolicyAssignment, PolicyVersion, PolicyItem]:
    result = db.execute(
        select(PolicyAssignment, PolicyVersion, PolicyItem)
        .join(PolicyVersion, PolicyVersion.id == PolicyAssignment.policy_version_id)
        .join(PolicyItem, PolicyItem.id == PolicyVersion.policy_item_id)
        .where(
            PolicyAssignment.id == assignment_id,
            PolicyAssignment.employee_id == employee.id,
            PolicyItem.archived_at.is_(None),
        )
    ).first()
    if result is None:
        raise HTTPException(status_code=404, detail="Zuweisung nicht gefunden")
    assignment, version, policy = result
    ensure_employee_object_access(db, employee, policy)
    if not active_version(db, version, utc_now()):
        raise HTTPException(status_code=404, detail="Zuweisung ist nicht aktuell gültig")
    return assignment, version, policy


def receipt_time(db: Session, assignment_id: UUID, action: str) -> datetime | None:
    return db.scalar(
        select(PolicyReceipt.created_at).where(
            PolicyReceipt.assignment_id == assignment_id,
            PolicyReceipt.action == action,
        )
    )


def commit_policy(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Der Vorgang kollidiert mit einem bestehenden Nachweis"
        ) from exc


@router.get("/policies", response_model=list[PolicyRead])
def list_policies(
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_permission("policies.manage")),
) -> list[PolicyRead]:
    object_ids = managed_object_ids(db, principal)
    query = select(PolicyItem).where(PolicyItem.archived_at.is_(None))
    if object_ids is not None:
        query = query.where(PolicyItem.object_id.in_(object_ids) if object_ids else False)
    else:
        query = query.where(
            or_(
                PolicyItem.object_id.is_(None),
                PolicyItem.object_id.in_(
                    select(SecurityObject.id).where(SecurityObject.archived_at.is_(None))
                ),
            )
        )
    policies = db.scalars(query.order_by(PolicyItem.kind, PolicyItem.title)).all()
    return [policy_read(db, policy) for policy in policies]


@router.post("/policies", response_model=PolicyRead, status_code=status.HTTP_201_CREATED)
def create_policy(
    payload: PolicyCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_permission("policies.manage")),
) -> PolicyRead:
    if payload.object_id is None:
        if "objects.manage_all" not in principal.permission_codes:
            raise HTTPException(
                status_code=403, detail="Globale Inhalte erfordern globale Objektverwaltung"
            )
    else:
        obj = db.get(SecurityObject, payload.object_id)
        if obj is None or obj.archived_at is not None or obj.status != "active":
            raise HTTPException(status_code=404, detail="Aktives Objekt nicht gefunden")
        if "objects.manage_all" not in principal.permission_codes and (
            "objects.manage" not in principal.permission_codes
            or db.scalar(
                select(ObjectAssignment.id).where(
                    ObjectAssignment.object_id == obj.id,
                    ObjectAssignment.user_id == principal.user.id,
                )
            )
            is None
        ):
            raise HTTPException(status_code=404, detail="Objekt nicht gefunden")
    policy = PolicyItem(
        kind=payload.kind,
        title=payload.title,
        object_id=payload.object_id,
        repeat_interval_days=payload.repeat_interval_days,
        reminder_days=payload.reminder_days,
        created_by_id=principal.user.id,
    )
    db.add(policy)
    db.flush()
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="policies.created",
        entity_type="policy",
        entity_id=str(policy.id),
        ip_address=request.client.host if request.client else None,
        details={
            "kind": policy.kind,
            "object_id": str(policy.object_id) if policy.object_id else None,
        },
    )
    commit_policy(db)
    db.refresh(policy)
    return policy_read(db, policy)


@router.get("/policies/objects", response_model=list[PolicyObjectOption])
def policy_object_options(
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_permission("policies.manage")),
) -> list[PolicyObjectOption]:
    query = select(SecurityObject).where(
        SecurityObject.archived_at.is_(None),
        SecurityObject.status == "active",
    )
    object_ids = managed_object_ids(db, principal)
    if object_ids is not None:
        query = query.where(SecurityObject.id.in_(object_ids) if object_ids else False)
    return [
        PolicyObjectOption(id=obj.id, name=obj.name, code=obj.code)
        for obj in db.scalars(query.order_by(SecurityObject.name)).all()
    ]


@router.post(
    "/policies/{policy_id}/versions",
    response_model=PolicyVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_policy_version(
    policy_id: UUID,
    payload: PolicyVersionCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_permission("policies.manage")),
) -> PolicyVersionRead:
    policy = get_policy_or_404(db, policy_id)
    require_policy_access(db, principal, policy)
    versions = db.scalars(
        select(PolicyVersion)
        .where(PolicyVersion.policy_item_id == policy.id)
        .order_by(PolicyVersion.version_number)
    ).all()
    new_start = payload.valid_from
    versions_to_close: list[PolicyVersion] = []
    for existing in versions:
        existing_start = as_utc(existing.valid_from)
        if existing_start >= new_start:
            raise HTTPException(
                status_code=409,
                detail="Neue Versionen müssen chronologisch nach vorhandenen Versionen beginnen",
            )
        existing_end = effective_version_end(db, existing)
        if existing_end is None or new_start < as_utc(existing_end):
            versions_to_close.append(existing)
    db.add_all(
        [
            PolicyVersionClosure(
                policy_version_id=existing.id,
                valid_until=new_start,
                closed_by_id=principal.user.id,
            )
            for existing in versions_to_close
        ]
    )
    version = PolicyVersion(
        policy_item_id=policy.id,
        version_number=(versions[-1].version_number + 1) if versions else 1,
        content=payload.content,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        created_by_id=principal.user.id,
    )
    db.add(version)
    db.flush()
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="policies.version_created",
        entity_type="policy_version",
        entity_id=str(version.id),
        ip_address=request.client.host if request.client else None,
        details={
            "policy_id": str(policy.id),
            "version_number": version.version_number,
            "closed_version_numbers": [item.version_number for item in versions_to_close],
        },
    )
    commit_policy(db)
    db.refresh(version)
    return policy_version_read(db, version)


@router.get("/policies/{policy_id}/employees", response_model=list[PolicyEmployeeOption])
def policy_employee_options(
    policy_id: UUID,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_permission("policies.manage")),
) -> list[PolicyEmployeeOption]:
    policy = get_policy_or_404(db, policy_id)
    require_policy_access(db, principal, policy)
    query = select(Employee).where(
        Employee.archived_at.is_(None),
        Employee.employment_status == "active",
        Employee.user_id.is_not(None),
    )
    if policy.object_id is not None:
        query = query.where(
            Employee.user_id.in_(
                select(ObjectAssignment.user_id).where(
                    ObjectAssignment.object_id == policy.object_id
                )
            )
        )
    elif "objects.manage_all" not in principal.permission_codes:
        object_ids = managed_object_ids(db, principal) or set()
        query = query.where(
            Employee.user_id.in_(
                select(ObjectAssignment.user_id).where(ObjectAssignment.object_id.in_(object_ids))
            )
        )
    employees = db.scalars(query.order_by(Employee.full_name)).all()
    return [
        PolicyEmployeeOption(
            id=employee.id,
            full_name=employee.full_name,
            employee_number=employee.employee_number,
        )
        for employee in employees
    ]


@router.post(
    "/policies/{policy_id}/versions/{version_id}/assignments",
    response_model=PolicyAssignmentRead,
    status_code=status.HTTP_201_CREATED,
)
def assign_policy(
    policy_id: UUID,
    version_id: UUID,
    payload: PolicyAssignmentCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_permission("policies.manage")),
) -> PolicyAssignmentRead:
    policy = get_policy_or_404(db, policy_id)
    require_policy_access(db, principal, policy)
    version = db.scalar(
        select(PolicyVersion).where(
            PolicyVersion.id == version_id,
            PolicyVersion.policy_item_id == policy.id,
        )
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Version nicht gefunden")
    valid_until = effective_version_end(db, version)
    if valid_until is not None and as_utc(valid_until) <= utc_now():
        raise HTTPException(
            status_code=409, detail="Abgelaufene Versionen können nicht zugewiesen werden"
        )
    if payload.due_at is not None and (
        as_utc(payload.due_at) < as_utc(version.valid_from)
        or (valid_until is not None and as_utc(payload.due_at) >= as_utc(valid_until))
    ):
        raise HTTPException(
            status_code=422,
            detail="Die Fälligkeit muss innerhalb des Gültigkeitszeitraums der Version liegen",
        )
    employee = db.scalar(
        select(Employee).where(
            Employee.id == payload.employee_id,
            Employee.archived_at.is_(None),
            Employee.employment_status == "active",
            Employee.user_id.is_not(None),
        )
    )
    if employee is None:
        raise HTTPException(
            status_code=404, detail="Aktiver Mitarbeiter mit Benutzerkonto nicht gefunden"
        )
    ensure_employee_object_access(db, employee, policy)
    assignment = PolicyAssignment(
        policy_version_id=version.id,
        employee_id=employee.id,
        cycle_number=1,
        due_at=payload.due_at,
        assigned_by_id=principal.user.id,
    )
    db.add(assignment)
    db.flush()
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="policies.assigned",
        entity_type="policy_assignment",
        entity_id=str(assignment.id),
        ip_address=request.client.host if request.client else None,
        details={"policy_id": str(policy.id), "version_number": version.version_number},
    )
    commit_policy(db)
    return assignment_read(db, assignment, policy, version)


def assignment_read(
    db: Session, assignment: PolicyAssignment, policy: PolicyItem, version: PolicyVersion
) -> PolicyAssignmentRead:
    now = utc_now()
    read_at = receipt_time(db, assignment.id, "read")
    confirmed_at = receipt_time(db, assignment.id, "confirmed")
    due_at = as_utc(assignment.due_at) if assignment.due_at else None
    reminder_at = (
        due_at - timedelta(days=policy.reminder_days)
        if due_at is not None and policy.reminder_days is not None
        else None
    )
    obj = db.get(SecurityObject, policy.object_id) if policy.object_id else None
    return PolicyAssignmentRead(
        id=assignment.id,
        policy_id=policy.id,
        kind=policy.kind,
        title=policy.title,
        object_id=policy.object_id,
        object_name=obj.name if obj else None,
        version_id=version.id,
        version_number=version.version_number,
        content=version.content,
        valid_from=as_utc(version.valid_from),
        valid_until=as_utc(effective_version_end(db, version))
        if effective_version_end(db, version)
        else None,
        cycle_number=assignment.cycle_number,
        due_at=as_utc(assignment.due_at) if assignment.due_at else None,
        read_at=as_utc(read_at) if read_at else None,
        confirmed_at=as_utc(confirmed_at) if confirmed_at else None,
        overdue=due_at is not None and due_at < now and confirmed_at is None,
        reminder_due=reminder_at is not None and reminder_at <= now and confirmed_at is None,
    )


@router.get("/policies/assignments/me", response_model=list[PolicyAssignmentRead])
def list_my_policy_assignments(
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_permission("policies.read_own")),
) -> list[PolicyAssignmentRead]:
    employee = current_employee(db, principal)
    now = utc_now()
    effective_until = func.coalesce(
        select(PolicyVersionClosure.valid_until)
        .where(PolicyVersionClosure.policy_version_id == PolicyVersion.id)
        .scalar_subquery(),
        PolicyVersion.valid_until,
    )
    query = (
        select(PolicyAssignment, PolicyVersion, PolicyItem)
        .join(PolicyVersion, PolicyVersion.id == PolicyAssignment.policy_version_id)
        .join(PolicyItem, PolicyItem.id == PolicyVersion.policy_item_id)
        .where(
            PolicyAssignment.employee_id == employee.id,
            PolicyItem.archived_at.is_(None),
            PolicyVersion.valid_from <= now,
            or_(effective_until.is_(None), effective_until > now),
            or_(
                PolicyItem.object_id.is_(None),
                PolicyItem.object_id.in_(
                    select(ObjectAssignment.object_id).where(
                        ObjectAssignment.user_id == principal.user.id
                    )
                ),
            ),
        )
        .order_by(PolicyAssignment.due_at, PolicyItem.title, PolicyAssignment.cycle_number)
    )
    return [
        assignment_read(db, assignment, policy, version)
        for assignment, version, policy in db.execute(query).all()
    ]


def record_policy_action(
    assignment_id: UUID,
    action: str,
    request: Request,
    db: Session,
    principal: AuthPrincipal,
) -> PolicyAssignmentRead:
    employee = current_employee(db, principal)
    assignment, version, policy = get_assignment_for_employee(db, assignment_id, employee)
    if action == "confirmed" and receipt_time(db, assignment.id, "read") is None:
        raise HTTPException(
            status_code=409, detail="Die Version muss vor der Bestätigung gelesen werden"
        )
    if receipt_time(db, assignment.id, action) is not None:
        raise HTTPException(status_code=409, detail="Dieser Nachweis wurde bereits gespeichert")
    now = utc_now()
    db.add(
        PolicyReceipt(
            assignment_id=assignment.id,
            action=action,
            actor_id=principal.user.id,
            created_at=now,
        )
    )
    if action == "confirmed" and policy.kind == "training" and policy.repeat_interval_days:
        due_at = now + timedelta(days=policy.repeat_interval_days)
        if version.valid_until is None or due_at < as_utc(version.valid_until):
            db.add(
                PolicyAssignment(
                    policy_version_id=version.id,
                    employee_id=employee.id,
                    cycle_number=assignment.cycle_number + 1,
                    due_at=due_at,
                    assigned_by_id=principal.user.id,
                    assigned_at=now,
                )
            )
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action=f"policies.{action}",
        entity_type="policy_assignment",
        entity_id=str(assignment.id),
        ip_address=request.client.host if request.client else None,
        details={"version_id": str(version.id)},
    )
    commit_policy(db)
    return assignment_read(db, assignment, policy, version)


@router.post("/policies/assignments/{assignment_id}/read", response_model=PolicyAssignmentRead)
def record_policy_read(
    assignment_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_permission("policies.read_own")),
) -> PolicyAssignmentRead:
    return record_policy_action(assignment_id, "read", request, db, principal)


@router.post("/policies/assignments/{assignment_id}/confirm", response_model=PolicyAssignmentRead)
def confirm_policy(
    assignment_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_permission("policies.read_own")),
) -> PolicyAssignmentRead:
    return record_policy_action(assignment_id, "confirmed", request, db, principal)


@router.get("/policies/{policy_id}/history", response_model=PolicyHistoryRead)
def get_policy_history(
    policy_id: UUID,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_permission("policies.manage")),
) -> PolicyHistoryRead:
    policy = get_policy_or_404(db, policy_id)
    require_policy_access(db, principal, policy)
    version_rows = db.execute(
        select(PolicyAssignment, PolicyVersion, Employee)
        .join(PolicyVersion, PolicyVersion.id == PolicyAssignment.policy_version_id)
        .join(Employee, Employee.id == PolicyAssignment.employee_id)
        .where(PolicyVersion.policy_item_id == policy.id)
        .order_by(PolicyVersion.version_number, Employee.full_name, PolicyAssignment.cycle_number)
    ).all()
    history = []
    for assignment, version, employee in version_rows:
        read_at = receipt_time(db, assignment.id, "read")
        confirmed_at = receipt_time(db, assignment.id, "confirmed")
        due_at = as_utc(assignment.due_at) if assignment.due_at else None
        reminder_at = (
            due_at - timedelta(days=policy.reminder_days)
            if due_at is not None and policy.reminder_days is not None
            else None
        )
        history.append(
            {
                "employee_id": str(employee.id),
                "employee_number": employee.employee_number,
                "employee_name": employee.full_name,
                "version_id": str(version.id),
                "version_number": version.version_number,
                "cycle_number": assignment.cycle_number,
                "due_at": as_utc(assignment.due_at).isoformat() if assignment.due_at else None,
                "assigned_at": as_utc(assignment.assigned_at).isoformat(),
                "read_at": as_utc(read_at).isoformat() if read_at else None,
                "confirmed_at": as_utc(confirmed_at).isoformat() if confirmed_at else None,
                "overdue": due_at is not None and due_at < utc_now() and confirmed_at is None,
                "reminder_due": (
                    reminder_at is not None and reminder_at <= utc_now() and confirmed_at is None
                ),
            }
        )
    return PolicyHistoryRead(policy=policy_read(db, policy), assignments=history)


def csv_safe(value: object) -> str:
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text


@router.get("/policies/{policy_id}/export.csv")
def export_policy_proof(
    policy_id: UUID,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_permission("policies.manage")),
) -> Response:
    policy = get_policy_or_404(db, policy_id)
    require_policy_access(db, principal, policy)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "Mitarbeiternummer",
            "Mitarbeiter",
            "Version",
            "Zyklus",
            "Fällig am (UTC)",
            "Zugewiesen am (UTC)",
            "Gelesen am (UTC)",
            "Bestätigt am (UTC)",
        ]
    )
    rows = db.execute(
        select(PolicyAssignment, PolicyVersion, Employee)
        .join(PolicyVersion, PolicyVersion.id == PolicyAssignment.policy_version_id)
        .join(Employee, Employee.id == PolicyAssignment.employee_id)
        .where(PolicyVersion.policy_item_id == policy.id)
        .order_by(Employee.full_name, PolicyVersion.version_number, PolicyAssignment.cycle_number)
    ).all()
    for assignment, version, employee in rows:
        read_at = receipt_time(db, assignment.id, "read")
        confirmed_at = receipt_time(db, assignment.id, "confirmed")
        writer.writerow(
            [
                csv_safe(employee.employee_number),
                csv_safe(employee.full_name),
                version.version_number,
                assignment.cycle_number,
                as_utc(assignment.due_at).isoformat() if assignment.due_at else "",
                as_utc(assignment.assigned_at).isoformat(),
                as_utc(read_at).isoformat() if read_at else "",
                as_utc(confirmed_at).isoformat() if confirmed_at else "",
            ]
        )
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="nachweis-{policy.id}.csv"'},
    )
