import base64
import binascii
import hashlib
import os
import re
import stat
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException, status

from app.config import Settings, get_settings

OFFICE_WORD = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
OFFICE_SHEET = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_ENCRYPTED_MAGIC = b"SECOPS-DOC\x00"
_NONCE_LENGTH = 12
_KEY_VERSION_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,32}\Z")
_STORAGE_KEY_PATTERN = re.compile(r"[a-f0-9]{32}\Z")

ALLOWED_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".docx": OFFICE_WORD,
    ".xlsx": OFFICE_SHEET,
}


def validate_upload(
    file_name: str | None, declared_type: str | None, content: bytes
) -> tuple[str, str]:
    maximum = get_settings().document_max_upload_bytes
    if maximum <= 0:
        raise RuntimeError("DOCUMENT_MAX_UPLOAD_BYTES muss größer als 0 sein.")
    if not content:
        raise HTTPException(status_code=422, detail="Die Datei ist leer.")
    if len(content) > maximum:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Die Datei überschreitet das Limit von {maximum} Bytes.",
        )

    raw_name = (file_name or "").replace("\\", "/").rsplit("/", 1)[-1]
    safe_name = "".join(
        character for character in raw_name if character.isprintable() and character not in "\r\n"
    ).strip()
    if not safe_name or len(safe_name) > 255:
        raise HTTPException(status_code=422, detail="Der Dateiname ist ungültig.")

    extension = Path(safe_name).suffix.lower()
    expected_type = ALLOWED_TYPES.get(extension)
    if expected_type is None:
        raise HTTPException(status_code=415, detail="Dieses Dateiformat ist nicht zugelassen.")
    if (declared_type or "").split(";", 1)[0].strip().lower() != expected_type:
        raise HTTPException(
            status_code=415, detail="Dateiendung und MIME-Typ stimmen nicht überein."
        )

    if expected_type == "application/pdf":
        valid_signature = content.startswith(b"%PDF-")
    elif expected_type == "image/png":
        valid_signature = content.startswith(b"\x89PNG\r\n\x1a\n")
    elif expected_type == "image/jpeg":
        valid_signature = content.startswith(b"\xff\xd8\xff")
    else:
        valid_signature = _is_ooxml_document(content, expected_type)
    if not valid_signature:
        raise HTTPException(status_code=415, detail="Die Dateisignatur ist ungültig.")

    return safe_name, expected_type


def _is_ooxml_document(content: bytes, media_type: str) -> bool:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names:
                return False
            required = "word/document.xml" if media_type == OFFICE_WORD else "xl/workbook.xml"
            return required in names and not any(
                name.startswith(("word/vbaProject", "xl/vbaProject")) for name in names
            )
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
        return False


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _validated_keyring(settings: Settings | None = None) -> dict[str, bytes]:
    configured = (settings or get_settings()).document_encryption_keys
    keyring: dict[str, bytes] = {}
    for version, secret in configured.items():
        if _KEY_VERSION_PATTERN.fullmatch(version) is None:
            raise RuntimeError("DOCUMENT_ENCRYPTION_KEYS enthält eine ungültige Schlüsselversion.")
        encoded_key = secret.get_secret_value()
        if re.fullmatch(r"[A-Za-z0-9_-]{43}=", encoded_key) is None:
            raise RuntimeError(f"Der Dokumentenschlüssel für Version {version} ist ungültig.")
        try:
            key = base64.b64decode(encoded_key, altchars=b"-_", validate=True)
        except (binascii.Error, ValueError) as exc:
            raise RuntimeError(
                f"Der Dokumentenschlüssel für Version {version} ist ungültig."
            ) from exc
        if len(key) != 32:
            raise RuntimeError(
                f"Der Dokumentenschlüssel für Version {version} muss 32 Byte lang sein."
            )
        keyring[version] = key
    return keyring


def validate_document_encryption(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    keyring = _validated_keyring(settings)
    active_version = settings.document_encryption_active_version
    if active_version is None or active_version not in keyring:
        raise RuntimeError(
            "Ein gültiger DOCUMENT_ENCRYPTION_ACTIVE_VERSION-Schlüssel ist erforderlich."
        )
    return active_version


def validate_production_document_encryption(settings: Settings) -> None:
    if settings.app_env == "production":
        validate_document_encryption(settings)


def _active_key() -> tuple[str, bytes]:
    settings = get_settings()
    keyring = _validated_keyring(settings)
    version = settings.document_encryption_active_version
    if version is None or version not in keyring:
        raise RuntimeError(
            "Ein gültiger DOCUMENT_ENCRYPTION_ACTIVE_VERSION-Schlüssel ist erforderlich."
        )
    return version, keyring[version]


def _aad(storage_key: str, version_header: bytes) -> bytes:
    return version_header + storage_key.encode("ascii")


def _encrypt_content(storage_key: str, content: bytes) -> bytes:
    version, key = _active_key()
    encoded_version = version.encode("ascii")
    header = _ENCRYPTED_MAGIC + bytes((len(encoded_version),)) + encoded_version
    nonce = os.urandom(_NONCE_LENGTH)
    encrypted = AESGCM(key).encrypt(nonce, content, _aad(storage_key, header))
    return header + nonce + encrypted


def _encrypted_version(content: bytes) -> str | None:
    if not content.startswith(_ENCRYPTED_MAGIC):
        return None
    version_length_offset = len(_ENCRYPTED_MAGIC)
    if len(content) <= version_length_offset:
        raise ValueError("Das verschlüsselte Dokumentformat ist beschädigt.")
    version_length = content[version_length_offset]
    version_start = version_length_offset + 1
    version_end = version_start + version_length
    if version_length == 0 or len(content) < version_end + _NONCE_LENGTH + 16:
        raise ValueError("Das verschlüsselte Dokumentformat ist beschädigt.")
    try:
        version = content[version_start:version_end].decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("Das verschlüsselte Dokumentformat ist beschädigt.") from exc
    if _KEY_VERSION_PATTERN.fullmatch(version) is None:
        raise ValueError("Das verschlüsselte Dokumentformat ist beschädigt.")
    return version


def _is_legacy_plaintext(content: bytes) -> bool:
    return (
        content.startswith((b"%PDF-", b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff"))
        or _is_ooxml_document(content, OFFICE_WORD)
        or _is_ooxml_document(content, OFFICE_SHEET)
    )


def _decrypt_content(storage_key: str, content: bytes, *, allow_legacy: bool = False) -> bytes:
    version = _encrypted_version(content)
    if version is None:
        if _is_legacy_plaintext(content):
            if get_settings().app_env == "production" and not allow_legacy:
                raise RuntimeError("Die Klartextdatei muss explizit verschlüsselt migriert werden.")
            return content
        raise ValueError(
            "Die Datei ist weder ein unterstütztes Klartext- noch ein Ciphertext-Format."
        )

    key = _validated_keyring().get(version)
    if key is None:
        raise RuntimeError(f"Der benötigte Dokumentenschlüssel für Version {version} fehlt.")
    header_end = len(_ENCRYPTED_MAGIC) + 1 + len(version)
    header = content[:header_end]
    nonce_start = header_end
    nonce_end = nonce_start + _NONCE_LENGTH
    try:
        return AESGCM(key).decrypt(
            content[nonce_start:nonce_end],
            content[nonce_end:],
            _aad(storage_key, header),
        )
    except InvalidTag as exc:
        raise ValueError(
            "Die Authentifizierung des verschlüsselten Dokuments ist fehlgeschlagen."
        ) from exc


def _storage_root(*, create: bool = False) -> Path:
    root = get_settings().document_storage_path.resolve()
    if create:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(root, 0o700)
    return root


def _storage_path(storage_key: str, *, create_root: bool = False) -> Path:
    if _STORAGE_KEY_PATTERN.fullmatch(storage_key) is None:
        raise ValueError("Ungültige Storage-ID")
    root = _storage_root(create=create_root)
    path = root / storage_key
    if path.parent != root:
        raise ValueError("Storage-Pfad liegt außerhalb des privaten Dokumentenspeichers")
    return path


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def store_file(storage_key: str, content: bytes) -> None:
    path = _storage_path(storage_key, create_root=True)
    encrypted_content = _encrypt_content(storage_key, content)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".rekey-{storage_key}-", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(encrypted_content)
            file.flush()
            os.fsync(file.fileno())
        os.link(temporary_path, path)
        _fsync_directory(path.parent)
    finally:
        temporary_path.unlink(missing_ok=True)


def remove_file(storage_key: str) -> None:
    _storage_path(storage_key).unlink(missing_ok=True)


def read_file(storage_key: str, *, allow_legacy: bool = False) -> bytes:
    path = _storage_path(storage_key)
    file_stat = path.lstat()
    if not stat.S_ISREG(file_stat.st_mode):
        raise OSError("Der private Dokumentenspeicher enthält keine reguläre Datei.")
    return _decrypt_content(storage_key, path.read_bytes(), allow_legacy=allow_legacy)


def read_attachment(storage_key: str | None, legacy_content: bytes | None) -> bytes:
    if storage_key is not None:
        return read_file(storage_key)
    if legacy_content is not None and get_settings().app_env != "production":
        return legacy_content
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Die Datei muss vor dem Abruf explizit verschlüsselt migriert werden.",
    )


def list_storage_keys() -> list[str]:
    root = _storage_root()
    if not root.exists():
        return []
    if not root.is_dir():
        raise OSError("Der private Dokumentenspeicher ist kein Verzeichnis.")
    keys: list[str] = []
    for path in root.iterdir():
        if path.name.startswith(".rekey-"):
            continue
        if _STORAGE_KEY_PATTERN.fullmatch(path.name) is None:
            raise ValueError(f"Unerwarteter Eintrag im privaten Dokumentenspeicher: {path.name}")
        file_stat = path.lstat()
        if not stat.S_ISREG(file_stat.st_mode):
            raise OSError(f"Storage-ID {path.name} ist keine reguläre Datei.")
        keys.append(path.name)
    return sorted(keys)


def inspect_storage_file(storage_key: str) -> str | None:
    path = _storage_path(storage_key)
    if not stat.S_ISREG(path.lstat().st_mode):
        raise OSError("Der private Dokumentenspeicher enthält keine reguläre Datei.")
    content = path.read_bytes()
    version = _encrypted_version(content)
    _decrypt_content(storage_key, content, allow_legacy=True)
    return version


def rekey_storage_file(storage_key: str) -> bool:
    path = _storage_path(storage_key)
    file_stat = path.lstat()
    if not stat.S_ISREG(file_stat.st_mode):
        raise OSError("Der private Dokumentenspeicher enthält keine reguläre Datei.")
    encoded_file = path.read_bytes()
    plaintext = _decrypt_content(storage_key, encoded_file, allow_legacy=True)
    active_version, _ = _active_key()
    if _encrypted_version(encoded_file) == active_version:
        return False

    replacement = _encrypt_content(storage_key, plaintext)
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=".rekey-", dir=path.parent)
        temporary_path = Path(temporary_name)
        temp_stat = os.fstat(descriptor)
        if (temp_stat.st_uid, temp_stat.st_gid) != (file_stat.st_uid, file_stat.st_gid):
            os.fchown(descriptor, file_stat.st_uid, file_stat.st_gid)
        os.fchmod(descriptor, stat.S_IMODE(file_stat.st_mode))
        with os.fdopen(descriptor, "wb") as file:
            file.write(replacement)
            file.flush()
            os.fsync(file.fileno())
        if (
            _decrypt_content(storage_key, temporary_path.read_bytes(), allow_legacy=True)
            != plaintext
        ):
            raise OSError("Integritätsprüfung der neu verschlüsselten Datei fehlgeschlagen.")
        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
        return True
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
