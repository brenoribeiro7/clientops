from __future__ import annotations

import base64
import binascii
import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from math import ceil
from typing import Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import ApiSettings
from app.core.errors import FoundationError
from app.core.http import check_if_match
from app.modules.business.models import BusinessProfile
from app.modules.clients.models import Client
from app.modules.quotes import repository
from app.modules.quotes.domain import (
    CalculatedItem,
    QuoteStatus,
    build_snapshot,
    calculate_line_total,
    calculate_total,
    current_business_date,
    is_commercially_expired,
    money_string,
    parse_money,
    parse_quantity,
    quantity_string,
    quote_number,
    validate_snapshot,
)
from app.modules.quotes.models import Quote, QuoteItem, QuotePublicAccess
from app.modules.quotes.schemas import (
    PageData,
    PublicAccessData,
    PublicApprovalData,
    PublicBusiness,
    PublicClient,
    PublicQuoteData,
    PublicQuoteItem,
    QuoteCreate,
    QuoteDetail,
    QuoteItemData,
    QuoteItemInput,
    QuotePatch,
    QuoteSummary,
    TimelineActor,
    TimelineData,
)
from app.modules.timeline.models import TimelineEvent
from app.modules.timeline.service import append_event

RETRYABLE_SQLSTATES = {"40001", "40P01"}
PROFILE_FIELDS = ("trade_name", "phone", "email", "address", "timezone")


@dataclass(frozen=True)
class IssuedAccess:
    model: QuotePublicAccess
    share_url: str


def not_found() -> FoundationError:
    return FoundationError(status_code=404, code="NOT_FOUND", message="Recurso não encontrado.")


def public_access_invalid() -> FoundationError:
    return FoundationError(
        status_code=401,
        code="PUBLIC_ACCESS_INVALID",
        message="Link de orçamento indisponível.",
    )


def _retryable(error: DBAPIError) -> bool:
    return getattr(error.orig, "sqlstate", None) in RETRYABLE_SQLSTATES


def run_command[T](
    session: Session,
    operation: Callable[[], T],
    *,
    reauthorize: Callable[[], None] | None = None,
) -> T:
    for attempt in range(3):
        try:
            return operation()
        except DBAPIError as error:
            session.rollback()
            if not _retryable(error):
                raise
            if attempt == 2:
                raise FoundationError(
                    status_code=503,
                    code="RETRYABLE_TRANSACTION",
                    message="Tente novamente em instantes.",
                ) from error
            if reauthorize is not None:
                reauthorize()
    raise AssertionError("unreachable")


def page_data(page: int, page_size: int, total: int) -> PageData:
    return PageData(
        number=page,
        size=page_size,
        total=total,
        total_pages=ceil(total / page_size) if total else 0,
    )


def _profile(session: Session, *, lock: bool) -> BusinessProfile:
    statement = select(BusinessProfile).where(BusinessProfile.id == 1)
    if lock:
        statement = statement.with_for_update()
    return session.execute(statement).scalar_one()


def _missing_profile(profile: BusinessProfile) -> list[str]:
    return [field for field in PROFILE_FIELDS if getattr(profile, field) is None]


def _business_today(profile: BusinessProfile, now: datetime) -> date:
    if profile.timezone is None:
        raise FoundationError(
            status_code=409,
            code="BUSINESS_PROFILE_INCOMPLETE",
            message="Configure o perfil da empresa.",
            details={"missing_fields": ["timezone"]},
        )
    return current_business_date(now, profile.timezone)


def business_today_for_read(session: Session, now: datetime) -> date | None:
    profile = _profile(session, lock=False)
    if profile.timezone is None:
        return None
    return current_business_date(now, profile.timezone)


def _complete_profile(profile: BusinessProfile) -> None:
    missing = _missing_profile(profile)
    if missing:
        raise FoundationError(
            status_code=409,
            code="BUSINESS_PROFILE_INCOMPLETE",
            message="Complete o perfil da empresa.",
            details={"missing_fields": missing},
        )


def _validate_valid_until(value: date, today: date, *, require_current: bool) -> None:
    if value > today + timedelta(days=365) or (require_current and value < today):
        raise FoundationError(
            status_code=422,
            code="VALIDATION_ERROR",
            message="Informe uma validade permitida.",
        )


def _client(session: Session, client_id: UUID, *, active: bool) -> Client:
    model = session.execute(
        select(Client).where(Client.id == client_id).with_for_update()
    ).scalar_one_or_none()
    if model is None:
        raise not_found()
    if active and model.status != "ACTIVE":
        raise FoundationError(
            status_code=409, code="CLIENT_ARCHIVED", message="O cliente está arquivado."
        )
    return model


def _calculated_input(item: QuoteItemInput, item_id: UUID) -> CalculatedItem:
    quantity = parse_quantity(item.quantity)
    price = parse_money(item.unit_price)
    return CalculatedItem(
        id=item_id,
        position=item.position,
        description=item.description,
        quantity=quantity,
        unit_price=price,
        line_total=calculate_line_total(quantity, price),
    )


def _replace_items(
    session: Session,
    quote: Quote,
    inputs: list[QuoteItemInput],
    now: datetime,
) -> tuple[list[CalculatedItem], bool]:
    existing = {item.id: item for item in repository.get_items(session, quote.id)}
    supplied_ids = {item.id for item in inputs if item.id is not None}
    if any(item_id not in existing for item_id in supplied_ids):
        raise not_found()
    calculated = [
        _calculated_input(item, item.id if item.id is not None else uuid4()) for item in inputs
    ]
    changed = supplied_ids != set(existing)
    for value in calculated:
        model = existing.get(value.id)
        if model is None:
            session.add(
                QuoteItem(
                    id=value.id,
                    quote_id=quote.id,
                    description=value.description,
                    quantity=value.quantity,
                    unit_price=value.unit_price,
                    line_total=value.line_total,
                    position=value.position,
                    created_at=now,
                    updated_at=now,
                    version=1,
                )
            )
            changed = True
            continue
        values = (
            value.description,
            value.quantity,
            value.unit_price,
            value.line_total,
            value.position,
        )
        current = (
            model.description,
            model.quantity,
            model.unit_price,
            model.line_total,
            model.position,
        )
        if values != current:
            model.description = value.description
            model.quantity = value.quantity
            model.unit_price = value.unit_price
            model.line_total = value.line_total
            model.position = value.position
            model.updated_at = now
            model.version += 1
            changed = True
    for item_id, model in existing.items():
        if item_id not in supplied_ids:
            session.delete(model)
    return calculated, changed


def _model_items(quote: Quote) -> list[CalculatedItem]:
    return [
        CalculatedItem(
            id=item.id,
            position=item.position,
            description=item.description,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_total=calculate_line_total(item.quantity, item.unit_price),
        )
        for item in sorted(quote.items, key=lambda value: value.position)
    ]


def _item_data(item: CalculatedItem) -> QuoteItemData:
    return QuoteItemData(
        id=item.id,
        position=item.position,
        description=item.description,
        quantity=quantity_string(item.quantity),
        unit_price=money_string(item.unit_price),
        line_total=money_string(item.line_total),
    )


def _snapshot_items(snapshot: dict[str, object]) -> list[QuoteItemData]:
    raw_items = validate_snapshot(snapshot)["items"]
    return [QuoteItemData.model_validate(item) for item in raw_items]


def _admin_snapshot(snapshot: dict[str, object] | None) -> dict[str, object] | None:
    if snapshot is None:
        return None
    validated = validate_snapshot(snapshot)
    raw_business = validated["business"]
    business = dict(raw_business)
    business["has_logo"] = business.pop("logo", None) is not None
    return {
        "schema_version": validated["schema_version"],
        "quote": validated["quote"],
        "business": business,
        "client": validated["client"],
        "items": validated["items"],
        "subtotal": validated["subtotal"],
        "total": validated["total"],
        "notes": validated["notes"],
    }


def public_access_data(model: QuotePublicAccess) -> PublicAccessData:
    return PublicAccessData(id=model.id, expires_at=model.expires_at, revoked_at=model.revoked_at)


def quote_summary(model: Quote, today: date | None) -> QuoteSummary:
    if model.status == "SENT" and today is None:
        raise FoundationError(
            status_code=409,
            code="BUSINESS_PROFILE_INCOMPLETE",
            message="Configure o timezone da empresa.",
            details={"missing_fields": ["timezone"]},
        )
    expired = bool(
        today
        and model.status == "SENT"
        and is_commercially_expired("SENT", model.valid_until, today)
    )
    return QuoteSummary(
        id=model.id,
        number=quote_number(model.number),
        client_id=model.client_id,
        status=cast(QuoteStatus, model.status),
        currency="BRL",
        valid_until=model.valid_until,
        subtotal=money_string(model.subtotal),
        total=money_string(model.total),
        is_expired=expired,
        created_at=model.created_at,
        updated_at=model.updated_at,
        version=model.version,
    )


def quote_detail(model: Quote, today: date | None) -> QuoteDetail:
    latest = max(
        model.public_accesses,
        key=lambda value: (value.created_at, value.id.int),
        default=None,
    )
    items = (
        _snapshot_items(model.commercial_snapshot)
        if model.commercial_snapshot is not None
        else [_item_data(item) for item in _model_items(model)]
    )
    return QuoteDetail(
        **quote_summary(model, today).model_dump(),
        source_quote_id=model.source_quote_id,
        notes=model.notes,
        items=items,
        commercial_snapshot=_admin_snapshot(model.commercial_snapshot),
        sent_at=model.sent_at,
        approved_at=model.approved_at,
        cancelled_at=model.cancelled_at,
        cancellation_reason=model.cancellation_reason,
        public_access=public_access_data(latest) if latest else None,
    )


def _event(
    session: Session,
    quote: Quote,
    event_type: str,
    payload: dict[str, object],
    now: datetime,
    *,
    actor_user_id: UUID | None = None,
    actor_public_access_id: UUID | None = None,
) -> None:
    append_event(
        session,
        event_type=event_type,
        actor_type="CUSTOMER_QUOTE_LINK" if actor_public_access_id else "USER",
        actor_user_id=actor_user_id,
        actor_public_access_id=actor_public_access_id,
        client_id=quote.client_id,
        quote_id=quote.id,
        payload=payload,
        occurred_at=now,
    )


def create_quote(
    session: Session,
    *,
    data: QuoteCreate,
    actor_user_id: UUID,
    now: datetime,
    reauthorize: Callable[[], None] | None = None,
) -> Quote:
    def attempt() -> Quote:
        profile = _profile(session, lock=True)
        today = _business_today(profile, now)
        _validate_valid_until(data.valid_until, today, require_current=False)
        client = _client(session, data.client_id, active=True)
        quote = Quote(
            id=uuid4(),
            client_id=client.id,
            source_quote_id=None,
            status="DRAFT",
            currency="BRL",
            valid_until=data.valid_until,
            notes=data.notes,
            subtotal=Decimal("0.00"),
            total=Decimal("0.00"),
            commercial_snapshot=None,
            sent_at=None,
            approved_at=None,
            cancelled_at=None,
            cancellation_reason=None,
            created_by=actor_user_id,
            created_at=now,
            updated_at=now,
            version=1,
        )
        session.add(quote)
        session.flush()
        calculated, _ = _replace_items(session, quote, data.items, now)
        quote.subtotal = quote.total = calculate_total(calculated)
        _event(
            session,
            quote,
            "quote.created",
            {"number": quote_number(quote.number), "status_to": "DRAFT"},
            now,
            actor_user_id=actor_user_id,
        )
        session.commit()
        return repository.get_quote(session, quote.id) or quote

    return run_command(session, attempt, reauthorize=reauthorize)


def patch_quote(
    session: Session,
    *,
    quote_id: UUID,
    patch: QuotePatch,
    if_match: str | None,
    actor_user_id: UUID,
    now: datetime,
    reauthorize: Callable[[], None] | None = None,
) -> Quote:
    def attempt() -> Quote:
        identity = repository.get_quote_identity(session, quote_id)
        if identity is None:
            raise not_found()
        current_client_id, _ = identity
        supplied = patch.model_fields_set
        if "valid_until" in supplied:
            profile = _profile(session, lock=True)
            today = _business_today(profile, now)
            assert patch.valid_until is not None
            _validate_valid_until(patch.valid_until, today, require_current=False)
        client_ids = {current_client_id}
        if "client_id" in supplied:
            assert patch.client_id is not None
            client_ids.add(patch.client_id)
        clients = {
            model.id: model
            for model in session.execute(
                select(Client)
                .where(Client.id.in_(client_ids))
                .order_by(Client.id)
                .with_for_update()
            ).scalars()
        }
        quote = repository.get_quote(session, quote_id, for_update=True)
        if quote is None:
            raise not_found()
        check_if_match(if_match, quote.version)
        if quote.status != "DRAFT":
            raise FoundationError(
                status_code=409, code="QUOTE_NOT_DRAFT", message="O orçamento não é rascunho."
            )
        changed = False
        if "client_id" in supplied:
            assert patch.client_id is not None
            client = clients.get(patch.client_id)
            if client is None:
                raise not_found()
            if client.status != "ACTIVE":
                raise FoundationError(
                    status_code=409,
                    code="CLIENT_ARCHIVED",
                    message="O cliente está arquivado.",
                )
            if quote.client_id != client.id:
                quote.client_id = client.id
                changed = True
        if "valid_until" in supplied and quote.valid_until != patch.valid_until:
            assert patch.valid_until is not None
            quote.valid_until = patch.valid_until
            changed = True
        if "notes" in supplied and quote.notes != patch.notes:
            quote.notes = patch.notes
            changed = True
        if "items" in supplied:
            assert patch.items is not None
            calculated, items_changed = _replace_items(session, quote, patch.items, now)
            total = calculate_total(calculated)
            if quote.subtotal != total or quote.total != total:
                quote.subtotal = quote.total = total
                items_changed = True
            changed = changed or items_changed
        if changed:
            quote.version += 1
            quote.updated_at = now
            _event(
                session,
                quote,
                "quote.updated",
                {
                    "number": quote_number(quote.number),
                    "status_from": "DRAFT",
                    "status_to": "DRAFT",
                },
                now,
                actor_user_id=actor_user_id,
            )
        session.commit()
        return repository.get_quote(session, quote.id) or quote

    return run_command(session, attempt, reauthorize=reauthorize)


def _new_access(
    quote: Quote,
    *,
    actor_user_id: UUID,
    now: datetime,
    settings: ApiSettings,
    after: QuotePublicAccess | None = None,
) -> tuple[QuotePublicAccess, str]:
    raw = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    access_id = uuid4()
    if after is not None and after.created_at == now and access_id.int <= after.id.int:
        if after.id.int == 2**128 - 1:
            raise FoundationError(
                status_code=503,
                code="RETRYABLE_TRANSACTION",
                message="Tente novamente em instantes.",
            )
        access_id = UUID(int=after.id.int + 1)
    model = QuotePublicAccess(
        id=access_id,
        quote_id=quote.id,
        bearer_hash=hashlib.sha256(raw.encode("ascii")).digest(),
        created_by=actor_user_id,
        created_at=now,
        expires_at=now + timedelta(seconds=settings.QUOTE_TOKEN_TTL_SECONDS),
        revoked_at=None,
        revocation_reason=None,
    )
    return model, raw


def send_quote(
    session: Session,
    *,
    quote_id: UUID,
    if_match: str | None,
    actor_user_id: UUID,
    now: datetime,
    settings: ApiSettings,
    reauthorize: Callable[[], None] | None = None,
) -> tuple[Quote, IssuedAccess, date]:
    def attempt() -> tuple[Quote, IssuedAccess, date]:
        identity = repository.get_quote_identity(session, quote_id)
        if identity is None:
            raise not_found()
        profile = _profile(session, lock=True)
        _complete_profile(profile)
        today = _business_today(profile, now)
        client = _client(session, identity[0], active=True)
        quote = repository.get_quote(session, quote_id, for_update=True)
        if quote is None:
            raise not_found()
        check_if_match(if_match, quote.version)
        if quote.status != "DRAFT":
            raise FoundationError(
                status_code=409, code="QUOTE_NOT_DRAFT", message="O orçamento não é rascunho."
            )
        if quote.client_id != client.id:
            raise FoundationError(
                status_code=412,
                code="VERSION_CONFLICT",
                message="O orçamento foi alterado.",
                details={"current_version": quote.version},
            )
        _validate_valid_until(quote.valid_until, today, require_current=True)
        items = _model_items(quote)
        if not 1 <= len(items) <= 100:
            raise FoundationError(
                status_code=422,
                code="VALIDATION_ERROR",
                message="Adicione ao menos um item antes de enviar.",
            )
        total = calculate_total(items)
        quote.subtotal = quote.total = total
        assert profile.timezone is not None
        business = {
            "trade_name": str(profile.trade_name),
            "phone": str(profile.phone),
            "email": str(profile.email),
            "address": str(profile.address),
        }
        client_snapshot: dict[str, str | UUID | None] = {
            "id": client.id,
            "name": client.name,
            "phone": client.phone,
            "email": client.email,
            "address": client.address,
        }
        quote.commercial_snapshot = dict(
            build_snapshot(
                quote_id=quote.id,
                number=quote.number,
                sent_at=now,
                valid_until=quote.valid_until,
                business_timezone=profile.timezone,
                business=business,
                client=client_snapshot,
                items=items,
                subtotal=total,
                notes=quote.notes,
            )
        )
        quote.status = "SENT"
        quote.sent_at = now
        quote.updated_at = now
        quote.version += 1
        access, raw = _new_access(
            quote,
            actor_user_id=actor_user_id,
            now=now,
            settings=settings,
        )
        session.add(access)
        _event(
            session,
            quote,
            "quote.sent",
            {"number": quote_number(quote.number), "status_from": "DRAFT", "status_to": "SENT"},
            now,
            actor_user_id=actor_user_id,
        )
        session.commit()
        loaded = repository.get_quote(session, quote.id) or quote
        share_url = f"{settings.PUBLIC_BASE_URL.rstrip('/')}/q#token={raw}"
        return loaded, IssuedAccess(access, share_url), today

    return run_command(session, attempt, reauthorize=reauthorize)


def cancel_quote(
    session: Session,
    *,
    quote_id: UUID,
    reason: str,
    if_match: str | None,
    actor_user_id: UUID,
    now: datetime,
    reauthorize: Callable[[], None] | None = None,
) -> Quote:
    def attempt() -> Quote:
        quote = repository.get_quote(session, quote_id, for_update=True)
        if quote is None:
            raise not_found()
        check_if_match(if_match, quote.version)
        if quote.status == "CANCELLED":
            session.commit()
            return quote
        if quote.status not in {"DRAFT", "SENT"}:
            raise FoundationError(
                status_code=409, code="INVALID_STATE", message="Estado incompatível."
            )
        previous = quote.status
        quote.status = "CANCELLED"
        quote.cancelled_at = now
        quote.cancellation_reason = reason
        quote.updated_at = now
        quote.version += 1
        for access in quote.public_accesses:
            if access.revoked_at is None:
                access.revoked_at = now
                access.revocation_reason = "QUOTE_CANCELLED"
        _event(
            session,
            quote,
            "quote.cancelled",
            {
                "number": quote_number(quote.number),
                "status_from": previous,
                "status_to": "CANCELLED",
                "cancellation_reason": reason,
            },
            now,
            actor_user_id=actor_user_id,
        )
        session.commit()
        return repository.get_quote(session, quote.id) or quote

    return run_command(session, attempt, reauthorize=reauthorize)


def duplicate_quote(
    session: Session,
    *,
    quote_id: UUID,
    actor_user_id: UUID,
    now: datetime,
    reauthorize: Callable[[], None] | None = None,
) -> Quote:
    def attempt() -> Quote:
        identity = repository.get_quote_identity(session, quote_id)
        if identity is None:
            raise not_found()
        profile = _profile(session, lock=True)
        today = _business_today(profile, now)
        _client(session, identity[0], active=False)
        source = repository.get_quote(session, quote_id, for_update=True)
        if source is None:
            raise not_found()
        result = Quote(
            id=uuid4(),
            client_id=source.client_id,
            source_quote_id=source.id,
            status="DRAFT",
            currency="BRL",
            valid_until=today + timedelta(days=14),
            notes=source.notes,
            subtotal=Decimal("0.00"),
            total=Decimal("0.00"),
            commercial_snapshot=None,
            sent_at=None,
            approved_at=None,
            cancelled_at=None,
            cancellation_reason=None,
            created_by=actor_user_id,
            created_at=now,
            updated_at=now,
            version=1,
        )
        session.add(result)
        session.flush()
        copied = [
            CalculatedItem(
                id=uuid4(),
                position=item.position,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                line_total=calculate_line_total(item.quantity, item.unit_price),
            )
            for item in source.items
        ]
        for item in copied:
            session.add(
                QuoteItem(
                    id=item.id,
                    quote_id=result.id,
                    description=item.description,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    line_total=item.line_total,
                    position=item.position,
                    created_at=now,
                    updated_at=now,
                    version=1,
                )
            )
        result.subtotal = result.total = calculate_total(copied)
        _event(
            session,
            result,
            "quote.duplicated",
            {
                "number": quote_number(result.number),
                "source_quote_id": str(source.id),
                "status_to": "DRAFT",
            },
            now,
            actor_user_id=actor_user_id,
        )
        session.commit()
        return repository.get_quote(session, result.id) or result

    return run_command(session, attempt, reauthorize=reauthorize)


def rotate_access(
    session: Session,
    *,
    quote_id: UUID,
    expected_access_id: UUID | None,
    actor_user_id: UUID,
    now: datetime,
    settings: ApiSettings,
    reauthorize: Callable[[], None] | None = None,
) -> IssuedAccess:
    def attempt() -> IssuedAccess:
        profile = _profile(session, lock=True)
        today = _business_today(profile, now)
        quote = repository.get_quote(session, quote_id, for_update=True)
        if quote is None:
            raise not_found()
        latest = repository.latest_access(session, quote.id)
        actual = latest.id if latest else None
        if actual != expected_access_id:
            raise FoundationError(
                status_code=409,
                code="ACCESS_CHANGED",
                message="O acesso público foi alterado.",
            )
        if quote.status != "SENT":
            raise FoundationError(
                status_code=409, code="INVALID_STATE", message="Estado incompatível."
            )
        if is_commercially_expired("SENT", quote.valid_until, today):
            raise FoundationError(
                status_code=409, code="QUOTE_EXPIRED", message="O orçamento está vencido."
            )
        if latest is not None and latest.revoked_at is None:
            latest.revoked_at = now
            latest.revocation_reason = "ROTATED"
            session.flush()
        access, raw = _new_access(
            quote,
            actor_user_id=actor_user_id,
            now=now,
            settings=settings,
            after=latest,
        )
        session.add(access)
        _event(
            session,
            quote,
            "quote.access_rotated",
            {"access_id": str(access.id)},
            now,
            actor_user_id=actor_user_id,
        )
        session.commit()
        return IssuedAccess(access, f"{settings.PUBLIC_BASE_URL.rstrip('/')}/q#token={raw}")

    return run_command(session, attempt, reauthorize=reauthorize)


def revoke_access(
    session: Session,
    *,
    quote_id: UUID,
    access_id: UUID,
    actor_user_id: UUID,
    now: datetime,
    reauthorize: Callable[[], None] | None = None,
) -> QuotePublicAccess:
    def attempt() -> QuotePublicAccess:
        quote = repository.get_quote(session, quote_id, for_update=True)
        if quote is None:
            raise not_found()
        access = repository.get_access_scoped(session, quote.id, access_id)
        if access is None:
            raise not_found()
        if quote.status not in {"SENT", "APPROVED"}:
            raise FoundationError(
                status_code=409, code="INVALID_STATE", message="Estado incompatível."
            )
        if access.revoked_at is None:
            access.revoked_at = now
            access.revocation_reason = "ADMIN_REVOKED"
            _event(
                session,
                quote,
                "quote.access_revoked",
                {"access_id": str(access.id)},
                now,
                actor_user_id=actor_user_id,
            )
        session.commit()
        return access

    return run_command(session, attempt, reauthorize=reauthorize)


def parse_public_bearer(raw: str | None) -> tuple[str, bytes]:
    if raw is None or len(raw) != 43:
        raise public_access_invalid()
    try:
        decoded = base64.b64decode(raw + "=", altchars=b"-_", validate=True)
        canonical = base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii")
    except (binascii.Error, ValueError, UnicodeError) as error:
        raise public_access_invalid() from error
    if len(decoded) != 32 or canonical != raw:
        raise public_access_invalid()
    return raw, hashlib.sha256(raw.encode("ascii")).digest()


def _validate_access(
    access: QuotePublicAccess | None, quote: Quote, now: datetime
) -> QuotePublicAccess:
    if (
        access is None
        or access.revoked_at is not None
        or now >= access.expires_at
        or quote.status == "CANCELLED"
    ):
        raise public_access_invalid()
    return access


def public_quote(
    session: Session,
    *,
    digest: bytes,
    now: datetime,
) -> PublicQuoteData:
    located = repository.locate_access_by_hash(session, digest)
    if located is None:
        raise public_access_invalid()
    quote = repository.get_quote(session, located[0])
    if quote is None:
        raise public_access_invalid()
    access = repository.access_under_quote_lock(session, quote.id, located[1], digest)
    _validate_access(access, quote, now)
    if quote.status not in {"SENT", "APPROVED"} or quote.commercial_snapshot is None:
        raise public_access_invalid()
    profile = _profile(session, lock=False)
    today = _business_today(profile, now)
    snapshot = validate_snapshot(quote.commercial_snapshot)
    business = snapshot["business"]
    client = snapshot["client"]
    raw_items = snapshot["items"]
    raw_quote = snapshot.get("quote")
    if (
        not isinstance(business, dict)
        or not isinstance(client, dict)
        or not isinstance(raw_items, list)
        or not isinstance(raw_quote, dict)
    ):
        raise ValueError("invalid quote snapshot")
    status = cast(QuoteStatus, quote.status)
    expired = is_commercially_expired(status, quote.valid_until, today)
    if quote.sent_at is None:
        raise ValueError("invalid sent quote")
    return PublicQuoteData(
        business=PublicBusiness(
            trade_name=str(business["trade_name"]),
            phone=str(business["phone"]),
            email=str(business["email"]),
            address=str(business["address"]),
            has_logo=business.get("logo") is not None,
        ),
        client=PublicClient(name=str(client["name"])),
        number=str(raw_quote["number"]),
        notes=snapshot["notes"] if isinstance(snapshot["notes"], str) else None,
        valid_until=date.fromisoformat(str(raw_quote["valid_until"])),
        items=[PublicQuoteItem.model_validate(item) for item in raw_items],
        subtotal=str(snapshot["subtotal"]),
        total=str(snapshot["total"]),
        currency="BRL",
        status=cast(Literal["SENT", "APPROVED"], status),
        sent_at=quote.sent_at,
        approved_at=quote.approved_at,
        is_expired=expired,
        can_approve=quote.status == "SENT" and not expired,
        server_now=now,
        business_today=today,
    )


def approve_quote(
    session: Session,
    *,
    digest: bytes,
    now: datetime,
) -> PublicApprovalData:
    def attempt() -> PublicApprovalData:
        located = repository.locate_access_by_hash(session, digest)
        if located is None:
            raise public_access_invalid()
        profile = _profile(session, lock=True)
        quote = repository.get_quote(session, located[0], for_update=True)
        if quote is None:
            raise public_access_invalid()
        access = repository.access_under_quote_lock(session, quote.id, located[1], digest)
        valid_access = _validate_access(access, quote, now)
        if quote.status == "APPROVED":
            assert quote.approved_at is not None
            session.commit()
            return PublicApprovalData(status="APPROVED", approved_at=quote.approved_at)
        if quote.status != "SENT":
            raise public_access_invalid()
        today = _business_today(profile, now)
        if is_commercially_expired("SENT", quote.valid_until, today):
            raise FoundationError(
                status_code=409, code="QUOTE_EXPIRED", message="O orçamento está vencido."
            )
        quote.status = "APPROVED"
        quote.approved_at = now
        quote.updated_at = now
        quote.version += 1
        _event(
            session,
            quote,
            "quote.approved",
            {
                "number": quote_number(quote.number),
                "status_from": "SENT",
                "status_to": "APPROVED",
            },
            now,
            actor_public_access_id=valid_access.id,
        )
        session.commit()
        return PublicApprovalData(status="APPROVED", approved_at=now)

    return run_command(session, attempt)


def timeline_data(event: TimelineEvent, actor_name: str | None) -> TimelineData:
    if event.actor_type == "USER":
        display = actor_name or "Usuário"
    elif event.actor_type == "CUSTOMER_QUOTE_LINK":
        display = "Link público do orçamento"
    else:
        display = "Sistema"
    return TimelineData(
        id=event.id,
        event_type=event.event_type,
        occurred_at=event.occurred_at,
        actor=TimelineActor(
            type=cast(
                Literal["USER", "CUSTOMER_QUOTE_LINK", "SYSTEM_AUTOMATION"],
                event.actor_type,
            ),
            display_name=display,
        ),
        payload=event.payload,
    )
