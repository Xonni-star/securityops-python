from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pwdlib import PasswordHash
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth import (
    AuthPrincipal,
    add_audit_entry,
    clear_session_cookies,
    get_auth_principal,
    hash_token,
    is_customer_portal_restricted,
    issue_session_tokens,
    require_permission,
    set_session_cookies,
)
from app.config import get_settings
from app.database import get_db
from app.mfa import (
    decrypt_secret,
    encrypt_secret,
    new_recovery_codes,
    new_totp_secret,
    provisioning_uri,
    recovery_code_hash,
    verify_totp,
)
from app.models import AuditLog, Role, User, UserMFARecoveryCode, UserSession, user_roles
from app.rate_limit import limiter
from app.schemas import (
    AdminPasswordReset,
    AuditLogRead,
    LoginRequest,
    MFADisableRequest,
    MFAEnableRequest,
    MFARecoveryCodesRead,
    MFASetupRead,
    MFASetupRequest,
    MFAStatusRead,
    PasswordChange,
    RoleRead,
    SessionRead,
    UserCreate,
    UserRead,
    UserSessionRead,
    UserUpdate,
)

password_hasher = PasswordHash.recommended()
dummy_password_hash = password_hasher.hash("SecurityOps-invalid-account-password")
router = APIRouter()


def user_read(user: User, *, customer_portal_restricted: bool = False) -> UserRead:
    portal_only = customer_portal_restricted or any(
        role.code == "customer_portal" for role in user.roles
    )
    permissions = (
        {"customer_portal.access"}
        if portal_only
        else {permission.code for role in user.roles for permission in role.permissions}
    )
    return UserRead(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        roles=["customer_portal"] if portal_only else sorted(role.code for role in user.roles),
        permissions=sorted(permissions),
    )


def ensure_role_permissions_grantable(roles: list[Role], principal: AuthPrincipal) -> None:
    requested_permissions = {permission.code for role in roles for permission in role.permissions}
    if (
        requested_permissions - principal.permission_codes
        and "users.manage_admin" not in principal.permission_codes
    ):
        raise HTTPException(
            status_code=403,
            detail="Du darfst keine Berechtigungen vergeben, die du selbst nicht besitzt",
        )


@router.post("/auth/login", response_model=SessionRead)
@limiter.limit("5/minute")
def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> SessionRead:
    username = payload.username.strip().lower()
    user = db.scalar(
        select(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .where(User.username == username)
        .with_for_update()
    )
    stored_hash = user.password_hash if user else dummy_password_hash
    valid_password = password_hasher.verify(payload.password, stored_hash)
    mfa_counter = None
    valid_mfa = True
    if user is not None and user.is_active and valid_password and user.mfa_enabled:
        valid_mfa = False
        if payload.mfa_code and user.mfa_secret_encrypted:
            mfa_counter = verify_totp(
                decrypt_secret(user.mfa_secret_encrypted),
                payload.mfa_code,
                last_counter=user.mfa_last_counter,
            )
            valid_mfa = mfa_counter is not None
        elif payload.recovery_code:
            recovery_hash = recovery_code_hash(payload.recovery_code)
            recovery_code = db.scalar(
                select(UserMFARecoveryCode)
                .where(
                    UserMFARecoveryCode.user_id == user.id,
                    UserMFARecoveryCode.code_hash == recovery_hash,
                )
                .with_for_update()
            )
            if recovery_code is not None:
                db.delete(recovery_code)
                valid_mfa = True
                add_audit_entry(
                    db,
                    actor_id=user.id,
                    action="auth.mfa_recovery_code_used",
                    entity_type="user",
                    entity_id=str(user.id),
                    ip_address=request.client.host if request.client else None,
                )
    elif payload.mfa_code or payload.recovery_code:
        valid_mfa = False

    if user is None or not user.is_active or not valid_password or not valid_mfa:
        add_audit_entry(
            db,
            actor_id=user.id if user else None,
            action="auth.login_failed",
            entity_type="user",
            entity_id=str(user.id) if user else None,
            ip_address=request.client.host if request.client else None,
            details={"username": username},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Benutzername oder Passwort ist ungültig",
        )

    if mfa_counter is not None:
        user.mfa_last_counter = mfa_counter

    settings = get_settings()
    now = datetime.now(UTC)
    session_token, csrf_token = issue_session_tokens()
    user_session = UserSession(
        user_id=user.id,
        token_hash=hash_token(session_token),
        csrf_token_hash=hash_token(csrf_token),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(minutes=settings.session_idle_minutes),
        absolute_expires_at=now + timedelta(hours=settings.session_absolute_hours),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", "")[:500] or None,
    )
    db.add(user_session)
    add_audit_entry(
        db,
        actor_id=user.id,
        action="auth.login",
        entity_type="user",
        entity_id=str(user.id),
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    set_session_cookies(response, session_token, csrf_token)
    return SessionRead(
        user=user_read(
            user,
            customer_portal_restricted=is_customer_portal_restricted(db, user),
        ),
        password_change_required=user.force_password_change,
    )


@router.get("/auth/me", response_model=SessionRead)
def get_me(
    principal: Annotated[AuthPrincipal, Depends(get_auth_principal)],
) -> SessionRead:
    return SessionRead(
        user=user_read(
            principal.user,
            customer_portal_restricted=principal.customer_portal_restricted,
        ),
        password_change_required=principal.user.force_password_change,
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    principal: Annotated[AuthPrincipal, Depends(get_auth_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="auth.logout",
        entity_type="user",
        entity_id=str(principal.user.id),
        ip_address=request.client.host if request.client else None,
    )
    db.delete(principal.session)
    db.commit()
    clear_session_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


def session_read(session: UserSession, current_session_id: UUID) -> UserSessionRead:
    return UserSessionRead(
        id=session.id,
        created_at=session.created_at,
        last_seen_at=session.last_seen_at,
        expires_at=session.expires_at,
        absolute_expires_at=session.absolute_expires_at,
        ip_address=session.ip_address,
        user_agent=session.user_agent,
        is_current=session.id == current_session_id,
    )


@router.get("/auth/sessions", response_model=list[UserSessionRead])
def list_own_sessions(
    principal: Annotated[AuthPrincipal, Depends(get_auth_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[UserSessionRead]:
    now = datetime.now(UTC)
    sessions = db.scalars(
        select(UserSession)
        .where(
            UserSession.user_id == principal.user.id,
            UserSession.expires_at > now,
            UserSession.absolute_expires_at > now,
        )
        .order_by(UserSession.last_seen_at.desc())
    ).all()
    return [session_read(session, principal.session.id) for session in sessions]


@router.get("/users/{user_id}/sessions", response_model=list[UserSessionRead])
def list_user_sessions(
    user_id: UUID,
    _principal: Annotated[AuthPrincipal, Depends(require_permission("sessions.manage"))],
    db: Annotated[Session, Depends(get_db)],
) -> list[UserSessionRead]:
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")
    now = datetime.now(UTC)
    sessions = db.scalars(
        select(UserSession)
        .where(
            UserSession.user_id == user_id,
            UserSession.expires_at > now,
            UserSession.absolute_expires_at > now,
        )
        .order_by(UserSession.last_seen_at.desc())
    ).all()
    return [session_read(session, _principal.session.id) for session in sessions]


@router.delete("/auth/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    request: Request,
    response: Response,
    session_id: UUID,
    principal: Annotated[AuthPrincipal, Depends(get_auth_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    target = db.get(UserSession, session_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Sitzung nicht gefunden")
    if target.user_id != principal.user.id and "sessions.manage" not in principal.permission_codes:
        raise HTTPException(status_code=403, detail="Keine Berechtigung für diese Aktion")
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="auth.session_revoked",
        entity_type="user_session",
        entity_id=str(target.id),
        ip_address=request.client.host if request.client else None,
        details={"owner_id": str(target.user_id)},
    )
    is_current_session = target.id == principal.session.id
    db.delete(target)
    db.commit()
    if is_current_session:
        clear_session_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/auth/mfa", response_model=MFAStatusRead)
def get_mfa_status(
    principal: Annotated[AuthPrincipal, Depends(get_auth_principal)],
) -> MFAStatusRead:
    return MFAStatusRead(enabled=principal.user.mfa_enabled)


@router.post("/auth/mfa/setup", response_model=MFASetupRead)
@limiter.limit("5/minute")
def start_mfa_setup(
    request: Request,
    payload: MFASetupRequest,
    principal: Annotated[AuthPrincipal, Depends(get_auth_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> MFASetupRead:
    user = db.scalar(select(User).where(User.id == principal.user.id).with_for_update())
    if user.mfa_enabled:
        raise HTTPException(status_code=409, detail="MFA ist bereits aktiviert")
    if not password_hasher.verify(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Das aktuelle Passwort ist nicht korrekt")

    secret = new_totp_secret()
    user.mfa_secret_encrypted = encrypt_secret(secret)
    user.mfa_last_counter = None
    db.query(UserMFARecoveryCode).filter(UserMFARecoveryCode.user_id == user.id).delete(
        synchronize_session=False
    )
    add_audit_entry(
        db,
        actor_id=user.id,
        action="auth.mfa_setup_started",
        entity_type="user",
        entity_id=str(user.id),
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return MFASetupRead(
        secret=secret,
        otpauth_uri=provisioning_uri(secret, user.username),
    )


@router.post("/auth/mfa/enable", response_model=MFARecoveryCodesRead)
@limiter.limit("5/minute")
def enable_mfa(
    request: Request,
    payload: MFAEnableRequest,
    principal: Annotated[AuthPrincipal, Depends(get_auth_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> MFARecoveryCodesRead:
    user = db.scalar(select(User).where(User.id == principal.user.id).with_for_update())
    if user.mfa_enabled or user.mfa_secret_encrypted is None:
        raise HTTPException(status_code=409, detail="MFA-Einrichtung wurde nicht gestartet")
    secret = decrypt_secret(user.mfa_secret_encrypted)
    counter = verify_totp(secret, payload.code)
    if counter is None:
        raise HTTPException(status_code=400, detail="Der MFA-Code ist ungültig oder abgelaufen")

    recovery_codes = new_recovery_codes()
    user.mfa_enabled = True
    user.mfa_last_counter = counter
    db.add_all(
        [
            UserMFARecoveryCode(user_id=user.id, code_hash=recovery_code_hash(code))
            for code in recovery_codes
        ]
    )
    add_audit_entry(
        db,
        actor_id=user.id,
        action="auth.mfa_enabled",
        entity_type="user",
        entity_id=str(user.id),
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return MFARecoveryCodesRead(recovery_codes=recovery_codes)


@router.post("/auth/mfa/disable", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
def disable_mfa(
    request: Request,
    payload: MFADisableRequest,
    response: Response,
    principal: Annotated[AuthPrincipal, Depends(get_auth_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    user = db.scalar(select(User).where(User.id == principal.user.id).with_for_update())
    if not user.mfa_enabled or user.mfa_secret_encrypted is None:
        raise HTTPException(status_code=409, detail="MFA ist nicht aktiviert")
    if not password_hasher.verify(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Das aktuelle Passwort ist nicht korrekt")
    counter = verify_totp(
        decrypt_secret(user.mfa_secret_encrypted),
        payload.code,
        last_counter=user.mfa_last_counter,
    )
    if counter is None:
        raise HTTPException(
            status_code=400, detail="Der MFA-Code ist ungültig oder wurde bereits verwendet"
        )

    user.mfa_enabled = False
    user.mfa_secret_encrypted = None
    user.mfa_last_counter = None
    db.query(UserMFARecoveryCode).filter(UserMFARecoveryCode.user_id == user.id).delete(
        synchronize_session=False
    )
    add_audit_entry(
        db,
        actor_id=user.id,
        action="auth.mfa_disabled",
        entity_type="user",
        entity_id=str(user.id),
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/auth/change-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
def change_password(
    request: Request,
    response: Response,
    payload: PasswordChange,
    principal: Annotated[AuthPrincipal, Depends(get_auth_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    if not password_hasher.verify(payload.current_password, principal.user.password_hash):
        raise HTTPException(status_code=400, detail="Das aktuelle Passwort ist nicht korrekt")
    if payload.current_password == payload.new_password:
        raise HTTPException(
            status_code=422, detail="Das neue Passwort muss sich vom bisherigen unterscheiden"
        )

    principal.user.password_hash = password_hasher.hash(payload.new_password)
    principal.user.force_password_change = False
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="auth.password_changed",
        entity_type="user",
        entity_id=str(principal.user.id),
        ip_address=request.client.host if request.client else None,
    )
    db.query(UserSession).filter(UserSession.user_id == principal.user.id).delete(
        synchronize_session=False
    )
    db.commit()
    clear_session_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/roles", response_model=list[RoleRead])
def list_roles(
    _principal: Annotated[AuthPrincipal, Depends(require_permission("roles.read"))],
    db: Annotated[Session, Depends(get_db)],
) -> list[RoleRead]:
    roles = db.scalars(
        select(Role).options(selectinload(Role.permissions)).order_by(Role.name)
    ).all()
    return [
        RoleRead(
            id=role.id,
            code=role.code,
            name=role.name,
            description=role.description,
            permissions=sorted(permission.code for permission in role.permissions),
        )
        for role in roles
    ]


@router.get("/users", response_model=list[UserRead])
def list_users(
    principal: Annotated[AuthPrincipal, Depends(get_auth_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[UserRead]:
    if "users.read" not in principal.permission_codes:
        raise HTTPException(status_code=403, detail="Keine Berechtigung für diese Aktion")
    users = db.scalars(
        select(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .order_by(User.username)
    ).all()
    return [user_read(user) for user in users]


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    request: Request,
    payload: UserCreate,
    principal: Annotated[AuthPrincipal, Depends(get_auth_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> UserRead:
    if "users.manage" not in principal.permission_codes:
        raise HTTPException(status_code=403, detail="Keine Berechtigung für diese Aktion")
    normalized_codes = [code.strip().lower() for code in payload.role_codes]
    roles = db.scalars(
        select(Role).options(selectinload(Role.permissions)).where(Role.code.in_(normalized_codes))
    ).all()
    if len(roles) != len(normalized_codes):
        raise HTTPException(status_code=422, detail="Mindestens eine Rolle ist unbekannt")
    ensure_role_permissions_grantable(roles, principal)
    if (
        any(role.code == "administrator" for role in roles)
        and "users.manage_admin" not in principal.permission_codes
    ):
        raise HTTPException(
            status_code=403,
            detail="Nur Administratoren dürfen Administratorrechte vergeben",
        )

    user = User(
        username=payload.username.strip().lower(),
        email=str(payload.email).lower(),
        full_name=payload.full_name.strip(),
        password_hash=password_hasher.hash(payload.password),
        roles=roles,
    )
    db.add(user)
    try:
        db.flush()
        add_audit_entry(
            db,
            actor_id=principal.user.id,
            action="users.created",
            entity_type="user",
            entity_id=str(user.id),
            ip_address=request.client.host if request.client else None,
            details={"roles": normalized_codes},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Benutzername oder E-Mail-Adresse ist bereits vergeben",
        ) from exc

    created = db.scalar(
        select(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .where(User.id == user.id)
    )
    return user_read(created)


@router.post(
    "/users/{user_id}/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
)
@limiter.limit("5/minute")
def reset_user_password(
    request: Request,
    user_id: UUID,
    payload: AdminPasswordReset,
    principal: Annotated[AuthPrincipal, Depends(get_auth_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    if (
        "users.manage" not in principal.permission_codes
        or "users.password_reset" not in principal.permission_codes
    ):
        raise HTTPException(status_code=403, detail="Keine Berechtigung für diese Aktion")
    if user_id == principal.user.id:
        raise HTTPException(
            status_code=409,
            detail="Das eigene Passwort muss über die Passwortänderung geändert werden",
        )
    user = db.scalar(
        select(User).options(selectinload(User.roles)).where(User.id == user_id).with_for_update()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")
    if (
        any(role.code == "administrator" for role in user.roles)
        and "users.manage_admin" not in principal.permission_codes
    ):
        raise HTTPException(
            status_code=403,
            detail="Nur Administratoren dürfen das Passwort eines Administrators zurücksetzen",
        )

    user.password_hash = password_hasher.hash(payload.temporary_password)
    user.force_password_change = True
    revoked_sessions = (
        db.query(UserSession)
        .filter(UserSession.user_id == user.id)
        .delete(synchronize_session=False)
    )
    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="users.password_reset",
        entity_type="user",
        entity_id=str(user.id),
        ip_address=request.client.host if request.client else None,
        details={"force_password_change": True, "revoked_sessions": revoked_sessions},
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    request: Request,
    user_id: UUID,
    payload: UserUpdate,
    principal: Annotated[AuthPrincipal, Depends(get_auth_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> UserRead:
    if "users.manage" not in principal.permission_codes:
        raise HTTPException(status_code=403, detail="Keine Berechtigung für diese Aktion")
    if user_id == principal.user.id:
        raise HTTPException(
            status_code=409,
            detail="Das eigene Administratorkonto kann hier nicht geändert werden",
        )

    user = db.scalar(select(User).options(selectinload(User.roles)).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    changes = payload.model_dump(exclude_unset=True)
    new_roles = user.roles
    if "role_codes" in changes:
        role_codes = [code.strip().lower() for code in changes["role_codes"]]
        new_roles = db.scalars(
            select(Role).options(selectinload(Role.permissions)).where(Role.code.in_(role_codes))
        ).all()
        if len(new_roles) != len(role_codes):
            raise HTTPException(status_code=422, detail="Mindestens eine Rolle ist unbekannt")
        ensure_role_permissions_grantable(new_roles, principal)

    current_admin = any(role.code == "administrator" for role in user.roles)
    desired_admin = any(role.code == "administrator" for role in new_roles)
    if (current_admin or desired_admin) and "users.manage_admin" not in principal.permission_codes:
        raise HTTPException(
            status_code=403,
            detail="Nur Administratoren dürfen Administratorrechte ändern",
        )

    was_active_admin = user.is_active and current_admin
    will_be_active = changes.get("is_active", user.is_active)
    will_be_admin = any(role.code == "administrator" for role in new_roles)
    if was_active_admin and (not will_be_active or not will_be_admin):
        db.scalar(select(Role).where(Role.code == "administrator").with_for_update())
        admin_count = (
            db.scalar(
                select(func.count(User.id))
                .join(user_roles, user_roles.c.user_id == User.id)
                .join(Role, Role.id == user_roles.c.role_id)
                .where(User.is_active.is_(True), Role.code == "administrator")
            )
            or 0
        )
        if admin_count <= 1:
            raise HTTPException(
                status_code=409,
                detail="Der letzte aktive Administrator kann nicht deaktiviert oder herabgestuft werden",
            )

    if "is_active" in changes:
        if changes["is_active"] is None:
            raise HTTPException(status_code=422, detail="is_active darf nicht null sein")
        user.is_active = changes["is_active"]
    if "role_codes" in changes:
        user.roles = new_roles

    add_audit_entry(
        db,
        actor_id=principal.user.id,
        action="users.updated",
        entity_type="user",
        entity_id=str(user.id),
        ip_address=request.client.host if request.client else None,
        details={
            "active": user.is_active,
            "roles": sorted(role.code for role in user.roles),
        },
    )
    if not user.is_active:
        db.query(UserSession).filter(UserSession.user_id == user.id).delete(
            synchronize_session=False
        )
    db.commit()
    refreshed = db.scalar(
        select(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .where(User.id == user.id)
    )
    return user_read(refreshed)


@router.get("/audit-logs", response_model=list[AuditLogRead])
def list_audit_logs(
    principal: Annotated[AuthPrincipal, Depends(get_auth_principal)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = 50,
) -> list[AuditLogRead]:
    if "audit.read" not in principal.permission_codes:
        raise HTTPException(status_code=403, detail="Keine Berechtigung für diese Aktion")
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="Limit muss zwischen 1 und 100 liegen")
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all()
    return [AuditLogRead.model_validate(row) for row in rows]
