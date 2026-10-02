from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import FoundationError
from app.core.http import check_if_match
from app.modules.business.models import BusinessProfile
from app.modules.business.schemas import BusinessProfileData, BusinessProfilePatch
from app.modules.timeline.service import append_event

FIELDS = ("trade_name", "phone", "email", "address", "timezone")


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def serialize(profile: BusinessProfile, now: datetime) -> BusinessProfileData:
    missing = [field for field in FIELDS if getattr(profile, field) is None]
    timezone = profile.timezone
    business_today = now.astimezone(ZoneInfo(timezone)).date() if timezone else None
    return BusinessProfileData(
        id=profile.id,
        trade_name=profile.trade_name,
        phone=profile.phone,
        email=profile.email,
        address=profile.address,
        timezone=timezone,
        is_complete=not missing,
        missing_fields=missing,
        business_timezone=timezone,
        business_today=business_today,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        version=profile.version,
    )


def get_profile(session: Session) -> BusinessProfile:
    return session.execute(select(BusinessProfile).where(BusinessProfile.id == 1)).scalar_one()


def update_profile(
    session: Session,
    *,
    patch: BusinessProfilePatch,
    if_match: str | None,
    actor_user_id: object,
    now: datetime,
) -> BusinessProfile:
    profile = session.execute(
        select(BusinessProfile).where(BusinessProfile.id == 1).with_for_update()
    ).scalar_one()
    check_if_match(if_match, profile.version)
    supplied = patch.model_fields_set - {"acknowledge_timezone_change"}
    values: dict[str, str | None] = {}
    for field in supplied:
        values[field] = _clean(getattr(patch, field))
    if "email" in values and values["email"] is not None:
        try:
            validate_email(values["email"], check_deliverability=False)
        except EmailNotValidError as error:
            raise FoundationError(
                status_code=422, code="VALIDATION_ERROR", message="E-mail inválido."
            ) from error
    if "timezone" in values and values["timezone"] is not None:
        try:
            ZoneInfo(values["timezone"])
        except ZoneInfoNotFoundError as error:
            raise FoundationError(
                status_code=422, code="VALIDATION_ERROR", message="Timezone IANA inválida."
            ) from error
    if profile.timezone is not None and values.get("timezone", profile.timezone) is None:
        raise FoundationError(
            status_code=422,
            code="VALIDATION_ERROR",
            message="Timezone configurada não pode ser removida.",
        )
    if (
        profile.timezone is not None
        and "timezone" in values
        and values["timezone"] != profile.timezone
        and not patch.acknowledge_timezone_change
    ):
        raise FoundationError(
            status_code=422,
            code="VALIDATION_ERROR",
            message="Confirme o impacto da mudança de timezone.",
        )
    was_complete = all(getattr(profile, field) is not None for field in FIELDS)
    candidate = {field: values.get(field, getattr(profile, field)) for field in FIELDS}
    if was_complete and any(value is None for value in candidate.values()):
        raise FoundationError(
            status_code=422,
            code="VALIDATION_ERROR",
            message="Um perfil completo não pode voltar a incompleto.",
        )
    changed = [field for field, value in values.items() if value != getattr(profile, field)]
    for field, value in values.items():
        setattr(profile, field, value)
    if changed:
        profile.version += 1
        profile.updated_at = now
        append_event(
            session,
            event_type="business.updated",
            actor_type="USER",
            actor_user_id=actor_user_id,  # type: ignore[arg-type]
            business_profile_id=1,
            payload={"changed_fields": sorted(changed)},
            occurred_at=now,
        )
    session.commit()
    return profile
