from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.orm import Session

from app.auth import AuthPrincipal, require_permission
from app.database import get_db
from app.models import Notification, ObjectAssignment, SecurityObject, Task
from app.notifications_schemas import NotificationPage, NotificationRead
from app.tasks_api import task_visibility

router = APIRouter()


def require_notification_reader(
    principal: AuthPrincipal = Depends(require_permission("notifications.read_own")),
) -> AuthPrincipal:
    if not principal.permission_codes.intersection(
        {"tasks.read_own", "tasks.read_all", "tasks.manage_all", "owks.read"}
    ):
        raise HTTPException(
            status_code=403,
            detail="Keine Berechtigung für diese Aktion",
        )
    return principal


def visible_notification_query(principal: AuthPrincipal):
    object_scope = (
        and_(
            Notification.object_id.is_not(None),
            SecurityObject.archived_at.is_(None),
            Notification.object_id.in_(
                select(ObjectAssignment.object_id).where(
                    ObjectAssignment.user_id == principal.user.id
                )
            ),
        )
        if "owks.read" in principal.permission_codes
        else false()
    )
    return (
        select(Notification)
        .outerjoin(Task, Notification.task_id == Task.id)
        .outerjoin(SecurityObject, Notification.object_id == SecurityObject.id)
        .where(
            Notification.recipient_id == principal.user.id,
            or_(
                and_(
                    Notification.task_id.is_not(None),
                    task_visibility(principal),
                ),
                object_scope,
            ),
        )
    )


@router.get("/notifications", response_model=NotificationPage)
def list_notifications(
    unread_only: bool = False,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_notification_reader),
) -> NotificationPage:
    base_query = visible_notification_query(principal)
    unread_count = (
        db.scalar(
            select(func.count()).select_from(
                visible_notification_query(principal)
                .where(Notification.read_at.is_(None))
                .subquery()
            )
        )
        or 0
    )
    query = base_query
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    notifications = db.scalars(
        query.order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return NotificationPage(
        items=[NotificationRead.model_validate(item) for item in notifications],
        total=total,
        unread_count=unread_count,
        limit=limit,
        offset=offset,
    )


@router.patch("/notifications/{notification_id}/read", response_model=NotificationRead)
def mark_notification_read(
    notification_id: UUID,
    principal: AuthPrincipal = Depends(require_notification_reader),
    db: Session = Depends(get_db),
) -> NotificationRead:
    notification = db.scalar(
        visible_notification_query(principal).where(Notification.id == notification_id)
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="Benachrichtigung nicht gefunden")
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        db.commit()
        db.refresh(notification)
    return NotificationRead.model_validate(notification)
