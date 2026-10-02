from __future__ import annotations

from math import ceil
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import ErrorResponse, FoundationError
from app.core.http import set_resource_headers
from app.core.rate_limits import LOGIN_EMAIL, LOGIN_INSTALLATION, LOGIN_IP, RESET_ADMIN, consume
from app.core.security import (
    clear_session_cookie,
    csrf_token,
    require_trusted_origin,
    set_session_cookie,
    validate_csrf,
)
from app.modules.identity.dependencies import (
    AuthContext,
    optional_context,
    require_admin,
    require_restricted,
)
from app.modules.identity.email import InvalidIdentityEmail, normalize_identity_email
from app.modules.identity.models import Session as SessionModel
from app.modules.identity.models import User
from app.modules.identity.schemas import (
    ChangePasswordInput,
    EmptyInput,
    LoginInput,
    SessionResponse,
    UserCreate,
    UserPage,
    UserPatch,
    UserResponse,
    UserSecretResponse,
)
from app.modules.identity.service import (
    authenticate,
    change_password,
    create_technician,
    mutate_user,
    session_data,
    user_data,
)

router = APIRouter(prefix="/api/v1", tags=["identity"])

ETAG_RESPONSE = {
    "headers": {
        "ETag": {"description": "Versão forte do recurso", "schema": {"type": "string"}},
        "Cache-Control": {"schema": {"type": "string", "example": "no-store"}},
    }
}
RATE_LIMIT_RESPONSE = {
    "model": ErrorResponse,
    "headers": {
        "Retry-After": {"description": "Segundos até nova tentativa", "schema": {"type": "string"}}
    },
}

Db = Annotated[Session, Depends(get_db)]
Restricted = Annotated[AuthContext, Depends(require_restricted)]
OptionalAuth = Annotated[AuthContext | None, Depends(optional_context)]
Admin = Annotated[AuthContext, Depends(require_admin)]
CsrfHeader = Annotated[str | None, Header(alias="X-CSRF-Token")]
IfMatchHeader = Annotated[str | None, Header(alias="If-Match")]


def _require_mutation_security(
    request: Request, context: AuthContext, supplied_csrf: str | None
) -> None:
    require_trusted_origin(request)
    validate_csrf(request.app.state.settings, context.raw_bearer, supplied_csrf)


def _consume(request: Request, rule: object, key: str, now: object) -> None:
    try:
        with request.app.state.session_factory() as limiter:
            consume(limiter, request.app.state.settings, rule, key, now)  # type: ignore[arg-type]
    except FoundationError:
        raise
    except SQLAlchemyError as error:
        raise FoundationError(
            status_code=503,
            code="TEMPORARILY_UNAVAILABLE",
            message="Serviço temporariamente indisponível.",
        ) from error


@router.post(
    "/auth/login",
    response_model=SessionResponse,
    responses={401: {"model": ErrorResponse}, 429: RATE_LIMIT_RESPONSE},
)
def login(payload: LoginInput, request: Request, response: Response, db: Db) -> SessionResponse:
    require_trusted_origin(request)
    if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
        raise FoundationError(
            status_code=415, code="UNSUPPORTED_MEDIA_TYPE", message="Use application/json."
        )
    if request.headers.get("x-clientops-request") != "browser-v1":
        raise FoundationError(
            status_code=403, code="ORIGIN_REJECTED", message="Cabeçalho do cliente ausente."
        )
    client_ip = getattr(request.state, "client_ip", None)
    if client_ip is None:
        raise FoundationError(
            status_code=400, code="MALFORMED_REQUEST", message="Origem de rede inválida."
        )
    now = request.app.state.clock.now_utc()
    _consume(request, LOGIN_INSTALLATION, "installation", now)
    _consume(request, LOGIN_IP, client_ip, now)
    try:
        normalized = normalize_identity_email(payload.email)
    except InvalidIdentityEmail:
        normalized = "invalid-login"
    _consume(request, LOGIN_EMAIL, normalized, now)
    user, issued = authenticate(
        db,
        email=payload.email,
        password=payload.password,
        now=now,
        settings=request.app.state.settings,
    )
    token = csrf_token(request.app.state.settings, issued.raw_bearer)
    set_session_cookie(response, request.app.state.settings, issued.raw_bearer)
    response.headers["Cache-Control"] = "no-store"
    return SessionResponse(
        data=session_data(user, issued.model, now, request.app.state.settings, token)
    )


@router.get("/auth/session", response_model=SessionResponse)
def current_session(request: Request, response: Response, context: Restricted) -> SessionResponse:
    response.headers["Cache-Control"] = "no-store"
    token = csrf_token(request.app.state.settings, context.raw_bearer)
    return SessionResponse(
        data=session_data(
            context.user, context.session, context.now, request.app.state.settings, token
        )
    )


@router.post("/auth/change-password", response_model=SessionResponse)
def password_change(
    payload: ChangePasswordInput,
    request: Request,
    response: Response,
    db: Db,
    context: Restricted,
    x_csrf_token: str | None = Header(default=None),
) -> SessionResponse:
    require_trusted_origin(request)
    validate_csrf(request.app.state.settings, context.raw_bearer, x_csrf_token)
    user, issued = change_password(
        db,
        user_id=context.user.id,
        current_password=payload.current_password,
        new_password=payload.new_password,
        now=context.now,
        settings=request.app.state.settings,
    )
    token = csrf_token(request.app.state.settings, issued.raw_bearer)
    set_session_cookie(response, request.app.state.settings, issued.raw_bearer)
    response.headers["Cache-Control"] = "no-store"
    return SessionResponse(
        data=session_data(user, issued.model, context.now, request.app.state.settings, token)
    )


@router.post("/auth/logout", status_code=204)
def logout(
    payload: EmptyInput,
    request: Request,
    response: Response,
    db: Db,
    context: OptionalAuth,
    x_csrf_token: str | None = Header(default=None),
) -> None:
    del payload
    require_trusted_origin(request)
    if context is not None:
        validate_csrf(request.app.state.settings, context.raw_bearer, x_csrf_token)
        model = db.get(SessionModel, context.session.id, with_for_update=True)
        if model and model.revoked_at is None:
            model.revoked_at = context.now
            model.revocation_reason = "LOGOUT"
            db.commit()
    elif request.headers.get("x-clientops-request") != "browser-v1":
        raise FoundationError(
            status_code=403, code="ORIGIN_REJECTED", message="Cabeçalho do cliente ausente."
        )
    clear_session_cookie(response, request.app.state.settings)


@router.get("/users", response_model=UserPage)
def list_users(
    response: Response,
    db: Db,
    _: Admin,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = None,
    role: str | None = None,
    q: str | None = Query(default=None, min_length=2, max_length=100),
) -> UserPage:
    response.headers["Cache-Control"] = "no-store"
    conditions = []
    if status:
        conditions.append(User.status == status)
    if role:
        conditions.append(User.role == role)
    if q:
        conditions.append(
            User.name.ilike(f"%{q.replace('%', r'\%').replace('_', r'\_')}%", escape="\\")
        )
    total = db.scalar(select(func.count()).select_from(User).where(*conditions)) or 0
    users = list(
        db.execute(
            select(User)
            .where(*conditions)
            .order_by(User.name, User.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars()
    )
    return UserPage(
        data=[user_data(user) for user in users],
        page={
            "number": page,
            "size": page_size,
            "total": total,
            "total_pages": ceil(total / page_size) if total else 0,
        },
    )


@router.post("/users", response_model=UserSecretResponse, status_code=201)
def add_user(
    payload: UserCreate,
    request: Request,
    response: Response,
    db: Db,
    context: Admin,
    x_csrf_token: CsrfHeader = None,
) -> UserSecretResponse:
    _require_mutation_security(request, context, x_csrf_token)
    user, temporary = create_technician(db, data=payload, actor=context.user, now=context.now)
    response.headers["Location"] = f"/api/v1/users/{user.id}"
    response.headers["Cache-Control"] = "no-store"
    return UserSecretResponse(data=user_data(user), temporary_password=temporary)


@router.get("/users/{user_id}", response_model=UserResponse, responses={200: ETAG_RESPONSE})
def get_user(
    user_id: UUID,
    response: Response,
    db: Db,
    _: Admin,
) -> UserResponse:
    user = db.get(User, user_id)
    if user is None:
        raise FoundationError(status_code=404, code="NOT_FOUND", message="Recurso não encontrado.")
    set_resource_headers(response, user.version)
    return UserResponse(data=user_data(user))


def _user_action(
    action: str,
    user_id: UUID,
    response: Response,
    db: Session,
    context: AuthContext,
    if_match: str | None,
    name: str | None = None,
) -> tuple[User, str | None]:
    user, temporary = mutate_user(
        db,
        target_id=user_id,
        actor=context.user,
        now=context.now,
        if_match=if_match,
        action=action,
        name=name,
    )
    set_resource_headers(response, user.version)
    return user, temporary


@router.patch("/users/{user_id}", response_model=UserResponse, responses={200: ETAG_RESPONSE})
def patch_user(
    user_id: UUID,
    payload: UserPatch,
    request: Request,
    response: Response,
    db: Db,
    context: Admin,
    if_match: IfMatchHeader = None,
    x_csrf_token: CsrfHeader = None,
) -> UserResponse:
    _require_mutation_security(request, context, x_csrf_token)
    user, _ = _user_action("rename", user_id, response, db, context, if_match, payload.name)
    return UserResponse(data=user_data(user))


@router.post(
    "/users/{user_id}/disable", response_model=UserResponse, responses={200: ETAG_RESPONSE}
)
def disable_user(
    user_id: UUID,
    payload: EmptyInput,
    request: Request,
    response: Response,
    db: Db,
    context: Admin,
    if_match: IfMatchHeader = None,
    x_csrf_token: CsrfHeader = None,
) -> UserResponse:
    del payload
    _require_mutation_security(request, context, x_csrf_token)
    user, _ = _user_action("disable", user_id, response, db, context, if_match)
    return UserResponse(data=user_data(user))


@router.post("/users/{user_id}/enable", response_model=UserResponse, responses={200: ETAG_RESPONSE})
def enable_user(
    user_id: UUID,
    payload: EmptyInput,
    request: Request,
    response: Response,
    db: Db,
    context: Admin,
    if_match: IfMatchHeader = None,
    x_csrf_token: CsrfHeader = None,
) -> UserResponse:
    del payload
    _require_mutation_security(request, context, x_csrf_token)
    user, _ = _user_action("enable", user_id, response, db, context, if_match)
    return UserResponse(data=user_data(user))


@router.post(
    "/users/{user_id}/reset-password",
    response_model=UserSecretResponse,
    responses={200: ETAG_RESPONSE, 429: RATE_LIMIT_RESPONSE},
)
def reset_user(
    user_id: UUID,
    payload: EmptyInput,
    request: Request,
    response: Response,
    db: Db,
    context: Admin,
    if_match: IfMatchHeader = None,
    x_csrf_token: CsrfHeader = None,
) -> UserSecretResponse:
    del payload
    _require_mutation_security(request, context, x_csrf_token)
    _consume(request, RESET_ADMIN, str(context.user.id), context.now)
    user, temporary = _user_action("reset", user_id, response, db, context, if_match)
    response.headers["Cache-Control"] = "no-store"
    if temporary is None:
        raise RuntimeError("reset did not issue temporary password")
    return UserSecretResponse(data=user_data(user), temporary_password=temporary)
