from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, case, cast, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from app.auth import AuthPrincipal, get_auth_principal
from app.database import get_db
from app.documents_contracts_api import _scope_contract_query, _scope_document_query
from app.incidents_api import GLOBAL_READ, _incident_query, _require_incident_reader
from app.inventory_api import has_global_object_access
from app.key_management_api import key_query
from app.models import (
    Contract,
    Customer,
    Document,
    Employee,
    Incident,
    InventoryAsset,
    ObjectAssignment,
    OWKSEvent,
    PhysicalKey,
    ScheduleShift,
    SecurityObject,
    Task,
)
from app.scheduling_api import visible_shift_query
from app.search_schemas import SearchEntityType, SearchPage, SearchResult
from app.tasks_api import task_visibility

router = APIRouter()

SEARCH_PERMISSIONS = {
    "customers.read",
    "objects.read",
    "employees.read",
    "documents.read",
    "contracts.read",
    "scheduling.read",
    "tasks.read_own",
    "tasks.read_all",
    "tasks.manage_all",
    "incidents.read",
    "incidents.read_all",
    "incidents.manage_all",
    "keys.read",
    "inventory.read",
    "owks.read",
}


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _active_customer(customer_id):
    return or_(
        customer_id.is_(None),
        select(Customer.id)
        .where(Customer.id == customer_id, Customer.archived_at.is_(None))
        .exists(),
    )


def _active_object(object_id):
    return or_(
        object_id.is_(None),
        select(SecurityObject.id)
        .join(Customer, Customer.id == SecurityObject.customer_id)
        .where(
            SecurityObject.id == object_id,
            SecurityObject.archived_at.is_(None),
            Customer.archived_at.is_(None),
        )
        .exists(),
    )


def _active_employee(employee_id):
    return or_(
        employee_id.is_(None),
        select(Employee.id)
        .where(Employee.id == employee_id, Employee.archived_at.is_(None))
        .exists(),
    )


def _search_query(
    query: str,
    entity_type: SearchEntityType | None,
    principal: AuthPrincipal,
    db: Session,
):
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
            SecurityObject.customer.has(Customer.archived_at.is_(None)),
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

    if "employees.read" in permissions and entity_type in (None, "employee"):
        selects.append(
            select(
                literal("employee").label("type"),
                Employee.id.label("id"),
                literal("Mitarbeiter").label("title"),
                Employee.employee_number.label("reference"),
                literal(2).label("rank"),
            ).where(
                Employee.archived_at.is_(None),
                Employee.employee_number.ilike(pattern, escape="\\"),
            )
        )

    if "documents.read" in permissions and entity_type in (None, "document"):
        document_query = _scope_document_query(select(Document), db, principal)
        selects.append(
            document_query.with_only_columns(
                literal("document").label("type"),
                Document.id.label("id"),
                Document.title.label("title"),
                Document.document_number.label("reference"),
                literal(2).label("rank"),
            ).where(
                Document.archived_at.is_(None),
                _active_customer(Document.customer_id),
                _active_object(Document.object_id),
                _active_employee(Document.employee_id),
                or_(
                    Document.title.ilike(pattern, escape="\\"),
                    Document.document_number.ilike(pattern, escape="\\"),
                ),
            )
        )

    if "contracts.read" in permissions and entity_type in (None, "contract"):
        contract_query = _scope_contract_query(select(Contract), db, principal)
        selects.append(
            contract_query.with_only_columns(
                literal("contract").label("type"),
                Contract.id.label("id"),
                Contract.name.label("title"),
                Contract.contract_number.label("reference"),
                literal(2).label("rank"),
            ).where(
                Contract.archived_at.is_(None),
                _active_customer(Contract.customer_id),
                _active_object(Contract.object_id),
                _active_employee(Contract.employee_id),
                or_(
                    Contract.name.ilike(pattern, escape="\\"),
                    Contract.contract_number.ilike(pattern, escape="\\"),
                ),
            )
        )

    if "scheduling.read" in permissions and entity_type in (None, "shift"):
        visible_shifts = visible_shift_query(principal).where(
            ScheduleShift.status != "cancelled",
            SecurityObject.archived_at.is_(None),
            SecurityObject.customer.has(Customer.archived_at.is_(None)),
            Employee.archived_at.is_(None),
            or_(
                SecurityObject.name.ilike(pattern, escape="\\"),
                SecurityObject.code.ilike(pattern, escape="\\"),
            ),
        )
        selects.append(
            visible_shifts.with_only_columns(
                literal("shift").label("type"),
                ScheduleShift.id.label("id"),
                literal("Dienst").label("title"),
                cast(ScheduleShift.starts_at, String).label("reference"),
                literal(2).label("rank"),
            )
        )

    if permissions.intersection({"tasks.read_own", "tasks.read_all", "tasks.manage_all"}) and (
        entity_type in (None, "task")
    ):
        visible_tasks = select(Task).where(
            task_visibility(principal),
            Task.title.ilike(pattern, escape="\\"),
            Task.status != "cancelled",
            _active_customer(Task.customer_id),
            _active_object(Task.object_id),
        )
        selects.append(
            visible_tasks.with_only_columns(
                literal("task").label("type"),
                Task.id.label("id"),
                Task.title.label("title"),
                literal("Aufgabe").label("reference"),
                literal(2).label("rank"),
            )
        )

    if permissions.intersection({"incidents.read", *GLOBAL_READ}) and (
        entity_type in (None, "incident")
    ):
        _require_incident_reader(principal)
        visible_incidents = (
            _incident_query(principal)
            .join(SecurityObject, SecurityObject.id == Incident.object_id)
            .where(
                Incident.title.ilike(pattern, escape="\\"),
                SecurityObject.archived_at.is_(None),
                SecurityObject.customer.has(Customer.archived_at.is_(None)),
            )
        )
        selects.append(
            visible_incidents.with_only_columns(
                literal("incident").label("type"),
                Incident.id.label("id"),
                Incident.title.label("title"),
                Incident.incident_type.label("reference"),
                literal(2).label("rank"),
            )
        )

    if "keys.read" in permissions and entity_type in (None, "key"):
        key_visibility = (
            key_query()
            .where(
                PhysicalKey.archived_at.is_(None),
                PhysicalKey.key_number.ilike(pattern, escape="\\"),
            )
            .join(SecurityObject, SecurityObject.id == PhysicalKey.object_id)
            .where(
                SecurityObject.archived_at.is_(None),
                SecurityObject.customer.has(Customer.archived_at.is_(None)),
            )
        )
        if not {"objects.read_all", "objects.manage_all"} & permissions:
            key_visibility = key_visibility.where(
                PhysicalKey.object_id.in_(
                    select(ObjectAssignment.object_id).where(
                        ObjectAssignment.user_id == principal.user.id
                    )
                )
            )
        selects.append(
            key_visibility.with_only_columns(
                literal("key").label("type"),
                PhysicalKey.id.label("id"),
                literal("Schlüssel").label("title"),
                PhysicalKey.key_number.label("reference"),
                literal(2).label("rank"),
            )
        )

    if "inventory.read" in permissions and entity_type in (None, "inventory_asset"):
        inventory_query = select(InventoryAsset).where(
            InventoryAsset.archived_at.is_(None),
            or_(
                InventoryAsset.asset_number.ilike(pattern, escape="\\"),
                InventoryAsset.name.ilike(pattern, escape="\\"),
            ),
            _active_object(InventoryAsset.object_id),
        )
        if not has_global_object_access(principal):
            inventory_query = inventory_query.where(
                InventoryAsset.object_id.in_(
                    select(ObjectAssignment.object_id).where(
                        ObjectAssignment.user_id == principal.user.id
                    )
                )
            )
        selects.append(
            inventory_query.with_only_columns(
                literal("inventory_asset").label("type"),
                InventoryAsset.id.label("id"),
                InventoryAsset.name.label("title"),
                InventoryAsset.asset_number.label("reference"),
                literal(2).label("rank"),
            )
        )

    if "owks.read" in permissions and entity_type in (None, "owks_event"):
        event_labels = {
            "entry": "Eintrag",
            "handover": "Übergabe",
            "control": "Kontrolle",
            "manipulation": "Manipulation",
            "deviation": "Abweichung",
            "missed": "Versäumte Kontrolle",
            "notification": "Meldung",
            "correction": "Korrektur",
        }
        category = case(event_labels, value=OWKSEvent.event_type)
        event_visibility = (
            select(
                OWKSEvent.id,
                OWKSEvent.event_type,
                OWKSEvent.occurred_at,
            )
            .join(SecurityObject, SecurityObject.id == OWKSEvent.object_id)
            .where(
                SecurityObject.archived_at.is_(None),
                SecurityObject.customer.has(Customer.archived_at.is_(None)),
                category.ilike(pattern, escape="\\"),
            )
        )
        if "objects.read_all" not in permissions:
            event_visibility = event_visibility.where(
                SecurityObject.assignments.any(ObjectAssignment.user_id == principal.user.id)
            )
        selects.append(
            event_visibility.with_only_columns(
                literal("owks_event").label("type"),
                OWKSEvent.id.label("id"),
                (literal("Wachbuch: ") + category).label("title"),
                cast(OWKSEvent.occurred_at, String).label("reference"),
                literal(2).label("rank"),
            )
        )

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
    if not permissions.intersection(SEARCH_PERMISSIONS):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung für die globale Suche",
        )

    results = _search_query(term, entity_type, principal, db)
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
