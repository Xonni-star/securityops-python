from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class CustomerPortalLinkStateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool


class CustomerPortalUserOption(BaseModel):
    id: UUID
    username: str
    full_name: str


class CustomerPortalContactOption(BaseModel):
    id: UUID
    customer_id: UUID
    customer_name: str
    first_name: str
    last_name: str


class CustomerPortalManagementOptions(BaseModel):
    users: list[CustomerPortalUserOption]
    contacts: list[CustomerPortalContactOption]


class CustomerPortalLinkHistoryRead(BaseModel):
    user_id: UUID
    contact_id: UUID
    actor_id: UUID | None
    action: Literal["linked", "unlinked", "activated", "deactivated"]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CustomerPortalAccessEventRead(BaseModel):
    actor_id: UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CustomerPortalDocumentGrantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    version_id: UUID


class CustomerPortalDocumentGrantRead(BaseModel):
    id: UUID
    document_id: UUID
    version_id: UUID
    customer_id: UUID
    granted_by_id: UUID | None
    granted_at: datetime
    revoked_by_id: UUID | None
    revoked_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class CustomerPortalDocumentRead(BaseModel):
    grant_id: UUID
    document_id: UUID
    version_id: UUID
    document_number: str
    title: str
    category: str
    version: int
    file_name: str
    media_type: str
    size_bytes: int
    granted_at: datetime


class CustomerPortalDocumentCandidateRead(BaseModel):
    document_id: UUID
    version_id: UUID
    customer_id: UUID
    customer_name: str
    object_id: UUID | None
    document_number: str
    title: str
    version: int
    file_name: str


class CustomerPortalRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal["request", "question", "complaint"]
    object_id: UUID
    title: str = Field(min_length=1, max_length=200)
    first_message: str = Field(min_length=1, max_length=4000)

    @field_validator("title", "first_message")
    @classmethod
    def trim_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Das Feld darf nicht leer sein.")
        return value


class CustomerPortalRequestMessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=4000)

    @field_validator("body")
    @classmethod
    def trim_body(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Die Nachricht darf nicht leer sein.")
        return value


class CustomerPortalRequestStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["submitted", "in_progress", "waiting_customer", "resolved", "closed"]


class CustomerPortalRequestMessageRead(BaseModel):
    id: UUID
    author_id: UUID | None
    body: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CustomerPortalRequestAttachmentRead(BaseModel):
    id: UUID
    file_name: str
    media_type: str
    size_bytes: int
    uploaded_by_id: UUID | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CustomerPortalRequestStatusEventRead(BaseModel):
    actor_id: UUID | None
    action: str
    old_status: str | None
    new_status: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CustomerPortalRequestRead(BaseModel):
    id: UUID
    category: Literal["request", "question", "complaint"]
    object_id: UUID
    object_name: str
    customer_name: str
    title: str
    status: Literal["submitted", "in_progress", "waiting_customer", "resolved", "closed"]
    created_at: datetime
    updated_at: datetime
    messages: list[CustomerPortalRequestMessageRead]
    attachments: list[CustomerPortalRequestAttachmentRead]
    history: list[CustomerPortalRequestStatusEventRead]
