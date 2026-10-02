from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.modules.timeline.models import TimelineEvent

ALLOWED_PAYLOAD_KEYS: dict[str, set[str]] = {
    "user.created": {"role", "status", "source"},
    "user.disabled": {"role", "status"},
    "user.enabled": {"role", "status"},
    "user.password_reset": {"role", "status", "source"},
    "user.password_changed": {"role", "status", "source"},
    "business.updated": {"changed_fields"},
    "client.created": set(),
    "client.updated": {"changed_fields"},
    "client.archived": set(),
    "client.restored": set(),
    "equipment.created": {"equipment_id"},
    "equipment.updated": {"equipment_id", "changed_fields"},
    "equipment.archived": {"equipment_id"},
    "equipment.restored": {"equipment_id"},
}


def append_event(
    session: Session,
    *,
    event_type: str,
    actor_type: str,
    occurred_at: datetime,
    payload: dict[str, object],
    actor_user_id: UUID | None = None,
    subject_user_id: UUID | None = None,
    business_profile_id: int | None = None,
    client_id: UUID | None = None,
) -> TimelineEvent:
    allowed = ALLOWED_PAYLOAD_KEYS[event_type]
    if set(payload) - allowed or len(json.dumps(payload, separators=(",", ":")).encode()) > 4096:
        raise ValueError("payload de timeline inválido")
    event = TimelineEvent(
        id=uuid4(),
        event_type=event_type,
        actor_type=actor_type,
        actor_user_id=actor_user_id,
        subject_user_id=subject_user_id,
        business_profile_id=business_profile_id,
        client_id=client_id,
        payload=payload,
        occurred_at=occurred_at,
    )
    session.add(event)
    return event
