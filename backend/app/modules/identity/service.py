from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import ApiSettings
from app.core.errors import FoundationError
from app.core.http import check_if_match
from app.modules.identity.email import InvalidIdentityEmail, normalize_identity_email
from app.modules.identity.models import Session as SessionModel
from app.modules.identity.models import User
from app.modules.identity.passwords import (
    DUMMY_HASH,
    hash_password,
    needs_rehash,
    validate_permanent_password,
    verify_password,
)
from app.modules.identity.schemas import SessionData, UserCreate, UserData
from app.modules.timeline.service import append_event


@dataclass(frozen=True)
class IssuedSession:
    model: SessionModel
    raw_bearer: str


def user_data(user: User) -> UserData:
    return UserData(
        id=user.id,
        name=user.name,
        email=user.email_normalized,
        role=user.role,
        status=user.status,
        must_change_password=user.must_change_password,
        version=user.version,
    )


def bearer_hash(raw: str) -> bytes:
    return hashlib.sha256(raw.encode("ascii")).digest()


def is_active(model: SessionModel, now: datetime, idle_seconds: int) -> bool:
    return (
        model.revoked_at is None
        and now < model.absolute_expires_at
        and now < model.last_seen_at + timedelta(seconds=idle_seconds)
    )


def _issue_session(
    session: Session, user: User, now: datetime, settings: ApiSettings
) -> IssuedSession:
    idle_cutoff = now - timedelta(seconds=settings.SESSION_IDLE_SECONDS)
    active = list(
        session.execute(
            select(SessionModel)
            .where(
                SessionModel.user_id == user.id,
                SessionModel.revoked_at.is_(None),
                SessionModel.absolute_expires_at > now,
                SessionModel.last_seen_at > idle_cutoff,
            )
            .order_by(SessionModel.created_at, SessionModel.id)
            .with_for_update()
        ).scalars()
    )
    for previous in active[: max(0, len(active) - 4)]:
        previous.revoked_at = now
        previous.revocation_reason = "SESSION_LIMIT"
    raw = secrets.token_urlsafe(32)
    model = SessionModel(
        id=uuid4(),
        user_id=user.id,
        bearer_hash=bearer_hash(raw),
        created_at=now,
        last_seen_at=now,
        absolute_expires_at=now + timedelta(seconds=settings.SESSION_ABSOLUTE_SECONDS),
        revoked_at=None,
        revocation_reason=None,
    )
    session.add(model)
    return IssuedSession(model=model, raw_bearer=raw)


def _invalid_credentials() -> FoundationError:
    return FoundationError(
        status_code=401, code="INVALID_CREDENTIALS", message="E-mail ou senha inválidos."
    )


def authenticate(
    session: Session,
    *,
    email: str,
    password: str,
    now: datetime,
    settings: ApiSettings,
) -> tuple[User, IssuedSession]:
    try:
        normalized = normalize_identity_email(email)
    except InvalidIdentityEmail:
        verify_password(DUMMY_HASH, password)
        raise _invalid_credentials() from None
    user = session.execute(
        select(User).where(User.email_normalized == normalized).with_for_update()
    ).scalar_one_or_none()
    eligible = bool(
        user
        and user.status == "ACTIVE"
        and (
            not user.must_change_password
            or (
                user.temporary_password_expires_at is not None
                and now < user.temporary_password_expires_at
            )
        )
    )
    verified = verify_password(user.password_hash if eligible and user else DUMMY_HASH, password)
    if not eligible or user is None or not verified:
        session.rollback()
        raise _invalid_credentials()
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        user.updated_at = now
        user.version += 1
    issued = _issue_session(session, user, now, settings)
    session.commit()
    return user, issued


def session_data(
    user: User,
    model: SessionModel,
    now: datetime,
    settings: ApiSettings,
    csrf: str,
) -> SessionData:
    return SessionData(
        user=user_data(user),
        expires_at=model.absolute_expires_at,
        idle_expires_at=model.last_seen_at + timedelta(seconds=settings.SESSION_IDLE_SECONDS),
        csrf_token=csrf,
        server_now=now,
    )


def revoke_all(session: Session, user_id: UUID, now: datetime, reason: str) -> None:
    session.execute(
        update(SessionModel)
        .where(SessionModel.user_id == user_id, SessionModel.revoked_at.is_(None))
        .values(revoked_at=now, revocation_reason=reason)
    )


def create_technician(
    session: Session, *, data: UserCreate, actor: User, now: datetime
) -> tuple[User, str]:
    try:
        email = normalize_identity_email(data.email)
    except InvalidIdentityEmail as error:
        raise FoundationError(
            status_code=422, code="VALIDATION_ERROR", message="E-mail inválido."
        ) from error
    name = data.name.strip()
    if not name:
        raise FoundationError(
            status_code=422, code="VALIDATION_ERROR", message="Nome é obrigatório."
        )
    temporary = secrets.token_urlsafe(24)
    user = User(
        id=uuid4(),
        name=name,
        email_normalized=email,
        password_hash=hash_password(temporary),
        role="TECHNICIAN",
        status="ACTIVE",
        must_change_password=True,
        temporary_password_expires_at=now + timedelta(hours=24),
        password_changed_at=now,
        created_at=now,
        updated_at=now,
        version=1,
    )
    session.add(user)
    append_event(
        session,
        event_type="user.created",
        actor_type="USER",
        actor_user_id=actor.id,
        subject_user_id=user.id,
        payload={"role": user.role, "status": user.status},
        occurred_at=now,
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise FoundationError(
            status_code=409, code="ALREADY_EXISTS", message="E-mail já cadastrado."
        ) from error
    return user, temporary


def mutate_user(
    session: Session,
    *,
    target_id: UUID,
    actor: User,
    now: datetime,
    if_match: str | None,
    action: str,
    name: str | None = None,
) -> tuple[User, str | None]:
    if action == "disable":
        # A single transaction-scoped lock serializes all last-admin decisions,
        # including attempts that target different Admin rows.
        session.execute(select(func.pg_advisory_xact_lock(1431197002)))
    target = session.execute(
        select(User).where(User.id == target_id).with_for_update()
    ).scalar_one_or_none()
    if target is None:
        raise FoundationError(status_code=404, code="NOT_FOUND", message="Recurso não encontrado.")
    check_if_match(if_match, target.version)
    temporary: str | None = None
    event: str | None = None
    if action == "rename":
        if name is None:
            raise ValueError("name is required")
        normalized_name = name.strip()
        if not normalized_name:
            raise FoundationError(
                status_code=422, code="VALIDATION_ERROR", message="Nome é obrigatório."
            )
        if normalized_name == target.name:
            return target, None
        target.name = normalized_name
    elif action == "disable":
        if target.id == actor.id:
            raise FoundationError(
                status_code=409,
                code="INVALID_STATE",
                message="Você não pode desabilitar sua própria conta.",
            )
        if target.status == "DISABLED":
            return target, None
        if target.role == "ADMIN":
            count = session.scalar(
                select(func.count())
                .select_from(User)
                .where(User.role == "ADMIN", User.status == "ACTIVE")
            )
            if count == 1:
                raise FoundationError(
                    status_code=409,
                    code="LAST_ADMIN_REQUIRED",
                    message="É necessário manter um Admin ativo.",
                )
        target.status = "DISABLED"
        revoke_all(session, target.id, now, "USER_DISABLED")
        event = "user.disabled"
    elif action == "enable":
        if target.status == "ACTIVE":
            return target, None
        target.status = "ACTIVE"
        event = "user.enabled"
    elif action == "reset":
        if target.id == actor.id:
            raise FoundationError(
                status_code=409,
                code="INVALID_STATE",
                message="Use a troca de senha da própria conta.",
            )
        temporary = secrets.token_urlsafe(24)
        target.password_hash = hash_password(temporary)
        target.must_change_password = True
        target.temporary_password_expires_at = now + timedelta(hours=24)
        target.password_changed_at = now
        revoke_all(session, target.id, now, "PASSWORD_RESET")
        event = "user.password_reset"
    else:
        raise ValueError("unknown user action")
    target.updated_at = now
    target.version += 1
    if event:
        append_event(
            session,
            event_type=event,
            actor_type="USER",
            actor_user_id=actor.id,
            subject_user_id=target.id,
            payload={"role": target.role, "status": target.status},
            occurred_at=now,
        )
    session.commit()
    return target, temporary


def change_password(
    session: Session,
    *,
    user_id: UUID,
    current_password: str,
    new_password: str,
    now: datetime,
    settings: ApiSettings,
) -> tuple[User, IssuedSession]:
    user = session.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()
    if user.status != "ACTIVE" or not verify_password(user.password_hash, current_password):
        raise _invalid_credentials()
    try:
        validate_permanent_password(new_password, current=current_password)
    except ValueError as error:
        raise FoundationError(
            status_code=422, code="VALIDATION_ERROR", message=str(error)
        ) from error
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.temporary_password_expires_at = None
    user.password_changed_at = now
    user.updated_at = now
    user.version += 1
    revoke_all(session, user.id, now, "PASSWORD_CHANGED")
    issued = _issue_session(session, user, now, settings)
    append_event(
        session,
        event_type="user.password_changed",
        actor_type="USER",
        actor_user_id=user.id,
        subject_user_id=user.id,
        payload={"role": user.role, "status": user.status},
        occurred_at=now,
    )
    session.commit()
    return user, issued
