from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth import AuthPrincipal, add_audit_entry, get_auth_principal, require_permission
from app.database import get_db
from app.models import (
    Customer,
    ObjectAssignment,
    SecurityObject,
    Task,
    TaskComment,
    TaskHistory,
    User,
)
from app.notifications_service import enqueue_task_event
from app.task_access import task_visibility
from app.task_schemas import (
    TaskAssigneeRead,
    TaskCommentCreate,
    TaskCommentRead,
    TaskCreate,
    TaskCustomerChoice,
    TaskDetail,
    TaskHistoryRead,
    TaskLocationsRead,
    TaskObjectChoice,
    TaskPage,
    TaskPriority,
    TaskRead,
    TaskStatus,
    TaskUpdate,
)

router = APIRouter()


def require_task_reader(
    principal: Annotated[AuthPrincipal, Depends(get_auth_principal)],
) -> AuthPrincipal:
    if not principal.permission_codes.intersection(
        {"tasks.read_own", "tasks.read_all", "tasks.manage_all"}
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung für diese Aktion",
        )
    return principal


def task_query():
    return select(Task).options(
        selectinload(Task.assignee),
        selectinload(Task.creator),
        selectinload(Task.customer),
        selectinload(Task.object),
    )


def get_visible_task(db: Session, task_id: UUID, principal: AuthPrincipal) -> Task:
    task = db.scalar(task_query().where(Task.id == task_id, task_visibility(principal)))
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aufgabe nicht gefunden")
    return task


def ensure_can_edit(task: Task, principal: AuthPrincipal, db: Session) -> None:
    permissions = principal.permission_codes
    if {"tasks.manage", "tasks.manage_all"} & permissions:
        return
    if "tasks.update_own" in permissions and (
        task.created_by_id == principal.user.id or task.assigned_to_id == principal.user.id
    ):
        return
    if "tasks.update_own" in permissions and task.object_id is not None:
        has_object_assignment = db.scalar(
            select(ObjectAssignment.id).where(
                ObjectAssignment.object_id == task.object_id,
                ObjectAssignment.user_id == principal.user.id,
            )
        )
        if has_object_assignment is not None:
            return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Keine Berechtigung, diese Aufgabe zu bearbeiten",
    )


def require_task_editor(principal: AuthPrincipal) -> None:
    if not {"tasks.update_own", "tasks.manage", "tasks.manage_all"} & principal.permission_codes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung für diese Aktion",
        )


def task_read(task: Task) -> TaskRead:
    return TaskRead(
        id=task.id,
        title=task.title,
        description=task.description,
        assigned_to_id=task.assigned_to_id,
        assigned_to_name=task.assignee.full_name,
        created_by_id=task.created_by_id,
        created_by_name=task.creator.full_name if task.creator else None,
        customer_id=task.customer_id,
        customer_name=task.customer.company_name if task.customer else None,
        object_id=task.object_id,
        object_name=task.object.name if task.object else None,
        due_at=task.due_at,
        priority=task.priority,
        status=task.status,
        completion_evidence=task.completion_evidence,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def task_detail(db: Session, task: Task) -> TaskDetail:
    comments = db.scalars(
        select(TaskComment)
        .options(selectinload(TaskComment.author))
        .where(TaskComment.task_id == task.id)
        .order_by(TaskComment.created_at, TaskComment.id)
    ).all()
    history = db.scalars(
        select(TaskHistory)
        .options(selectinload(TaskHistory.actor))
        .where(TaskHistory.task_id == task.id)
        .order_by(TaskHistory.created_at, TaskHistory.id)
    ).all()
    return TaskDetail(
        **task_read(task).model_dump(),
        comments=[
            TaskCommentRead(
                id=comment.id,
                author_id=comment.author_id,
                author_name=comment.author.full_name if comment.author else None,
                body=comment.body,
                created_at=comment.created_at,
            )
            for comment in comments
        ],
        history=[
            TaskHistoryRead(
                id=entry.id,
                actor_id=entry.actor_id,
                actor_name=entry.actor.full_name if entry.actor else None,
                action=entry.action,
                changes=entry.changes,
                created_at=entry.created_at,
            )
            for entry in history
        ],
    )


def record_history(
    db: Session,
    task: Task,
    actor_id: UUID,
    action: str,
    changes: dict[str, object] | None = None,
) -> TaskHistory:
    history = TaskHistory(
        id=uuid4(),
        task_id=task.id,
        actor_id=actor_id,
        action=action,
        changes=changes or {},
    )
    db.add(history)
    return history


def audit_task(
    db: Session,
    request: Request,
    principal: AuthPrincipal,
    action: str,
    task: Task,
    details: dict[str, object] | None = None,
) -> None:
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action=action,
        entity_type="task",
        entity_id=str(task.id),
        ip_address=request.client.host if request.client else None,
        details=details,
    )


def commit_task_transaction(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Die Aufgabenänderung verletzt eine Datenbankbedingung",
        ) from exc


def flush_task_transaction(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Die Aufgabenänderung verletzt eine Datenbankbedingung",
        ) from exc


def normalize_due_at(value: datetime | None) -> datetime | None:
    return value.astimezone(UTC) if value is not None else None


def validate_location(
    db: Session,
    principal: AuthPrincipal,
    *,
    customer_id: UUID | None,
    object_id: UUID | None,
) -> tuple[UUID | None, UUID | None]:
    if customer_id is not None:
        customer = db.get(Customer, customer_id)
        if customer is None or customer.archived_at is not None:
            raise HTTPException(status_code=404, detail="Kunde nicht gefunden")

    security_object = None
    permissions = principal.permission_codes
    has_global_scope = bool(
        {"tasks.read_all", "tasks.manage_all", "objects.manage_all"} & permissions
    )
    if customer_id is not None and object_id is None and not has_global_scope:
        has_customer_object = db.scalar(
            select(SecurityObject.id)
            .join(ObjectAssignment, ObjectAssignment.object_id == SecurityObject.id)
            .where(
                SecurityObject.customer_id == customer_id,
                SecurityObject.archived_at.is_(None),
                ObjectAssignment.user_id == principal.user.id,
            )
        )
        if has_customer_object is None:
            raise HTTPException(status_code=404, detail="Kunde nicht gefunden")
    if object_id is not None:
        security_object = db.get(SecurityObject, object_id)
        if security_object is None:
            raise HTTPException(status_code=404, detail="Objekt nicht gefunden")
        if security_object.archived_at is not None:
            raise HTTPException(status_code=422, detail="Archivierte Objekte sind nicht auswählbar")
        has_object_assignment = db.scalar(
            select(ObjectAssignment.id).where(
                ObjectAssignment.object_id == object_id,
                ObjectAssignment.user_id == principal.user.id,
            )
        )
        if not has_global_scope and has_object_assignment is None:
            raise HTTPException(status_code=404, detail="Objekt nicht gefunden")
        if customer_id is not None and customer_id != security_object.customer_id:
            raise HTTPException(
                status_code=422,
                detail="Kunde und Objekt gehören nicht zusammen",
            )
        customer_id = security_object.customer_id
    return customer_id, object_id


def validate_assignee(
    db: Session,
    principal: AuthPrincipal,
    assignee_id: UUID,
    object_id: UUID | None,
) -> User:
    assignee = db.scalar(select(User).where(User.id == assignee_id, User.is_active.is_(True)))
    if assignee is None:
        raise HTTPException(status_code=422, detail="Verantwortliche Person ist ungültig")
    if assignee_id != principal.user.id and "tasks.assign" not in principal.permission_codes:
        raise HTTPException(
            status_code=403,
            detail="Keine Berechtigung, Aufgaben anderen Personen zuzuweisen",
        )
    if object_id is not None and assignee_id != principal.user.id:
        permissions = principal.permission_codes
        has_global_scope = bool(
            {"tasks.read_all", "tasks.manage_all", "objects.manage_all"} & permissions
        )
        is_assigned = db.scalar(
            select(ObjectAssignment.id).where(
                ObjectAssignment.object_id == object_id,
                ObjectAssignment.user_id == assignee_id,
            )
        )
        if not has_global_scope and is_assigned is None:
            raise HTTPException(
                status_code=422,
                detail="Die verantwortliche Person ist diesem Objekt nicht zugewiesen",
            )
    return assignee


@router.get("/tasks/assignees", response_model=list[TaskAssigneeRead])
def list_task_assignees(
    object_id: UUID | None = None,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("tasks.assign")),
) -> list[TaskAssigneeRead]:
    query = select(User).where(User.is_active.is_(True))
    if object_id is not None:
        validate_location(db, principal, customer_id=None, object_id=object_id)
        permissions = principal.permission_codes
        has_global_scope = bool(
            {"tasks.read_all", "tasks.manage_all", "objects.manage_all"} & permissions
        )
        if not has_global_scope:
            assigned_to_object = select(ObjectAssignment.user_id).where(
                ObjectAssignment.object_id == object_id
            )
            query = query.where(User.id.in_(assigned_to_object))
    elif not {"tasks.read_all", "tasks.manage_all"} & principal.permission_codes:
        query = query.where(User.id == principal.user.id)
    return [
        TaskAssigneeRead(id=user.id, full_name=user.full_name)
        for user in db.scalars(query.order_by(User.full_name, User.id)).all()
    ]


@router.get("/tasks/locations", response_model=TaskLocationsRead)
def list_task_locations(
    db: Session = Depends(get_db),
    principal=Depends(require_permission("tasks.create")),
) -> TaskLocationsRead:
    permissions = principal.permission_codes
    if {"tasks.read_all", "tasks.manage_all", "objects.manage_all"} & permissions:
        customers = db.scalars(
            select(Customer).where(Customer.archived_at.is_(None)).order_by(Customer.company_name)
        ).all()
        objects = db.scalars(
            select(SecurityObject)
            .options(selectinload(SecurityObject.customer))
            .where(SecurityObject.archived_at.is_(None))
            .order_by(SecurityObject.name)
        ).all()
    else:
        assigned_objects = (
            select(SecurityObject)
            .join(ObjectAssignment, ObjectAssignment.object_id == SecurityObject.id)
            .where(
                ObjectAssignment.user_id == principal.user.id,
                SecurityObject.archived_at.is_(None),
            )
            .options(selectinload(SecurityObject.customer))
            .order_by(SecurityObject.name)
        )
        objects = db.scalars(assigned_objects).all()
        customer_ids = {security_object.customer_id for security_object in objects}
        customers = (
            db.scalars(
                select(Customer)
                .where(Customer.id.in_(customer_ids), Customer.archived_at.is_(None))
                .order_by(Customer.company_name)
            ).all()
            if customer_ids
            else []
        )
    return TaskLocationsRead(
        customers=[
            TaskCustomerChoice(id=customer.id, company_name=customer.company_name)
            for customer in customers
        ],
        objects=[
            TaskObjectChoice(
                id=security_object.id,
                name=security_object.name,
                customer_id=security_object.customer_id,
                customer_name=security_object.customer.company_name,
            )
            for security_object in objects
        ],
    )


@router.get("/tasks", response_model=TaskPage)
def list_tasks(
    q: str | None = Query(default=None, max_length=200),
    task_status: TaskStatus | None = Query(default=None, alias="status"),
    priority: TaskPriority | None = None,
    assigned_to_id: UUID | None = None,
    customer_id: UUID | None = None,
    object_id: UUID | None = None,
    overdue: bool = False,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_task_reader),
) -> TaskPage:
    filters = [task_visibility(principal)]
    if task_status is not None:
        filters.append(Task.status == task_status)
    if priority is not None:
        filters.append(Task.priority == priority)
    if assigned_to_id is not None:
        filters.append(Task.assigned_to_id == assigned_to_id)
    if customer_id is not None:
        filters.append(Task.customer_id == customer_id)
    if object_id is not None:
        filters.append(Task.object_id == object_id)
    if overdue:
        filters.extend(
            (Task.due_at < datetime.now(UTC), Task.status.not_in(("completed", "cancelled")))
        )
    if q and q.strip():
        term = f"%{q.strip()}%"
        filters.append(or_(Task.title.ilike(term), Task.description.ilike(term)))
    query = task_query().where(*filters)
    count_query = select(func.count()).select_from(Task).where(*filters)
    items = db.scalars(
        query.order_by(Task.due_at.asc().nulls_last(), Task.created_at.desc(), Task.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return TaskPage(
        items=[task_read(task) for task in items],
        total=db.scalar(count_query) or 0,
        limit=limit,
        offset=offset,
    )


@router.post("/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal=Depends(require_permission("tasks.create")),
) -> TaskRead:
    assignee_id = payload.assigned_to_id or principal.user.id
    customer_id, object_id = validate_location(
        db,
        principal,
        customer_id=payload.customer_id,
        object_id=payload.object_id,
    )
    validate_assignee(db, principal, assignee_id, object_id)
    task = Task(
        id=uuid4(),
        title=payload.title,
        description=payload.description,
        assigned_to_id=assignee_id,
        created_by_id=principal.user.id,
        customer_id=customer_id,
        object_id=object_id,
        due_at=normalize_due_at(payload.due_at),
        priority=payload.priority,
        status="open",
    )
    db.add(task)
    flush_task_transaction(db)
    record_history(
        db,
        task,
        principal.user.id,
        "created",
        {"title": task.title, "assigned_to_id": str(task.assigned_to_id)},
    )
    audit_task(db, request, principal, "task.created", task)
    if assignee_id != principal.user.id:
        assignment_history = record_history(
            db,
            task,
            principal.user.id,
            "assigned",
            {"previous_assignee_id": None, "assignee_id": str(assignee_id)},
        )
        enqueue_task_event(
            db,
            task,
            assignment_history,
            event_type="task.assigned",
            recipient_ids={assignee_id},
        )
        audit_task(
            db,
            request,
            principal,
            "task.assigned",
            task,
            {"previous_assignee_id": None, "assignee_id": str(assignee_id)},
        )
    commit_task_transaction(db)
    task = db.scalar(task_query().where(Task.id == task.id))
    return task_read(task)


@router.get("/tasks/{task_id}", response_model=TaskDetail)
def get_task(
    task_id: UUID,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_task_reader),
) -> TaskDetail:
    task = get_visible_task(db, task_id, principal)
    return task_detail(db, task)


@router.patch("/tasks/{task_id}", response_model=TaskRead)
def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    request: Request,
    db: Session = Depends(get_db),
    principal=Depends(get_auth_principal),
) -> TaskRead:
    require_task_editor(principal)
    task = get_visible_task(db, task_id, principal)
    ensure_can_edit(task, principal, db)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Es wurden keine Änderungen übermittelt")
    if "title" in changes and changes["title"] is None:
        raise HTTPException(status_code=422, detail="Der Aufgabentitel darf nicht leer sein")
    for field in ("assigned_to_id", "priority", "status"):
        if field in changes and changes[field] is None:
            raise HTTPException(status_code=422, detail=f"{field} darf nicht leer sein")

    original_assignee_id = task.assigned_to_id
    original_status = task.status
    before: dict[str, object] = {}
    after: dict[str, object] = {}
    if any(field in changes for field in ("customer_id", "object_id")):
        next_object_id = changes.get("object_id", task.object_id)
        next_customer_id = changes.get("customer_id", task.customer_id)
        next_customer_id, next_object_id = validate_location(
            db,
            principal,
            customer_id=next_customer_id,
            object_id=next_object_id,
        )
        changes["customer_id"] = next_customer_id
        changes["object_id"] = next_object_id
    if "assigned_to_id" in changes:
        validate_assignee(
            db, principal, changes["assigned_to_id"], changes.get("object_id", task.object_id)
        )
    if (
        changes.get("status") == "completed"
        and original_status != "completed"
        and not changes.get("completion_evidence")
    ):
        raise HTTPException(
            status_code=422,
            detail="Zum Abschließen ist ein Erledigungsnachweis erforderlich",
        )
    if (
        changes.get("status", original_status) == "completed"
        and changes.get("completion_evidence") is None
        and "completion_evidence" in changes
    ):
        raise HTTPException(
            status_code=422,
            detail="Der Erledigungsnachweis einer abgeschlossenen Aufgabe darf nicht entfernt werden",
        )

    for field, requested_value in changes.items():
        old_value = getattr(task, field)
        new_value = normalize_due_at(requested_value) if field == "due_at" else requested_value
        old_record = old_value
        new_record = new_value
        if field in {"assigned_to_id", "customer_id", "object_id"}:
            old_record = str(old_value) if old_value is not None else None
            new_record = str(new_value) if new_value is not None else None
        elif field == "due_at":
            old_record = old_value.isoformat() if old_value is not None else None
            new_record = new_value.isoformat() if new_value is not None else None
        if old_record != new_record:
            before[field] = old_record
            after[field] = new_record
            setattr(task, field, new_value)
    if not after:
        raise HTTPException(status_code=422, detail="Es wurden keine Änderungen übermittelt")

    task.updated_at = datetime.now(UTC)
    action = (
        "completed" if task.status == "completed" and original_status != "completed" else "updated"
    )
    history = record_history(
        db, task, principal.user.id, action, {"before": before, "after": after}
    )
    audit_task(db, request, principal, "task.updated", task, {"fields": sorted(after)})
    if task.assigned_to_id != original_assignee_id:
        assignment_history = record_history(
            db,
            task,
            principal.user.id,
            "assigned",
            {
                "previous_assignee_id": str(original_assignee_id),
                "assignee_id": str(task.assigned_to_id),
            },
        )
        enqueue_task_event(
            db,
            task,
            assignment_history,
            event_type="task.assigned",
            recipient_ids={task.assigned_to_id},
            previous_assignee_id=original_assignee_id,
        )
        audit_task(
            db,
            request,
            principal,
            "task.assigned",
            task,
            {
                "previous_assignee_id": str(original_assignee_id),
                "assignee_id": str(task.assigned_to_id),
            },
        )
    if task.status == "completed" and original_status != "completed":
        audit_task(db, request, principal, "task.completed", task)
    if task.status != original_status:
        status_recipients = {
            recipient_id
            for recipient_id in (task.assigned_to_id, task.created_by_id)
            if recipient_id is not None and recipient_id != principal.user.id
        }
        enqueue_task_event(
            db,
            task,
            history,
            event_type="task.status_changed",
            recipient_ids=status_recipients,
        )
    commit_task_transaction(db)
    db.expire(task, ["assignee", "customer", "object"])
    task = db.scalar(task_query().where(Task.id == task.id))
    return task_read(task)


@router.post(
    "/tasks/{task_id}/comments",
    response_model=TaskCommentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_task_comment(
    task_id: UUID,
    payload: TaskCommentCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal=Depends(get_auth_principal),
) -> TaskCommentRead:
    require_task_editor(principal)
    task = get_visible_task(db, task_id, principal)
    ensure_can_edit(task, principal, db)
    comment = TaskComment(
        id=uuid4(),
        task_id=task.id,
        author_id=principal.user.id,
        body=payload.body,
    )
    db.add(comment)
    flush_task_transaction(db)
    record_history(db, task, principal.user.id, "comment_added", {"comment_id": str(comment.id)})
    audit_task(db, request, principal, "task.comment_added", task)
    commit_task_transaction(db)
    return TaskCommentRead(
        id=comment.id,
        author_id=comment.author_id,
        author_name=principal.user.full_name,
        body=comment.body,
        created_at=comment.created_at,
    )
