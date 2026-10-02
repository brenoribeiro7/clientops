from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.http import set_resource_headers
from app.core.security import require_trusted_origin, validate_csrf
from app.modules.business.schemas import BusinessProfilePatch, BusinessProfileResponse
from app.modules.business.service import get_profile, serialize, update_profile
from app.modules.identity.dependencies import AuthContext, require_admin

router = APIRouter(prefix="/api/v1/business-profile", tags=["business-profile"])

RESOURCE_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "headers": {
            "ETag": {"description": "Versão forte do perfil", "schema": {"type": "string"}},
            "Cache-Control": {"schema": {"type": "string", "example": "no-store"}},
        }
    }
}

Db = Annotated[Session, Depends(get_db)]
Admin = Annotated[AuthContext, Depends(require_admin)]
CsrfHeader = Annotated[str | None, Header(alias="X-CSRF-Token")]
IfMatchHeader = Annotated[str | None, Header(alias="If-Match")]


@router.get("", response_model=BusinessProfileResponse, responses=RESOURCE_RESPONSE)
def read_profile(
    request: Request,
    response: Response,
    db: Db,
    _: Admin,
) -> BusinessProfileResponse:
    profile = get_profile(db)
    set_resource_headers(response, profile.version)
    return BusinessProfileResponse(data=serialize(profile, request.app.state.clock.now_utc()))


@router.patch("", response_model=BusinessProfileResponse, responses=RESOURCE_RESPONSE)
def patch_profile(
    payload: BusinessProfilePatch,
    request: Request,
    response: Response,
    db: Db,
    context: Admin,
    if_match: IfMatchHeader = None,
    x_csrf_token: CsrfHeader = None,
) -> BusinessProfileResponse:
    require_trusted_origin(request)
    validate_csrf(request.app.state.settings, context.raw_bearer, x_csrf_token)
    profile = update_profile(
        db,
        patch=payload,
        if_match=if_match,
        actor_user_id=context.user.id,
        now=context.now,
    )
    set_resource_headers(response, profile.version)
    return BusinessProfileResponse(data=serialize(profile, context.now))
