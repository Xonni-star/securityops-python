import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.database import get_db
from app.models import CustomerPortalLink, Role, User, UserSession

SESSION_COOKIE = "securityops_session"
CSRF_COOKIE = "securityops_csrf"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def is_customer_portal_restricted(db: Session, user: User) -> bool:
    if any(role.code == "customer_portal" for role in user.roles):
        return True
    return (
        db.scalar(
            select(CustomerPortalLink.id).where(CustomerPortalLink.user_id == user.id).limit(1)
        )
        is not None
    )


@dataclass
class AuthPrincipal:
    user: User
    session: UserSession
    customer_portal_restricted: bool = False

    @property
    def permission_codes(self) -> set[str]:
        if self.customer_portal_restricted or any(
            role.code == "customer_portal" for role in self.user.roles
        ):
            return {"customer_portal.access"}
        return {permission.code for role in self.user.roles for permission in role.permissions}

    @property
    def role_codes(self) -> list[str]:
        return sorted(role.code for role in self.user.roles)


def get_auth_principal(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> AuthPrincipal:
    settings = get_settings()
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Anmeldung erforderlich",
            headers={"WWW-Authenticate": "Cookie"},
        )

    session = db.scalar(
        select(UserSession)
        .options(
            selectinload(UserSession.user).selectinload(User.roles).selectinload(Role.permissions)
        )
        .where(UserSession.token_hash == hash_token(token))
    )
    now = utc_now()
    if (
        session is None
        or as_utc(session.expires_at) <= now
        or as_utc(session.absolute_expires_at) <= now
        or not session.user.is_active
    ):
        if session is not None:
            db.delete(session)
            db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sitzung abgelaufen oder ungültig",
        )

    if session.user.force_password_change and not request.url.path.endswith(
        ("/auth/change-password", "/auth/logout")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vor der weiteren Nutzung muss das Passwort geändert werden.",
        )

    csrf_cookie = request.cookies.get(CSRF_COOKIE, "")
    csrf_header = request.headers.get("X-CSRF-Token", "")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and (
        not csrf_cookie
        or not csrf_header
        or not hmac.compare_digest(csrf_cookie, csrf_header)
        or not hmac.compare_digest(hash_token(csrf_header), session.csrf_token_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF-Prüfung fehlgeschlagen",
        )

    session.last_seen_at = now
    session.expires_at = min(
        now + timedelta(minutes=settings.session_idle_minutes),
        as_utc(session.absolute_expires_at),
    )
    db.commit()
    return AuthPrincipal(
        user=session.user,
        session=session,
        customer_portal_restricted=is_customer_portal_restricted(db, session.user),
    )


def require_permission(permission_code: str):
    def dependency(
        principal: Annotated[AuthPrincipal, Depends(get_auth_principal)],
    ) -> AuthPrincipal:
        if permission_code not in principal.permission_codes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Keine Berechtigung für diese Aktion",
            )
        return principal

    return dependency


CurrentPrincipal = Annotated[AuthPrincipal, Depends(get_auth_principal)]


def add_audit_entry(
    db: Session,
    *,
    actor_id,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    ip_address: str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    from app.models import AuditLog

    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            ip_address=ip_address,
            details=details or {},
        )
    )


def issue_session_tokens() -> tuple[str, str]:
    return secrets.token_urlsafe(32), secrets.token_urlsafe(32)


def set_session_cookies(response, session_token: str, csrf_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="strict",
        path="/",
        max_age=settings.session_absolute_hours * 60 * 60,
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="strict",
        path="/",
        max_age=settings.session_absolute_hours * 60 * 60,
    )


def clear_session_cookies(response) -> None:
    settings = get_settings()
    for name, httponly in ((SESSION_COOKIE, True), (CSRF_COOKIE, False)):
        response.delete_cookie(
            name,
            path="/",
            secure=settings.session_cookie_secure,
            httponly=httponly,
            samesite="strict",
        )
