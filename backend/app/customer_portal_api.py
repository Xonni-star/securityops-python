from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Annotated
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth import AuthPrincipal, add_audit_entry, require_permission
from app.billing_api import build_pdf
from app.config import get_settings
from app.customer_portal_schemas import (
    CustomerPortalAccessEventRead,
    CustomerPortalAddressRead,
    CustomerPortalContactOption,
    CustomerPortalContactRead,
    CustomerPortalCustomerRead,
    CustomerPortalDocumentCandidateRead,
    CustomerPortalDocumentGrantCreate,
    CustomerPortalDocumentGrantRead,
    CustomerPortalDocumentRead,
    CustomerPortalInvoiceRead,
    CustomerPortalLinkCreate,
    CustomerPortalLinkHistoryRead,
    CustomerPortalLinkRead,
    CustomerPortalLinkStateUpdate,
    CustomerPortalManagementOptions,
    CustomerPortalMeRead,
    CustomerPortalObjectRead,
    CustomerPortalRequestAttachmentRead,
    CustomerPortalRequestCreate,
    CustomerPortalRequestMessageCreate,
    CustomerPortalRequestMessageRead,
    CustomerPortalRequestRead,
    CustomerPortalRequestStatusUpdate,
    CustomerPortalUserOption,
)
from app.database import get_db
from app.document_storage import (
    ALLOWED_TYPES,
    read_file,
    remove_file,
    sha256_hex,
    store_file,
    validate_upload,
)
from app.models import (
    AuditLog,
    BillingInvoice,
    Customer,
    CustomerContact,
    CustomerPortalDocumentGrant,
    CustomerPortalDocumentGrantHistory,
    CustomerPortalLink,
    CustomerPortalLinkHistory,
    CustomerPortalRequest,
    CustomerPortalRequestAttachment,
    CustomerPortalRequestHistory,
    CustomerPortalRequestMessage,
    Document,
    DocumentVersion,
    Role,
    SecurityObject,
    User,
)
from app.upload_scanning import scan_upload_or_reject

ALLOWED_CUSTOMER_ATTACHMENT_TYPES = {"application/pdf", "image/png", "image/jpeg"}

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
        .where(
            CustomerPortalLink.user_id == principal.user.id,
            CustomerPortalLink.is_active.is_(True),
        )
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


def _visible_portal_documents(
    db: Session, customer_id: UUID
) -> list[tuple[CustomerPortalDocumentGrant, Document, DocumentVersion]]:
    latest_version = (
        select(func.max(DocumentVersion.version))
        .where(DocumentVersion.document_id == Document.id)
        .correlate(Document)
        .scalar_subquery()
    )
    return list(
        db.execute(
            select(CustomerPortalDocumentGrant, Document, DocumentVersion)
            .join(Document, Document.id == CustomerPortalDocumentGrant.document_id)
            .join(DocumentVersion, DocumentVersion.id == CustomerPortalDocumentGrant.version_id)
            .outerjoin(SecurityObject, SecurityObject.id == Document.object_id)
            .where(
                CustomerPortalDocumentGrant.customer_id == customer_id,
                CustomerPortalDocumentGrant.revoked_at.is_(None),
                Document.customer_id == customer_id,
                Document.employee_id.is_(None),
                Document.status == "active",
                Document.archived_at.is_(None),
                DocumentVersion.version == latest_version,
                or_(
                    Document.object_id.is_(None),
                    and_(
                        SecurityObject.customer_id == customer_id,
                        SecurityObject.archived_at.is_(None),
                        SecurityObject.status == "active",
                    ),
                ),
            )
            .order_by(Document.title, Document.document_number)
        ).all()
    )


def _portal_document_read(
    grant: CustomerPortalDocumentGrant, document: Document, version: DocumentVersion
) -> CustomerPortalDocumentRead:
    return CustomerPortalDocumentRead(
        grant_id=grant.id,
        document_id=document.id,
        version_id=version.id,
        document_number=document.document_number,
        title=document.title,
        category=document.category,
        version=version.version,
        file_name=version.file_name,
        media_type=version.media_type,
        size_bytes=version.size_bytes,
        granted_at=grant.granted_at,
    )


def _shareable_document(db: Session, document: Document) -> DocumentVersion:
    if (
        document.customer_id is None
        or document.employee_id is not None
        or document.status != "active"
        or document.archived_at is not None
    ):
        raise HTTPException(
            status_code=422,
            detail="Nur aktive, nicht personenbezogene Kundendokumente können freigegeben werden.",
        )
    if document.object_id is not None:
        object_customer_id = db.scalar(
            select(SecurityObject.customer_id).where(
                SecurityObject.id == document.object_id,
                SecurityObject.archived_at.is_(None),
                SecurityObject.status == "active",
            )
        )
        if object_customer_id != document.customer_id:
            raise HTTPException(
                status_code=422,
                detail="Das Dokument ist keinem aktiven Objekt desselben Kunden zugeordnet.",
            )
    version = db.scalar(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.version.desc())
        .limit(1)
    )
    if version is None:
        raise HTTPException(status_code=409, detail="Für das Dokument liegt keine Datei vor.")
    return version


def _request_read(db: Session, item: CustomerPortalRequest) -> CustomerPortalRequestRead:
    object_name = db.scalar(select(SecurityObject.name).where(SecurityObject.id == item.object_id))
    customer_name = db.scalar(select(Customer.company_name).where(Customer.id == item.customer_id))
    messages = db.scalars(
        select(CustomerPortalRequestMessage)
        .where(CustomerPortalRequestMessage.request_id == item.id)
        .order_by(CustomerPortalRequestMessage.created_at, CustomerPortalRequestMessage.id)
    ).all()
    attachments = db.scalars(
        select(CustomerPortalRequestAttachment)
        .where(CustomerPortalRequestAttachment.request_id == item.id)
        .order_by(
            CustomerPortalRequestAttachment.created_at,
            CustomerPortalRequestAttachment.id,
        )
    ).all()
    history = db.scalars(
        select(CustomerPortalRequestHistory)
        .where(CustomerPortalRequestHistory.request_id == item.id)
        .order_by(CustomerPortalRequestHistory.created_at, CustomerPortalRequestHistory.id)
    ).all()
    return CustomerPortalRequestRead(
        id=item.id,
        category=item.category,
        object_id=item.object_id,
        object_name=object_name or "Unbekanntes Objekt",
        customer_name=customer_name or "Unbekannter Kunde",
        title=item.title,
        status=item.status,
        created_at=item.created_at,
        updated_at=item.updated_at,
        messages=messages,
        attachments=attachments,
        history=history,
    )


def _customer_request(
    db: Session,
    request_id: UUID,
    contact: CustomerContact,
    customer: Customer,
    *,
    for_update: bool = False,
) -> CustomerPortalRequest:
    query = select(CustomerPortalRequest).where(
        CustomerPortalRequest.id == request_id,
        CustomerPortalRequest.customer_id == customer.id,
        CustomerPortalRequest.contact_id == contact.id,
    )
    if for_update:
        query = query.with_for_update()
    item = db.scalar(query)
    if item is None:
        raise HTTPException(status_code=404, detail="Kundenanfrage nicht gefunden.")
    return item


def _add_request_history(
    db: Session,
    item: CustomerPortalRequest,
    actor_id: UUID,
    action: str,
    *,
    old_status: str | None = None,
    new_status: str | None = None,
) -> None:
    db.add(
        CustomerPortalRequestHistory(
            request_id=item.id,
            actor_id=actor_id,
            action=action,
            old_status=old_status,
            new_status=new_status,
        )
    )


def _record_portal_access(
    db: Session,
    request: Request,
    principal: AuthPrincipal,
    *,
    action: str,
    entity_type: str,
    entity_id: UUID | str,
) -> None:
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        ip_address=request.client.host if request.client else None,
    )
    db.commit()


@router.get("/customer-portal/me", response_model=CustomerPortalMeRead)
def get_customer_portal_me(
    response: Response,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthPrincipal, Depends(require_permission("customer_portal.access"))],
) -> CustomerPortalMeRead:
    response.headers["Cache-Control"] = "private, no-store"
    contact, customer = portal_context(db, principal)
    _record_portal_access(
        db,
        request,
        principal,
        action="customer_portal.profile_viewed",
        entity_type="customer",
        entity_id=customer.id,
    )
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
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthPrincipal, Depends(require_permission("customer_portal.access"))],
) -> list[CustomerPortalInvoiceRead]:
    response.headers["Cache-Control"] = "private, no-store"
    _, customer = portal_context(db, principal)
    _record_portal_access(
        db,
        request,
        principal,
        action="customer_portal.invoices_viewed",
        entity_type="customer",
        entity_id=customer.id,
    )
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


@router.get(
    "/customer-portal/documents",
    response_model=list[CustomerPortalDocumentRead],
)
def list_customer_portal_documents(
    response: Response,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthPrincipal, Depends(require_permission("customer_portal.access"))],
) -> list[CustomerPortalDocumentRead]:
    response.headers["Cache-Control"] = "private, no-store"
    _, customer = portal_context(db, principal)
    _record_portal_access(
        db,
        request,
        principal,
        action="customer_portal.documents_viewed",
        entity_type="customer",
        entity_id=customer.id,
    )
    return [
        _portal_document_read(grant, document, version)
        for grant, document, version in _visible_portal_documents(db, customer.id)
    ]


@router.get(
    "/customer-portal/document-grants",
    response_model=list[CustomerPortalDocumentGrantRead],
)
def list_customer_portal_document_grants(
    document_id: UUID,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    _principal: Annotated[
        AuthPrincipal, Depends(require_permission("customer_portal.documents.manage"))
    ],
) -> list[CustomerPortalDocumentGrant]:
    response.headers["Cache-Control"] = "private, no-store"
    return db.scalars(
        select(CustomerPortalDocumentGrant)
        .where(CustomerPortalDocumentGrant.document_id == document_id)
        .order_by(CustomerPortalDocumentGrant.granted_at.desc())
    ).all()


@router.get(
    "/customer-portal/document-candidates",
    response_model=list[CustomerPortalDocumentCandidateRead],
)
def list_customer_portal_document_candidates(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    _principal: Annotated[
        AuthPrincipal, Depends(require_permission("customer_portal.documents.manage"))
    ],
) -> list[CustomerPortalDocumentCandidateRead]:
    response.headers["Cache-Control"] = "private, no-store"
    latest_version = (
        select(func.max(DocumentVersion.version))
        .where(DocumentVersion.document_id == Document.id)
        .correlate(Document)
        .scalar_subquery()
    )
    rows = db.execute(
        select(Document, DocumentVersion, Customer)
        .join(Customer, Customer.id == Document.customer_id)
        .join(DocumentVersion, DocumentVersion.document_id == Document.id)
        .outerjoin(SecurityObject, SecurityObject.id == Document.object_id)
        .where(
            Customer.status == "active",
            Customer.archived_at.is_(None),
            Document.employee_id.is_(None),
            Document.status == "active",
            Document.archived_at.is_(None),
            DocumentVersion.version == latest_version,
            or_(
                Document.object_id.is_(None),
                and_(
                    SecurityObject.customer_id == Document.customer_id,
                    SecurityObject.status == "active",
                    SecurityObject.archived_at.is_(None),
                ),
            ),
        )
        .order_by(Customer.company_name, Document.title, Document.document_number)
    ).all()
    return [
        CustomerPortalDocumentCandidateRead(
            document_id=document.id,
            version_id=version.id,
            customer_id=customer.id,
            customer_name=customer.company_name,
            object_id=document.object_id,
            document_number=document.document_number,
            title=document.title,
            version=version.version,
            file_name=version.file_name,
        )
        for document, version, customer in rows
    ]


@router.post(
    "/customer-portal/document-grants",
    response_model=CustomerPortalDocumentGrantRead,
    status_code=status.HTTP_201_CREATED,
)
def grant_customer_portal_document(
    request: Request,
    payload: CustomerPortalDocumentGrantCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[
        AuthPrincipal, Depends(require_permission("customer_portal.documents.manage"))
    ],
) -> CustomerPortalDocumentGrant:
    document = db.scalar(
        select(Document).where(Document.id == payload.document_id).with_for_update()
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden.")
    version = _shareable_document(db, document)
    if version.id != payload.version_id:
        raise HTTPException(
            status_code=409,
            detail="Nur die aktuelle Dokumentversion kann für Kunden freigegeben werden.",
        )

    grant = CustomerPortalDocumentGrant(
        document_id=document.id,
        version_id=version.id,
        customer_id=document.customer_id,
        granted_by_id=principal.user.id,
    )
    db.add(grant)
    try:
        db.flush()
        db.add(
            CustomerPortalDocumentGrantHistory(
                grant_id=grant.id,
                actor_id=principal.user.id,
                action="granted",
            )
        )
        add_audit_entry(
            db,
            actor_id=principal.user.id,
            action="customer_portal.document_granted",
            entity_type="document",
            entity_id=str(document.id),
            ip_address=request.client.host if request.client else None,
            details={"version": version.version, "customer_id": str(document.customer_id)},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Diese Dokumentversion ist bereits freigegeben."
        ) from exc
    return grant


@router.delete(
    "/customer-portal/document-grants/{grant_id}",
    response_model=CustomerPortalDocumentGrantRead,
)
def revoke_customer_portal_document(
    grant_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[
        AuthPrincipal, Depends(require_permission("customer_portal.documents.manage"))
    ],
) -> CustomerPortalDocumentGrant:
    grant = db.scalar(
        select(CustomerPortalDocumentGrant)
        .where(CustomerPortalDocumentGrant.id == grant_id)
        .with_for_update()
    )
    if grant is None:
        raise HTTPException(status_code=404, detail="Kundenfreigabe nicht gefunden.")
    if grant.revoked_at is not None:
        raise HTTPException(status_code=409, detail="Die Kundenfreigabe wurde bereits widerrufen.")

    grant.revoked_by_id = principal.user.id
    grant.revoked_at = datetime.now(UTC)
    db.add(
        CustomerPortalDocumentGrantHistory(
            grant_id=grant.id,
            actor_id=principal.user.id,
            action="revoked",
        )
    )
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="customer_portal.document_revoked",
        entity_type="document",
        entity_id=str(grant.document_id),
        ip_address=request.client.host if request.client else None,
        details={"version_id": str(grant.version_id), "customer_id": str(grant.customer_id)},
    )
    db.commit()
    return grant


@router.get("/customer-portal/documents/{grant_id}/download")
def download_customer_portal_document(
    grant_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthPrincipal, Depends(require_permission("customer_portal.access"))],
) -> Response:
    response_headers = {"Cache-Control": "private, no-store"}
    contact, customer = portal_context(db, principal)
    visible_documents = _visible_portal_documents(db, customer.id)
    result = next(
        (
            (grant, document, version)
            for grant, document, version in visible_documents
            if grant.id == grant_id
        ),
        None,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Freigegebenes Dokument nicht gefunden.")
    grant, document, version = result
    try:
        content = read_file(version.storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503, detail="Die freigegebene Datei ist nicht verfügbar."
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=503, detail="Der private Dokumentenspeicher ist nicht verfügbar."
        ) from exc

    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="customer_portal.document_downloaded",
        entity_type="document",
        entity_id=str(document.id),
        ip_address=request.client.host if request.client else None,
        details={
            "version": version.version,
            "grant_id": str(grant.id),
            "contact_id": str(contact.id),
        },
    )
    db.commit()
    safe_name = PurePosixPath(version.file_name.replace("\\", "/")).name
    return Response(
        content=content,
        media_type=version.media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_name, safe='')}",
            "Cache-Control": response_headers["Cache-Control"],
            "X-Content-Type-Options": "nosniff",
        },
    )


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


@router.get(
    "/customer-portal/requests",
    response_model=list[CustomerPortalRequestRead],
)
def list_customer_portal_requests(
    response: Response,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthPrincipal, Depends(require_permission("customer_portal.access"))],
) -> list[CustomerPortalRequestRead]:
    response.headers["Cache-Control"] = "private, no-store"
    contact, customer = portal_context(db, principal)
    _record_portal_access(
        db,
        request,
        principal,
        action="customer_portal.requests_viewed",
        entity_type="customer",
        entity_id=customer.id,
    )
    items = db.scalars(
        select(CustomerPortalRequest)
        .where(
            CustomerPortalRequest.customer_id == customer.id,
            CustomerPortalRequest.contact_id == contact.id,
        )
        .order_by(CustomerPortalRequest.updated_at.desc())
        .limit(100)
    ).all()
    return [_request_read(db, item) for item in items]


@router.post(
    "/customer-portal/requests",
    response_model=CustomerPortalRequestRead,
    status_code=status.HTTP_201_CREATED,
)
def create_customer_portal_request(
    payload: CustomerPortalRequestCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthPrincipal, Depends(require_permission("customer_portal.access"))],
) -> CustomerPortalRequestRead:
    contact, customer = portal_context(db, principal)
    obj = db.scalar(
        select(SecurityObject).where(
            SecurityObject.id == payload.object_id,
            SecurityObject.customer_id == customer.id,
            SecurityObject.status == "active",
            SecurityObject.archived_at.is_(None),
        )
    )
    if obj is None:
        raise HTTPException(
            status_code=404, detail="Aktives Objekt des verknüpften Kunden nicht gefunden."
        )
    item = CustomerPortalRequest(
        customer_id=customer.id,
        contact_id=contact.id,
        object_id=obj.id,
        category=payload.category,
        title=payload.title,
    )
    db.add(item)
    db.flush()
    db.add(
        CustomerPortalRequestMessage(
            request_id=item.id, author_id=principal.user.id, body=payload.first_message
        )
    )
    _add_request_history(db, item, principal.user.id, "created", new_status="submitted")
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="customer_portal.request_created",
        entity_type="customer_portal_request",
        entity_id=str(item.id),
        ip_address=request.client.host if request.client else None,
        details={"category": item.category, "object_id": str(item.object_id)},
    )
    db.commit()
    return _request_read(db, item)


@router.get(
    "/customer-portal/requests/{request_id}",
    response_model=CustomerPortalRequestRead,
)
def get_customer_portal_request(
    response: Response,
    request_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthPrincipal, Depends(require_permission("customer_portal.access"))],
) -> CustomerPortalRequestRead:
    response.headers["Cache-Control"] = "private, no-store"
    contact, customer = portal_context(db, principal)
    item = _customer_request(db, request_id, contact, customer)
    _record_portal_access(
        db,
        request,
        principal,
        action="customer_portal.request_viewed",
        entity_type="customer_portal_request",
        entity_id=item.id,
    )
    return _request_read(db, item)


@router.post(
    "/customer-portal/requests/{request_id}/messages",
    response_model=CustomerPortalRequestMessageRead,
    status_code=status.HTTP_201_CREATED,
)
def add_customer_portal_request_message(
    request_id: UUID,
    payload: CustomerPortalRequestMessageCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthPrincipal, Depends(require_permission("customer_portal.access"))],
) -> CustomerPortalRequestMessage:
    contact, customer = portal_context(db, principal)
    item = _customer_request(db, request_id, contact, customer, for_update=True)
    message = CustomerPortalRequestMessage(
        request_id=item.id,
        author_id=principal.user.id,
        body=payload.body,
    )
    db.add(message)
    item.updated_at = datetime.now(UTC)
    _add_request_history(db, item, principal.user.id, "message_added")
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="customer_portal.request_message_added",
        entity_type="customer_portal_request",
        entity_id=str(item.id),
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return message


@router.post(
    "/customer-portal/requests/{request_id}/attachments",
    response_model=CustomerPortalRequestAttachmentRead,
    status_code=status.HTTP_201_CREATED,
)
def upload_customer_portal_request_attachment(
    request_id: UUID,
    request: Request,
    file: Annotated[UploadFile, File()],
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthPrincipal, Depends(require_permission("customer_portal.access"))],
) -> CustomerPortalRequestAttachment:
    contact, customer = portal_context(db, principal)
    item = _customer_request(db, request_id, contact, customer, for_update=True)
    configured_limit = get_settings().document_max_upload_bytes
    if configured_limit <= 0:
        raise RuntimeError("DOCUMENT_MAX_UPLOAD_BYTES muss größer als 0 sein.")
    maximum = min(configured_limit, 10 * 1024 * 1024)
    if file.size is not None and file.size > maximum:
        raise HTTPException(status_code=413, detail="Die Datei überschreitet das Limit von 10 MiB.")
    content = file.file.read(maximum + 1)
    if len(content) > maximum:
        raise HTTPException(status_code=413, detail="Die Datei überschreitet das Limit von 10 MiB.")
    safe_name, media_type = validate_upload(file.filename, file.content_type, content)
    if (
        media_type not in ALLOWED_CUSTOMER_ATTACHMENT_TYPES
        or media_type not in ALLOWED_TYPES.values()
    ):
        raise HTTPException(
            status_code=415,
            detail="Für Kundenanhänge sind nur PDF-, PNG- und JPEG-Dateien zugelassen.",
        )
    scan_upload_or_reject(
        db,
        request,
        content=content,
        actor_id=principal.user.id,
        surface="customer_portal_request",
    )
    storage_key = uuid4().hex
    attachment = CustomerPortalRequestAttachment(
        request_id=item.id,
        storage_key=storage_key,
        file_name=safe_name,
        media_type=media_type,
        size_bytes=len(content),
        sha256=sha256_hex(content),
        uploaded_by_id=principal.user.id,
    )
    db.add(attachment)
    item.updated_at = datetime.now(UTC)
    _add_request_history(db, item, principal.user.id, "attachment_added")
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="customer_portal.request_attachment_added",
        entity_type="customer_portal_request",
        entity_id=str(item.id),
        ip_address=request.client.host if request.client else None,
        details={"size_bytes": len(content), "media_type": media_type},
    )
    stored = False
    try:
        store_file(storage_key, content)
        stored = True
        db.commit()
    except OSError as exc:
        db.rollback()
        if stored:
            remove_file(storage_key)
        raise HTTPException(
            status_code=500, detail="Datei konnte nicht sicher gespeichert werden."
        ) from exc
    except Exception:
        db.rollback()
        if stored:
            remove_file(storage_key)
        raise
    return attachment


@router.get(
    "/customer-portal/requests/{request_id}/attachments/{attachment_id}/download",
)
def download_customer_portal_request_attachment(
    request_id: UUID,
    attachment_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthPrincipal, Depends(require_permission("customer_portal.access"))],
) -> Response:
    contact, customer = portal_context(db, principal)
    item = _customer_request(db, request_id, contact, customer)
    attachment = db.scalar(
        select(CustomerPortalRequestAttachment).where(
            CustomerPortalRequestAttachment.id == attachment_id,
            CustomerPortalRequestAttachment.request_id == item.id,
        )
    )
    if attachment is None:
        raise HTTPException(status_code=404, detail="Kundenanhang nicht gefunden.")
    try:
        content = read_file(attachment.storage_key)
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=503, detail="Der private Dateispeicher ist nicht verfügbar."
        ) from exc
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="customer_portal.request_attachment_downloaded",
        entity_type="customer_portal_request",
        entity_id=str(item.id),
        ip_address=request.client.host if request.client else None,
        details={"attachment_id": str(attachment.id)},
    )
    db.commit()
    return Response(
        content=content,
        media_type=attachment.media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(attachment.file_name, safe='')}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/customer-portal/admin/requests",
    response_model=list[CustomerPortalRequestRead],
)
def list_managed_customer_portal_requests(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    _principal: Annotated[
        AuthPrincipal, Depends(require_permission("customer_portal.requests.manage"))
    ],
) -> list[CustomerPortalRequestRead]:
    response.headers["Cache-Control"] = "private, no-store"
    items = db.scalars(
        select(CustomerPortalRequest).order_by(CustomerPortalRequest.updated_at.desc()).limit(500)
    ).all()
    return [_request_read(db, item) for item in items]


@router.get(
    "/customer-portal/admin/requests/{request_id}",
    response_model=CustomerPortalRequestRead,
)
def get_managed_customer_portal_request(
    response: Response,
    request_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _principal: Annotated[
        AuthPrincipal, Depends(require_permission("customer_portal.requests.manage"))
    ],
) -> CustomerPortalRequestRead:
    response.headers["Cache-Control"] = "private, no-store"
    item = db.get(CustomerPortalRequest, request_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Kundenanfrage nicht gefunden.")
    return _request_read(db, item)


@router.post(
    "/customer-portal/admin/requests/{request_id}/messages",
    response_model=CustomerPortalRequestMessageRead,
    status_code=status.HTTP_201_CREATED,
)
def add_managed_customer_portal_request_message(
    request_id: UUID,
    payload: CustomerPortalRequestMessageCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[
        AuthPrincipal, Depends(require_permission("customer_portal.requests.manage"))
    ],
) -> CustomerPortalRequestMessage:
    item = db.scalar(
        select(CustomerPortalRequest)
        .where(CustomerPortalRequest.id == request_id)
        .with_for_update()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Kundenanfrage nicht gefunden.")
    message = CustomerPortalRequestMessage(
        request_id=item.id,
        author_id=principal.user.id,
        body=payload.body,
    )
    db.add(message)
    item.updated_at = datetime.now(UTC)
    _add_request_history(db, item, principal.user.id, "message_added")
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="customer_portal.request_message_added",
        entity_type="customer_portal_request",
        entity_id=str(item.id),
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return message


@router.patch(
    "/customer-portal/admin/requests/{request_id}/status",
    response_model=CustomerPortalRequestRead,
)
def update_managed_customer_portal_request_status(
    request_id: UUID,
    payload: CustomerPortalRequestStatusUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[
        AuthPrincipal, Depends(require_permission("customer_portal.requests.manage"))
    ],
) -> CustomerPortalRequestRead:
    item = db.scalar(
        select(CustomerPortalRequest)
        .where(CustomerPortalRequest.id == request_id)
        .with_for_update()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Kundenanfrage nicht gefunden.")
    if item.status != payload.status:
        old_status = item.status
        item.status = payload.status
        item.updated_at = datetime.now(UTC)
        _add_request_history(
            db,
            item,
            principal.user.id,
            "status_changed",
            old_status=old_status,
            new_status=payload.status,
        )
        add_audit_entry(
            db,
            actor_id=principal.user.id,
            action="customer_portal.request_status_changed",
            entity_type="customer_portal_request",
            entity_id=str(item.id),
            ip_address=request.client.host if request.client else None,
            details={"old_status": old_status, "new_status": payload.status},
        )
        db.commit()
    return _request_read(db, item)


@router.get(
    "/customer-portal/admin/requests/{request_id}/attachments/{attachment_id}/download",
)
def download_managed_customer_portal_request_attachment(
    request_id: UUID,
    attachment_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[
        AuthPrincipal, Depends(require_permission("customer_portal.requests.manage"))
    ],
) -> Response:
    item = db.get(CustomerPortalRequest, request_id)
    attachment = db.scalar(
        select(CustomerPortalRequestAttachment).where(
            CustomerPortalRequestAttachment.id == attachment_id,
            CustomerPortalRequestAttachment.request_id == request_id,
        )
    )
    if item is None or attachment is None:
        raise HTTPException(status_code=404, detail="Kundenanhang nicht gefunden.")
    try:
        content = read_file(attachment.storage_key)
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=503, detail="Der private Dateispeicher ist nicht verfügbar."
        ) from exc
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="customer_portal.request_attachment_downloaded",
        entity_type="customer_portal_request",
        entity_id=str(item.id),
        ip_address=request.client.host if request.client else None,
        details={"attachment_id": str(attachment.id)},
    )
    db.commit()
    return Response(
        content=content,
        media_type=attachment.media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(attachment.file_name, safe='')}",
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


@router.get(
    "/customer-portal/management-options",
    response_model=CustomerPortalManagementOptions,
)
def customer_portal_management_options(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    _principal: Annotated[AuthPrincipal, Depends(require_permission("customers.portal.manage"))],
) -> CustomerPortalManagementOptions:
    response.headers["Cache-Control"] = "private, no-store"
    users = db.scalars(
        select(User)
        .options(selectinload(User.roles))
        .where(User.is_active.is_(True))
        .order_by(User.username)
    ).all()
    contacts = db.execute(
        select(CustomerContact, Customer)
        .join(Customer, Customer.id == CustomerContact.customer_id)
        .where(Customer.archived_at.is_(None), Customer.status == "active")
        .order_by(Customer.company_name, CustomerContact.last_name, CustomerContact.first_name)
    ).all()
    return CustomerPortalManagementOptions(
        users=[
            CustomerPortalUserOption(
                id=user.id,
                username=user.username,
                full_name=user.full_name,
            )
            for user in users
            if [role.code for role in user.roles] == ["customer_portal"]
        ],
        contacts=[
            CustomerPortalContactOption(
                id=contact.id,
                customer_id=customer.id,
                customer_name=customer.company_name,
                first_name=contact.first_name,
                last_name=contact.last_name,
            )
            for contact, customer in contacts
        ],
    )


@router.get(
    "/customer-portal/link-history",
    response_model=list[CustomerPortalLinkHistoryRead],
)
def list_customer_portal_link_history(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    _principal: Annotated[AuthPrincipal, Depends(require_permission("customers.portal.manage"))],
) -> list[CustomerPortalLinkHistory]:
    response.headers["Cache-Control"] = "private, no-store"
    return db.scalars(
        select(CustomerPortalLinkHistory)
        .order_by(CustomerPortalLinkHistory.created_at.desc())
        .limit(500)
    ).all()


@router.get(
    "/customer-portal/access-history",
    response_model=list[CustomerPortalAccessEventRead],
)
def list_customer_portal_access_history(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    _principal: Annotated[AuthPrincipal, Depends(require_permission("customers.portal.manage"))],
) -> list[AuditLog]:
    response.headers["Cache-Control"] = "private, no-store"
    return db.scalars(
        select(AuditLog)
        .where(AuditLog.action.like("customer_portal.%"))
        .order_by(AuditLog.created_at.desc())
        .limit(500)
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


@router.patch(
    "/customer-portal/links/{contact_id}",
    response_model=CustomerPortalLinkRead,
)
def update_customer_portal_link_state(
    contact_id: UUID,
    payload: CustomerPortalLinkStateUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthPrincipal, Depends(require_permission("customers.portal.manage"))],
) -> CustomerPortalLink:
    link = db.scalar(
        select(CustomerPortalLink)
        .where(CustomerPortalLink.contact_id == contact_id)
        .with_for_update()
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Portal-Verknüpfung nicht gefunden.")
    if link.is_active == payload.is_active:
        return link

    if payload.is_active:
        user = db.scalar(
            select(User)
            .options(selectinload(User.roles))
            .where(User.id == link.user_id)
            .with_for_update()
        )
        contact = db.scalar(
            select(CustomerContact)
            .join(Customer, Customer.id == CustomerContact.customer_id)
            .where(
                CustomerContact.id == link.contact_id,
                Customer.archived_at.is_(None),
                Customer.status == "active",
            )
            .with_for_update()
        )
        if (
            user is None
            or not user.is_active
            or [role.code for role in user.roles] != ["customer_portal"]
            or contact is None
        ):
            raise HTTPException(
                status_code=409,
                detail="Die Verknüpfung kann mit dem aktuellen Konto- oder Kundenstatus nicht aktiviert werden.",
            )

    action = "activated" if payload.is_active else "deactivated"
    link.is_active = payload.is_active
    db.add(
        CustomerPortalLinkHistory(
            user_id=link.user_id,
            contact_id=link.contact_id,
            actor_id=principal.user.id,
            action=action,
        )
    )
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action=f"customer_portal.{action}",
        entity_type="customer_portal_link",
        entity_id=str(link.id),
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return link
