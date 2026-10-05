from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.http import set_resource_headers
from app.core.security import require_trusted_origin, validate_csrf
from app.modules.clients import repository
from app.modules.clients.schemas import (
    ClientCreate,
    ClientPage,
    ClientPatch,
    ClientResponse,
    EmptyInput,
    EquipmentCreate,
    EquipmentPage,
    EquipmentPatch,
    EquipmentResponse,
    ListQuery,
    TimelinePage,
    TimelineQuery,
)
from app.modules.clients.service import (
    client_data,
    client_summary,
    create_client,
    create_equipment,
    equipment_data,
    equipment_summary,
    not_found,
    page_data,
    patch_client,
    patch_equipment,
    set_client_archived,
    set_equipment_archived,
    timeline_data,
)
from app.modules.identity.dependencies import AuthContext, require_admin

router = APIRouter(prefix="/api/v1/clients", tags=["clients"])

RESOURCE_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "headers": {
            "ETag": {"description": "Versão forte do recurso", "schema": {"type": "string"}},
            "Cache-Control": {"schema": {"type": "string", "example": "no-store"}},
        }
    }
}

Db = Annotated[Session, Depends(get_db)]
Admin = Annotated[AuthContext, Depends(require_admin)]
ListParams = Annotated[ListQuery, Query()]
TimelineParams = Annotated[TimelineQuery, Query()]
CsrfHeader = Annotated[str | None, Header(alias="X-CSRF-Token")]
IfMatchHeader = Annotated[str | None, Header(alias="If-Match")]


def _secure_mutation(request: Request, context: AuthContext, csrf: str | None) -> None:
    require_trusted_origin(request)
    validate_csrf(request.app.state.settings, context.raw_bearer, csrf)


@router.get("", response_model=ClientPage)
def clients(response: Response, db: Db, _: Admin, query: ListParams) -> ClientPage:
    models, total = repository.list_clients(
        db,
        page=query.page,
        page_size=query.page_size,
        status=query.status,
        q=query.q,
        sort=query.sort,
    )
    response.headers["Cache-Control"] = "no-store"
    return ClientPage(
        data=[client_summary(model) for model in models],
        page=page_data(query.page, query.page_size, total),
    )


@router.post("", response_model=ClientResponse, status_code=201)
def add_client(
    payload: ClientCreate,
    request: Request,
    response: Response,
    db: Db,
    context: Admin,
    x_csrf_token: CsrfHeader = None,
) -> ClientResponse:
    _secure_mutation(request, context, x_csrf_token)
    model = create_client(db, data=payload, actor_user_id=context.user.id, now=context.now)
    response.headers["Location"] = f"/api/v1/clients/{model.id}"
    set_resource_headers(response, model.version)
    return ClientResponse(data=client_data(model))


@router.get("/{client_id}", response_model=ClientResponse, responses=RESOURCE_RESPONSE)
def get_client(client_id: UUID, response: Response, db: Db, _: Admin) -> ClientResponse:
    model = repository.get_client(db, client_id)
    if model is None:
        raise not_found()
    set_resource_headers(response, model.version)
    return ClientResponse(data=client_data(model))


@router.patch("/{client_id}", response_model=ClientResponse, responses=RESOURCE_RESPONSE)
def update_client(
    client_id: UUID,
    payload: ClientPatch,
    request: Request,
    response: Response,
    db: Db,
    context: Admin,
    if_match: IfMatchHeader = None,
    x_csrf_token: CsrfHeader = None,
) -> ClientResponse:
    _secure_mutation(request, context, x_csrf_token)
    model = patch_client(
        db,
        client_id=client_id,
        patch=payload,
        if_match=if_match,
        actor_user_id=context.user.id,
        now=context.now,
    )
    set_resource_headers(response, model.version)
    return ClientResponse(data=client_data(model))


def _client_action(
    *,
    client_id: UUID,
    archived: bool,
    response: Response,
    db: Session,
    context: AuthContext,
    if_match: str | None,
) -> ClientResponse:
    model = set_client_archived(
        db,
        client_id=client_id,
        archived=archived,
        if_match=if_match,
        actor_user_id=context.user.id,
        now=context.now,
    )
    set_resource_headers(response, model.version)
    return ClientResponse(data=client_data(model))


@router.post("/{client_id}/archive", response_model=ClientResponse, responses=RESOURCE_RESPONSE)
def archive_client(
    client_id: UUID,
    payload: EmptyInput,
    request: Request,
    response: Response,
    db: Db,
    context: Admin,
    if_match: IfMatchHeader = None,
    x_csrf_token: CsrfHeader = None,
) -> ClientResponse:
    del payload
    _secure_mutation(request, context, x_csrf_token)
    return _client_action(
        client_id=client_id,
        archived=True,
        response=response,
        db=db,
        context=context,
        if_match=if_match,
    )


@router.post("/{client_id}/restore", response_model=ClientResponse, responses=RESOURCE_RESPONSE)
def restore_client(
    client_id: UUID,
    payload: EmptyInput,
    request: Request,
    response: Response,
    db: Db,
    context: Admin,
    if_match: IfMatchHeader = None,
    x_csrf_token: CsrfHeader = None,
) -> ClientResponse:
    del payload
    _secure_mutation(request, context, x_csrf_token)
    return _client_action(
        client_id=client_id,
        archived=False,
        response=response,
        db=db,
        context=context,
        if_match=if_match,
    )


@router.get("/{client_id}/timeline", response_model=TimelinePage)
def client_timeline(
    client_id: UUID, response: Response, db: Db, _: Admin, query: TimelineParams
) -> TimelinePage:
    if repository.get_client(db, client_id) is None:
        raise not_found()
    rows, total = repository.list_timeline(
        db, client_id=client_id, page=query.page, page_size=query.page_size
    )
    response.headers["Cache-Control"] = "no-store"
    return TimelinePage(
        data=[timeline_data(event, actor_name) for event, actor_name in rows],
        page=page_data(query.page, query.page_size, total),
    )


@router.get("/{client_id}/equipment", response_model=EquipmentPage)
def equipment(
    client_id: UUID, response: Response, db: Db, _: Admin, query: ListParams
) -> EquipmentPage:
    if repository.get_client(db, client_id) is None:
        raise not_found()
    models, total = repository.list_equipment(
        db,
        client_id=client_id,
        page=query.page,
        page_size=query.page_size,
        status=query.status,
        q=query.q,
        sort=query.sort,
    )
    response.headers["Cache-Control"] = "no-store"
    return EquipmentPage(
        data=[equipment_summary(model) for model in models],
        page=page_data(query.page, query.page_size, total),
    )


@router.post("/{client_id}/equipment", response_model=EquipmentResponse, status_code=201)
def add_equipment(
    client_id: UUID,
    payload: EquipmentCreate,
    request: Request,
    response: Response,
    db: Db,
    context: Admin,
    x_csrf_token: CsrfHeader = None,
) -> EquipmentResponse:
    _secure_mutation(request, context, x_csrf_token)
    model = create_equipment(
        db, client_id=client_id, data=payload, actor_user_id=context.user.id, now=context.now
    )
    response.headers["Location"] = f"/api/v1/clients/{client_id}/equipment/{model.id}"
    set_resource_headers(response, model.version)
    return EquipmentResponse(data=equipment_data(model))


@router.get(
    "/{client_id}/equipment/{equipment_id}",
    response_model=EquipmentResponse,
    responses=RESOURCE_RESPONSE,
)
def get_equipment(
    client_id: UUID, equipment_id: UUID, response: Response, db: Db, _: Admin
) -> EquipmentResponse:
    model = repository.get_equipment(db, client_id=client_id, equipment_id=equipment_id)
    if model is None:
        raise not_found()
    set_resource_headers(response, model.version)
    return EquipmentResponse(data=equipment_data(model))


@router.patch(
    "/{client_id}/equipment/{equipment_id}",
    response_model=EquipmentResponse,
    responses=RESOURCE_RESPONSE,
)
def update_equipment(
    client_id: UUID,
    equipment_id: UUID,
    payload: EquipmentPatch,
    request: Request,
    response: Response,
    db: Db,
    context: Admin,
    if_match: IfMatchHeader = None,
    x_csrf_token: CsrfHeader = None,
) -> EquipmentResponse:
    _secure_mutation(request, context, x_csrf_token)
    model = patch_equipment(
        db,
        client_id=client_id,
        equipment_id=equipment_id,
        patch=payload,
        if_match=if_match,
        actor_user_id=context.user.id,
        now=context.now,
    )
    set_resource_headers(response, model.version)
    return EquipmentResponse(data=equipment_data(model))


def _equipment_action(
    *,
    client_id: UUID,
    equipment_id: UUID,
    archived: bool,
    response: Response,
    db: Session,
    context: AuthContext,
    if_match: str | None,
) -> EquipmentResponse:
    model = set_equipment_archived(
        db,
        client_id=client_id,
        equipment_id=equipment_id,
        archived=archived,
        if_match=if_match,
        actor_user_id=context.user.id,
        now=context.now,
    )
    set_resource_headers(response, model.version)
    return EquipmentResponse(data=equipment_data(model))


@router.post(
    "/{client_id}/equipment/{equipment_id}/archive",
    response_model=EquipmentResponse,
    responses=RESOURCE_RESPONSE,
)
def archive_equipment(
    client_id: UUID,
    equipment_id: UUID,
    payload: EmptyInput,
    request: Request,
    response: Response,
    db: Db,
    context: Admin,
    if_match: IfMatchHeader = None,
    x_csrf_token: CsrfHeader = None,
) -> EquipmentResponse:
    del payload
    _secure_mutation(request, context, x_csrf_token)
    return _equipment_action(
        client_id=client_id,
        equipment_id=equipment_id,
        archived=True,
        response=response,
        db=db,
        context=context,
        if_match=if_match,
    )


@router.post(
    "/{client_id}/equipment/{equipment_id}/restore",
    response_model=EquipmentResponse,
    responses=RESOURCE_RESPONSE,
)
def restore_equipment(
    client_id: UUID,
    equipment_id: UUID,
    payload: EmptyInput,
    request: Request,
    response: Response,
    db: Db,
    context: Admin,
    if_match: IfMatchHeader = None,
    x_csrf_token: CsrfHeader = None,
) -> EquipmentResponse:
    del payload
    _secure_mutation(request, context, x_csrf_token)
    return _equipment_action(
        client_id=client_id,
        equipment_id=equipment_id,
        archived=False,
        response=response,
        db=db,
        context=context,
        if_match=if_match,
    )
