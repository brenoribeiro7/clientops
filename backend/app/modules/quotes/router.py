from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import ErrorResponse, FoundationError
from app.core.http import set_resource_headers
from app.core.rate_limits import (
    PUBLIC_QUOTE_APPROVE_BEARER,
    PUBLIC_QUOTE_APPROVE_INSTALLATION,
    PUBLIC_QUOTE_APPROVE_IP,
    PUBLIC_QUOTE_GET_BEARER,
    PUBLIC_QUOTE_GET_INSTALLATION,
    PUBLIC_QUOTE_GET_IP,
    RateRule,
    consume,
)
from app.core.security import require_trusted_origin, validate_csrf
from app.modules.identity.dependencies import (
    AuthContext,
    require_admin,
    revalidate_private_command,
)
from app.modules.quotes import repository
from app.modules.quotes.schemas import (
    ApproveInput,
    CancelInput,
    EmptyInput,
    IssuedPublicAccess,
    PublicAccessIssuedResponse,
    PublicAccessResponse,
    PublicApprovalResponse,
    PublicQuoteResponse,
    QuoteCreate,
    QuoteIssuedResponse,
    QuoteListQuery,
    QuotePage,
    QuotePatch,
    QuoteResponse,
    RotateInput,
    TimelinePage,
    TimelineQuery,
)
from app.modules.quotes.service import (
    approve_quote,
    business_today_for_read,
    cancel_quote,
    create_quote,
    duplicate_quote,
    not_found,
    page_data,
    parse_public_bearer,
    patch_quote,
    public_access_data,
    public_quote,
    quote_detail,
    quote_summary,
    revoke_access,
    rotate_access,
    send_quote,
    timeline_data,
)

router = APIRouter(prefix="/api/v1/quotes", tags=["quotes"])
public_router = APIRouter(prefix="/api/v1/public", tags=["public-quotes"])

documented_public_bearer = HTTPBearer(scheme_name="bearerAuth", auto_error=False)

RESOURCE_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "headers": {
            "ETag": {"description": "Versão forte do orçamento", "schema": {"type": "string"}},
            "Cache-Control": {"schema": {"type": "string", "example": "no-store"}},
        }
    }
}
RATE_LIMIT_RESPONSE = {
    "model": ErrorResponse,
    "headers": {
        "Retry-After": {"description": "Segundos até nova tentativa", "schema": {"type": "string"}}
    },
}

Db = Annotated[Session, Depends(get_db)]
Admin = Annotated[AuthContext, Depends(require_admin)]
ListParams = Annotated[QuoteListQuery, Query()]
TimelineParams = Annotated[TimelineQuery, Query()]
CsrfHeader = Annotated[str | None, Header(alias="X-CSRF-Token")]
IfMatchHeader = Annotated[str | None, Header(alias="If-Match")]
PublicBearer = Annotated[
    HTTPAuthorizationCredentials | None,
    Security(documented_public_bearer),
]


def _secure_mutation(request: Request, context: AuthContext, csrf: str | None) -> None:
    require_trusted_origin(request)
    validate_csrf(request.app.state.settings, context.raw_bearer, csrf)


def _require_json(request: Request) -> None:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip()
    if content_type != "application/json":
        raise FoundationError(
            status_code=415,
            code="UNSUPPORTED_MEDIA_TYPE",
            message="Use application/json.",
        )


def _reauthorize(request: Request, db: Session, context: AuthContext) -> None:
    revalidate_private_command(
        request,
        db,
        context,
        consume_rate_limit=False,
        touch_session=False,
    )


def _consume(request: Request, rule: RateRule, key: str, now: datetime) -> None:
    try:
        with request.app.state.session_factory() as limiter:
            consume(limiter, request.app.state.settings, rule, key, now)
    except FoundationError:
        raise
    except SQLAlchemyError as error:
        raise FoundationError(
            status_code=503,
            code="TEMPORARILY_UNAVAILABLE",
            message="Serviço temporariamente indisponível.",
        ) from error


def _network_key(request: Request) -> str:
    client_ip = getattr(request.state, "client_ip", None)
    if client_ip is None:
        raise FoundationError(
            status_code=400,
            code="MALFORMED_REQUEST",
            message="Origem de rede inválida.",
        )
    return str(client_ip)


def _raw_public_bearer(request: Request) -> str | None:
    value = request.headers.get("authorization")
    if value is None:
        return None
    pieces = value.split(" ")
    if len(pieces) != 2 or pieces[0] != "Bearer" or not pieces[1]:
        return None
    return pieces[1]


def _public_digest(
    request: Request,
    now: datetime,
    *,
    installation_rule: RateRule,
    ip_rule: RateRule,
    bearer_rule: RateRule,
) -> bytes:
    _consume(request, installation_rule, "installation", now)
    _consume(request, ip_rule, _network_key(request), now)
    _, digest = parse_public_bearer(_raw_public_bearer(request))
    _consume(request, bearer_rule, digest.hex(), now)
    return digest


@router.get("", response_model=QuotePage)
def quotes(response: Response, db: Db, context: Admin, query: ListParams) -> QuotePage:
    today = business_today_for_read(db, context.now)
    if query.is_expired is not None and today is None:
        raise FoundationError(
            status_code=409,
            code="BUSINESS_PROFILE_INCOMPLETE",
            message="Configure o timezone da empresa.",
            details={"missing_fields": ["timezone"]},
        )
    models, total = repository.list_quotes(
        db,
        page=query.page,
        page_size=query.page_size,
        status=query.status,
        client_id=query.client_id,
        expired=query.is_expired,
        today=today,
        q=query.q,
        sort=query.sort,
    )
    response.headers["Cache-Control"] = "no-store"
    return QuotePage(
        data=[quote_summary(model, today) for model in models],
        page=page_data(query.page, query.page_size, total),
    )


@router.post("", response_model=QuoteResponse, status_code=201)
def add_quote(
    payload: QuoteCreate,
    request: Request,
    response: Response,
    db: Db,
    context: Admin,
    _json: Annotated[None, Depends(_require_json)],
    x_csrf_token: CsrfHeader = None,
) -> QuoteResponse:
    _secure_mutation(request, context, x_csrf_token)
    model = create_quote(
        db,
        data=payload,
        actor_user_id=context.user.id,
        now=context.now,
        reauthorize=lambda: _reauthorize(request, db, context),
    )
    response.headers["Location"] = f"/api/v1/quotes/{model.id}"
    set_resource_headers(response, model.version)
    return QuoteResponse(data=quote_detail(model, None))


@router.get("/{quote_id}", response_model=QuoteResponse, responses=RESOURCE_RESPONSE)
def get_quote(quote_id: UUID, response: Response, db: Db, context: Admin) -> QuoteResponse:
    model = repository.get_quote(db, quote_id)
    if model is None:
        raise not_found()
    set_resource_headers(response, model.version)
    return QuoteResponse(data=quote_detail(model, business_today_for_read(db, context.now)))


@router.patch("/{quote_id}", response_model=QuoteResponse, responses=RESOURCE_RESPONSE)
def update_quote(
    quote_id: UUID,
    payload: QuotePatch,
    request: Request,
    response: Response,
    db: Db,
    context: Admin,
    _json: Annotated[None, Depends(_require_json)],
    if_match: IfMatchHeader = None,
    x_csrf_token: CsrfHeader = None,
) -> QuoteResponse:
    _secure_mutation(request, context, x_csrf_token)
    model = patch_quote(
        db,
        quote_id=quote_id,
        patch=payload,
        if_match=if_match,
        actor_user_id=context.user.id,
        now=context.now,
        reauthorize=lambda: _reauthorize(request, db, context),
    )
    set_resource_headers(response, model.version)
    return QuoteResponse(data=quote_detail(model, None))


@router.post("/{quote_id}/send", response_model=QuoteIssuedResponse)
def issue_quote(
    quote_id: UUID,
    payload: EmptyInput,
    request: Request,
    response: Response,
    db: Db,
    context: Admin,
    _json: Annotated[None, Depends(_require_json)],
    if_match: IfMatchHeader = None,
    x_csrf_token: CsrfHeader = None,
) -> QuoteIssuedResponse:
    del payload
    _secure_mutation(request, context, x_csrf_token)
    model, issued, today = send_quote(
        db,
        quote_id=quote_id,
        if_match=if_match,
        actor_user_id=context.user.id,
        now=context.now,
        settings=request.app.state.settings,
        reauthorize=lambda: _reauthorize(request, db, context),
    )
    set_resource_headers(response, model.version)
    return QuoteIssuedResponse(
        data=quote_detail(model, today),
        public_access=IssuedPublicAccess(
            **public_access_data(issued.model).model_dump(), share_url=issued.share_url
        ),
    )


@router.post("/{quote_id}/cancel", response_model=QuoteResponse, responses=RESOURCE_RESPONSE)
def cancel(
    quote_id: UUID,
    payload: CancelInput,
    request: Request,
    response: Response,
    db: Db,
    context: Admin,
    _json: Annotated[None, Depends(_require_json)],
    if_match: IfMatchHeader = None,
    x_csrf_token: CsrfHeader = None,
) -> QuoteResponse:
    _secure_mutation(request, context, x_csrf_token)
    model = cancel_quote(
        db,
        quote_id=quote_id,
        reason=payload.reason,
        if_match=if_match,
        actor_user_id=context.user.id,
        now=context.now,
        reauthorize=lambda: _reauthorize(request, db, context),
    )
    set_resource_headers(response, model.version)
    return QuoteResponse(data=quote_detail(model, None))


@router.post("/{quote_id}/duplicate", response_model=QuoteResponse, status_code=201)
def duplicate(
    quote_id: UUID,
    payload: EmptyInput,
    request: Request,
    response: Response,
    db: Db,
    context: Admin,
    _json: Annotated[None, Depends(_require_json)],
    x_csrf_token: CsrfHeader = None,
) -> QuoteResponse:
    del payload
    _secure_mutation(request, context, x_csrf_token)
    model = duplicate_quote(
        db,
        quote_id=quote_id,
        actor_user_id=context.user.id,
        now=context.now,
        reauthorize=lambda: _reauthorize(request, db, context),
    )
    response.headers["Location"] = f"/api/v1/quotes/{model.id}"
    set_resource_headers(response, model.version)
    return QuoteResponse(data=quote_detail(model, None))


@router.post("/{quote_id}/public-access", response_model=PublicAccessIssuedResponse)
def rotate_public_access(
    quote_id: UUID,
    payload: RotateInput,
    request: Request,
    response: Response,
    db: Db,
    context: Admin,
    _json: Annotated[None, Depends(_require_json)],
    x_csrf_token: CsrfHeader = None,
) -> PublicAccessIssuedResponse:
    _secure_mutation(request, context, x_csrf_token)
    issued = rotate_access(
        db,
        quote_id=quote_id,
        expected_access_id=payload.expected_access_id,
        actor_user_id=context.user.id,
        now=context.now,
        settings=request.app.state.settings,
        reauthorize=lambda: _reauthorize(request, db, context),
    )
    response.headers["Cache-Control"] = "no-store"
    return PublicAccessIssuedResponse(
        data=IssuedPublicAccess(
            **public_access_data(issued.model).model_dump(), share_url=issued.share_url
        )
    )


@router.post(
    "/{quote_id}/public-access/{access_id}/revoke",
    response_model=PublicAccessResponse,
)
def revoke_public_access(
    quote_id: UUID,
    access_id: UUID,
    payload: EmptyInput,
    request: Request,
    response: Response,
    db: Db,
    context: Admin,
    _json: Annotated[None, Depends(_require_json)],
    x_csrf_token: CsrfHeader = None,
) -> PublicAccessResponse:
    del payload
    _secure_mutation(request, context, x_csrf_token)
    model = revoke_access(
        db,
        quote_id=quote_id,
        access_id=access_id,
        actor_user_id=context.user.id,
        now=context.now,
        reauthorize=lambda: _reauthorize(request, db, context),
    )
    response.headers["Cache-Control"] = "no-store"
    return PublicAccessResponse(data=public_access_data(model))


@router.get("/{quote_id}/logo", status_code=404)
def quote_logo(quote_id: UUID, db: Db, _: Admin) -> None:
    if repository.get_quote(db, quote_id) is None:
        raise not_found()
    raise not_found()


@router.get("/{quote_id}/timeline", response_model=TimelinePage)
def quote_timeline(
    quote_id: UUID,
    response: Response,
    db: Db,
    _: Admin,
    query: TimelineParams,
) -> TimelinePage:
    if repository.get_quote_identity(db, quote_id) is None:
        raise not_found()
    rows, total = repository.list_timeline(
        db,
        quote_id=quote_id,
        page=query.page,
        page_size=query.page_size,
    )
    response.headers["Cache-Control"] = "no-store"
    return TimelinePage(
        data=[timeline_data(event, name) for event, name in rows],
        page=page_data(query.page, query.page_size, total),
    )


@public_router.get(
    "/quote",
    response_model=PublicQuoteResponse,
    responses={401: {"model": ErrorResponse}, 429: RATE_LIMIT_RESPONSE},
)
def read_public_quote(
    request: Request,
    response: Response,
    db: Db,
    _: PublicBearer,
) -> PublicQuoteResponse:
    now = request.app.state.clock.now_utc()
    digest = _public_digest(
        request,
        now,
        installation_rule=PUBLIC_QUOTE_GET_INSTALLATION,
        ip_rule=PUBLIC_QUOTE_GET_IP,
        bearer_rule=PUBLIC_QUOTE_GET_BEARER,
    )
    response.headers["Cache-Control"] = "no-store"
    return PublicQuoteResponse(data=public_quote(db, digest=digest, now=now))


@public_router.get(
    "/quote/logo",
    status_code=404,
    responses={401: {"model": ErrorResponse}, 429: RATE_LIMIT_RESPONSE},
)
def public_quote_logo(request: Request, db: Db, _: PublicBearer) -> None:
    now = request.app.state.clock.now_utc()
    digest = _public_digest(
        request,
        now,
        installation_rule=PUBLIC_QUOTE_GET_INSTALLATION,
        ip_rule=PUBLIC_QUOTE_GET_IP,
        bearer_rule=PUBLIC_QUOTE_GET_BEARER,
    )
    public_quote(db, digest=digest, now=now)
    raise not_found()


@public_router.post(
    "/quote/approve",
    response_model=PublicApprovalResponse,
    responses={401: {"model": ErrorResponse}, 429: RATE_LIMIT_RESPONSE},
)
def approve_public_quote(
    payload: ApproveInput,
    request: Request,
    response: Response,
    db: Db,
    _json: Annotated[None, Depends(_require_json)],
    _: PublicBearer,
) -> PublicApprovalResponse:
    del payload
    now = request.app.state.clock.now_utc()
    digest = _public_digest(
        request,
        now,
        installation_rule=PUBLIC_QUOTE_APPROVE_INSTALLATION,
        ip_rule=PUBLIC_QUOTE_APPROVE_IP,
        bearer_rule=PUBLIC_QUOTE_APPROVE_BEARER,
    )
    require_trusted_origin(request)
    response.headers["Cache-Control"] = "no-store"
    return PublicApprovalResponse(data=approve_quote(db, digest=digest, now=now))
