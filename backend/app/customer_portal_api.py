from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth import AuthPrincipal, add_audit_entry, require_permission
from app.billing_api import build_pdf
from app.customer_portal_schemas import (
    CustomerPortalAddressRead,
    CustomerPortalContactRead,
    CustomerPortalCustomerRead,
    CustomerPortalInvoiceRead,
    CustomerPortalLinkCreate,
    CustomerPortalLinkRead,
    CustomerPortalMeRead,
    CustomerPortalObjectRead,
)
from app.database import get_db
from app.models import (
    BillingInvoice,
    Customer,
    CustomerContact,
    CustomerPortalLink,
    CustomerPortalLinkHistory,
    Role,
    SecurityObject,
    User,
)

router = APIRouter()


def portal_context(db: Session, principal: AuthPrincipal) -> tuple[CustomerContact, Customer]:
    if principal.role_codes != ["customer_portal"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Das Kundenportal-Konto ist nicht mehr freigeschaltet.",
        )

    result = db.execute(
        select(CustomerPortalLink, CustomerContact, Customer)
        .join(CustomerContact, CustomerContact.id == CustomerPortalLink.contact_id)
        .join(Customer, Customer.id == CustomerContact.customer_id)
        .options(selectinload(Customer.addresses))
        .where(CustomerPortalLink.user_id == principal.user.id)
    ).one_or_none()
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Für dieses Konto ist kein Kundenportalzugang eingerichtet.",
        )
    _, contact, customer = result
    if customer.archived_at is not None or customer.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Der Kundenportalzugang ist derzeit nicht verfügbar.",
        )
    return contact, customer


def address_read(address) -> CustomerPortalAddressRead | None:
    return CustomerPortalAddressRead.model_validate(address) if address else None


def customer_read(customer: Customer) -> CustomerPortalCustomerRead:
    addresses = {address.kind: address for address in customer.addresses}
    return CustomerPortalCustomerRead(
        customer_number=customer.customer_number,
        company_name=customer.company_name,
        email=customer.email,
        phone=customer.phone,
        legal_form=customer.legal_form,
        website=customer.website,
        business_address=address_read(addresses.get("business")),
        billing_address=address_read(addresses.get("billing")),
    )


@router.get("/customer-portal/me", response_model=CustomerPortalMeRead)
def get_customer_portal_me(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthPrincipal, Depends(require_permission("customer_portal.access"))],
) -> CustomerPortalMeRead:
    response.headers["Cache-Control"] = "private, no-store"
    contact, customer = portal_context(db, principal)
    objects = db.scalars(
        select(SecurityObject)
        .where(
            SecurityObject.customer_id == customer.id,
            SecurityObject.archived_at.is_(None),
        )
        .order_by(SecurityObject.name, SecurityObject.code)
        .options(selectinload(SecurityObject.address))
    ).all()
    return CustomerPortalMeRead(
        contact=CustomerPortalContactRead.model_validate(contact),
        customer=customer_read(customer),
        objects=[
            CustomerPortalObjectRead(
                id=obj.id,
                code=obj.code,
                name=obj.name,
                object_type=obj.object_type,
                status=obj.status,
                operating_hours=obj.operating_hours,
                service_times=obj.service_times,
                address=address_read(obj.address),
            )
            for obj in objects
        ],
    )


@router.get("/customer-portal/invoices", response_model=list[CustomerPortalInvoiceRead])
def list_customer_portal_invoices(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthPrincipal, Depends(require_permission("customer_portal.access"))],
) -> list[CustomerPortalInvoiceRead]:
    response.headers["Cache-Control"] = "private, no-store"
    _, customer = portal_context(db, principal)
    invoices = db.scalars(
        select(BillingInvoice)
        .where(
            BillingInvoice.customer_id == customer.id,
            BillingInvoice.status == "approved",
            BillingInvoice.archived_at.is_(None),
        )
        .options(selectinload(BillingInvoice.lines))
        .order_by(BillingInvoice.issued_on.desc(), BillingInvoice.created_at.desc())
        .limit(100)
    ).all()
    return [CustomerPortalInvoiceRead.model_validate(invoice) for invoice in invoices]


@router.get("/customer-portal/invoices/{invoice_id}/pdf")
def download_customer_portal_invoice(
    request: Request,
    invoice_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthPrincipal, Depends(require_permission("customer_portal.access"))],
) -> Response:
    _, customer = portal_context(db, principal)
    invoice = db.scalar(
        select(BillingInvoice)
        .where(
            BillingInvoice.id == invoice_id,
            BillingInvoice.customer_id == customer.id,
            BillingInvoice.status == "approved",
            BillingInvoice.archived_at.is_(None),
        )
        .options(selectinload(BillingInvoice.lines))
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail="Freigegebene Rechnung nicht gefunden.")

    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="customer_portal.invoice.downloaded",
        entity_type="billing_invoice",
        entity_id=str(invoice.id),
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return Response(
        content=build_pdf(invoice),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{invoice.invoice_number}.pdf"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/customer-portal/links", response_model=list[CustomerPortalLinkRead])
def list_customer_portal_links(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    _principal: Annotated[AuthPrincipal, Depends(require_permission("customers.portal.manage"))],
) -> list[CustomerPortalLink]:
    response.headers["Cache-Control"] = "private, no-store"
    return db.scalars(
        select(CustomerPortalLink).order_by(CustomerPortalLink.created_at.desc())
    ).all()


@router.post(
    "/customer-portal/links",
    response_model=CustomerPortalLinkRead,
    status_code=status.HTTP_201_CREATED,
)
def create_customer_portal_link(
    request: Request,
    payload: CustomerPortalLinkCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthPrincipal, Depends(require_permission("customers.portal.manage"))],
) -> CustomerPortalLink:
    user = db.scalar(
        select(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .where(User.id == payload.user_id)
        .with_for_update()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Portal-Benutzerkonto nicht gefunden.")
    if not user.is_active or [role.code for role in user.roles] != ["customer_portal"]:
        raise HTTPException(
            status_code=422,
            detail="Das Konto muss aktiv sein und ausschließlich die Kundenportal-Rolle besitzen.",
        )

    contact = db.scalar(
        select(CustomerContact)
        .join(Customer, Customer.id == CustomerContact.customer_id)
        .where(
            CustomerContact.id == payload.contact_id,
            Customer.archived_at.is_(None),
            Customer.status == "active",
        )
        .with_for_update()
    )
    if contact is None:
        raise HTTPException(status_code=404, detail="Aktiver Kundenkontakt nicht gefunden.")
    existing = db.scalar(
        select(CustomerPortalLink)
        .where(
            or_(
                CustomerPortalLink.user_id == user.id,
                CustomerPortalLink.contact_id == contact.id,
            )
        )
        .with_for_update()
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Benutzerkonto oder Kundenkontakt ist bereits verknüpft.",
        )

    link = CustomerPortalLink(
        user_id=user.id,
        contact_id=contact.id,
        created_by_id=principal.user.id,
    )
    db.add(link)
    try:
        db.flush()
        db.add(
            CustomerPortalLinkHistory(
                user_id=user.id,
                contact_id=contact.id,
                actor_id=principal.user.id,
                action="linked",
            )
        )
        add_audit_entry(
            db,
            actor_id=principal.user.id,
            action="customer_portal.linked",
            entity_type="customer_portal_link",
            entity_id=str(link.id),
            ip_address=request.client.host if request.client else None,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Benutzerkonto oder Kundenkontakt ist bereits verknüpft.",
        ) from exc
    return link


@router.delete(
    "/customer-portal/links/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_customer_portal_link(
    request: Request,
    contact_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthPrincipal, Depends(require_permission("customers.portal.manage"))],
) -> Response:
    link = db.scalar(
        select(CustomerPortalLink)
        .where(CustomerPortalLink.contact_id == contact_id)
        .with_for_update()
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Portal-Verknüpfung nicht gefunden.")

    db.add(
        CustomerPortalLinkHistory(
            user_id=link.user_id,
            contact_id=link.contact_id,
            actor_id=principal.user.id,
            action="unlinked",
        )
    )
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="customer_portal.unlinked",
        entity_type="customer_portal_link",
        entity_id=str(link.id),
        ip_address=request.client.host if request.client else None,
    )
    db.delete(link)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
