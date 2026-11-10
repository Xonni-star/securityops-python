from sqlalchemy import or_, select

from app.auth import AuthPrincipal
from app.models import ObjectAssignment, Task


def task_visibility(principal: AuthPrincipal):
    if {"tasks.read_all", "tasks.manage_all"} & principal.permission_codes:
        return True
    object_ids = select(ObjectAssignment.object_id).where(
        ObjectAssignment.user_id == principal.user.id
    )
    return or_(
        Task.assigned_to_id == principal.user.id,
        Task.created_by_id == principal.user.id,
        Task.object_id.in_(object_ids),
    )
