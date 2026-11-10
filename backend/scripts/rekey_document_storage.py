"""Re-encrypt private document files and migrate legacy database attachments."""

import argparse
import hashlib
import sys
from collections.abc import Iterable
from uuid import UUID

from pydantic import ValidationError
from pydantic_settings.exceptions import SettingsError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.database import SessionLocal
from app.document_storage import (
    inspect_storage_file,
    list_storage_keys,
    read_file,
    rekey_storage_file,
    store_file,
    validate_document_encryption,
)
from app.models import (
    CustomerPortalRequestAttachment,
    DocumentVersion,
    EmployeeQualificationDocument,
    IncidentAttachment,
    OWKSAttachment,
)

LEGACY_ATTACHMENT_MODELS = (EmployeeQualificationDocument, OWKSAttachment)
FILE_METADATA_MODELS = (
    CustomerPortalRequestAttachment,
    DocumentVersion,
    EmployeeQualificationDocument,
    IncidentAttachment,
    OWKSAttachment,
)


def _file_metadata(
    session_factory: sessionmaker[Session],
) -> tuple[dict[str, tuple[int, str]], dict[str, tuple[int, str]]]:
    metadata: dict[str, tuple[int, str]] = {}
    pending: dict[str, tuple[int, str]] = {}
    with session_factory() as db:
        for model in FILE_METADATA_MODELS:
            rows = db.execute(
                select(model.storage_key, model.size_bytes, model.sha256).where(
                    model.storage_key.is_not(None)
                )
            )
            for storage_key, size_bytes, checksum in rows:
                current = (size_bytes, checksum)
                previous = metadata.setdefault(storage_key, current)
                if previous != current:
                    raise RuntimeError(
                        f"Storage-ID {storage_key} besitzt widersprüchliche Prüfsummen."
                    )
        for model in LEGACY_ATTACHMENT_MODELS:
            rows = db.execute(
                select(model.id, model.size_bytes, model.sha256).where(
                    model.storage_key.is_(None), model.content.is_not(None)
                )
            )
            for attachment_id, size_bytes, checksum in rows:
                storage_key = attachment_id.hex
                current = (size_bytes, checksum)
                previous = pending.setdefault(storage_key, current)
                if previous != current or (
                    storage_key in metadata and metadata[storage_key] != current
                ):
                    raise RuntimeError(
                        f"Legacy-Anhang {attachment_id} kollidiert mit einer Storage-ID."
                    )
    return metadata, pending


def rekey_files(
    *, dry_run: bool, session_factory: sessionmaker[Session] = SessionLocal
) -> tuple[int, int]:
    active_version = validate_document_encryption()
    rekeyed = 0
    current = 0
    storage_keys = list_storage_keys()
    metadata, pending = _file_metadata(session_factory)
    storage_key_set = set(storage_keys)
    if not set(metadata).issubset(storage_key_set) or not storage_key_set.issubset(
        set(metadata) | set(pending)
    ):
        missing = sorted(set(metadata) - set(storage_keys))
        unreferenced = sorted(set(storage_keys) - set(metadata) - set(pending))
        raise RuntimeError(
            "Dateispeicher und Datenbankreferenzen stimmen nicht überein "
            f"(fehlende Dateien: {len(missing)}, nicht referenzierte Dateien: {len(unreferenced)})."
        )
    for storage_key in storage_keys:
        version = inspect_storage_file(storage_key)
        plaintext = read_file(storage_key, allow_legacy=True)
        expected_size, expected_hash = (
            metadata[storage_key] if storage_key in metadata else pending[storage_key]
        )
        if (
            len(plaintext) != expected_size
            or hashlib.sha256(plaintext).hexdigest() != expected_hash
        ):
            raise RuntimeError(f"Integritätsprüfung für Datei {storage_key} fehlgeschlagen.")
        if version == active_version:
            current += 1
        elif dry_run or rekey_storage_file(storage_key):
            rekeyed += 1
    return rekeyed, current


def _validate_legacy_attachment(row) -> bytes:
    content = row.content
    if content is None:
        raise RuntimeError(f"Anhang {row.id} enthält keinen migrierbaren Dateiinhalt.")
    if len(content) != row.size_bytes or hashlib.sha256(content).hexdigest() != row.sha256:
        raise RuntimeError(f"Integritätsprüfung für Anhang {row.id} fehlgeschlagen.")
    return content


def _migrate_attachment(
    session_factory: sessionmaker[Session], model, attachment_id: UUID, *, dry_run: bool
) -> bool:
    with session_factory() as db, db.begin():
        row = db.scalar(select(model).where(model.id == attachment_id).with_for_update())
        if row is None or row.storage_key is not None:
            return False
        content = _validate_legacy_attachment(row)
        storage_key = row.id.hex
        try:
            existing_content = read_file(storage_key, allow_legacy=True)
        except FileNotFoundError:
            existing_content = None
        if existing_content is not None and existing_content != content:
            raise RuntimeError(
                f"Storage-ID {storage_key} existiert bereits mit abweichendem Inhalt."
            )
        if not dry_run:
            if existing_content is None:
                store_file(storage_key, content)
            row.storage_key = storage_key
            row.content = None
        return True


def rekey_database_attachments(
    session_factory: sessionmaker[Session] = SessionLocal, *, dry_run: bool
) -> int:
    pending = 0
    for model in LEGACY_ATTACHMENT_MODELS:
        while True:
            with session_factory() as db:
                query = (
                    select(model.id)
                    .where(model.storage_key.is_(None), model.content.is_not(None))
                    .order_by(model.id)
                )
                if not dry_run:
                    query = query.limit(100)
                attachment_ids = db.scalars(query).all()
            if not attachment_ids:
                break
            progressed = False
            for attachment_id in attachment_ids:
                if _migrate_attachment(session_factory, model, attachment_id, dry_run=dry_run):
                    pending += 1
                    progressed = True
            if dry_run or not progressed:
                break
    return pending


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dateien explizit verschlüsseln oder auf den aktiven Schlüssel umstellen."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dateien und Datenbankanhänge prüfen, ohne sie zu verändern.",
    )
    args = parser.parse_args(argv)
    try:
        file_count, current_count = rekey_files(dry_run=args.dry_run)
        attachment_count = rekey_database_attachments(dry_run=args.dry_run)
    except (SettingsError, ValidationError):
        print(
            "Dokumenten-Rekey abgebrochen: Schlüssel-/Umgebungskonfiguration ungültig; "
            "Eingabewerte werden nicht ausgegeben.",
            file=sys.stderr,
        )
        return 1
    except (OSError, RuntimeError, ValueError, SQLAlchemyError) as exc:
        print(f"Dokumenten-Rekey abgebrochen: {exc}", file=sys.stderr)
        return 1

    action = "Geplant" if args.dry_run else "Verschlüsselt/umgestellt"
    print(
        f"{action}: {file_count} Dateien, {attachment_count} Datenbankanhänge; "
        f"{current_count} Dateien bereits mit aktivem Schlüssel."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
