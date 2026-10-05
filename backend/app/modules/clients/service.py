from __future__ import annotations

from datetime import datetime
from math import ceil
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.errors import FoundationError
from app.core.http import check_if_match
from app.modules.clients import repository
from app.modules.clients.models import Client, Equipment
from app.modules.clients.schemas import (
    ClientCreate,
    ClientData,
    ClientLinks,
    ClientPatch,
    ClientSummary,
    EquipmentCreate,
    EquipmentData,
    EquipmentPatch,
    EquipmentSummary,
    PageData,
    TimelineActor,
    TimelineData,
)
from app.modules.timeline.service import append_event


def not_found() -> FoundationError:
    return FoundationError(status_code=404, code="NOT_FOUND", message="Recurso não encontrado.")


def page_data(page: int, page_size: int, total: int) -> PageData:
    return PageData(
        number=page,
        size=page_size,
        total=total,
        total_pages=ceil(total / page_size) if total else 0,
    )


def client_summary(model: Client) -> ClientSummary:
    return ClientSummary(
        id=model.id,
        name=model.name,
        phone=model.phone,
        email=model.email,
        status=model.status,
        created_at=model.created_at,
        updated_at=model.updated_at,
        version=model.version,
    )


def client_data(model: Client) -> ClientData:
    return ClientData(
        **client_summary(model).model_dump(),
        address=model.address,
        notes=model.notes,
        archived_at=model.archived_at,
        links=ClientLinks(
            equipment=f"/api/v1/clients/{model.id}/equipment",
            timeline=f"/api/v1/clients/{model.id}/timeline",
        ),
    )


def equipment_summary(model: Equipment) -> EquipmentSummary:
    return EquipmentSummary(
        id=model.id,
        client_id=model.client_id,
        name=model.name,
        brand=model.brand,
        model=model.model,
        serial_number=model.serial_number,
        location_description=model.location_description,
        status=model.status,
        created_at=model.created_at,
        updated_at=model.updated_at,
        version=model.version,
    )


def equipment_data(model: Equipment) -> EquipmentData:
    return EquipmentData(
        **equipment_summary(model).model_dump(), notes=model.notes, archived_at=model.archived_at
    )


def create_client(
    session: Session, *, data: ClientCreate, actor_user_id: UUID, now: datetime
) -> Client:
    model = Client(
        id=uuid4(),
        **data.model_dump(),
        status="ACTIVE",
        archived_at=None,
        created_at=now,
        updated_at=now,
        version=1,
    )
    session.add(model)
    append_event(
        session,
        event_type="client.created",
        actor_type="USER",
        actor_user_id=actor_user_id,
        client_id=model.id,
        payload={},
        occurred_at=now,
    )
    session.commit()
    return model


def patch_client(
    session: Session,
    *,
    client_id: UUID,
    patch: ClientPatch,
    if_match: str | None,
    actor_user_id: UUID,
    now: datetime,
) -> Client:
    model = repository.get_client(session, client_id, for_update=True)
    if model is None:
        raise not_found()
    check_if_match(if_match, model.version)
    values = patch.model_dump(exclude_unset=True)
    changed = sorted(field for field, value in values.items() if getattr(model, field) != value)
    for field in changed:
        setattr(model, field, values[field])
    if changed:
        model.version += 1
        model.updated_at = now
        append_event(
            session,
            event_type="client.updated",
            actor_type="USER",
            actor_user_id=actor_user_id,
            client_id=model.id,
            payload={"changed_fields": changed},
            occurred_at=now,
        )
    session.commit()
    return model


def set_client_archived(
    session: Session,
    *,
    client_id: UUID,
    archived: bool,
    if_match: str | None,
    actor_user_id: UUID,
    now: datetime,
) -> Client:
    model = repository.get_client(session, client_id, for_update=True)
    if model is None:
        raise not_found()
    check_if_match(if_match, model.version)
    target = "ARCHIVED" if archived else "ACTIVE"
    if model.status != target:
        model.status = target
        model.archived_at = now if archived else None
        model.updated_at = now
        model.version += 1
        append_event(
            session,
            event_type="client.archived" if archived else "client.restored",
            actor_type="USER",
            actor_user_id=actor_user_id,
            client_id=model.id,
            payload={},
            occurred_at=now,
        )
    session.commit()
    return model


def create_equipment(
    session: Session,
    *,
    client_id: UUID,
    data: EquipmentCreate,
    actor_user_id: UUID,
    now: datetime,
) -> Equipment:
    client = repository.get_client(session, client_id, for_update=True)
    if client is None:
        raise not_found()
    if client.status == "ARCHIVED":
        raise FoundationError(
            status_code=409, code="CLIENT_ARCHIVED", message="O cliente está arquivado."
        )
    model = Equipment(
        id=uuid4(),
        client_id=client.id,
        **data.model_dump(),
        status="ACTIVE",
        archived_at=None,
        created_at=now,
        updated_at=now,
        version=1,
    )
    session.add(model)
    append_event(
        session,
        event_type="equipment.created",
        actor_type="USER",
        actor_user_id=actor_user_id,
        client_id=client.id,
        payload={"equipment_id": str(model.id)},
        occurred_at=now,
    )
    session.commit()
    return model


def _locked_equipment(session: Session, client_id: UUID, equipment_id: UUID) -> Equipment:
    client = repository.get_client(session, client_id, for_update=True)
    if client is None:
        raise not_found()
    model = repository.get_equipment(
        session, client_id=client_id, equipment_id=equipment_id, for_update=True
    )
    if model is None:
        raise not_found()
    return model


def patch_equipment(
    session: Session,
    *,
    client_id: UUID,
    equipment_id: UUID,
    patch: EquipmentPatch,
    if_match: str | None,
    actor_user_id: UUID,
    now: datetime,
) -> Equipment:
    model = _locked_equipment(session, client_id, equipment_id)
    check_if_match(if_match, model.version)
    values = patch.model_dump(exclude_unset=True)
    changed = sorted(field for field, value in values.items() if getattr(model, field) != value)
    for field in changed:
        setattr(model, field, values[field])
    if changed:
        model.version += 1
        model.updated_at = now
        append_event(
            session,
            event_type="equipment.updated",
            actor_type="USER",
            actor_user_id=actor_user_id,
            client_id=model.client_id,
            payload={"equipment_id": str(model.id), "changed_fields": changed},
            occurred_at=now,
        )
    session.commit()
    return model


def set_equipment_archived(
    session: Session,
    *,
    client_id: UUID,
    equipment_id: UUID,
    archived: bool,
    if_match: str | None,
    actor_user_id: UUID,
    now: datetime,
) -> Equipment:
    model = _locked_equipment(session, client_id, equipment_id)
    check_if_match(if_match, model.version)
    target = "ARCHIVED" if archived else "ACTIVE"
    if model.status != target:
        model.status = target
        model.archived_at = now if archived else None
        model.updated_at = now
        model.version += 1
        append_event(
            session,
            event_type="equipment.archived" if archived else "equipment.restored",
            actor_type="USER",
            actor_user_id=actor_user_id,
            client_id=model.client_id,
            payload={"equipment_id": str(model.id)},
            occurred_at=now,
        )
    session.commit()
    return model


def timeline_data(event: object, actor_name: str | None) -> TimelineData:
    from app.modules.timeline.models import TimelineEvent

    if not isinstance(event, TimelineEvent):
        raise TypeError("timeline event expected")
    actor_type = event.actor_type
    return TimelineData(
        id=event.id,
        event_type=event.event_type,
        occurred_at=event.occurred_at,
        actor=TimelineActor(
            type=actor_type,
            display_name=actor_name if actor_type == "USER" and actor_name else "Sistema",
        ),
        payload=event.payload,
    )
