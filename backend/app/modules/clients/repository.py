from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.clients.models import Client, Equipment
from app.modules.identity.models import User
from app.modules.timeline.models import TimelineEvent


def _literal_search(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _ordered[Model: (Client, Equipment)](
    statement: Select[tuple[Model]], model: type[Model], sort: str
) -> Select[tuple[Model]]:
    field_name = sort.removeprefix("-")
    column = getattr(model, field_name)
    ordering = column.desc() if sort.startswith("-") else column.asc()
    return statement.order_by(ordering, model.id.asc())


def list_clients(
    session: Session, *, page: int, page_size: int, status: str, q: str | None, sort: str
) -> tuple[list[Client], int]:
    conditions = [Client.status == status]
    if q is not None:
        conditions.append(Client.name.ilike(f"%{_literal_search(q)}%", escape="\\"))
    total = session.scalar(select(func.count()).select_from(Client).where(*conditions)) or 0
    statement = select(Client).where(*conditions)
    statement = _ordered(statement, Client, sort)
    rows = list(
        session.execute(statement.offset((page - 1) * page_size).limit(page_size)).scalars()
    )
    return rows, total


def get_client(session: Session, client_id: UUID, *, for_update: bool = False) -> Client | None:
    statement = select(Client).where(Client.id == client_id)
    if for_update:
        statement = statement.with_for_update()
    return session.execute(statement).scalar_one_or_none()


def list_equipment(
    session: Session,
    *,
    client_id: UUID,
    page: int,
    page_size: int,
    status: str,
    q: str | None,
    sort: str,
) -> tuple[list[Equipment], int]:
    conditions = [Equipment.client_id == client_id, Equipment.status == status]
    if q is not None:
        conditions.append(Equipment.name.ilike(f"%{_literal_search(q)}%", escape="\\"))
    total = session.scalar(select(func.count()).select_from(Equipment).where(*conditions)) or 0
    statement = select(Equipment).where(*conditions)
    statement = _ordered(statement, Equipment, sort)
    rows = list(
        session.execute(statement.offset((page - 1) * page_size).limit(page_size)).scalars()
    )
    return rows, total


def get_equipment(
    session: Session,
    *,
    client_id: UUID,
    equipment_id: UUID,
    for_update: bool = False,
) -> Equipment | None:
    statement = select(Equipment).where(
        Equipment.id == equipment_id, Equipment.client_id == client_id
    )
    if for_update:
        statement = statement.with_for_update()
    return session.execute(statement).scalar_one_or_none()


def list_timeline(
    session: Session, *, client_id: UUID, page: int, page_size: int
) -> tuple[list[tuple[TimelineEvent, str | None]], int]:
    total = (
        session.scalar(
            select(func.count())
            .select_from(TimelineEvent)
            .where(TimelineEvent.client_id == client_id)
        )
        or 0
    )
    result = session.execute(
        select(TimelineEvent, User.name)
        .outerjoin(User, TimelineEvent.actor_user_id == User.id)
        .where(TimelineEvent.client_id == client_id)
        .order_by(TimelineEvent.occurred_at.desc(), TimelineEvent.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    rows = [(row[0], row[1]) for row in result]
    return rows, total
