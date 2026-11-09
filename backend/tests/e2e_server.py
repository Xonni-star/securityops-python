"""Test-only API server backed by isolated synthetic SQLite data for browser E2E tests."""

import tempfile
from collections.abc import Generator
from pathlib import Path

import uvicorn
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import get_db
from app.identity_api import password_hasher
from app.main import app
from app.models import Base, Customer, Permission, Role, SecurityObject, User

E2E_PASSWORD = "e2e-only-synthetic-password-2026"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="securityops-e2e-") as directory:
        engine = create_engine(
            f"sqlite:///{Path(directory) / 'e2e.sqlite3'}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        with session_factory() as db:
            object_reader = Role(
                code="e2e_object_reader",
                name="E2E-Objektleser",
                description="Synthetische E2E-Testrolle.",
                permissions=[
                    Permission(code="customers.read", description="Synthetischer E2E-Test."),
                    Permission(code="objects.read", description="Synthetischer E2E-Test."),
                    Permission(code="objects.read_all", description="Synthetischer E2E-Test."),
                ],
            )
            no_object_access = Role(
                code="e2e_no_object_access",
                name="E2E-ohne-Objektzugriff",
                description="Synthetische E2E-Testrolle ohne Objektleserecht.",
            )
            customer = Customer(
                customer_number="E2E-CUSTOMER-001",
                company_name="Synthetischer E2E-Kunde",
                status="active",
                contract_status="none",
            )
            db.add_all(
                [
                    object_reader,
                    no_object_access,
                    customer,
                    User(
                        username="e2e-object-reader",
                        email="e2e-object-reader@example.com",
                        full_name="Synthetischer E2E-Objektleser",
                        password_hash=password_hasher.hash(E2E_PASSWORD),
                        roles=[object_reader],
                    ),
                    User(
                        username="e2e-no-object-access",
                        email="e2e-no-object-access@example.com",
                        full_name="Synthetischer E2E-Nutzer ohne Objektzugriff",
                        password_hash=password_hasher.hash(E2E_PASSWORD),
                        roles=[no_object_access],
                    ),
                    SecurityObject(
                        customer=customer,
                        code="E2E-OBJECT-001",
                        name="E2E-Synthetisches Testobjekt",
                        object_type="Synthetischer Testbereich",
                        status="active",
                    ),
                ]
            )
            db.commit()

        def override_get_db() -> Generator[Session, None, None]:
            db = session_factory()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        try:
            uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")
        finally:
            app.dependency_overrides.clear()
            engine.dispose()


if __name__ == "__main__":
    main()
