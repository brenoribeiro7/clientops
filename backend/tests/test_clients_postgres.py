from __future__ import annotations

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import Clock
from app.core.config import ApiSettings
from app.core.db import create_session_factory
from app.core.errors import FoundationError
from app.main import create_app
from app.modules.clients.models import Client, Equipment
from app.modules.clients.schemas import ClientPatch, EquipmentCreate, EquipmentPatch
from app.modules.clients.service import (
    create_equipment,
    patch_client,
    patch_equipment,
    set_client_archived,
)
from app.modules.identity.models import User
from app.modules.identity.passwords import hash_password
from app.modules.timeline.models import TimelineEvent

ORIGIN = "http://clientops.test"
NOW = datetime(2026, 10, 2, 15, 0, tzinfo=UTC)
ADMIN_PASSWORD = "Client test password 2026!"


class MutableClock(Clock):
    def __init__(self, current: datetime) -> None:
        self.current = current

    def now_utc(self) -> datetime:
        return self.current


@dataclass
class ClientHarness:
    client: TestClient
    factory: sessionmaker[Session]
    clock: MutableClock
    csrf: str
    actor_id: UUID

    @property
    def headers(self) -> dict[str, str]:
        return {"Origin": ORIGIN, "X-CSRF-Token": self.csrf}

    def etag(self, path: str) -> str:
        response = self.client.get(path)
        assert response.status_code == 200, response.text
        return str(response.headers["etag"])

    def add_client(
        self, name: str = "Cliente A", **fields: object
    ) -> tuple[dict[str, object], str]:
        response = self.client.post(
            "/api/v1/clients", json={"name": name, **fields}, headers=self.headers
        )
        assert response.status_code == 201, response.text
        return response.json()["data"], response.headers["etag"]

    def add_equipment(
        self, client_id: object, name: str = "Equipamento A", **fields: object
    ) -> tuple[dict[str, object], str]:
        response = self.client.post(
            f"/api/v1/clients/{client_id}/equipment",
            json={"name": name, **fields},
            headers=self.headers,
        )
        assert response.status_code == 201, response.text
        return response.json()["data"], response.headers["etag"]


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is required")
    return value


def _user(factory: sessionmaker[Session], *, role: str = "ADMIN") -> User:
    value = uuid4()
    user = User(
        id=value,
        name=f"{role.title()} CL03",
        email_normalized=f"{value}@example.com",
        password_hash=hash_password(ADMIN_PASSWORD),
        role=role,
        status="ACTIVE",
        must_change_password=False,
        temporary_password_expires_at=None,
        password_changed_at=NOW,
        created_at=NOW,
        updated_at=NOW,
        version=1,
    )
    with factory() as session:
        session.add(user)
        session.commit()
    return user


@pytest.fixture
def clients_api() -> Iterator[ClientHarness]:
    migration = create_engine(_required("MIGRATION_DATABASE_URL"))
    with migration.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE equipment, clients, timeline_events, sessions, rate_limit_buckets, users "
                "RESTART IDENTITY CASCADE"
            )
        )
    settings = ApiSettings().model_copy(
        update={"PUBLIC_BASE_URL": ORIGIN, "TRUSTED_ORIGINS": ORIGIN}
    )
    app = create_app(settings)
    clock = MutableClock(NOW)
    app.state.clock = clock
    factory = create_session_factory(app.state.engine)
    actor = _user(factory)
    with TestClient(app, client=("198.51.100.30", 50000)) as browser:
        login = browser.post(
            "/api/v1/auth/login",
            json={"email": actor.email_normalized, "password": ADMIN_PASSWORD},
            headers={"Origin": ORIGIN, "X-ClientOps-Request": "browser-v1"},
        )
        assert login.status_code == 200, login.text
        yield ClientHarness(
            browser, factory, clock, str(login.json()["data"]["csrf_token"]), actor.id
        )
    migration.dispose()


@pytest.mark.postgres
def test_client_crud_search_pagination_archive_restore_and_timeline(
    clients_api: ClientHarness,
) -> None:
    created, etag = clients_api.add_client(
        "  Cliente %_ Literal  ",
        phone="  +55 71 3000-0000  ",
        email="  CONTATO sem formato  ",
        address=" Rua A\nSala 1 ",
        notes=" canary-private-notes ",
    )
    client_id = created["id"]
    assert created["email"] == "CONTATO sem formato"
    assert created["status"] == "ACTIVE"
    assert created["version"] == 1
    literal = clients_api.client.get("/api/v1/clients?q=%25_&sort=name")
    assert literal.status_code == 200
    assert [item["id"] for item in literal.json()["data"]] == [client_id]
    insensitive = clients_api.client.get("/api/v1/clients?q=cliente%20%25_&sort=name")
    assert [item["id"] for item in insensitive.json()["data"]] == [client_id]
    backslash, _ = clients_api.add_client(r"Cliente \\ Literal")
    sql_like, _ = clients_api.add_client("Cliente ' OR 1=1 --")
    hidden, _ = clients_api.add_client(
        "Nome sem canário",
        phone="PHONE-SEARCH-CANARY",
        email="EMAIL-SEARCH-CANARY",
        notes="NOTES-SEARCH-CANARY",
    )
    backslash_result = clients_api.client.get(r"/api/v1/clients?q=%5C%5C")
    assert backslash_result.json()["data"][0]["id"] == backslash["id"]
    sql_search = clients_api.client.get("/api/v1/clients?q=%27%20OR%201%3D1%20--")
    assert [item["id"] for item in sql_search.json()["data"]] == [sql_like["id"]]
    for excluded in ("PHONE-SEARCH", "EMAIL-SEARCH", "NOTES-SEARCH"):
        assert clients_api.client.get(f"/api/v1/clients?q={excluded}").json()["data"] == []
    assert hidden["name"] == "Nome sem canário"
    assert clients_api.client.get("/api/v1/clients?unknown=x").status_code == 422
    assert clients_api.client.get("/api/v1/clients?status=INVALID").status_code == 422
    assert clients_api.client.get("/api/v1/clients?sort=phone").status_code == 422
    assert clients_api.client.get("/api/v1/clients?page=0").status_code == 422
    assert clients_api.client.get("/api/v1/clients?page_size=0").status_code == 422
    assert clients_api.client.get("/api/v1/clients?page_size=101").status_code == 422
    assert clients_api.client.get("/api/v1/clients?page=200").json()["data"] == []
    default_page = clients_api.client.get("/api/v1/clients").json()["page"]
    assert default_page["number"] == 1 and default_page["size"] == 20
    same_a, _ = clients_api.add_client("Same name")
    same_b, _ = clients_api.add_client("Same name")
    tied = clients_api.client.get("/api/v1/clients?q=Same%20name&sort=name&page_size=100")
    assert [item["id"] for item in tied.json()["data"]] == sorted(
        [str(same_a["id"]), str(same_b["id"])]
    )

    no_op = clients_api.client.patch(
        f"/api/v1/clients/{client_id}",
        json={"name": created["name"]},
        headers={**clients_api.headers, "If-Match": etag},
    )
    assert no_op.status_code == 200
    assert no_op.headers["etag"] == etag
    assert no_op.json()["data"]["updated_at"] == created["updated_at"]

    clients_api.clock.current += timedelta(minutes=1)
    patched = clients_api.client.patch(
        f"/api/v1/clients/{client_id}",
        json={"name": "Cliente Atualizado", "phone": ""},
        headers={**clients_api.headers, "If-Match": etag},
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["phone"] is None
    etag = patched.headers["etag"]

    missing = clients_api.client.post(
        f"/api/v1/clients/{client_id}/archive", json={}, headers=clients_api.headers
    )
    assert missing.status_code == 428
    stale = clients_api.client.post(
        f"/api/v1/clients/{client_id}/archive",
        json={},
        headers={**clients_api.headers, "If-Match": '"v1"'},
    )
    assert stale.status_code == 412

    clients_api.clock.current += timedelta(minutes=1)
    archived = clients_api.client.post(
        f"/api/v1/clients/{client_id}/archive",
        json={},
        headers={**clients_api.headers, "If-Match": etag},
    )
    assert archived.status_code == 200
    archive_etag = archived.headers["etag"]
    repeated = clients_api.client.post(
        f"/api/v1/clients/{client_id}/archive",
        json={},
        headers={**clients_api.headers, "If-Match": archive_etag},
    )
    assert repeated.headers["etag"] == archive_etag
    assert repeated.json()["data"]["updated_at"] == archived.json()["data"]["updated_at"]
    active_ids = {item["id"] for item in clients_api.client.get("/api/v1/clients").json()["data"]}
    assert client_id not in active_ids
    assert (
        clients_api.client.get("/api/v1/clients?status=ARCHIVED").json()["data"][0]["id"]
        == client_id
    )
    assert clients_api.client.get(f"/api/v1/clients/{client_id}").status_code == 200

    restored = clients_api.client.post(
        f"/api/v1/clients/{client_id}/restore",
        json={},
        headers={**clients_api.headers, "If-Match": archive_etag},
    )
    assert restored.status_code == 200
    restore_etag = restored.headers["etag"]
    repeated_restore = clients_api.client.post(
        f"/api/v1/clients/{client_id}/restore",
        json={},
        headers={**clients_api.headers, "If-Match": restore_etag},
    )
    assert repeated_restore.status_code == 200
    assert repeated_restore.headers["etag"] == restore_etag
    assert repeated_restore.json()["data"]["updated_at"] == restored.json()["data"]["updated_at"]
    timeline = clients_api.client.get(f"/api/v1/clients/{client_id}/timeline?page_size=100")
    assert timeline.status_code == 200
    assert {event["event_type"] for event in timeline.json()["data"]} == {
        "client.created",
        "client.updated",
        "client.archived",
        "client.restored",
    }
    serialized = timeline.text
    assert "canary-private-notes" not in serialized
    assert "+55 71" not in serialized
    assert "CONTATO sem formato" not in serialized


@pytest.mark.postgres
def test_equipment_ownership_archive_no_cascade_and_archived_parent_rule(
    clients_api: ClientHarness,
) -> None:
    client_a, client_a_etag = clients_api.add_client("Cliente A")
    client_b, _ = clients_api.add_client("Cliente B")
    equipment_a, equipment_etag = clients_api.add_equipment(
        client_a["id"],
        "Equipamento %_ \\ A",
        serial_number="SERIAL-CANARY",
        location_description="LOCATION-CANARY",
    )
    equipment_b, _ = clients_api.add_equipment(client_b["id"], "Equipamento B")
    cross_path = f"/api/v1/clients/{client_b['id']}/equipment/{equipment_a['id']}"
    for method, suffix in (("get", ""), ("patch", ""), ("post", "/archive"), ("post", "/restore")):
        headers = clients_api.headers
        if method != "get":
            headers = {**headers, "If-Match": equipment_etag}
        response = getattr(clients_api.client, method)(
            cross_path + suffix,
            **({"json": {"name": "Cross"} if method == "patch" else {}} if method != "get" else {}),
            headers=headers,
        )
        assert response.status_code == 404
        assert "Equipamento A" not in response.text
        assert "SERIAL-CANARY" not in response.text
        assert str(client_a["id"]) not in response.text

    literal = clients_api.client.get(
        f"/api/v1/clients/{client_a['id']}/equipment?q=%25_%20%5C&sort=name"
    )
    assert [item["id"] for item in literal.json()["data"]] == [equipment_a["id"]]
    for excluded in ("SERIAL-CANARY", "LOCATION-CANARY"):
        response = clients_api.client.get(
            f"/api/v1/clients/{client_a['id']}/equipment?q={excluded}"
        )
        assert response.json()["data"] == []

    overpost = clients_api.client.patch(
        f"/api/v1/clients/{client_a['id']}/equipment/{equipment_a['id']}",
        json={"client_id": client_b["id"]},
        headers={**clients_api.headers, "If-Match": equipment_etag},
    )
    assert overpost.status_code == 422

    archived_client = clients_api.client.post(
        f"/api/v1/clients/{client_a['id']}/archive",
        json={},
        headers={**clients_api.headers, "If-Match": client_a_etag},
    )
    assert archived_client.status_code == 200
    existing = clients_api.client.get(
        f"/api/v1/clients/{client_a['id']}/equipment/{equipment_a['id']}"
    )
    assert existing.status_code == 200
    assert existing.json()["data"]["status"] == "ACTIVE"
    blocked = clients_api.client.post(
        f"/api/v1/clients/{client_a['id']}/equipment",
        json={"name": "Novo"},
        headers=clients_api.headers,
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "CLIENT_ARCHIVED"

    archived_equipment = clients_api.client.post(
        f"/api/v1/clients/{client_a['id']}/equipment/{equipment_a['id']}/archive",
        json={},
        headers={**clients_api.headers, "If-Match": equipment_etag},
    )
    assert archived_equipment.status_code == 200
    archive_equipment_etag = archived_equipment.headers["etag"]
    repeated_archive = clients_api.client.post(
        f"/api/v1/clients/{client_a['id']}/equipment/{equipment_a['id']}/archive",
        json={},
        headers={**clients_api.headers, "If-Match": archive_equipment_etag},
    )
    assert repeated_archive.headers["etag"] == archive_equipment_etag
    assert (
        repeated_archive.json()["data"]["updated_at"]
        == archived_equipment.json()["data"]["updated_at"]
    )
    stale_restore = clients_api.client.post(
        f"/api/v1/clients/{client_a['id']}/equipment/{equipment_a['id']}/restore",
        json={},
        headers={**clients_api.headers, "If-Match": equipment_etag},
    )
    assert stale_restore.status_code == 412
    restored_equipment = clients_api.client.post(
        f"/api/v1/clients/{client_a['id']}/equipment/{equipment_a['id']}/restore",
        json={},
        headers={**clients_api.headers, "If-Match": archive_equipment_etag},
    )
    assert restored_equipment.status_code == 200
    assert restored_equipment.json()["data"]["status"] == "ACTIVE"
    restore_equipment_etag = restored_equipment.headers["etag"]
    repeated_restore = clients_api.client.post(
        f"/api/v1/clients/{client_a['id']}/equipment/{equipment_a['id']}/restore",
        json={},
        headers={**clients_api.headers, "If-Match": restore_equipment_etag},
    )
    assert repeated_restore.headers["etag"] == restore_equipment_etag
    assert (
        repeated_restore.json()["data"]["updated_at"]
        == restored_equipment.json()["data"]["updated_at"]
    )
    assert equipment_b["client_id"] == client_b["id"]

    timeline_a = clients_api.client.get(
        f"/api/v1/clients/{client_a['id']}/timeline?page_size=100"
    ).json()["data"]
    timeline_b = clients_api.client.get(
        f"/api/v1/clients/{client_b['id']}/timeline?page_size=100"
    ).json()["data"]
    assert sum(item["event_type"] == "equipment.archived" for item in timeline_a) == 1
    assert sum(item["event_type"] == "equipment.restored" for item in timeline_a) == 1
    assert all(item["payload"].get("equipment_id") != equipment_a["id"] for item in timeline_b)
    assert "SERIAL-CANARY" not in str(timeline_a)
    assert "LOCATION-CANARY" not in str(timeline_a)


@pytest.mark.postgres
def test_authorization_precedes_client_lookup(clients_api: ClientHarness) -> None:
    anonymous = TestClient(clients_api.client.app, client=("198.51.100.40", 50001))
    assert anonymous.get("/api/v1/clients").status_code == 401
    technician = _user(clients_api.factory, role="TECHNICIAN")
    with TestClient(clients_api.client.app, client=("198.51.100.41", 50002)) as browser:
        login = browser.post(
            "/api/v1/auth/login",
            json={"email": technician.email_normalized, "password": ADMIN_PASSWORD},
            headers={"Origin": ORIGIN, "X-ClientOps-Request": "browser-v1"},
        )
        assert login.status_code == 200
        client_id = uuid4()
        equipment_id = uuid4()
        for path in (
            "/api/v1/clients",
            f"/api/v1/clients/{client_id}",
            f"/api/v1/clients/{client_id}/equipment",
            f"/api/v1/clients/{client_id}/equipment/{equipment_id}",
            f"/api/v1/clients/{client_id}/timeline",
        ):
            response = browser.get(path)
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.postgres
def test_same_etag_concurrent_client_and_equipment_patches(
    clients_api: ClientHarness,
) -> None:
    client, _ = clients_api.add_client("Race Client")
    equipment, _ = clients_api.add_equipment(client["id"], "Race Equipment")

    def run_client(name: str, barrier: Barrier) -> str:
        with clients_api.factory() as session:
            barrier.wait(timeout=10)
            try:
                patch_client(
                    session,
                    client_id=UUID(str(client["id"])),
                    patch=ClientPatch(name=name),
                    if_match='"v1"',
                    actor_user_id=clients_api.actor_id,
                    now=NOW + timedelta(hours=1),
                )
                return "ok"
            except FoundationError as error:
                return error.code

    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [
            pool.submit(run_client, "Race One", barrier),
            pool.submit(run_client, "Race Two", barrier),
        ]
    assert sorted(result.result(timeout=20) for result in outcomes) == ["VERSION_CONFLICT", "ok"]

    def run_equipment(name: str, equipment_barrier: Barrier) -> str:
        with clients_api.factory() as session:
            equipment_barrier.wait(timeout=10)
            try:
                patch_equipment(
                    session,
                    client_id=UUID(str(client["id"])),
                    equipment_id=UUID(str(equipment["id"])),
                    patch=EquipmentPatch(name=name),
                    if_match='"v1"',
                    actor_user_id=clients_api.actor_id,
                    now=NOW + timedelta(hours=2),
                )
                return "ok"
            except FoundationError as error:
                return error.code

    equipment_barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [
            pool.submit(run_equipment, "Equipment One", equipment_barrier),
            pool.submit(run_equipment, "Equipment Two", equipment_barrier),
        ]
    assert sorted(result.result(timeout=20) for result in outcomes) == ["VERSION_CONFLICT", "ok"]


@pytest.mark.postgres
@pytest.mark.parametrize("starting_archived", [False, True])
def test_client_archive_restore_races_with_patch(
    clients_api: ClientHarness, starting_archived: bool
) -> None:
    client, etag = clients_api.add_client("Lifecycle Race")
    client_id = UUID(str(client["id"]))
    if starting_archived:
        archived = clients_api.client.post(
            f"/api/v1/clients/{client['id']}/archive",
            json={},
            headers={**clients_api.headers, "If-Match": etag},
        )
        assert archived.status_code == 200
        etag = archived.headers["etag"]
    barrier = Barrier(2)

    def lifecycle() -> str:
        with clients_api.factory() as session:
            barrier.wait(timeout=10)
            try:
                set_client_archived(
                    session,
                    client_id=client_id,
                    archived=not starting_archived,
                    if_match=etag,
                    actor_user_id=clients_api.actor_id,
                    now=NOW + timedelta(hours=4),
                )
                return "ok"
            except FoundationError as error:
                return error.code

    def patch() -> str:
        with clients_api.factory() as session:
            barrier.wait(timeout=10)
            try:
                patch_client(
                    session,
                    client_id=client_id,
                    patch=ClientPatch(name="Concurrent name"),
                    if_match=etag,
                    actor_user_id=clients_api.actor_id,
                    now=NOW + timedelta(hours=4),
                )
                return "ok"
            except FoundationError as error:
                return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [pool.submit(lifecycle), pool.submit(patch)]
    assert sorted(future.result(timeout=20) for future in outcomes) == [
        "VERSION_CONFLICT",
        "ok",
    ]
    with clients_api.factory() as session:
        model = session.get(Client, client_id)
        assert model is not None
        assert model.version == (3 if starting_archived else 2)


@pytest.mark.postgres
def test_equipment_mutation_serializes_with_client_archive(
    clients_api: ClientHarness,
) -> None:
    client, _ = clients_api.add_client("Equipment Parent Race")
    equipment, _ = clients_api.add_equipment(client["id"], "Before")
    client_id = UUID(str(client["id"]))
    equipment_id = UUID(str(equipment["id"]))
    barrier = Barrier(2)

    def archive_client() -> str:
        with clients_api.factory() as session:
            barrier.wait(timeout=10)
            set_client_archived(
                session,
                client_id=client_id,
                archived=True,
                if_match='"v1"',
                actor_user_id=clients_api.actor_id,
                now=NOW + timedelta(hours=5),
            )
        return "archived"

    def mutate_equipment() -> str:
        with clients_api.factory() as session:
            barrier.wait(timeout=10)
            patch_equipment(
                session,
                client_id=client_id,
                equipment_id=equipment_id,
                patch=EquipmentPatch(name="After"),
                if_match='"v1"',
                actor_user_id=clients_api.actor_id,
                now=NOW + timedelta(hours=5),
            )
        return "mutated"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [pool.submit(archive_client), pool.submit(mutate_equipment)]
    assert {future.result(timeout=20) for future in outcomes} == {"archived", "mutated"}
    with clients_api.factory() as session:
        parent = session.get(Client, client_id)
        child = session.get(Equipment, equipment_id)
        assert parent is not None and parent.status == "ARCHIVED" and parent.version == 2
        assert child is not None and child.name == "After" and child.version == 2


@pytest.mark.postgres
def test_client_archive_races_serialize_with_equipment_commands(
    clients_api: ClientHarness,
) -> None:
    client, _ = clients_api.add_client("Parent Race")
    equipment, _ = clients_api.add_equipment(client["id"], "Existing")
    client_id = UUID(str(client["id"]))
    barrier = Barrier(2)

    def archive() -> str:
        with clients_api.factory() as session:
            barrier.wait(timeout=10)
            try:
                set_client_archived(
                    session,
                    client_id=client_id,
                    archived=True,
                    if_match='"v1"',
                    actor_user_id=clients_api.actor_id,
                    now=NOW + timedelta(hours=3),
                )
                return "archived"
            except FoundationError as error:
                return error.code

    def create() -> str:
        with clients_api.factory() as session:
            barrier.wait(timeout=10)
            try:
                create_equipment(
                    session,
                    client_id=client_id,
                    data=EquipmentCreate(name="Concurrent"),
                    actor_user_id=clients_api.actor_id,
                    now=NOW + timedelta(hours=3),
                )
                return "created"
            except FoundationError as error:
                return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = {pool.submit(archive), pool.submit(create)}
    result = {future.result(timeout=20) for future in outcomes}
    assert "archived" in result
    assert result in ({"archived", "created"}, {"archived", "CLIENT_ARCHIVED"})

    with clients_api.factory() as session:
        parent = session.get(Client, client_id)
        original = session.get(Equipment, UUID(str(equipment["id"])))
        assert parent is not None and parent.status == "ARCHIVED"
        assert original is not None and original.status == "ACTIVE" and original.version == 1
        assert (
            session.scalar(
                select(TimelineEvent).where(
                    TimelineEvent.client_id == client_id,
                    TimelineEvent.event_type == "client.archived",
                )
            )
            is not None
        )


@pytest.mark.postgres
def test_all_client_timeline_event_types_and_payload_allowlist(
    clients_api: ClientHarness,
) -> None:
    client, client_etag = clients_api.add_client("Timeline Client")
    client_id = client["id"]
    updated = clients_api.client.patch(
        f"/api/v1/clients/{client_id}",
        json={"phone": "PRIVATE-PHONE", "notes": "PRIVATE-NOTES"},
        headers={**clients_api.headers, "If-Match": client_etag},
    )
    archived = clients_api.client.post(
        f"/api/v1/clients/{client_id}/archive",
        json={},
        headers={**clients_api.headers, "If-Match": updated.headers["etag"]},
    )
    restored = clients_api.client.post(
        f"/api/v1/clients/{client_id}/restore",
        json={},
        headers={**clients_api.headers, "If-Match": archived.headers["etag"]},
    )
    assert restored.status_code == 200
    equipment, equipment_etag = clients_api.add_equipment(
        client_id, "Timeline Equipment", notes="EQUIPMENT-PRIVATE"
    )
    patched = clients_api.client.patch(
        f"/api/v1/clients/{client_id}/equipment/{equipment['id']}",
        json={"brand": "PRIVATE-BRAND"},
        headers={**clients_api.headers, "If-Match": equipment_etag},
    )
    equipment_archived = clients_api.client.post(
        f"/api/v1/clients/{client_id}/equipment/{equipment['id']}/archive",
        json={},
        headers={**clients_api.headers, "If-Match": patched.headers["etag"]},
    )
    equipment_restored = clients_api.client.post(
        f"/api/v1/clients/{client_id}/equipment/{equipment['id']}/restore",
        json={},
        headers={**clients_api.headers, "If-Match": equipment_archived.headers["etag"]},
    )
    assert equipment_restored.status_code == 200
    events = clients_api.client.get(f"/api/v1/clients/{client_id}/timeline?page_size=100").json()[
        "data"
    ]
    assert {item["event_type"] for item in events} == {
        "client.created",
        "client.updated",
        "client.archived",
        "client.restored",
        "equipment.created",
        "equipment.updated",
        "equipment.archived",
        "equipment.restored",
    }
    serialized = str(events)
    for secret in ("PRIVATE-PHONE", "PRIVATE-NOTES", "EQUIPMENT-PRIVATE", "PRIVATE-BRAND"):
        assert secret not in serialized
    update_payloads = [
        item["payload"] for item in events if item["event_type"].endswith(".updated")
    ]
    assert {tuple(payload["changed_fields"]) for payload in update_payloads} == {
        ("notes", "phone"),
        ("brand",),
    }


@pytest.mark.postgres
def test_timeline_change_and_domain_row_rollback_together(clients_api: ClientHarness) -> None:
    client, _ = clients_api.add_client("Rollback")
    client_id = UUID(str(client["id"]))
    with clients_api.factory() as session:
        model = session.get(Client, client_id)
        assert model is not None
        model.name = "Not committed"
        session.add(
            TimelineEvent(
                id=uuid4(),
                event_type="client.updated",
                actor_type="USER",
                actor_user_id=clients_api.actor_id,
                subject_user_id=None,
                business_profile_id=None,
                client_id=client_id,
                payload={"changed_fields": ["name"]},
                occurred_at=NOW,
            )
        )
        session.rollback()
    with clients_api.factory() as session:
        model = session.get(Client, client_id)
        assert model is not None and model.name == "Rollback"
        assert (
            session.scalar(
                select(TimelineEvent).where(
                    TimelineEvent.client_id == client_id,
                    TimelineEvent.event_type == "client.updated",
                )
            )
            is None
        )
