"""Validate the configured document-encryption keyring without accessing stored files."""

import sys

from pydantic import ValidationError
from pydantic_settings.exceptions import SettingsError

from app.document_storage import validate_document_encryption


def main() -> int:
    try:
        active_version = validate_document_encryption()
    except RuntimeError as exc:
        print(f"Dokumentenschlüssel-Konfiguration ungültig: {exc}", file=sys.stderr)
        return 1
    except (SettingsError, ValidationError):
        print(
            "Dokumentenschlüssel-Konfiguration ungültig; Eingabewerte werden nicht ausgegeben.",
            file=sys.stderr,
        )
        return 1

    print(f"Dokumentenschlüssel-Konfiguration gültig (aktive Version: {active_version}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
