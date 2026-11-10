import base64
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy import Uuid, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import Settings, get_settings
from app.document_storage import (
    inspect_storage_file,
    read_attachment,
    read_file,
    rekey_storage_file,
    sha256_hex,
    store_file,
    validate_production_document_encryption,
)
from scripts import rekey_document_storage

TEST_KEY_V1 = base64.urlsafe_b64encode(bytes([17]) * 32).decode()
TEST_KEY_V2 = base64.urlsafe_b64encode(bytes([34]) * 32).decode()
PDF_CONTENT = b"%PDF-1.7\nsynthetic storage test"


def set_keys(monkeypatch, *versions: tuple[str, str], active: str) -> None:
    monkeypatch.setattr(
        get_settings(),
        "document_encryption_keys",
        {version: SecretStr(key) for version, key in versions},
    )
    monkeypatch.setattr(get_settings(), "document_encryption_active_version", active)


def test_new_files_are_encrypted_and_read_back_exactly() -> None:
    storage_key = uuid4().hex

    store_file(storage_key, PDF_CONTENT)

    raw_content = (get_settings().document_storage_path / storage_key).read_bytes()
    assert raw_content.startswith(b"SECOPS-DOC\x00")
    assert PDF_CONTENT not in raw_content
    assert read_file(storage_key) == PDF_CONTENT


def test_new_file_is_published_only_after_ciphertext_is_complete(monkeypatch) -> None:
    storage_key = uuid4().hex
    path = get_settings().document_storage_path / storage_key
    real_link = os.link
    publish_attempts = 0

    def publish(source, destination) -> None:
        nonlocal publish_attempts
        staged_path = Path(source)
        encoded = staged_path.read_bytes()
        assert encoded.startswith(b"SECOPS-DOC\x00")
        assert PDF_CONTENT not in encoded
        assert not path.exists()
        publish_attempts += 1
        real_link(source, destination)

    monkeypatch.setattr("app.document_storage.os.link", publish)
    store_file(storage_key, PDF_CONTENT)

    assert publish_attempts == 1
    assert read_file(storage_key) == PDF_CONTENT


def test_failed_staging_sync_leaves_no_target_and_can_be_retried(monkeypatch) -> None:
    storage_key = uuid4().hex
    path = get_settings().document_storage_path / storage_key

    def fail_sync(_descriptor: int) -> None:
        raise OSError("injected sync failure")

    with monkeypatch.context() as patch:
        patch.setattr("app.document_storage.os.fsync", fail_sync)
        with pytest.raises(OSError, match="injected sync failure"):
            store_file(storage_key, PDF_CONTENT)

    assert not path.exists()
    assert not list(path.parent.glob(f".rekey-{storage_key}-*"))
    store_file(storage_key, PDF_CONTENT)
    assert read_file(storage_key) == PDF_CONTENT


def test_failed_publish_sync_removes_target_and_can_be_retried(monkeypatch) -> None:
    storage_key = uuid4().hex
    path = get_settings().document_storage_path / storage_key
    sync_attempts = 0
    target_exists_during_sync: list[bool] = []

    def fail_first_directory_sync(directory: Path) -> None:
        nonlocal sync_attempts
        target_exists_during_sync.append(path.exists())
        if path.exists():
            assert path.read_bytes().startswith(b"SECOPS-DOC\x00")
        sync_attempts += 1
        if sync_attempts == 1:
            raise OSError("injected post-publish sync failure")

    with monkeypatch.context() as patch:
        patch.setattr(
            "app.document_storage._fsync_directory",
            fail_first_directory_sync,
        )
        with pytest.raises(OSError, match="injected post-publish sync failure"):
            store_file(storage_key, PDF_CONTENT)

        assert not path.exists()
        assert not list(path.parent.glob(f".rekey-{storage_key}-*"))
        store_file(storage_key, PDF_CONTENT)
        assert read_file(storage_key) == PDF_CONTENT

    assert sync_attempts == 3
    assert target_exists_during_sync == [True, False, True]


def test_failed_publish_sync_does_not_remove_replaced_target(monkeypatch) -> None:
    storage_key = uuid4().hex
    path = get_settings().document_storage_path / storage_key

    def replace_before_sync_failure(_directory: Path) -> None:
        path.unlink()
        path.write_bytes(b"replacement from concurrent writer")
        raise OSError("injected post-publish sync failure")

    monkeypatch.setattr(
        "app.document_storage._fsync_directory",
        replace_before_sync_failure,
    )
    with pytest.raises(OSError, match="injected post-publish sync failure"):
        store_file(storage_key, PDF_CONTENT)

    assert path.read_bytes() == b"replacement from concurrent writer"
    assert not list(path.parent.glob(f".rekey-{storage_key}-*"))


def test_failed_cleanup_sync_reports_both_errors_and_allows_retry(monkeypatch) -> None:
    storage_key = uuid4().hex
    path = get_settings().document_storage_path / storage_key
    sync_attempts = 0

    def fail_both_directory_syncs(_directory: Path) -> None:
        nonlocal sync_attempts
        sync_attempts += 1
        raise OSError(f"injected directory sync failure {sync_attempts}")

    with monkeypatch.context() as patch:
        patch.setattr(
            "app.document_storage._fsync_directory",
            fail_both_directory_syncs,
        )
        with pytest.raises(ExceptionGroup, match="Zielpfad muss geprüft werden") as error:
            store_file(storage_key, PDF_CONTENT)

    assert len(error.value.exceptions) == 2
    assert all(isinstance(exception, OSError) for exception in error.value.exceptions)
    assert not path.exists()
    assert not list(path.parent.glob(f".rekey-{storage_key}-*"))
    store_file(storage_key, PDF_CONTENT)
    assert read_file(storage_key) == PDF_CONTENT


def test_legacy_pdf_is_readable_until_explicit_rekey() -> None:
    storage_key = uuid4().hex
    (get_settings().document_storage_path / storage_key).write_bytes(PDF_CONTENT)

    assert read_file(storage_key) == PDF_CONTENT
    assert rekey_storage_file(storage_key)
    assert read_file(storage_key) == PDF_CONTENT
    assert inspect_storage_file(storage_key) == "test-v1"


@pytest.mark.parametrize("tamper_header", [False, True])
def test_tampered_ciphertext_is_rejected(tamper_header: bool) -> None:
    storage_key = uuid4().hex
    store_file(storage_key, PDF_CONTENT)
    path = get_settings().document_storage_path / storage_key
    encrypted = bytearray(path.read_bytes())
    encrypted[0 if tamper_header else -1] ^= 0x01
    path.write_bytes(encrypted)

    with pytest.raises(ValueError):
        read_file(storage_key)


def test_ciphertext_cannot_be_moved_to_another_storage_id() -> None:
    original_key = uuid4().hex
    copied_key = uuid4().hex
    store_file(original_key, PDF_CONTENT)
    original = get_settings().document_storage_path / original_key
    (get_settings().document_storage_path / copied_key).write_bytes(original.read_bytes())

    with pytest.raises(ValueError, match="Authentifizierung"):
        read_file(copied_key)


def test_storage_symlinks_are_rejected(tmp_path) -> None:
    storage_key = uuid4().hex
    (tmp_path / "target").write_bytes(PDF_CONTENT)
    (tmp_path / storage_key).symlink_to(tmp_path / "target")

    with pytest.raises(OSError, match="reguläre Datei"):
        read_file(storage_key)


def test_wrong_key_and_missing_key_fail_closed(monkeypatch) -> None:
    storage_key = uuid4().hex
    store_file(storage_key, PDF_CONTENT)
    set_keys(monkeypatch, ("test-v1", TEST_KEY_V2), active="test-v1")
    with pytest.raises(ValueError, match="Authentifizierung"):
        read_file(storage_key)

    set_keys(monkeypatch, active="test-v1")
    with pytest.raises(RuntimeError, match="Version test-v1 fehlt"):
        read_file(storage_key)


def test_store_without_key_does_not_write_plaintext(monkeypatch) -> None:
    storage_key = uuid4().hex
    set_keys(monkeypatch, active="test-v1")

    with pytest.raises(RuntimeError, match="DOCUMENT_ENCRYPTION_ACTIVE_VERSION"):
        store_file(storage_key, PDF_CONTENT)
    assert not (get_settings().document_storage_path / storage_key).exists()


def test_production_requires_valid_encryption_key() -> None:
    settings = Settings(
        _env_file=None,
        postgres_password="test-only-not-for-production",
        app_env="production",
        session_cookie_secure=True,
        rate_limit_storage_uri="redis://localhost:6379/0",
        forwarded_allow_ips="127.0.0.1",
        document_encryption_keys={},
        document_encryption_active_version=None,
    )

    with pytest.raises(RuntimeError, match="DOCUMENT_ENCRYPTION_ACTIVE_VERSION"):
        validate_production_document_encryption(settings)


def test_invalid_configured_key_is_rejected() -> None:
    settings = Settings(
        _env_file=None,
        postgres_password="test-only-not-for-production",
        app_env="production",
        session_cookie_secure=True,
        rate_limit_storage_uri="redis://localhost:6379/0",
        forwarded_allow_ips="127.0.0.1",
        document_encryption_keys={"v1": SecretStr("invalid-test-key")},
        document_encryption_active_version="v1",
    )

    with pytest.raises(RuntimeError, match="Dokumentenschlüssel für Version v1 ist ungültig"):
        validate_production_document_encryption(settings)


def test_rekey_is_atomic_resumable_and_preserves_mode(monkeypatch) -> None:
    storage_key = uuid4().hex
    set_keys(monkeypatch, ("test-v1", TEST_KEY_V1), active="test-v1")
    store_file(storage_key, PDF_CONTENT)
    path = get_settings().document_storage_path / storage_key
    path.chmod(0o640)
    set_keys(
        monkeypatch,
        ("test-v1", TEST_KEY_V1),
        ("test-v2", TEST_KEY_V2),
        active="test-v2",
    )

    assert rekey_storage_file(storage_key)
    assert inspect_storage_file(storage_key) == "test-v2"
    assert stat_mode(path) == 0o640
    assert read_file(storage_key) == PDF_CONTENT
    assert not rekey_storage_file(storage_key)


def test_failed_atomic_replace_keeps_original_for_resume(monkeypatch) -> None:
    storage_key = uuid4().hex
    set_keys(monkeypatch, ("test-v1", TEST_KEY_V1), active="test-v1")
    store_file(storage_key, PDF_CONTENT)
    path = get_settings().document_storage_path / storage_key
    original = path.read_bytes()
    real_replace = os.replace
    set_keys(
        monkeypatch,
        ("test-v1", TEST_KEY_V1),
        ("test-v2", TEST_KEY_V2),
        active="test-v2",
    )

    def fail_replace(*_args) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr("app.document_storage.os.replace", fail_replace)

    with pytest.raises(OSError, match="injected replace failure"):
        rekey_storage_file(storage_key)
    assert path.read_bytes() == original
    assert read_file(storage_key) == PDF_CONTENT
    assert not list(path.parent.glob(".rekey-*"))
    monkeypatch.setattr("app.document_storage.os.replace", real_replace)
    assert rekey_storage_file(storage_key)


def test_database_attachment_rekey_is_explicit_and_resumable(monkeypatch) -> None:
    class TestBase(DeclarativeBase):
        pass

    class LegacyAttachment(TestBase):
        __tablename__ = "legacy_attachments"

        id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
        storage_key: Mapped[str | None] = mapped_column(nullable=True)
        content: Mapped[bytes | None] = mapped_column(nullable=True)
        size_bytes: Mapped[int] = mapped_column(nullable=False)
        sha256: Mapped[str] = mapped_column(nullable=False)

    engine = create_engine("sqlite://")
    TestBase.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    attachment_id = uuid4()
    with session_factory.begin() as db:
        db.add(
            LegacyAttachment(
                id=attachment_id,
                content=PDF_CONTENT,
                size_bytes=len(PDF_CONTENT),
                sha256=sha256_hex(PDF_CONTENT),
            )
        )
    monkeypatch.setattr(
        rekey_document_storage,
        "LEGACY_ATTACHMENT_MODELS",
        (LegacyAttachment,),
    )
    monkeypatch.setattr(
        rekey_document_storage,
        "FILE_METADATA_MODELS",
        (LegacyAttachment,),
    )
    set_keys(monkeypatch, ("test-v1", TEST_KEY_V1), active="test-v1")

    assert rekey_document_storage.rekey_database_attachments(session_factory, dry_run=True) == 1
    with session_factory() as db:
        unchanged = db.get(LegacyAttachment, attachment_id)
        assert unchanged is not None and unchanged.content == PDF_CONTENT
        assert unchanged.storage_key is None

    storage_key = attachment_id.hex
    store_file(storage_key, PDF_CONTENT)
    set_keys(
        monkeypatch,
        ("test-v1", TEST_KEY_V1),
        ("test-v2", TEST_KEY_V2),
        active="test-v2",
    )
    assert rekey_document_storage.rekey_files(session_factory=session_factory, dry_run=False) == (
        1,
        0,
    )
    assert rekey_document_storage.rekey_database_attachments(session_factory, dry_run=False) == 1
    assert rekey_document_storage.rekey_database_attachments(session_factory, dry_run=False) == 0
    with session_factory() as db:
        migrated = db.scalar(select(LegacyAttachment).where(LegacyAttachment.id == attachment_id))
        assert migrated is not None
        assert migrated.storage_key == storage_key
        assert migrated.content is None
    assert read_file(storage_key) == PDF_CONTENT
    engine.dispose()


def test_legacy_database_attachment_is_not_served_in_production(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "app_env", "production")

    with pytest.raises(HTTPException) as error:
        read_attachment(None, PDF_CONTENT)
    assert error.value.status_code == 503


def test_legacy_files_are_not_served_in_production(monkeypatch) -> None:
    storage_key = uuid4().hex
    (get_settings().document_storage_path / storage_key).write_bytes(PDF_CONTENT)
    monkeypatch.setattr(get_settings(), "app_env", "production")

    with pytest.raises(RuntimeError, match="explizit verschlüsselt migriert"):
        read_file(storage_key)


def stat_mode(path) -> int:
    return os.stat(path).st_mode & 0o777
