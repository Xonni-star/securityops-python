import os
from collections.abc import Generator

os.environ.setdefault("POSTGRES_PASSWORD", "test-only-not-for-production")
os.environ.setdefault("MFA_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.identity_api import password_hasher
from app.main import app
from app.models import (
    AuditLog,
    Base,
    BillingExport,
    BillingInvoice,
    BillingInvoiceLine,
    BillingPayment,
    BillingRate,
    Contract,
    ContractHistory,
    Customer,
    CustomerAddress,
    CustomerContact,
    CustomerHistory,
    CustomerPortalDocumentGrant,
    CustomerPortalDocumentGrantHistory,
    CustomerPortalLink,
    CustomerPortalLinkHistory,
    CustomerPortalRequest,
    CustomerPortalRequestAttachment,
    CustomerPortalRequestHistory,
    CustomerPortalRequestMessage,
    Document,
    DocumentApproval,
    DocumentContractReminder,
    DocumentContractReminderSettings,
    DocumentHistory,
    DocumentReadReceipt,
    DocumentVersion,
    Employee,
    EmployeeAbsence,
    EmployeeAvailabilityWindow,
    EmployeeHistory,
    EmployeeObjectAssignmentHistory,
    EmployeeQualification,
    EmployeeQualificationDocument,
    EmployeeSensitiveDetails,
    Incident,
    IncidentAttachment,
    IncidentHistory,
    IncidentMeasure,
    IncidentPerson,
    IncidentSensitiveDetails,
    InventoryAsset,
    InventoryEvent,
    KeyMovement,
    Notification,
    NotificationOutbox,
    NotificationOutboxAttempt,
    ObjectAddress,
    ObjectAssignment,
    ObjectContact,
    ObjectHistory,
    ObjectSecurityDetails,
    OWKSAttachment,
    OWKSChallenge,
    OWKSControlPoint,
    OWKSEvent,
    OWKSEventStatus,
    OWKSRoute,
    OWKSRoutePoint,
    Permission,
    PhysicalKey,
    Role,
    ScheduleAvailabilityRequest,
    ScheduleSettings,
    ScheduleShift,
    ScheduleShiftHistory,
    SecurityObject,
    Task,
    TaskComment,
    TaskHistory,
    TimeEntry,
    TimeEntryCorrection,
    TimeEntryCorrectionSegment,
    TimeEntryHistory,
    TimeEntrySegment,
    TimeSurchargeCalculation,
    TimeSurchargeRule,
    TimeTrackingPeriod,
    TimeTrackingSettings,
    User,
    UserMFARecoveryCode,
    UserSession,
    user_roles,
)
from app.rate_limit import limiter

ADMIN_PASSWORD = "sicheres-test-passwort-2026"
test_database_url = os.environ.get("SECURITYOPS_TEST_DATABASE_URL", "sqlite://")
engine_options = {}
if test_database_url == "sqlite://":
    engine_options = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
else:
    parsed_test_url = make_url(test_database_url)
    if (
        parsed_test_url.drivername != "postgresql+psycopg"
        or parsed_test_url.host not in {"localhost", "127.0.0.1"}
        or parsed_test_url.database != "securityops_test"
    ):
        raise RuntimeError("PostgreSQL-Tests sind nur für localhost/securityops_test zulässig.")
test_engine = create_engine(test_database_url, **engine_options)
TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)


def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def mock_upload_scanner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.upload_scanning.scan_upload", lambda _content: None)


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    limiter.reset()
    Base.metadata.create_all(bind=test_engine)
    with TestingSessionLocal() as db:
        if test_engine.dialect.name == "postgresql":
            for table in (
                "incident_history",
                "incident_people",
                "incident_attachments",
                "owks_events",
                "owks_event_statuses",
                "owks_attachments",
                "key_movements",
                "inventory_events",
                "notification_outbox_attempts",
                "customer_portal_link_history",
                "customer_portal_document_grant_history",
                "customer_portal_request_messages",
                "customer_portal_request_attachments",
                "customer_portal_request_history",
            ):
                db.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER {table}_append_only"))
        db.execute(delete(UserSession))
        db.execute(delete(UserMFARecoveryCode))
        if test_engine.dialect.name != "postgresql":
            db.execute(delete(AuditLog))
        db.execute(delete(TaskComment))
        db.execute(delete(TaskHistory))
        db.execute(delete(Notification))
        db.execute(delete(NotificationOutboxAttempt))
        db.execute(delete(NotificationOutbox))
        db.execute(delete(Task))
        db.execute(delete(IncidentHistory))
        db.execute(delete(IncidentPerson))
        db.execute(delete(IncidentAttachment))
        db.execute(delete(IncidentMeasure))
        db.execute(delete(IncidentSensitiveDetails))
        db.execute(delete(Incident))
        db.execute(delete(KeyMovement))
        db.execute(delete(PhysicalKey))
        db.execute(delete(InventoryEvent))
        db.execute(delete(InventoryAsset))
        db.execute(delete(OWKSAttachment))
        db.execute(delete(OWKSEventStatus))
        db.execute(delete(OWKSEvent))
        db.execute(delete(OWKSChallenge))
        db.execute(delete(OWKSRoutePoint))
        db.execute(delete(OWKSRoute))
        db.execute(delete(OWKSControlPoint))
        db.execute(delete(TimeEntryCorrectionSegment))
        db.execute(delete(TimeEntryCorrection))
        db.execute(delete(TimeEntryHistory))
        db.execute(delete(DocumentContractReminder))
        db.execute(delete(BillingExport))
        db.execute(delete(BillingPayment))
        db.execute(delete(BillingInvoiceLine))
        db.execute(delete(BillingInvoice).where(BillingInvoice.kind != "invoice"))
        db.execute(delete(BillingInvoice))
        db.execute(delete(BillingRate))
        db.execute(delete(ContractHistory))
        db.execute(delete(DocumentReadReceipt))
        db.execute(delete(CustomerPortalDocumentGrantHistory))
        db.execute(delete(CustomerPortalDocumentGrant))
        db.execute(delete(CustomerPortalRequestHistory))
        db.execute(delete(CustomerPortalRequestAttachment))
        db.execute(delete(CustomerPortalRequestMessage))
        db.execute(delete(CustomerPortalRequest))
        db.execute(delete(CustomerPortalLinkHistory))
        db.execute(delete(CustomerPortalLink))
        db.execute(delete(DocumentApproval))
        db.execute(delete(DocumentVersion))
        db.execute(delete(Contract))
        db.execute(delete(DocumentHistory))
        db.execute(delete(Document))
        db.execute(delete(DocumentContractReminderSettings))
        db.execute(delete(TimeSurchargeCalculation))
        db.execute(delete(TimeEntrySegment))
        db.execute(delete(TimeEntry))
        db.execute(delete(TimeTrackingPeriod))
        db.execute(delete(TimeSurchargeRule))
        db.execute(delete(TimeTrackingSettings))
        db.execute(delete(ScheduleShiftHistory))
        db.execute(delete(ScheduleShift))
        db.execute(delete(ScheduleAvailabilityRequest))
        db.execute(delete(EmployeeAvailabilityWindow))
        db.execute(delete(ScheduleSettings))
        db.execute(delete(ObjectHistory))
        db.execute(delete(ObjectAssignment))
        db.execute(delete(ObjectContact))
        db.execute(delete(ObjectAddress))
        db.execute(delete(ObjectSecurityDetails))
        db.execute(delete(EmployeeObjectAssignmentHistory))
        db.execute(delete(SecurityObject))
        db.execute(delete(CustomerHistory))
        db.execute(delete(CustomerContact))
        db.execute(delete(CustomerAddress))
        db.execute(delete(Customer))
        db.execute(delete(EmployeeHistory))
        db.execute(delete(EmployeeAbsence))
        db.execute(delete(EmployeeQualificationDocument))
        db.execute(delete(EmployeeQualification))
        db.execute(delete(EmployeeSensitiveDetails))
        db.execute(delete(Employee))
        db.execute(delete(user_roles))
        db.execute(delete(User))
        if test_engine.dialect.name == "postgresql":
            for table in (
                "incident_history",
                "incident_people",
                "incident_attachments",
                "owks_events",
                "owks_event_statuses",
                "owks_attachments",
                "key_movements",
                "inventory_events",
                "notification_outbox_attempts",
                "customer_portal_link_history",
                "customer_portal_document_grant_history",
                "customer_portal_request_messages",
                "customer_portal_request_attachments",
                "customer_portal_request_history",
            ):
                db.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER {table}_append_only"))
        db.commit()

        permission_codes = (
            "customers.read",
            "customers.portal.manage",
            "customer_portal.access",
            "customer_portal.documents.manage",
            "customer_portal.requests.manage",
            "customers.create",
            "customers.update",
            "customers.archive",
            "objects.read",
            "objects.manage",
            "objects.read_all",
            "objects.manage_all",
            "objects.assign",
            "objects.sensitive.read",
            "objects.sensitive.manage",
            "dashboard.read",
            "users.read",
            "users.manage",
            "users.password_reset",
            "sessions.manage",
            "roles.read",
            "audit.read",
            "owks.read",
            "owks.manage",
            "owks.write",
            "employees.read",
            "employees.manage",
            "employees.sensitive.read",
            "employees.sensitive.manage",
            "employees.absences.read",
            "employees.absences.manage",
            "employees.documents.read",
            "employees.documents.manage",
            "scheduling.read",
            "scheduling.manage",
            "scheduling.availability.request",
            "time_tracking.read_own",
            "time_tracking.read_all",
            "time_tracking.create",
            "time_tracking.correct_own",
            "time_tracking.correct_all",
            "time_tracking.approve",
            "time_tracking.reject",
            "time_tracking.export",
            "time_tracking.manage",
            "time_tracking.surcharges.read",
            "time_tracking.surcharges.manage",
            "time_tracking.periods.read",
            "time_tracking.periods.lock",
            "documents.read",
            "documents.create",
            "documents.update",
            "documents.archive",
            "documents.download",
            "documents.approve",
            "contracts.read",
            "contracts.create",
            "contracts.update",
            "contracts.archive",
            "contracts.manage_reminders",
            "billing.invoices.read",
            "billing.invoices.create",
            "billing.invoices.approve",
            "billing.invoices.archive",
            "billing.rates.manage",
            "billing.payments.manage",
            "billing.exports.create",
            "tasks.read_own",
            "tasks.read_all",
            "tasks.create",
            "tasks.update_own",
            "tasks.manage",
            "tasks.assign",
            "tasks.manage_all",
            "notifications.read_own",
            "keys.read",
            "keys.manage",
            "keys.move",
            "inventory.read",
            "inventory.manage",
            "inventory.move",
            "incidents.read",
            "incidents.read_all",
            "incidents.create",
            "incidents.update",
            "incidents.manage_all",
            "incidents.sensitive.read",
            "incidents.sensitive.manage",
            "control_room.read",
        )
        permissions = {}
        for code in permission_codes:
            permission = db.scalar(select(Permission).where(Permission.code == code))
            if permission is None:
                permission = Permission(code=code, description=code)
                db.add(permission)
            permissions[code] = permission

        def get_or_create_role(
            code: str,
            name: str,
            description: str,
            permission_codes: tuple[str, ...],
        ) -> Role:
            role = db.scalar(select(Role).where(Role.code == code))
            if role is None:
                role = Role(code=code, name=name, description=description)
                db.add(role)
            role.permissions = [
                permissions[permission_code] for permission_code in permission_codes
            ]
            return role

        administrator = get_or_create_role(
            "administrator",
            "Administrator",
            "Testrolle",
            permission_codes,
        )
        management = get_or_create_role(
            "management",
            "Geschäftsführung",
            "Testrolle ohne Administratorrechte",
            (
                "users.read",
                "users.manage",
                "customers.read",
                "objects.read",
                "objects.manage",
                "objects.read_all",
                "objects.manage_all",
                "objects.assign",
                "objects.sensitive.read",
                "objects.sensitive.manage",
                "owks.read",
                "owks.manage",
                "owks.write",
                "employees.read",
                "employees.manage",
                "time_tracking.read_all",
                "time_tracking.create",
                "time_tracking.correct_all",
                "time_tracking.approve",
                "time_tracking.reject",
                "time_tracking.export",
                "time_tracking.manage",
                "time_tracking.surcharges.read",
                "time_tracking.surcharges.manage",
                "time_tracking.periods.read",
                "time_tracking.periods.lock",
                "tasks.read_all",
                "tasks.create",
                "tasks.manage",
                "tasks.assign",
                "notifications.read_own",
                "keys.read",
                "keys.manage",
                "keys.move",
                "inventory.read",
                "inventory.manage",
                "inventory.move",
                "incidents.read",
                "incidents.read_all",
                "incidents.create",
                "incidents.update",
                "incidents.manage_all",
                "incidents.sensitive.read",
                "incidents.sensitive.manage",
                "control_room.read",
                "documents.read",
                "documents.create",
                "documents.update",
                "documents.archive",
                "documents.download",
                "documents.approve",
                "contracts.read",
                "contracts.create",
                "contracts.update",
                "contracts.archive",
                "contracts.manage_reminders",
            ),
        )
        get_or_create_role(
            "employee",
            "Mitarbeiter",
            "Operative Testrolle",
            (
                "owks.read",
                "owks.write",
                "objects.read",
                "scheduling.read",
                "scheduling.availability.request",
                "time_tracking.read_own",
                "time_tracking.create",
                "time_tracking.correct_own",
                "tasks.read_own",
                "tasks.create",
                "tasks.update_own",
                "notifications.read_own",
                "incidents.read",
                "incidents.create",
            ),
        )
        get_or_create_role(
            "object_manager",
            "Objektleitung",
            "Testrolle mit zugewiesener Objektverwaltung",
            (
                "objects.read",
                "objects.manage",
                "objects.sensitive.read",
                "documents.read",
                "documents.download",
                "keys.read",
                "keys.move",
                "inventory.read",
                "inventory.move",
                "incidents.read",
                "incidents.create",
                "incidents.update",
                "incidents.sensitive.read",
                "control_room.read",
            ),
        )
        get_or_create_role(
            "customer_portal",
            "Kundenportal",
            "Ausschließlich eigene freigegebene Kundeninformationen",
            ("customer_portal.access",),
        )
        get_or_create_role(
            "hr",
            "Personalverwaltung",
            "Personal-Testrolle",
            (
                "employees.read",
                "employees.manage",
                "employees.sensitive.read",
                "employees.sensitive.manage",
                "employees.absences.read",
                "employees.absences.manage",
                "employees.documents.read",
                "employees.documents.manage",
                "time_tracking.read_all",
                "time_tracking.create",
                "time_tracking.correct_all",
                "time_tracking.approve",
                "time_tracking.reject",
                "time_tracking.export",
                "time_tracking.manage",
                "time_tracking.surcharges.read",
                "time_tracking.surcharges.manage",
                "time_tracking.periods.read",
                "time_tracking.periods.lock",
                "documents.read",
                "documents.create",
                "documents.update",
                "documents.archive",
                "documents.download",
                "documents.approve",
                "contracts.read",
                "contracts.create",
                "contracts.update",
                "contracts.archive",
                "contracts.manage_reminders",
            ),
        )
        db.add(ScheduleSettings(id=1, time_zone="Europe/Berlin", minimum_rest_hours=11))
        db.add(
            User(
                username="admin",
                email="admin@example.com",
                full_name="Test Administration",
                password_hash=password_hasher.hash(ADMIN_PASSWORD),
                roles=[administrator],
            )
        )
        db.add(
            User(
                username="geschaeftsfuehrung",
                email="management@example.com",
                full_name="Test Geschäftsführung",
                password_hash=password_hasher.hash("management-test-passwort-2026"),
                roles=[management],
            )
        )
        db.commit()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()
    limiter.reset()
