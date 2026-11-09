from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CustomerPortalAddressRead(BaseModel):
    street: str
    house_number: str
    postal_code: str
    city: str
    country_code: str

    model_config = ConfigDict(from_attributes=True)


class CustomerPortalContactRead(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    responsibility: str | None
    email: str | None
    phone: str | None

    model_config = ConfigDict(from_attributes=True)


class CustomerPortalCustomerRead(BaseModel):
    customer_number: str
    company_name: str
    email: str | None
    phone: str | None
    legal_form: str | None
    website: str | None
    business_address: CustomerPortalAddressRead | None
    billing_address: CustomerPortalAddressRead | None


class CustomerPortalObjectRead(BaseModel):
    id: UUID
    code: str
    name: str
    object_type: str | None
    status: Literal["active", "inactive"]
    operating_hours: str | None
    service_times: str | None
    address: CustomerPortalAddressRead | None


class CustomerPortalMeRead(BaseModel):
    contact: CustomerPortalContactRead
    customer: CustomerPortalCustomerRead
    objects: list[CustomerPortalObjectRead]


class CustomerPortalInvoiceLineRead(BaseModel):
    position: int
    description: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    tax_rate: Decimal
    net_amount: Decimal
    tax_amount: Decimal
    gross_amount: Decimal

    model_config = ConfigDict(from_attributes=True)


class CustomerPortalInvoiceRead(BaseModel):
    id: UUID
    invoice_number: str
    kind: Literal["invoice", "correction", "cancellation"]
    payment_status: Literal["open", "partial", "paid"]
    currency: str
    issued_on: date
    due_on: date
    net_amount: Decimal
    tax_amount: Decimal
    gross_amount: Decimal
    lines: list[CustomerPortalInvoiceLineRead]

    model_config = ConfigDict(from_attributes=True)


class CustomerPortalLinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    contact_id: UUID


class CustomerPortalLinkRead(BaseModel):
    id: UUID
    user_id: UUID
    contact_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
