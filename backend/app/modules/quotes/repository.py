from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import Select, String, cast, exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.modules.identity.models import User
from app.modules.quotes.models import Quote, QuoteItem, QuotePublicAccess
from app.modules.timeline.models import TimelineEvent


def _literal_search(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def get_quote(session: Session, quote_id: UUID, *, for_update: bool = False) -> Quote | None:
    statement = (
        select(Quote)
        .options(selectinload(Quote.items), selectinload(Quote.public_accesses))
        .where(Quote.id == quote_id)
    )
    if for_update:
        statement = statement.with_for_update()
    return session.execute(statement).scalar_one_or_none()


def get_quote_identity(session: Session, quote_id: UUID) -> tuple[UUID, int] | None:
    row = session.execute(
        select(Quote.client_id, Quote.version).where(Quote.id == quote_id)
    ).one_or_none()
    return (row.client_id, row.version) if row else None


def _ordered(statement: Select[tuple[Quote]], sort: str) -> Select[tuple[Quote]]:
    column = getattr(Quote, sort.removeprefix("-"))
    ordering = column.desc() if sort.startswith("-") else column.asc()
    return statement.order_by(ordering, Quote.id.asc())


def list_quotes(
    session: Session,
    *,
    page: int,
    page_size: int,
    status: str | None,
    client_id: UUID | None,
    expired: bool | None,
    today: date | None,
    q: str | None,
    sort: str,
) -> tuple[list[Quote], int]:
    conditions = []
    if status is not None:
        conditions.append(Quote.status == status)
    if client_id is not None:
        conditions.append(Quote.client_id == client_id)
    if expired is not None:
        if today is None:
            raise ValueError("business date required")
        predicate = (Quote.status == "SENT") & (Quote.valid_until < today)
        conditions.append(predicate if expired else ~predicate)
    if q is not None:
        escaped = f"%{_literal_search(q)}%"
        displayed_number = func.concat("ORC-", func.lpad(cast(Quote.number, String), 6, "0"))
        item_match = exists(
            select(QuoteItem.id).where(
                QuoteItem.quote_id == Quote.id,
                QuoteItem.description.ilike(escaped, escape="\\"),
            )
        )
        conditions.append(or_(displayed_number.ilike(escaped, escape="\\"), item_match))
    total = session.scalar(select(func.count()).select_from(Quote).where(*conditions)) or 0
    statement = select(Quote).options(selectinload(Quote.items)).where(*conditions)
    statement = _ordered(statement, sort)
    rows = list(
        session.execute(statement.offset((page - 1) * page_size).limit(page_size)).scalars()
    )
    return rows, total


def get_items(session: Session, quote_id: UUID) -> list[QuoteItem]:
    return list(
        session.execute(
            select(QuoteItem).where(QuoteItem.quote_id == quote_id).order_by(QuoteItem.position)
        ).scalars()
    )


def latest_access(session: Session, quote_id: UUID) -> QuotePublicAccess | None:
    return session.execute(
        select(QuotePublicAccess)
        .where(QuotePublicAccess.quote_id == quote_id)
        .order_by(QuotePublicAccess.created_at.desc(), QuotePublicAccess.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def get_access_scoped(
    session: Session, quote_id: UUID, access_id: UUID
) -> QuotePublicAccess | None:
    return session.execute(
        select(QuotePublicAccess).where(
            QuotePublicAccess.id == access_id, QuotePublicAccess.quote_id == quote_id
        )
    ).scalar_one_or_none()


def locate_access_by_hash(session: Session, digest: bytes) -> tuple[UUID, UUID] | None:
    row = session.execute(
        select(QuotePublicAccess.quote_id, QuotePublicAccess.id).where(
            QuotePublicAccess.bearer_hash == digest
        )
    ).one_or_none()
    return (row.quote_id, row.id) if row else None


def access_under_quote_lock(
    session: Session, quote_id: UUID, access_id: UUID, digest: bytes
) -> QuotePublicAccess | None:
    return session.execute(
        select(QuotePublicAccess).where(
            QuotePublicAccess.quote_id == quote_id,
            QuotePublicAccess.id == access_id,
            QuotePublicAccess.bearer_hash == digest,
        )
    ).scalar_one_or_none()


def list_timeline(
    session: Session, *, quote_id: UUID, page: int, page_size: int
) -> tuple[list[tuple[TimelineEvent, str | None]], int]:
    total = (
        session.scalar(
            select(func.count())
            .select_from(TimelineEvent)
            .where(TimelineEvent.quote_id == quote_id)
        )
        or 0
    )
    result = session.execute(
        select(TimelineEvent, User.name)
        .outerjoin(User, TimelineEvent.actor_user_id == User.id)
        .where(TimelineEvent.quote_id == quote_id)
        .order_by(TimelineEvent.occurred_at.desc(), TimelineEvent.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [(row[0], row[1]) for row in result], total
