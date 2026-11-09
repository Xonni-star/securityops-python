from datetime import date, datetime, time
from decimal import Decimal
from itertools import pairwise
from typing import Literal
from uuid import UUID

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

CustomerStatus = Literal["active", "inactive", "lead"]
CustomerContractStatus = Literal["none", "draft", "active", "expired", "terminated"]
ObjectStatus = Literal["active", "inactive"]
OWKSEventType = Literal[
    "entry", "handover", "control", "manipulation", "deviation", "missed", "notification"
]
OWKSEventSeverity = Literal["info", "warning", "critical"]
OWKSEventState = Literal["open", "in_progress", "resolved"]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = None
    recovery_code: str | None = None

    @field_validator("mfa_code")
    @classmethod
    def mfa_code_must_have_six_digits(cls, value: str | None) -> str | None:
        if value is not None and (len(value) != 6 or not value.isascii() or not value.isdigit()):
            raise ValueError("Der MFA-Code muss aus sechs Ziffern bestehen.")
        return value

    @field_validator("recovery_code")
    @classmethod
    def recovery_code_must_have_valid_format(cls, value: str | None) -> str | None:
        if value is not None:
            normalized = value.replace("-", "")
            if (
                len(normalized) != 32
                or not normalized.isascii()
                or any(character not in "0123456789ABCDEFabcdef" for character in normalized)
            ):
                raise ValueError("Der Wiederherstellungscode hat ein ungültiges Format.")
        return value

    @model_validator(mode="after")
    def only_one_mfa_factor(self):
        if self.mfa_code and self.recovery_code:
            raise ValueError("MFA-Code und Wiederherstellungscode dürfen nicht kombiniert werden.")
        return self


class UserRead(BaseModel):
    id: UUID
    username: str
    email: EmailStr
    full_name: str
    is_active: bool
    roles: list[str]
    permissions: list[str]


class SessionRead(BaseModel):
    user: UserRead
    password_change_required: bool = False


class UserSessionRead(BaseModel):
    id: UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    absolute_expires_at: datetime
    ip_address: str | None
    user_agent: str | None
    is_current: bool


class MFAStatusRead(BaseModel):
    enabled: bool


class MFASetupRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)


class MFASetupRead(BaseModel):
    secret: str
    otpauth_uri: str


class MFAEnableRequest(BaseModel):
    code: str

    @field_validator("code")
    @classmethod
    def code_must_have_six_digits(cls, value: str) -> str:
        if len(value) != 6 or not value.isascii() or not value.isdigit():
            raise ValueError("Der MFA-Code muss aus sechs Ziffern bestehen.")
        return value


class MFARecoveryCodesRead(BaseModel):
    recovery_codes: list[str]


class MFADisableRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    code: str

    @field_validator("code")
    @classmethod
    def code_must_have_six_digits(cls, value: str) -> str:
        if len(value) != 6 or not value.isascii() or not value.isdigit():
            raise ValueError("Der MFA-Code muss aus sechs Ziffern bestehen.")
        return value


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9._-]+$")
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=12, max_length=128)
    role_codes: list[str] = Field(min_length=1, max_length=10)

    @field_validator("full_name")
    @classmethod
    def full_name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Der Name darf nicht leer sein.")
        return value

    @field_validator("role_codes")
    @classmethod
    def role_codes_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Rollen dürfen nicht doppelt zugewiesen werden.")
        return value


class UserUpdate(BaseModel):
    is_active: bool | None = None
    role_codes: list[str] | None = Field(default=None, min_length=1, max_length=10)

    @field_validator("is_active", "role_codes")
    @classmethod
    def update_values_must_not_be_null(cls, value):
        if value is None:
            raise ValueError("Ein gesetzter Änderungswert darf nicht null sein.")
        return value

    @field_validator("role_codes")
    @classmethod
    def role_codes_must_be_unique(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(set(value)) != len(value):
            raise ValueError("Rollen dürfen nicht doppelt zugewiesen werden.")
        return value


class RoleRead(BaseModel):
    id: UUID
    code: str
    name: str
    description: str
    permissions: list[str]


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class AdminPasswordReset(BaseModel):
    temporary_password: str

    @field_validator("temporary_password")
    @classmethod
    def temporary_password_must_be_long_enough(cls, value: str) -> str:
        if not 12 <= len(value) <= 128:
            raise ValueError("Das Übergangspasswort muss zwischen 12 und 128 Zeichen lang sein.")
        return value


class AuditLogRead(BaseModel):
    id: UUID
    actor_id: UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    ip_address: str | None
    details: dict[str, object]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CustomerCreate(BaseModel):
    company_name: str = Field(min_length=1, max_length=200)
    status: CustomerStatus = "active"
    contract_status: CustomerContractStatus = "none"
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    legal_form: str | None = Field(default=None, max_length=100)
    website: AnyHttpUrl | None = Field(default=None, max_length=2048)
    vat_number: str | None = Field(default=None, max_length=32)
    tax_number: str | None = Field(default=None, max_length=32)
    internal_notes: str | None = Field(default=None, max_length=10000)
    business_address: "CustomerAddressInput | None" = None
    billing_address: "CustomerAddressInput | None" = None

    @field_validator("company_name")
    @classmethod
    def company_name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Der Unternehmensname darf nicht leer sein.")
        return value


class CustomerUpdate(BaseModel):
    company_name: str | None = Field(default=None, min_length=1, max_length=200)
    status: CustomerStatus | None = None
    contract_status: CustomerContractStatus | None = None
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    legal_form: str | None = Field(default=None, max_length=100)
    website: AnyHttpUrl | None = Field(default=None, max_length=2048)
    vat_number: str | None = Field(default=None, max_length=32)
    tax_number: str | None = Field(default=None, max_length=32)
    internal_notes: str | None = Field(default=None, max_length=10000)
    business_address: "CustomerAddressInput | None" = None
    billing_address: "CustomerAddressInput | None" = None

    @field_validator("company_name", "status", "contract_status")
    @classmethod
    def required_update_values_must_not_be_null(cls, value):
        if value is None:
            raise ValueError("Dieses Feld darf nicht null sein.")
        return value

    @field_validator("company_name")
    @classmethod
    def company_name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Der Unternehmensname darf nicht leer sein.")
        return value


class CustomerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_number: str
    company_name: str
    status: CustomerStatus
    contract_status: CustomerContractStatus
    email: str | None
    phone: str | None
    legal_form: str | None
    website: str | None
    vat_number: str | None
    tax_number: str | None
    internal_notes: str | None
    archived_at: datetime | None
    business_address: "CustomerAddressRead | None"
    billing_address: "CustomerAddressRead | None"
    contacts: list["CustomerContactRead"] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CustomerPage(BaseModel):
    items: list[CustomerRead]
    total: int
    limit: int
    offset: int


class DashboardRead(BaseModel):
    customers_total: int
    customers_active: int
    customers_leads: int


class CustomerAddressInput(BaseModel):
    street: str = Field(min_length=1, max_length=160)
    house_number: str = Field(min_length=1, max_length=30)
    postal_code: str = Field(min_length=1, max_length=20)
    city: str = Field(min_length=1, max_length=100)
    country_code: str = Field(default="DE", min_length=2, max_length=2, pattern=r"^[A-Z]{2}$")

    @field_validator("street", "house_number", "postal_code", "city")
    @classmethod
    def address_values_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Adressfelder dürfen nicht leer sein.")
        return value


class CustomerAddressRead(CustomerAddressInput):
    model_config = ConfigDict(from_attributes=True)

    id: UUID


class CustomerContactCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    responsibility: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    is_primary: bool = False

    @field_validator("first_name", "last_name")
    @classmethod
    def contact_names_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name und Nachname dürfen nicht leer sein.")
        return value


class CustomerContactUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    responsibility: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    is_primary: bool | None = None

    @field_validator("first_name", "last_name", "is_primary")
    @classmethod
    def non_nullable_contact_fields_must_not_be_null(cls, value):
        if value is None:
            raise ValueError("Ein gesetzter Änderungswert darf nicht null sein.")
        return value


class CustomerContactRead(CustomerContactCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID


class CustomerHistoryRead(BaseModel):
    id: UUID
    actor_id: UUID | None
    action: str
    changed_fields: list[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ObjectAddressInput(BaseModel):
    street: str = Field(min_length=1, max_length=160)
    house_number: str = Field(min_length=1, max_length=30)
    postal_code: str = Field(min_length=1, max_length=20)
    city: str = Field(min_length=1, max_length=100)
    country_code: str = Field(default="DE", min_length=2, max_length=2, pattern=r"^[A-Z]{2}$")

    @field_validator("street", "house_number", "postal_code", "city")
    @classmethod
    def address_values_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Adressfelder dürfen nicht leer sein.")
        return value


class ObjectAddressRead(ObjectAddressInput):
    model_config = ConfigDict(from_attributes=True)

    id: UUID


class ObjectContactCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    role: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    is_primary: bool = False

    @field_validator("first_name", "last_name")
    @classmethod
    def contact_names_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Vor- und Nachname dürfen nicht leer sein.")
        return value


class ObjectContactUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    role: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    is_primary: bool | None = None

    @field_validator("first_name", "last_name", "is_primary")
    @classmethod
    def non_nullable_contact_fields_must_not_be_null(cls, value):
        if value is None:
            raise ValueError("Ein gesetzter Änderungswert darf nicht null sein.")
        return value


class ObjectContactRead(ObjectContactCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID


class ObjectAssignmentCandidateRead(BaseModel):
    id: UUID
    username: str
    full_name: str


class ObjectAssignmentRead(BaseModel):
    user_id: UUID
    username: str
    full_name: str
    assigned_at: datetime


class ObjectAssignmentUpdate(BaseModel):
    user_ids: list[UUID] = Field(max_length=200)

    @field_validator("user_ids")
    @classmethod
    def assignment_users_must_be_unique(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("Benutzer dürfen einem Objekt nicht doppelt zugewiesen werden.")
        return value


class ObjectSecurityUpdate(BaseModel):
    security_requirements: str | None = Field(default=None, max_length=10000)
    access_information: str | None = Field(default=None, max_length=10000)
    emergency_contact: str | None = Field(default=None, max_length=200)

    @field_validator("security_requirements", "access_information", "emergency_contact")
    @classmethod
    def normalize_sensitive_values(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class ObjectSecurityRead(BaseModel):
    object_id: UUID
    security_requirements: str | None
    access_information: str | None
    emergency_contact: str | None
    updated_at: datetime | None


class ObjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: UUID
    name: str = Field(min_length=1, max_length=200)
    code: str | None = Field(default=None, min_length=1, max_length=50)
    object_type: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=10000)
    status: ObjectStatus = "active"
    operating_hours: str | None = Field(default=None, max_length=200)
    service_times: str | None = Field(default=None, max_length=200)
    staffing_requirements: str | None = Field(default=None, max_length=10000)
    address: ObjectAddressInput | None = None
    contact: ObjectContactCreate | None = None
    contacts: list[ObjectContactCreate] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def at_most_one_primary_contact(self):
        primary_count = sum(contact.is_primary for contact in self.contacts)
        primary_count += int(self.contact.is_primary) if self.contact is not None else 0
        if primary_count > 1:
            raise ValueError("Für ein Objekt darf nur ein Primärkontakt gesetzt sein.")
        return self

    @field_validator("name", "code")
    @classmethod
    def values_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Name und Code dürfen nicht leer sein.")
        return value


class ObjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    code: str | None = Field(default=None, min_length=1, max_length=50)
    object_type: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=10000)
    status: ObjectStatus | None = None
    operating_hours: str | None = Field(default=None, max_length=200)
    service_times: str | None = Field(default=None, max_length=200)
    staffing_requirements: str | None = Field(default=None, max_length=10000)
    address: ObjectAddressInput | None = None

    @field_validator("name", "code")
    @classmethod
    def values_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Name und Code dürfen nicht leer sein.")
        return value


class ObjectHistoryRead(BaseModel):
    id: UUID
    actor_id: UUID | None
    action: str
    changed_fields: list[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ObjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    customer_name: str
    code: str
    name: str
    object_type: str | None
    description: str | None
    status: ObjectStatus
    operating_hours: str | None
    service_times: str | None
    staffing_requirements: str | None
    archived_at: datetime | None
    address: ObjectAddressRead | None
    contacts: list[ObjectContactRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ObjectPage(BaseModel):
    items: list[ObjectRead]
    total: int
    limit: int
    offset: int


KeyStatus = Literal["available", "issued", "lost", "defective", "archived"]
KeyMovementType = Literal["issued", "returned", "lost", "defective", "inventory"]


class PhysicalKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_number: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=500)
    object_id: UUID

    @field_validator("key_number", "description")
    @classmethod
    def key_text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Schlüsselnummer und Beschreibung dürfen nicht leer sein.")
        return value


class PhysicalKeyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=500)

    @field_validator("description")
    @classmethod
    def description_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Die Beschreibung darf nicht leer sein.")
        return value


class PhysicalKeyRead(BaseModel):
    id: UUID
    key_number: str
    description: str
    object_id: UUID
    object_code: str
    object_name: str
    status: KeyStatus
    current_employee_id: UUID | None
    current_employee_name: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PhysicalKeyPage(BaseModel):
    items: list[PhysicalKeyRead]
    total: int
    limit: int
    offset: int


class KeyMovementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    movement_type: KeyMovementType
    employee_id: UUID | None = None
    acknowledged: bool = False
    acknowledgement_note: str | None = Field(default=None, max_length=2000)
    note: str | None = Field(default=None, max_length=5000)

    @field_validator("acknowledgement_note", "note")
    @classmethod
    def movement_notes_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def issue_requires_employee_acknowledgement(self):
        if self.movement_type == "issued":
            if self.employee_id is None:
                raise ValueError("Für eine Ausgabe muss ein Mitarbeiter gewählt werden.")
            if not self.acknowledged:
                raise ValueError("Die Empfangsquittierung muss bestätigt werden.")
        elif self.employee_id is not None or self.acknowledged or self.acknowledgement_note:
            raise ValueError(
                "Mitarbeiter- und Quittierungsangaben sind nur bei einer Ausgabe zulässig."
            )
        return self


class KeyMovementRead(BaseModel):
    id: UUID
    key_id: UUID
    key_number: str
    object_id: UUID
    employee_id: UUID | None
    employee_name: str | None
    actor_id: UUID
    actor_name: str
    movement_type: KeyMovementType
    key_status_after: Literal["available", "issued", "lost", "defective"]
    acknowledged_at: datetime | None
    acknowledgement_note: str | None
    note: str | None
    created_at: datetime


class KeyMovementPage(BaseModel):
    items: list[KeyMovementRead]
    total: int
    limit: int
    offset: int


class KeyEmployeeCandidate(BaseModel):
    id: UUID
    employee_number: str
    full_name: str


class KeyObjectCandidate(BaseModel):
    id: UUID
    code: str
    name: str


InventoryCategory = Literal[
    "access_media",
    "radio",
    "smartphone",
    "tablet",
    "computer",
    "clothing",
    "safety_equipment",
    "vehicle",
    "other",
]
InventoryCondition = Literal["new", "good", "used", "worn", "defective"]
InventoryStatus = Literal["available", "issued", "maintenance", "lost", "damaged", "archived"]
InventoryEventType = Literal[
    "created",
    "updated",
    "issued",
    "returned",
    "transferred",
    "lost",
    "damaged",
    "maintenance",
    "repair",
    "archived",
]
InventoryActionType = Literal[
    "issued", "returned", "transferred", "lost", "damaged", "maintenance", "repair"
]


class InventoryAssetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_number: str = Field(min_length=1, max_length=80)
    serial_number: str | None = Field(default=None, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    category: InventoryCategory
    condition: InventoryCondition = "good"
    location: str = Field(min_length=1, max_length=200)
    object_id: UUID | None = None

    @field_validator("asset_number", "name", "location")
    @classmethod
    def required_inventory_values_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Inventarnummer, Bezeichnung und Standort dürfen nicht leer sein.")
        return value

    @field_validator("serial_number")
    @classmethod
    def serial_number_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class InventoryAssetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    serial_number: str | None = Field(default=None, max_length=120)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: InventoryCategory | None = None
    condition: InventoryCondition | None = None
    location: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("name", "location")
    @classmethod
    def optional_required_inventory_values_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("Bezeichnung und Standort dürfen nicht null sein.")
        value = value.strip()
        if not value:
            raise ValueError("Bezeichnung und Standort dürfen nicht leer sein.")
        return value

    @field_validator("category", "condition")
    @classmethod
    def inventory_classification_must_not_be_null(cls, value):
        if value is None:
            raise ValueError("Kategorie und Zustand dürfen nicht null sein.")
        return value

    @field_validator("serial_number")
    @classmethod
    def optional_serial_number_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def at_least_one_field_must_be_set(self):
        if not self.model_fields_set:
            raise ValueError("Mindestens ein Inventarfeld muss geändert werden.")
        return self


class InventoryAssetRead(BaseModel):
    id: UUID
    asset_number: str
    serial_number: str | None
    name: str
    category: InventoryCategory
    condition: InventoryCondition
    status: InventoryStatus
    location: str
    object_id: UUID | None
    object_code: str | None
    object_name: str | None
    current_employee_id: UUID | None
    current_employee_name: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class InventoryAssetPage(BaseModel):
    items: list[InventoryAssetRead]
    total: int
    limit: int
    offset: int


class InventoryEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: InventoryActionType
    employee_id: UUID | None = None
    object_id: UUID | None = None
    acknowledged: bool = False
    acknowledgement_note: str | None = Field(default=None, max_length=2000)
    condition: InventoryCondition | None = None
    location: str | None = Field(default=None, min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=5000)

    @field_validator("acknowledgement_note", "note")
    @classmethod
    def inventory_notes_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("location")
    @classmethod
    def optional_location_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Der Standort darf nicht leer sein.")
        return value

    @model_validator(mode="after")
    def validate_action_fields(self):
        if self.event_type in {"issued", "transferred"}:
            if self.employee_id is None:
                raise ValueError("Für Ausgabe und Übergabe muss ein Mitarbeiter gewählt werden.")
            if not self.acknowledged:
                raise ValueError("Die Empfangsquittierung muss bestätigt werden.")
        elif self.employee_id is not None or self.acknowledged or self.acknowledgement_note:
            raise ValueError(
                "Mitarbeiter- und Quittierungsangaben sind nur bei Ausgabe und Übergabe zulässig."
            )
        if self.event_type in {"lost", "damaged", "maintenance", "repair"} and not self.note:
            raise ValueError("Für diese Inventarmeldung ist eine Notiz erforderlich.")
        if self.condition is not None and self.event_type != "repair":
            raise ValueError("Der Zustand darf nur beim Abschluss einer Reparatur gesetzt werden.")
        if "object_id" in self.model_fields_set and self.event_type != "transferred":
            raise ValueError("Das Objekt kann nur bei einer Übergabe geändert werden.")
        return self


class InventoryEventRead(BaseModel):
    id: UUID
    asset_id: UUID
    asset_number: str
    object_id: UUID | None
    object_name: str | None
    from_object_id: UUID | None
    from_object_name: str | None
    to_object_id: UUID | None
    to_object_name: str | None
    from_employee_id: UUID | None
    from_employee_name: str | None
    to_employee_id: UUID | None
    to_employee_name: str | None
    actor_id: UUID
    actor_name: str
    event_type: InventoryEventType
    status_after: InventoryStatus
    condition_after: InventoryCondition
    location_after: str
    acknowledged_at: datetime | None
    acknowledgement_note: str | None
    note: str | None
    created_at: datetime


class InventoryEventPage(BaseModel):
    items: list[InventoryEventRead]
    total: int
    limit: int
    offset: int


class InventoryEmployeeCandidate(BaseModel):
    id: UUID
    employee_number: str
    full_name: str


class InventoryObjectCandidate(BaseModel):
    id: UUID
    code: str
    name: str


EmployeeStatus = Literal["active", "inactive", "leave", "terminated"]


class EmployeeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_number: str = Field(min_length=1, max_length=40)
    user_id: UUID | None = None
    full_name: str = Field(min_length=1, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    job_title: str | None = Field(default=None, max_length=120)
    employment_status: EmployeeStatus = "active"
    hired_on: date
    ended_on: date | None = None
    contract_type: str | None = Field(default=None, max_length=80)
    weekly_hours: Decimal | None = Field(default=None, gt=0, le=168, max_digits=5, decimal_places=2)

    @field_validator("employee_number", "full_name")
    @classmethod
    def required_values_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Personalnummer und Name dürfen nicht leer sein.")
        return value

    @field_validator("phone", "job_title", "contract_type")
    @classmethod
    def optional_values_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def end_date_must_not_precede_hire_date(self):
        if self.ended_on is not None and self.ended_on < self.hired_on:
            raise ValueError("Das Austrittsdatum darf nicht vor dem Eintrittsdatum liegen.")
        return self


class EmployeeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_number: str | None = Field(default=None, min_length=1, max_length=40)
    user_id: UUID | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    job_title: str | None = Field(default=None, max_length=120)
    employment_status: EmployeeStatus | None = None
    hired_on: date | None = None
    ended_on: date | None = None
    contract_type: str | None = Field(default=None, max_length=80)
    weekly_hours: Decimal | None = Field(default=None, gt=0, le=168, max_digits=5, decimal_places=2)

    @field_validator("employee_number", "full_name", "employment_status", "hired_on")
    @classmethod
    def required_values_must_not_be_blank_or_null(cls, value):
        if value is None:
            raise ValueError("Ein gesetzter Änderungswert darf nicht null sein.")
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("Personalnummer und Name dürfen nicht leer sein.")
        return value

    @field_validator("phone", "job_title", "contract_type")
    @classmethod
    def optional_values_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def end_date_must_not_precede_hire_date(self):
        if (
            self.ended_on is not None
            and self.hired_on is not None
            and self.ended_on < self.hired_on
        ):
            raise ValueError("Das Austrittsdatum darf nicht vor dem Eintrittsdatum liegen.")
        return self


class EmployeeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee_number: str
    user_id: UUID | None
    full_name: str
    email: EmailStr | None
    phone: str | None
    job_title: str | None
    employment_status: EmployeeStatus
    hired_on: date
    ended_on: date | None
    contract_type: str | None
    weekly_hours: Decimal | None
    assigned_objects: list[str] = Field(default_factory=list)
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EmployeePage(BaseModel):
    items: list[EmployeeRead]
    total: int
    limit: int
    offset: int


class EmployeeSensitiveUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address: str | None = Field(default=None, max_length=500)
    emergency_contact: str | None = Field(default=None, max_length=300)
    internal_notes: str | None = Field(default=None, max_length=10000)

    @field_validator("address", "emergency_contact", "internal_notes")
    @classmethod
    def normalize_sensitive_values(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class EmployeeSensitiveRead(BaseModel):
    employee_id: UUID
    address: str | None
    emergency_contact: str | None
    internal_notes: str | None
    updated_at: datetime | None


class EmployeeQualificationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    issuer: str | None = Field(default=None, max_length=160)
    valid_from: date | None = None
    expires_on: date | None = None

    @field_validator("category", "name")
    @classmethod
    def required_values_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Kategorie und Bezeichnung dürfen nicht leer sein.")
        return value

    @field_validator("issuer")
    @classmethod
    def optional_issuer_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def expiry_must_not_precede_start(self):
        if (
            self.valid_from is not None
            and self.expires_on is not None
            and self.expires_on < self.valid_from
        ):
            raise ValueError("Das Ablaufdatum darf nicht vor dem Gültigkeitsbeginn liegen.")
        return self


class EmployeeQualificationUpdate(EmployeeQualificationCreate):
    category: str | None = Field(default=None, min_length=1, max_length=80)
    name: str | None = Field(default=None, min_length=1, max_length=160)

    @field_validator("category", "name")
    @classmethod
    def supplied_required_values_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("Ein gesetzter Änderungswert darf nicht null sein.")
        value = value.strip()
        if not value:
            raise ValueError("Kategorie und Bezeichnung dürfen nicht leer sein.")
        return value


class EmployeeQualificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee_id: UUID
    category: str
    name: str
    issuer: str | None
    valid_from: date | None
    expires_on: date | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EmployeeQualificationExpiringRead(EmployeeQualificationRead):
    employee_number: str
    employee_name: str
    days_until_expiry: int


class EmployeeHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_id: UUID | None
    action: str
    changed_fields: list[str]
    created_at: datetime


class EmployeeAccountCandidateRead(BaseModel):
    id: UUID
    username: str
    full_name: str


class EmployeeObjectAssignmentRead(BaseModel):
    object_id: UUID
    object_code: str
    object_name: str
    assigned_at: datetime


class EmployeeObjectCandidateRead(BaseModel):
    object_id: UUID
    object_code: str
    object_name: str


class EmployeeObjectAssignmentHistoryRead(BaseModel):
    id: UUID
    object_id: UUID
    object_code: str
    object_name: str
    action: Literal["assigned", "ended"]
    actor_id: UUID | None
    created_at: datetime


class EmployeeQualificationDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    qualification_id: UUID
    version: int
    file_name: str
    media_type: Literal["application/pdf", "image/jpeg", "image/png"]
    size_bytes: int
    sha256: str
    uploaded_by_id: UUID | None
    created_at: datetime


EmployeeAbsenceType = Literal["vacation", "sick_leave", "other"]
EmployeeAbsenceStatus = Literal["pending", "approved", "rejected"]


class EmployeeAbsenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    absence_type: EmployeeAbsenceType
    starts_on: date
    ends_on: date
    status: EmployeeAbsenceStatus = "pending"

    @model_validator(mode="after")
    def end_date_must_not_precede_start(self):
        if self.ends_on < self.starts_on:
            raise ValueError("Das Abwesenheitsende darf nicht vor dem Beginn liegen.")
        return self


class EmployeeAbsenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    absence_type: EmployeeAbsenceType | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    status: EmployeeAbsenceStatus | None = None

    @field_validator("absence_type", "starts_on", "ends_on", "status")
    @classmethod
    def supplied_values_must_not_be_null(cls, value):
        if value is None:
            raise ValueError("Ein gesetzter Änderungswert darf nicht null sein.")
        return value

    @model_validator(mode="after")
    def end_date_must_not_precede_start(self):
        if (
            self.starts_on is not None
            and self.ends_on is not None
            and self.ends_on < self.starts_on
        ):
            raise ValueError("Das Abwesenheitsende darf nicht vor dem Beginn liegen.")
        return self


class EmployeeAbsenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee_id: UUID
    absence_type: EmployeeAbsenceType
    starts_on: date
    ends_on: date
    status: EmployeeAbsenceStatus
    created_by_id: UUID | None
    created_at: datetime
    updated_at: datetime


class EmployeeAvailabilityWindowInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weekday: int = Field(ge=0, le=6)
    starts_at: time
    ends_at: time

    @field_validator("starts_at", "ends_at")
    @classmethod
    def window_times_must_not_have_time_zones(cls, value: time) -> time:
        if value.tzinfo is not None and value.utcoffset() is not None:
            raise ValueError("Verfügbarkeitszeiten dürfen keinen UTC-Offset enthalten.")
        return value

    @model_validator(mode="after")
    def end_must_follow_start(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("Das Ende des Verfügbarkeitsfensters muss nach dem Beginn liegen.")
        return self


class EmployeeAvailabilityWindowRead(EmployeeAvailabilityWindowInput):
    id: UUID
    employee_id: UUID

    model_config = ConfigDict(from_attributes=True)


class EmployeeAvailabilityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    windows: list[EmployeeAvailabilityWindowInput] = Field(max_length=70)

    @model_validator(mode="after")
    def windows_must_not_overlap(self):
        by_weekday: dict[int, list[EmployeeAvailabilityWindowInput]] = {}
        for window in self.windows:
            by_weekday.setdefault(window.weekday, []).append(window)
        for windows in by_weekday.values():
            windows.sort(key=lambda item: item.starts_at)
            if any(left.ends_at > right.starts_at for left, right in pairwise(windows)):
                raise ValueError(
                    "Verfügbarkeitsfenster desselben Wochentags dürfen sich nicht überschneiden."
                )
        return self


ScheduleAvailabilityRequestKind = Literal["preferred", "blocked"]
ScheduleAvailabilityRequestStatus = Literal["open", "accepted", "rejected"]


class ScheduleAvailabilityRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: UUID | None = None
    kind: ScheduleAvailabilityRequestKind
    starts_at_local: datetime
    ends_at_local: datetime
    starts_at_fold: int = Field(default=0, ge=0, le=1)
    ends_at_fold: int = Field(default=0, ge=0, le=1)

    @field_validator("starts_at_local", "ends_at_local")
    @classmethod
    def local_times_must_not_have_an_offset(cls, value: datetime) -> datetime:
        if value.tzinfo is not None and value.utcoffset() is not None:
            raise ValueError("Lokale Wunsch- und Sperrzeiten dürfen keinen UTC-Offset enthalten.")
        return value

    @model_validator(mode="after")
    def end_must_follow_start(self):
        if self.ends_at_local <= self.starts_at_local:
            raise ValueError("Das Ende des Zeitraums muss nach dem Beginn liegen.")
        return self


class ScheduleAvailabilityRequestUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted", "rejected"]


class ScheduleAvailabilityRequestRead(BaseModel):
    id: UUID
    employee_id: UUID
    employee_name: str
    employee_number: str
    kind: ScheduleAvailabilityRequestKind
    starts_at: datetime
    ends_at: datetime
    time_zone: str
    status: ScheduleAvailabilityRequestStatus
    conflicting_shift_ids: list[UUID]
    created_by_id: UUID | None
    reviewed_by_id: UUID | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


ScheduleReplacementReason = Literal[
    "short_notice",
    "schedule_change",
    "employee_request",
    "qualification",
    "other",
]


class ScheduleShiftReplacementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: UUID
    reason: ScheduleReplacementReason


class ScheduleSettingsRead(BaseModel):
    time_zone: str
    minimum_rest_hours: int
    updated_at: datetime


class ScheduleSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time_zone: str = Field(min_length=1, max_length=80)
    minimum_rest_hours: int = Field(ge=0, le=168)

    @field_validator("time_zone")
    @classmethod
    def time_zone_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Die Zeitzone darf nicht leer sein.")
        return value


class ScheduleShiftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: UUID
    object_id: UUID
    starts_at_local: datetime
    ends_at_local: datetime
    starts_at_fold: int = Field(default=0, ge=0, le=1)
    ends_at_fold: int = Field(default=0, ge=0, le=1)
    break_minutes: int = Field(default=0, ge=0, le=1440)
    required_qualification: str | None = Field(default=None, max_length=160)

    @field_validator("starts_at_local", "ends_at_local")
    @classmethod
    def local_times_must_not_have_an_offset(cls, value: datetime) -> datetime:
        if value.tzinfo is not None and value.utcoffset() is not None:
            raise ValueError("Lokale Dienstzeiten dürfen keinen UTC-Offset enthalten.")
        return value

    @field_validator("required_qualification")
    @classmethod
    def optional_text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def end_must_follow_start(self):
        if self.ends_at_local <= self.starts_at_local:
            raise ValueError("Das Dienstende muss nach dem Dienstbeginn liegen.")
        return self


class ScheduleShiftUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: UUID | None = None
    object_id: UUID | None = None
    starts_at_local: datetime | None = None
    ends_at_local: datetime | None = None
    starts_at_fold: int | None = Field(default=None, ge=0, le=1)
    ends_at_fold: int | None = Field(default=None, ge=0, le=1)
    break_minutes: int | None = Field(default=None, ge=0, le=1440)
    required_qualification: str | None = Field(default=None, max_length=160)

    @field_validator(
        "employee_id",
        "object_id",
        "starts_at_local",
        "ends_at_local",
        "starts_at_fold",
        "ends_at_fold",
        "break_minutes",
    )
    @classmethod
    def supplied_update_values_must_not_be_null(cls, value):
        if value is None:
            raise ValueError("Ein gesetzter Änderungswert darf nicht null sein.")
        return value

    @field_validator("starts_at_local", "ends_at_local")
    @classmethod
    def local_times_must_not_have_an_offset(cls, value: datetime | None):
        if value is not None and value.tzinfo is not None and value.utcoffset() is not None:
            raise ValueError("Lokale Dienstzeiten dürfen keinen UTC-Offset enthalten.")
        return value

    @field_validator("required_qualification")
    @classmethod
    def optional_text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def supplied_end_must_follow_start(self):
        if (
            self.starts_at_local is not None
            and self.ends_at_local is not None
            and self.ends_at_local <= self.starts_at_local
        ):
            raise ValueError("Das Dienstende muss nach dem Dienstbeginn liegen.")
        return self


class ScheduleShiftRead(BaseModel):
    id: UUID
    employee_id: UUID
    employee_number: str
    employee_name: str
    object_id: UUID
    object_code: str
    object_name: str
    starts_at: datetime
    ends_at: datetime
    time_zone: str
    break_minutes: int
    required_qualification: str | None
    status: Literal["draft", "published", "cancelled"]
    created_by_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ScheduleConflictRead(BaseModel):
    code: str
    message: str


class ScheduleShiftHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_id: UUID | None
    action: str
    changed_fields: list[str]
    details: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


TimeEntryStatus = Literal[
    "open", "submitted", "approved", "rejected", "correction_requested", "locked"
]
TimeSegmentKind = Literal["work", "break"]


class TimeEntryStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shift_id: UUID | None = None
    employee_id: UUID | None = None
    object_id: UUID | None = None


class TimeSegmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: TimeSegmentKind
    started_at: datetime
    ended_at: datetime

    @field_validator("started_at", "ended_at")
    @classmethod
    def timestamps_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Zeitpunkte müssen einen UTC-Offset enthalten.")
        return value

    @model_validator(mode="after")
    def end_must_follow_start(self):
        if self.ended_at <= self.started_at:
            raise ValueError("Das Segmentende muss nach dem Segmentbeginn liegen.")
        return self


class TimeSegmentsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segments: list[TimeSegmentInput] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def segments_must_form_a_continuous_work_period(self):
        for index, segment in enumerate(self.segments):
            expected_kind = "work" if index % 2 == 0 else "break"
            if segment.kind != expected_kind:
                raise ValueError("Arbeits- und Pausensegmente müssen sich abwechseln.")
            if index and self.segments[index - 1].ended_at != segment.started_at:
                raise ValueError("Arbeits- und Pausensegmente müssen lückenlos aufeinanderfolgen.")
        return self


class TimeEntryManualCreate(TimeSegmentsInput):
    employee_id: UUID
    object_id: UUID
    shift_id: UUID | None = None


class TimeCorrectionCreate(TimeSegmentsInput):
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Ein Korrekturgrund ist erforderlich.")
        return value


class TimeEntryDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=2000)

    @field_validator("reason")
    @classmethod
    def optional_reason_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Der Begründungstext darf nicht leer sein.")
        return value


class TimeEntrySegmentRead(BaseModel):
    id: UUID
    position: int
    kind: TimeSegmentKind
    started_at: datetime
    ended_at: datetime | None


class TimeEntryCorrectionRead(BaseModel):
    id: UUID
    entry_id: UUID
    reason: str
    status: Literal["pending", "approved", "rejected"]
    rejection_reason: str | None
    requested_by_id: UUID | None
    decided_by_id: UUID | None
    requested_at: datetime
    decided_at: datetime | None
    segments: list[TimeEntrySegmentRead]


class TimeEntryRead(BaseModel):
    id: UUID
    employee_id: UUID
    employee_number: str
    employee_name: str
    object_id: UUID
    object_code: str
    object_name: str
    customer_id: UUID
    customer_name: str
    shift_id: UUID | None
    planned_start_at: datetime | None
    planned_end_at: datetime | None
    planned_break_seconds: int
    time_zone: str
    started_at: datetime
    ended_at: datetime | None
    status: TimeEntryStatus
    actual_work_seconds: float
    actual_break_seconds: float
    planned_work_seconds: int | None
    difference_seconds: float | None
    start_deviation_seconds: float | None
    end_deviation_seconds: float | None
    created_by_id: UUID | None
    submitted_at: datetime | None
    reviewed_by_id: UUID | None
    reviewed_at: datetime | None
    decision_reason: str | None
    segments: list[TimeEntrySegmentRead]
    corrections: list[TimeEntryCorrectionRead]


class TimeEntrySummaryRead(BaseModel):
    from_date: date
    to_date: date
    time_zone: str
    group_by: Literal["employee", "object", "customer", "day", "week", "month"] | None
    entry_count: int
    actual_work_seconds: float
    actual_break_seconds: float
    planned_work_seconds: int
    difference_seconds: float
    overtime_seconds: float
    pending_count: int
    groups: list["TimeEntryReportGroup"]
    items: list[TimeEntryRead]


class TimeEntryReportGroup(BaseModel):
    key: str
    label: str
    entry_count: int
    actual_work_seconds: float
    actual_break_seconds: float
    planned_work_seconds: int
    difference_seconds: float
    overtime_seconds: float
    pending_count: int


class MissingShiftRead(BaseModel):
    shift_id: UUID
    employee_id: UUID
    employee_number: str
    employee_name: str
    object_id: UUID
    object_code: str
    object_name: str
    starts_at: datetime
    ends_at: datetime
    time_zone: str


FederalState = Literal[
    "BW",
    "BY",
    "BE",
    "BB",
    "HB",
    "HH",
    "HE",
    "MV",
    "NI",
    "NW",
    "RP",
    "SL",
    "SN",
    "ST",
    "SH",
    "TH",
]
SurchargeCategory = Literal["night", "saturday", "sunday", "public_holiday", "business"]
SurchargeCalculationType = Literal["percentage", "fixed"]
SurchargeCombinationMode = Literal["exclusive", "combine"]


class TimeTrackingSettingsRead(BaseModel):
    federal_state: FederalState | None
    updated_at: datetime


class TimeTrackingSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    federal_state: FederalState | None


class TimeSurchargeRuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=2, max_length=80, pattern=r"^[a-zA-Z0-9._-]+$")
    name: str = Field(min_length=1, max_length=160)
    category: SurchargeCategory
    calculation_type: SurchargeCalculationType
    value: Decimal = Field(gt=0, max_digits=12, decimal_places=4)
    currency: str | None = Field(default=None, min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    basis_description: str = Field(min_length=1, max_length=240)
    valid_from: date
    valid_to: date | None = None
    priority: int = Field(default=100, ge=0, le=10000)
    combination_mode: SurchargeCombinationMode = "exclusive"
    weekdays: list[int] = Field(default_factory=list, max_length=7)
    starts_local: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    ends_local: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")

    @field_validator("name", "basis_description")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Das Feld darf nicht leer sein.")
        return value

    @field_validator("currency")
    @classmethod
    def currency_must_be_present_for_fixed_amount(cls, value: str | None, info):
        if info.data.get("calculation_type") == "fixed" and value is None:
            raise ValueError("Für einen festen Zuschlag muss eine Währung angegeben werden.")
        if info.data.get("calculation_type") == "percentage" and value is not None:
            raise ValueError("Prozentuale Zuschläge dürfen keine Währung enthalten.")
        return value

    @field_validator("weekdays")
    @classmethod
    def weekdays_must_be_unique_and_valid(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value) or any(day < 0 or day > 6 for day in value):
            raise ValueError("Wochentage müssen eindeutige ISO-Werte von 0 bis 6 sein.")
        return sorted(value)

    @model_validator(mode="after")
    def validate_rule_window(self):
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("Das Gültigkeitsende darf nicht vor dem Gültigkeitsbeginn liegen.")
        if self.category in {"night", "business"}:
            if self.starts_local is None or self.ends_local is None:
                raise ValueError("Für Zeitfenster müssen Beginn und Ende angegeben werden.")
            if self.category == "business" and not self.weekdays:
                raise ValueError("Individuelle Zuschläge benötigen mindestens einen Wochentag.")
        elif self.starts_local is not None or self.ends_local is not None or self.weekdays:
            raise ValueError(
                "Zeitfenster und Wochentage gelten nur für Nacht- oder Betriebsregeln."
            )
        if self.calculation_type == "fixed" and self.currency is None:
            raise ValueError("Für einen festen Zuschlag muss eine Währung angegeben werden.")
        if self.calculation_type == "percentage" and self.currency is not None:
            raise ValueError("Prozentuale Zuschläge dürfen keine Währung enthalten.")
        return self


class TimeSurchargeRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    category: SurchargeCategory
    calculation_type: SurchargeCalculationType
    value: Decimal
    currency: str | None
    basis_description: str
    valid_from: date
    valid_to: date | None
    priority: int
    combination_mode: SurchargeCombinationMode
    weekdays: list[int]
    starts_local: str | None
    ends_local: str | None
    created_by_id: UUID | None
    created_at: datetime


class TimeSurchargeAllocationRead(BaseModel):
    rule_id: UUID | None
    rule_code: str | None
    rule_name: str
    eligible_work_seconds: Decimal
    configured_value: Decimal | None
    calculation_type: SurchargeCalculationType | None
    currency: str | None
    basis_description: str | None
    calculated_amount: Decimal | None
    calculation_note: str


class TimeSurchargeCalculationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entry_id: UUID
    version: int
    gross_work_seconds: Decimal
    time_zone: str
    federal_state: FederalState | None
    rule_snapshot: list[dict[str, object]]
    allocation_snapshot: list[TimeSurchargeAllocationRead]
    source_segments: list[dict[str, str]]
    created_by_id: UUID | None
    created_at: datetime


class TimeTrackingPeriodLockCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_date: date
    to_date: date

    @model_validator(mode="after")
    def period_must_be_ordered_and_bounded(self):
        if self.to_date < self.from_date:
            raise ValueError("Das Periodenende darf nicht vor dem Beginn liegen.")
        if (self.to_date - self.from_date).days > 366:
            raise ValueError("Eine Abrechnungsperiode darf höchstens 367 Kalendertage umfassen.")
        return self


class TimeTrackingPeriodRead(BaseModel):
    id: UUID
    from_date: date
    to_date: date
    time_zone: str
    federal_state: FederalState | None
    locked_by_id: UUID | None
    locked_at: datetime


class OWKSControlPointCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    identifier_type: Literal["qr", "nfc"]

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Der Kontrollpunktname darf nicht leer sein.")
        return value


class OWKSControlPointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    object_id: UUID
    name: str
    identifier_type: Literal["qr", "nfc"]
    is_active: bool
    created_at: datetime
    credential: str | None = None


class OWKSRouteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    interval_minutes: int = Field(ge=1, le=1440)
    control_point_ids: list[UUID] = Field(min_length=1, max_length=100)

    @field_validator("control_point_ids")
    @classmethod
    def points_must_be_unique(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("Kontrollpunkte dürfen einer Route nicht doppelt zugeordnet werden.")
        return value


class OWKSRouteRead(BaseModel):
    id: UUID
    object_id: UUID
    name: str
    interval_minutes: int
    is_active: bool
    control_point_ids: list[UUID]
    created_at: datetime


class OWKSEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_id: UUID
    event_type: Literal["entry", "handover", "deviation", "notification", "manipulation"]
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    severity: OWKSEventSeverity = "info"
    occurred_at: datetime | None = None
    client_event_id: UUID

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Der Ereignistitel darf nicht leer sein.")
        return value

    @field_validator("occurred_at")
    @classmethod
    def timestamp_must_have_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("Der Ereigniszeitpunkt muss eine Zeitzone enthalten.")
        return value


class OWKSSyncEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_id: UUID
    event_type: Literal["entry", "handover", "deviation", "notification", "manipulation", "control"]
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    severity: OWKSEventSeverity = "info"
    occurred_at: datetime
    client_event_id: UUID

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Der Ereignistitel darf nicht leer sein.")
        return value

    @field_validator("occurred_at")
    @classmethod
    def timestamp_must_have_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("Der Ereigniszeitpunkt muss eine Zeitzone enthalten.")
        return value


class OWKSChallengeRead(BaseModel):
    id: UUID
    object_id: UUID
    expires_at: datetime


class OWKSScanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    challenge_id: UUID
    credential: str = Field(min_length=20, max_length=200)
    client_event_id: UUID
    occurred_at: datetime | None = None
    route_id: UUID | None = None

    @field_validator("occurred_at")
    @classmethod
    def timestamp_must_have_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("Der Kontrollzeitpunkt muss eine Zeitzone enthalten.")
        return value


class OWKSEventStateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: OWKSEventState
    note: str = Field(default="", max_length=1000)


class OWKSEventCorrectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=2000)
    client_event_id: UUID

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Eine Korrekturbegründung ist erforderlich.")
        return value


class OWKSEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    object_id: UUID
    route_id: UUID | None
    control_point_id: UUID | None
    corrects_event_id: UUID | None
    employee_id: UUID | None
    actor_id: UUID | None
    client_event_id: UUID | None
    event_type: str
    severity: str
    title: str
    description: str
    occurred_at: datetime
    sync_status: str
    presence_verified: bool
    status: OWKSEventState
    created_at: datetime


class OWKSAttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_id: UUID
    file_name: str
    media_type: Literal["application/pdf", "image/jpeg", "image/png"]
    size_bytes: int
    sha256: str
    uploaded_by_id: UUID | None
    created_at: datetime


class OWKSSyncResult(BaseModel):
    client_event_id: UUID
    status: Literal["synced", "conflict", "duplicate"]
    event: OWKSEventRead | None = None
    detail: str | None = None


CustomerCreate.model_rebuild()
CustomerUpdate.model_rebuild()
CustomerRead.model_rebuild()
ObjectCreate.model_rebuild()
ObjectUpdate.model_rebuild()
ObjectRead.model_rebuild()
