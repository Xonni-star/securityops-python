from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from app.auth import AuthPrincipal, get_auth_principal
from app.database import get_db
from app.models import Customer, ObjectAssignment, SecurityObject
from app.search_schemas import SearchEntityType, SearchPage, SearchResult

router = APIRouter()


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _search_query(query: str, entity_type: SearchEntityType | None, principal: AuthPrincipal):
    term = query.strip()
    escaped_term = _escape_like(term)
    pattern = f"%{escaped_term}%"
    prefix_pattern = f"{escaped_term}%"
    term_lower = term.lower()
    selects = []
    permissions = principal.permission_codes

    if "customers.read" in permissions and entity_type in (None, "customer"):
        title = Customer.company_name
        reference = Customer.customer_number
        selects.append(
            select(
                literal("customer").label("type"),
                Customer.id.label("id"),
                title.label("title"),
                reference.label("reference"),
                case(
                    (
                        or_(
                            func.lower(title) == term_lower,
                            func.lower(reference) == term_lower,
                        ),
                        0,
                    ),
                    (
                        or_(
                            title.ilike(prefix_pattern, escape="\\"),
                            reference.ilike(prefix_pattern, escape="\\"),
                        ),
                        1,
                    ),
                    else_=2,
                ).label("rank"),
            ).where(
                Customer.archived_at.is_(None),
                or_(
                    title.ilike(pattern, escape="\\"),
                    reference.ilike(pattern, escape="\\"),
                ),
            )
        )

    if "objects.read" in permissions and entity_type in (None, "object"):
        title = SecurityObject.name
        reference = SecurityObject.code
        object_query = select(
            literal("object").label("type"),
            SecurityObject.id.label("id"),
            title.label("title"),
            reference.label("reference"),
            case(
                (
                    or_(
                        func.lower(title) == term_lower,
                        func.lower(reference) == term_lower,
                    ),
                    0,
                ),
                (
                    or_(
                        title.ilike(prefix_pattern, escape="\\"),
                        reference.ilike(prefix_pattern, escape="\\"),
                    ),
                    1,
                ),
                else_=2,
            ).label("rank"),
        ).where(
            SecurityObject.archived_at.is_(None),
            or_(
                title.ilike(pattern, escape="\\"),
                reference.ilike(pattern, escape="\\"),
            ),
        )
        if "objects.read_all" not in permissions:
            object_query = object_query.where(
                SecurityObject.assignments.any(ObjectAssignment.user_id == principal.user.id)
            )
        selects.append(object_query)

    return union_all(*selects).subquery() if selects else None


@router.get("/search", response_model=SearchPage)
def global_search(
    q: Annotated[str, Query(min_length=2, max_length=100)],
    entity_type: Annotated[SearchEntityType | None, Query(alias="type")] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0, le=5000)] = 0,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_auth_principal),
) -> SearchPage:
    term = q.strip()
    if len(term) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Die Sucheingabe muss mindestens zwei Zeichen enthalten.",
        )

    permissions = principal.permission_codes
    if not permissions.intersection({"customers.read", "objects.read"}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung für die globale Suche",
        )

    results = _search_query(term, entity_type, principal)
    if results is None:
        return SearchPage(items=[], total=0, limit=limit, offset=offset)

    total = db.scalar(select(func.count()).select_from(results)) or 0
    rows = db.execute(
        select(
            results.c.id,
            results.c.type,
            results.c.title,
            results.c.reference,
        )
        .order_by(
            results.c.rank,
            func.lower(results.c.title),
            results.c.type,
            results.c.reference,
            results.c.id,
        )
        .limit(limit)
        .offset(offset)
    ).all()
    return SearchPage(
        items=[
            SearchResult(id=row.id, type=row.type, title=row.title, reference=row.reference)
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
