import hashlib
import json
import unicodedata
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth import AuthPrincipal, add_audit_entry, require_permission
from app.billing_schemas import (
    ArchiveInvoice,
    BillingExportRead,
    BillingPaymentRead,
    BillingRateCreate,
    BillingRateRead,
    DunningUpdate,
    InvoiceCorrectionCreate,
    InvoiceCreate,
    InvoiceRead,
    PaymentCreate,
)
from app.database import get_db
from app.models import (
    BillingExport,
    BillingInvoice,
    BillingInvoiceLine,
    BillingPayment,
    BillingRate,
    Contract,
    Customer,
    TimeEntry,
    TimeEntryCorrection,
    TimeSurchargeCalculation,
)
from app.notifications_service import enqueue_invoice_approved_event

router = APIRouter()
CENT = Decimal("0.01")
QUANTITY = Decimal("0.0001")
EXPORT_VERSION = "securityops-accounting-v1"


def rounded(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def commit_or_conflict(db: Session, message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=message) from exc


def invoice_query():
    return select(BillingInvoice).options(selectinload(BillingInvoice.lines))


def get_invoice(db: Session, invoice_id: UUID, *, lock: bool = False) -> BillingInvoice:
    query = invoice_query().where(BillingInvoice.id == invoice_id)
    if lock:
        query = query.with_for_update()
    invoice = db.scalar(query)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Rechnung nicht gefunden.")
    return invoice


def require_customer(db: Session, customer_id: UUID) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None or customer.archived_at is not None:
        raise HTTPException(status_code=404, detail="Aktiver Kunde nicht gefunden.")
    return customer


def customer_snapshot(customer: Customer) -> dict[str, object]:
    address = customer.billing_address
    return {
        "customer_number": customer.customer_number,
        "company_name": customer.company_name,
        "email": customer.email,
        "billing_address": (
            {
                "street": address.street,
                "house_number": address.house_number,
                "postal_code": address.postal_code,
                "city": address.city,
                "country_code": address.country_code,
            }
            if address
            else None
        ),
    }


def source_time_snapshot(
    db: Session, entry_ids: list[UUID], customer_id: UUID
) -> tuple[Decimal, list[dict[str, object]]]:
    if not entry_ids:
        return Decimal(0), []
    entries = (
        db.scalars(
            select(TimeEntry)
            .where(TimeEntry.id.in_(entry_ids))
            .order_by(TimeEntry.id)
            .options(
                selectinload(TimeEntry.object),
                selectinload(TimeEntry.segments),
                selectinload(TimeEntry.corrections).selectinload(TimeEntryCorrection.segments),
            )
            .with_for_update(of=TimeEntry)
        )
        .unique()
        .all()
    )
    if len(entries) != len(set(entry_ids)):
        raise HTTPException(status_code=422, detail="Eine Zeitbuchung wurde nicht gefunden.")
    total_seconds = 0
    snapshots = []
    for entry in entries:
        if entry.status not in {"approved", "locked"} or entry.ended_at is None:
            raise HTTPException(
                status_code=409,
                detail="Nur freigegebene oder gesperrte Zeitbuchungen sind abrechenbar.",
            )
        if entry.object.customer_id != customer_id:
            raise HTTPException(
                status_code=422, detail="Die Zeitbuchung gehört nicht zum gewählten Kunden."
            )
        approved = [item for item in entry.corrections if item.status == "approved"]
        correction = (
            max(approved, key=lambda item: item.decided_at or item.requested_at)
            if approved
            else None
        )
        segments = correction.segments if correction else entry.segments
        work_seconds = 0
        segment_values = []
        for segment in segments:
            if segment.kind == "work" and segment.ended_at is not None:
                duration = int((segment.ended_at - segment.started_at).total_seconds())
                work_seconds += duration
                segment_values.append(
                    {
                        "position": segment.position,
                        "started_at": segment.started_at.isoformat(),
                        "ended_at": segment.ended_at.isoformat(),
                        "duration_seconds": duration,
                    }
                )
        total_seconds += work_seconds
        surcharge = db.scalar(
            select(TimeSurchargeCalculation)
            .where(TimeSurchargeCalculation.entry_id == entry.id)
            .order_by(TimeSurchargeCalculation.version.desc())
            .limit(1)
        )
        snapshots.append(
            {
                "time_entry_id": str(entry.id),
                "employee_id": str(entry.employee_id),
                "object_id": str(entry.object_id),
                "status": entry.status,
                "started_at": entry.started_at.isoformat(),
                "ended_at": entry.ended_at.isoformat(),
                "approved_correction_id": str(correction.id) if correction else None,
                "segments": segment_values,
                "work_seconds": work_seconds,
                "surcharge_calculation": (
                    {
                        "id": str(surcharge.id),
                        "version": surcharge.version,
                        "rules": surcharge.rule_snapshot,
                        "allocations": surcharge.allocation_snapshot,
                    }
                    if surcharge
                    else None
                ),
            }
        )
    hours = (Decimal(total_seconds) / Decimal(3600)).quantize(QUANTITY, rounding=ROUND_HALF_UP)
    return hours, snapshots


def make_line(
    rate: BillingRate,
    position: int,
    quantity: Decimal,
    description: str,
    *,
    source_ids: list[str] | None = None,
    source_values: list[dict[str, object]] | None = None,
    sign: int = 1,
) -> BillingInvoiceLine:
    quantity = quantity.quantize(QUANTITY, rounding=ROUND_HALF_UP)
    net = rounded(quantity * rate.unit_price) * sign
    tax = rounded(net * rate.tax_rate / Decimal(100))
    return BillingInvoiceLine(
        rate_id=rate.id,
        position=position,
        description=description,
        kind=rate.kind,
        quantity=quantity,
        unit=rate.unit,
        unit_price=rate.unit_price * sign,
        tax_code=rate.tax_code,
        tax_rate=rate.tax_rate,
        net_amount=net,
        tax_amount=tax,
        gross_amount=net + tax,
        inputs_snapshot={
            "rate": {
                "id": str(rate.id),
                "code": rate.code,
                "name": rate.name,
                "kind": rate.kind,
                "unit": rate.unit,
                "unit_price": str(rate.unit_price),
                "tax_code": rate.tax_code,
                "tax_rate": str(rate.tax_rate),
                "currency": rate.currency,
            },
            "quantity": str(quantity),
            "source_time_entry_ids": source_ids or [],
            "source_time_entries": source_values or [],
            "rounding": "ROUND_HALF_UP auf 0,01 je Rechnungsposition",
            "sign": sign,
        },
    )


def invoice_totals(lines: list[BillingInvoiceLine]) -> tuple[Decimal, Decimal, Decimal]:
    net = sum((line.net_amount for line in lines), Decimal(0))
    tax = sum((line.tax_amount for line in lines), Decimal(0))
    return net, tax, net + tax


def save_invoice(
    db: Session,
    *,
    principal: AuthPrincipal,
    request: Request,
    customer: Customer,
    contract_id: UUID | None,
    kind: str,
    issued_on: date,
    due_on: date,
    correction_of_id: UUID | None,
    correction_reason: str | None,
    key: str,
    lines: list[BillingInvoiceLine],
    input_snapshot: dict[str, object],
) -> BillingInvoice:
    currencies = {
        str(line.inputs_snapshot["rate"]["currency"])
        for line in lines
        if isinstance(line.inputs_snapshot.get("rate"), dict)
    }
    if len(currencies) != 1:
        raise HTTPException(
            status_code=422, detail="Alle Rechnungspositionen müssen dieselbe Währung verwenden."
        )
    net, tax, gross = invoice_totals(lines)
    invoice_id = uuid4()
    invoice = BillingInvoice(
        id=invoice_id,
        invoice_number=f"R-{issued_on:%Y}-{invoice_id.hex[:12].upper()}",
        idempotency_key=key,
        customer_id=customer.id,
        contract_id=contract_id,
        kind=kind,
        status="draft",
        payment_status="open",
        dunning_status="none",
        currency=currencies.pop(),
        issued_on=issued_on,
        due_on=due_on,
        correction_of_id=correction_of_id,
        correction_reason=correction_reason,
        customer_snapshot=customer_snapshot(customer),
        inputs_snapshot=input_snapshot,
        net_amount=net,
        tax_amount=tax,
        gross_amount=gross,
        created_by_id=principal.user.id,
        lines=lines,
    )
    db.add(invoice)
    db.flush()
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="billing.invoice.created",
        entity_type="billing_invoice",
        entity_id=str(invoice.id),
        ip_address=request.client.host if request.client else None,
        details={
            "kind": kind,
            "invoice_number": invoice.invoice_number,
            "gross_amount": str(gross),
        },
    )
    return invoice


def build_lines(
    db: Session, line_inputs, customer_id: UUID
) -> tuple[list[BillingInvoiceLine], list[dict[str, object]]]:
    lines = []
    sources_all = []
    source_ids_seen = set()
    for position, item in enumerate(line_inputs, start=1):
        rate = db.scalar(
            select(BillingRate)
            .where(BillingRate.id == item.rate_id, BillingRate.is_active)
            .with_for_update()
        )
        if rate is None:
            raise HTTPException(status_code=422, detail="Ein Preis ist nicht verfügbar.")
        quantity, source_values = item.quantity, []
        if item.source_time_entry_ids:
            if rate.kind != "hourly":
                raise HTTPException(
                    status_code=422, detail="Zeitbuchungen können nur Stundenpositionen belegen."
                )
            if source_ids_seen.intersection(item.source_time_entry_ids):
                raise HTTPException(
                    status_code=422,
                    detail="Eine Zeitbuchung darf nicht mehrfach zugeordnet werden.",
                )
            source_ids_seen.update(item.source_time_entry_ids)
            quantity, source_values = source_time_snapshot(
                db, item.source_time_entry_ids, customer_id
            )
            if quantity <= 0:
                raise HTTPException(
                    status_code=422, detail="Die Zeitbuchungen enthalten keine Arbeitszeit."
                )
        lines.append(
            make_line(
                rate,
                position,
                quantity,
                item.description or rate.name,
                source_ids=[str(value) for value in item.source_time_entry_ids],
                source_values=source_values,
            )
        )
        sources_all.extend(source_values)
    return lines, sources_all


def ensure_time_entries_not_already_billed(db: Session, entry_ids: list[UUID]) -> None:
    if not entry_ids:
        return
    requested = {str(entry_id) for entry_id in entry_ids}
    invoices = db.scalars(select(BillingInvoice).where(BillingInvoice.kind == "invoice")).all()
    already_billed = {
        str(snapshot["time_entry_id"])
        for invoice in invoices
        for snapshot in invoice.inputs_snapshot.get("source_time_entries", [])
        if isinstance(snapshot, dict) and snapshot.get("time_entry_id")
    }
    if requested.intersection(already_billed):
        raise HTTPException(
            status_code=409,
            detail="Eine oder mehrere Zeitbuchungen sind bereits einer Rechnung zugeordnet.",
        )


@router.get("/billing/rates", response_model=list[BillingRateRead])
def list_rates(
    db: Annotated[Session, Depends(get_db)],
    _principal: Annotated[AuthPrincipal, Depends(require_permission("billing.invoices.read"))],
) -> list[BillingRate]:
    return db.scalars(
        select(BillingRate).where(BillingRate.is_active).order_by(BillingRate.code)
    ).all()


@router.post("/billing/rates", response_model=BillingRateRead, status_code=201)
def create_rate(
    request: Request,
    payload: BillingRateCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthPrincipal, Depends(require_permission("billing.rates.manage"))],
) -> BillingRate:
    rate = BillingRate(**payload.model_dump(), created_by_id=principal.user.id)
    db.add(rate)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Der Preisschlüssel ist bereits vergeben."
        ) from exc
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="billing.rate.created",
        entity_type="billing_rate",
        entity_id=str(rate.id),
        ip_address=request.client.host if request.client else None,
        details={"code": rate.code, "kind": rate.kind},
    )
    commit_or_conflict(db, "Der Preisschlüssel ist bereits vergeben.")
    return rate


@router.get("/billing/invoices", response_model=list[InvoiceRead])
def list_invoices(
    db: Annotated[Session, Depends(get_db)],
    _principal: Annotated[AuthPrincipal, Depends(require_permission("billing.invoices.read"))],
    customer_id: UUID | None = None,
    invoice_status: str | None = None,
) -> list[BillingInvoice]:
    query = invoice_query().order_by(
        BillingInvoice.issued_on.desc(), BillingInvoice.created_at.desc()
    )
    if customer_id is not None:
        query = query.where(BillingInvoice.customer_id == customer_id)
    if invoice_status:
        if invoice_status not in {"draft", "approved", "archived"}:
            raise HTTPException(status_code=422, detail="Ungültiger Rechnungsstatus.")
        query = query.where(BillingInvoice.status == invoice_status)
    return db.scalars(query.limit(500)).all()


@router.post("/billing/invoices", response_model=InvoiceRead, status_code=201)
def create_invoice(
    request: Request,
    payload: InvoiceCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthPrincipal, Depends(require_permission("billing.invoices.create"))],
) -> BillingInvoice:
    fingerprint = payload.model_dump(mode="json")
    existing = db.scalar(
        invoice_query().where(BillingInvoice.idempotency_key == payload.idempotency_key)
    )
    if existing is not None:
        if existing.inputs_snapshot.get("request") != fingerprint:
            raise HTTPException(
                status_code=409, detail="Idempotenzschlüssel bereits mit anderen Daten verwendet."
            )
        return existing
    customer = require_customer(db, payload.customer_id)
    if payload.contract_id:
        contract = db.get(Contract, payload.contract_id)
        if (
            contract is None
            or contract.customer_id != customer.id
            or contract.archived_at
            or contract.status != "active"
        ):
            raise HTTPException(
                status_code=422, detail="Der aktive Vertrag gehört nicht zum aktiven Kunden."
            )
    lines, sources = build_lines(db, payload.lines, customer.id)
    ensure_time_entries_not_already_billed(
        db, [entry_id for item in payload.lines for entry_id in item.source_time_entry_ids]
    )
    invoice = save_invoice(
        db,
        principal=principal,
        request=request,
        customer=customer,
        contract_id=payload.contract_id,
        kind="invoice",
        issued_on=payload.issued_on,
        due_on=payload.due_on,
        correction_of_id=None,
        correction_reason=None,
        key=payload.idempotency_key,
        lines=lines,
        input_snapshot={
            "schema_version": 1,
            "request": fingerprint,
            "source_time_entries": sources,
            "tax_handling": "Steuerkennzeichen und -satz sind konfigurierte Eingaben; keine Rechtsprüfung.",
        },
    )
    commit_or_conflict(db, "Rechnungsnummer oder Idempotenzschlüssel bereits vergeben.")
    return get_invoice(db, invoice.id)


@router.post(
    "/billing/invoices/{invoice_id}/corrections", response_model=InvoiceRead, status_code=201
)
def create_correction(
    request: Request,
    invoice_id: UUID,
    payload: InvoiceCorrectionCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthPrincipal, Depends(require_permission("billing.invoices.create"))],
) -> BillingInvoice:
    fingerprint = payload.model_dump(mode="json")
    existing = db.scalar(
        invoice_query().where(BillingInvoice.idempotency_key == payload.idempotency_key)
    )
    if existing is not None:
        if (
            existing.correction_of_id != invoice_id
            or existing.inputs_snapshot.get("request") != fingerprint
        ):
            raise HTTPException(status_code=409, detail="Idempotenzschlüssel bereits vergeben.")
        return existing
    original = get_invoice(db, invoice_id, lock=True)
    if original.kind != "invoice" or original.status not in {"approved", "archived"}:
        raise HTTPException(
            status_code=409, detail="Nur freigegebene Originalrechnungen können korrigiert werden."
        )
    lines = [
        BillingInvoiceLine(
            position=index,
            rate_id=line.rate_id,
            description=f"Storno: {line.description}",
            kind=line.kind,
            quantity=line.quantity,
            unit=line.unit,
            unit_price=-line.unit_price,
            tax_code=line.tax_code,
            tax_rate=line.tax_rate,
            net_amount=-line.net_amount,
            tax_amount=-line.tax_amount,
            gross_amount=-line.gross_amount,
            inputs_snapshot={**line.inputs_snapshot, "reverses_line_id": str(line.id)},
        )
        for index, line in enumerate(original.lines, start=1)
    ]
    replacements, sources = build_lines(db, payload.replacement_lines, original.customer_id)
    for line in replacements:
        line.position += len(lines)
    lines.extend(replacements)
    correction = save_invoice(
        db,
        principal=principal,
        request=request,
        customer=require_customer(db, original.customer_id),
        contract_id=original.contract_id,
        kind="correction" if payload.replacement_lines else "cancellation",
        issued_on=payload.issued_on,
        due_on=payload.due_on,
        correction_of_id=original.id,
        correction_reason=payload.reason,
        key=payload.idempotency_key,
        lines=lines,
        input_snapshot={
            "schema_version": 1,
            "request": fingerprint,
            "reversed_invoice_id": str(original.id),
            "source_time_entries": sources,
            "tax_handling": "Steuerkennzeichen und -satz sind konfigurierte Eingaben; keine Rechtsprüfung.",
        },
    )
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="billing.invoice.correction_created",
        entity_type="billing_invoice",
        entity_id=str(correction.id),
        ip_address=request.client.host if request.client else None,
        details={"corrects_invoice_id": str(original.id), "reason": payload.reason},
    )
    commit_or_conflict(db, "Korrekturbeleg konnte nicht idempotent gespeichert werden.")
    return get_invoice(db, correction.id)


@router.post("/billing/invoices/{invoice_id}/approve", response_model=InvoiceRead)
def approve_invoice(
    request: Request,
    invoice_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthPrincipal, Depends(require_permission("billing.invoices.approve"))],
) -> BillingInvoice:
    invoice = get_invoice(db, invoice_id, lock=True)
    if invoice.status != "draft":
        raise HTTPException(
            status_code=409, detail="Nur Rechnungsentwürfe können freigegeben werden."
        )
    invoice.status = "approved"
    invoice.approved_by_id = principal.user.id
    invoice.approved_at = datetime.now(UTC)
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="billing.invoice.approved",
        entity_type="billing_invoice",
        entity_id=str(invoice.id),
        ip_address=request.client.host if request.client else None,
        details={
            "invoice_number": invoice.invoice_number,
            "gross_amount": str(invoice.gross_amount),
        },
    )
    enqueue_invoice_approved_event(db, invoice)
    commit_or_conflict(db, "Rechnung konnte nicht freigegeben werden.")
    return get_invoice(db, invoice.id)


@router.post("/billing/invoices/{invoice_id}/archive", response_model=InvoiceRead)
def archive_invoice(
    request: Request,
    invoice_id: UUID,
    payload: ArchiveInvoice,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthPrincipal, Depends(require_permission("billing.invoices.archive"))],
) -> BillingInvoice:
    invoice = get_invoice(db, invoice_id, lock=True)
    if invoice.status != "approved":
        raise HTTPException(
            status_code=409, detail="Nur freigegebene Rechnungen können archiviert werden."
        )
    invoice.status = "archived"
    invoice.archived_at = datetime.now(UTC)
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="billing.invoice.archived",
        entity_type="billing_invoice",
        entity_id=str(invoice.id),
        ip_address=request.client.host if request.client else None,
        details={"reason": payload.reason},
    )
    commit_or_conflict(db, "Rechnung konnte nicht archiviert werden.")
    return get_invoice(db, invoice.id)


@router.get("/billing/invoices/{invoice_id}/payments", response_model=list[BillingPaymentRead])
def list_payments(
    invoice_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _principal: Annotated[AuthPrincipal, Depends(require_permission("billing.invoices.read"))],
) -> list[BillingPayment]:
    get_invoice(db, invoice_id)
    return db.scalars(
        select(BillingPayment)
        .where(BillingPayment.invoice_id == invoice_id)
        .order_by(BillingPayment.paid_on)
    ).all()


@router.post(
    "/billing/invoices/{invoice_id}/payments", response_model=BillingPaymentRead, status_code=201
)
def add_payment(
    request: Request,
    invoice_id: UUID,
    payload: PaymentCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthPrincipal, Depends(require_permission("billing.payments.manage"))],
) -> BillingPayment:
    invoice = get_invoice(db, invoice_id, lock=True)
    existing = db.scalar(
        select(BillingPayment).where(
            BillingPayment.invoice_id == invoice.id,
            BillingPayment.idempotency_key == payload.idempotency_key,
        )
    )
    if existing:
        if (
            existing.amount != payload.amount
            or existing.paid_on != payload.paid_on
            or existing.reference != payload.reference
        ):
            raise HTTPException(
                status_code=409, detail="Idempotenzschlüssel mit abweichender Zahlung verwendet."
            )
        return existing
    if invoice.status not in {"approved", "archived"} or invoice.gross_amount <= 0:
        raise HTTPException(
            status_code=409,
            detail="Zahlungen sind nur für freigegebene positive Rechnungen möglich.",
        )
    paid = db.scalar(
        select(func.coalesce(func.sum(BillingPayment.amount), 0)).where(
            BillingPayment.invoice_id == invoice.id
        )
    )
    if Decimal(paid) + payload.amount > invoice.gross_amount:
        raise HTTPException(
            status_code=422, detail="Die Zahlung übersteigt den offenen Rechnungsbetrag."
        )
    payment = BillingPayment(
        invoice_id=invoice.id,
        idempotency_key=payload.idempotency_key,
        amount=payload.amount,
        paid_on=payload.paid_on,
        reference=payload.reference,
        created_by_id=principal.user.id,
    )
    db.add(payment)
    db.flush()
    total_paid = Decimal(paid) + payload.amount
    invoice.payment_status = "paid" if total_paid == invoice.gross_amount else "partial"
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="billing.payment.recorded",
        entity_type="billing_invoice",
        entity_id=str(invoice.id),
        ip_address=request.client.host if request.client else None,
        details={"payment_id": str(payment.id), "amount": str(payment.amount)},
    )
    commit_or_conflict(db, "Zahlung konnte nicht idempotent gespeichert werden.")
    return payment


@router.patch("/billing/invoices/{invoice_id}/dunning", response_model=InvoiceRead)
def update_dunning(
    request: Request,
    invoice_id: UUID,
    payload: DunningUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthPrincipal, Depends(require_permission("billing.payments.manage"))],
) -> BillingInvoice:
    invoice = get_invoice(db, invoice_id, lock=True)
    if invoice.status not in {"approved", "archived"} or invoice.payment_status == "paid":
        raise HTTPException(
            status_code=409, detail="Für diese Rechnung kann kein Mahnstatus gesetzt werden."
        )
    invoice.dunning_status = payload.status
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="billing.dunning.updated",
        entity_type="billing_invoice",
        entity_id=str(invoice.id),
        ip_address=request.client.host if request.client else None,
        details={"status": payload.status, "note": payload.note},
    )
    commit_or_conflict(db, "Mahnstatus konnte nicht gespeichert werden.")
    return get_invoice(db, invoice.id)


def export_payload(invoice: BillingInvoice) -> dict[str, object]:
    return {
        "schema_version": EXPORT_VERSION,
        "invoice_number": invoice.invoice_number,
        "kind": invoice.kind,
        "issued_on": invoice.issued_on.isoformat(),
        "due_on": invoice.due_on.isoformat(),
        "currency": invoice.currency,
        "customer": invoice.customer_snapshot,
        "lines": [
            {
                "position": line.position,
                "description": line.description,
                "quantity": str(line.quantity),
                "unit": line.unit,
                "unit_price": str(line.unit_price),
                "tax_code": line.tax_code,
                "tax_rate": str(line.tax_rate),
                "net_amount": str(line.net_amount),
                "tax_amount": str(line.tax_amount),
                "gross_amount": str(line.gross_amount),
            }
            for line in invoice.lines
        ],
        "totals": {
            "currency": invoice.currency,
            "net_amount": str(invoice.net_amount),
            "tax_amount": str(invoice.tax_amount),
            "gross_amount": str(invoice.gross_amount),
        },
        "payment_status": invoice.payment_status,
        "dunning_status": invoice.dunning_status,
    }


@router.post(
    "/billing/invoices/{invoice_id}/exports", response_model=BillingExportRead, status_code=201
)
def export_invoice(
    request: Request,
    invoice_id: UUID,
    idempotency_key: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthPrincipal, Depends(require_permission("billing.exports.create"))],
) -> BillingExport:
    if (
        len(idempotency_key) < 8
        or len(idempotency_key) > 100
        or not all(char.isalnum() or char in "._:-" for char in idempotency_key)
    ):
        raise HTTPException(status_code=422, detail="Ungültiger Idempotenzschlüssel.")
    invoice = get_invoice(db, invoice_id, lock=True)
    if invoice.status not in {"approved", "archived"}:
        raise HTTPException(
            status_code=409, detail="Nur freigegebene Rechnungen können exportiert werden."
        )
    existing = db.scalar(
        select(BillingExport).where(
            BillingExport.invoice_id == invoice.id,
            BillingExport.format_version == EXPORT_VERSION,
        )
    )
    if existing:
        if existing.idempotency_key != idempotency_key:
            raise HTTPException(
                status_code=409,
                detail="Für diese Rechnung existiert bereits ein Export dieser Version.",
            )
        return existing
    payload = export_payload(invoice)
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    export = BillingExport(
        invoice_id=invoice.id,
        format_version=EXPORT_VERSION,
        idempotency_key=idempotency_key,
        payload=payload,
        payload_sha256=digest,
        created_by_id=principal.user.id,
    )
    db.add(export)
    db.flush()
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="billing.invoice.exported",
        entity_type="billing_invoice",
        entity_id=str(invoice.id),
        ip_address=request.client.host if request.client else None,
        details={"format_version": EXPORT_VERSION, "payload_sha256": digest},
    )
    commit_or_conflict(db, "Buchhaltungsexport wurde parallel oder bereits erzeugt.")
    return export


def build_pdf(invoice: BillingInvoice) -> bytes:
    def safe_text(value: object) -> str:
        text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    customer = invoice.customer_snapshot
    rows = [
        f"Rechnung {invoice.invoice_number}",
        f"Kunde: {customer.get('company_name', '')} ({customer.get('customer_number', '')})",
        f"Rechnungsdatum: {invoice.issued_on.isoformat()}    Faellig: {invoice.due_on.isoformat()}",
        "",
    ]
    address = customer.get("billing_address")
    if isinstance(address, dict):
        rows.append(
            f"{address.get('street', '')} {address.get('house_number', '')}, "
            f"{address.get('postal_code', '')} {address.get('city', '')}"
        )
    rows.extend(
        f"{line.position}. {line.description[:100]} | {line.quantity} {line.unit} x "
        f"{line.unit_price} | Netto {line.net_amount} | {line.tax_code} {line.tax_rate}%: "
        f"{line.tax_amount} | Brutto {line.gross_amount} {invoice.currency}"
        for line in invoice.lines
    )
    rows.extend(
        [
            "",
            f"Summe netto: {invoice.net_amount} {invoice.currency}",
            f"Steuerbetrag (konfiguriert): {invoice.tax_amount} {invoice.currency}",
            f"Gesamtbetrag: {invoice.gross_amount} {invoice.currency}",
            "Steuerwerte sind konfigurierte Eingaben; keine Rechts- oder Steuerpruefung.",
        ]
    )
    commands = ["BT", "/F1 10 Tf", "50 790 Td"]
    for index, row in enumerate(rows):
        if index:
            commands.append("0 -16 Td")
        commands.append(f"({safe_text(row)}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, content in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode() + content + b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return bytes(pdf)


@router.get("/billing/invoices/{invoice_id}/pdf")
def download_invoice_pdf(
    request: Request,
    invoice_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthPrincipal, Depends(require_permission("billing.invoices.read"))],
) -> Response:
    invoice = get_invoice(db, invoice_id)
    if invoice.status not in {"approved", "archived"}:
        raise HTTPException(
            status_code=409, detail="PDFs können erst nach Freigabe erzeugt werden."
        )
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="billing.invoice.pdf_downloaded",
        entity_type="billing_invoice",
        entity_id=str(invoice.id),
        ip_address=request.client.host if request.client else None,
        details={"invoice_number": invoice.invoice_number},
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
