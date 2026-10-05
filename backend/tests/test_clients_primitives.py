from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.modules.clients.schemas import (
    ClientCreate,
    ClientPatch,
    EquipmentCreate,
    EquipmentPatch,
    ListQuery,
)
from app.modules.timeline.service import append_event


def test_client_text_rules_trim_null_and_do_not_treat_contact_email_as_identity() -> None:
    data = ClientCreate(
        name="  Clínica Exemplo  ",
        phone="   ",
        email="  CONTATO sem formato  ",
        address=" Rua A\nSala 2 ",
        notes=" nota\toperacional ",
    )
    assert data.name == "Clínica Exemplo"
    assert data.phone is None
    assert data.email == "CONTATO sem formato"
    assert data.address == "Rua A\nSala 2"
    assert data.notes == "nota\toperacional"


@pytest.mark.parametrize("value", ["", "   ", "nome\x00", "nome\x01", "nome\nquebrado"])
def test_required_single_line_client_name_rejects_blank_and_controls(value: str) -> None:
    with pytest.raises(ValidationError):
        ClientCreate(name=value)


def test_optional_text_rejects_controls_and_allows_multiline_notes() -> None:
    assert EquipmentCreate(name="Ar", notes="linha 1\nlinha 2\tvalor").notes is not None
    with pytest.raises(ValidationError):
        EquipmentCreate(name="Ar", serial_number="ABC\n123")
    with pytest.raises(ValidationError):
        ClientPatch(notes="segredo\x07")


@pytest.mark.parametrize(
    ("patch_type", "nullable_field"),
    ((ClientPatch, "phone"), (EquipmentPatch, "brand")),
)
def test_patch_name_is_omissible_but_not_nullable(
    patch_type: type[BaseModel], nullable_field: str
) -> None:
    omitted = patch_type.model_validate({})
    assert omitted.model_dump(exclude_unset=True) == {}

    named = patch_type.model_validate({"name": "  Nome  "})
    assert named.model_dump(exclude_unset=True) == {"name": "Nome"}

    for invalid_name in (None, "   "):
        with pytest.raises(ValidationError):
            patch_type.model_validate({"name": invalid_name})

    nullable_omitted = patch_type.model_validate({})
    assert nullable_field not in nullable_omitted.model_dump(exclude_unset=True)
    nullable_cleared = patch_type.model_validate({nullable_field: None})
    assert nullable_cleared.model_dump(exclude_unset=True)[nullable_field] is None


def test_input_allowlists_reject_server_and_ownership_fields() -> None:
    with pytest.raises(ValidationError):
        ClientCreate.model_validate({"name": "Cliente", "status": "ARCHIVED"})
    with pytest.raises(ValidationError):
        EquipmentCreate.model_validate({"name": "Ar", "client_id": "00000000-0000-4000-8000-0"})


def test_list_query_contract() -> None:
    assert ListQuery().model_dump() == {
        "page": 1,
        "page_size": 20,
        "status": "ACTIVE",
        "q": None,
        "sort": "-created_at",
    }
    for payload in (
        {"page": 0},
        {"page_size": 101},
        {"status": "ALL"},
        {"q": "x"},
        {"sort": "email"},
        {"unknown": "value"},
    ):
        with pytest.raises(ValidationError):
            ListQuery.model_validate(payload)


def test_timeline_rejects_unknown_or_oversized_payload_without_persisting() -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.added: list[object] = []

        def add(self, value: object) -> None:
            self.added.append(value)

    session = FakeSession()
    with pytest.raises(ValueError):
        append_event(
            cast(Session, session),
            event_type="client.created",
            actor_type="USER",
            occurred_at=datetime.now(UTC),
            payload={"phone": "canary"},
        )
    with pytest.raises(ValueError):
        append_event(
            cast(Session, session),
            event_type="client.updated",
            actor_type="USER",
            occurred_at=datetime.now(UTC),
            payload={"changed_fields": ["x" * 5000]},
        )
    assert session.added == []
