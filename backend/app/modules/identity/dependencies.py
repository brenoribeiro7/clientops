from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyCookie
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import FoundationError
from app.core.rate_limits import PRIVATE_USER, consume
from app.core.security import raw_session_cookie
from app.modules.identity.models import Session as SessionModel
from app.modules.identity.models import User
from app.modules.identity.service import bearer_hash, is_active

documented_session_cookie = APIKeyCookie(
    name="__Host-clientops_session", scheme_name="cookieAuth", auto_error=False
)


@dataclass(frozen=True)
class AuthContext:
    session: SessionModel
    user: User
    raw_bearer: str
    now: datetime


def optional_context(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    _documented_cookie: Annotated[str | None, Security(documented_session_cookie)],
) -> AuthContext | None:
    raw = raw_session_cookie(request)
    if raw is None or len(raw) != 43:
        return None
    try:
        digest = bearer_hash(raw)
    except UnicodeEncodeError:
        return None
    model = db.execute(
        select(SessionModel).where(SessionModel.bearer_hash == digest)
    ).scalar_one_or_none()
    if model is None:
        return None
    user = db.get(User, model.user_id)
    now = request.app.state.clock.now_utc()
    settings = request.app.state.settings
    if (
        user is None
        or user.status != "ACTIVE"
        or not is_active(model, now, settings.SESSION_IDLE_SECONDS)
        or (
            user.must_change_password
            and (
                user.temporary_password_expires_at is None
                or now >= user.temporary_password_expires_at
            )
        )
    ):
        return None
    return AuthContext(model, user, raw, now)


def require_restricted(
    context: Annotated[AuthContext | None, Depends(optional_context)],
) -> AuthContext:
    if context is None:
        raise FoundationError(
            status_code=401,
            code="AUTHENTICATION_REQUIRED",
            message="Autenticação necessária.",
        )
    return context


def require_unrestricted(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    context: Annotated[AuthContext, Depends(require_restricted)],
) -> AuthContext:
    if context.user.must_change_password:
        raise FoundationError(
            status_code=403,
            code="PASSWORD_CHANGE_REQUIRED",
            message="Troque a senha temporária antes de continuar.",
        )
    factory = request.app.state.session_factory
    with factory() as limiter:
        consume(
            limiter,
            request.app.state.settings,
            PRIVATE_USER,
            str(context.user.id),
            context.now,
        )
    settings = request.app.state.settings
    threshold = context.now - timedelta(seconds=settings.SESSION_TOUCH_SECONDS)
    db.execute(
        update(SessionModel)
        .where(
            SessionModel.id == context.session.id,
            SessionModel.revoked_at.is_(None),
            SessionModel.absolute_expires_at > context.now,
            SessionModel.last_seen_at
            > context.now - timedelta(seconds=settings.SESSION_IDLE_SECONDS),
            SessionModel.last_seen_at <= threshold,
        )
        .values(last_seen_at=context.now)
    )
    db.commit()
    return context


def require_admin(
    context: Annotated[AuthContext, Depends(require_unrestricted)],
) -> AuthContext:
    if context.user.role != "ADMIN":
        raise FoundationError(status_code=403, code="FORBIDDEN", message="Acesso não permitido.")
    return context


def require_technician(
    context: Annotated[AuthContext, Depends(require_unrestricted)],
) -> AuthContext:
    if context.user.role != "TECHNICIAN":
        raise FoundationError(status_code=403, code="FORBIDDEN", message="Acesso não permitido.")
    return context
