from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import Clock
from app.core.config import ApiSettings
from app.core.db import create_session_factory
from app.main import create_app
from app.modules.clients.models import Client
from app.modules.identity.models import User
from app.modules.identity.passwords import hash_password
from app.modules.quotes.models import Quote, QuotePublicAccess
from app.modules.timeline.models import TimelineEvent

ORIGIN = "http://clientops.test"
NOW = datetime(2026, 10, 5, 16, 0, tzinfo=UTC)
PASSWORD = "CL04 secure test password 2026!"


class MutableClock(Clock):
    def __init__(self, current: datetime) -> None:
        self.current = current

    def now_utc(self) -> datetime:
        return self.current


@dataclass
class QuoteHarness:
    client: TestClient
    factory: sessionmaker[Session]
    migration_factory: sessionmaker[Session]
    clock: MutableClock
    csrf: str
    actor_id: UUID
    client_id: UUID

    @property
    def headers(self) -> dict[str, str]:
        return {"Origin": ORIGIN, "X-CSRF-Token": self.csrf}

    def create_quote(self, **changes: object) -> tuple[dict[str, object], str]:
        payload: dict[str, object] = {
            "client_id": str(self.client_id),
            "valid_until": "2026-10-09",
            "notes": "Atendimento em horário comercial.",
            "items": [
                {
                    "position": 1,
                    "description": "Inspeção preventiva",
                    "quantity": "0.005",
                    "unit_price": "1.00",
                }
            ],
        }
        payload.update(changes)
        response = self.client.post("/api/v1/quotes", json=payload, headers=self.headers)
        assert response.status_code == 201, response.text
        return response.json()["data"], response.headers["etag"]

    def send_quote(self, quote_id: object, etag: str) -> tuple[dict[str, object], str]:
        response = self.client.post(
            f"/api/v1/quotes/{quote_id}/send",
            json={},
            headers={**self.headers, "If-Match": etag},
        )
        assert response.status_code == 200, response.text
        return response.json(), response.headers["etag"]

    def relogin(self) -> None:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": "admin.cl04@example.com", "password": PASSWORD},
            headers={"Origin": ORIGIN, "X-ClientOps-Request": "browser-v1"},
        )
        assert response.status_code == 200, response.text
        self.csrf = str(response.json()["data"]["csrf_token"])


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is required")
    return value


@pytest.fixture
def quotes_api() -> Iterator[QuoteHarness]:
    migration = create_engine(_required("MIGRATION_DATABASE_URL"))
    with migration.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE quote_items, timeline_events, quote_public_access, quotes, "
                "equipment, clients, sessions, rate_limit_buckets, users "
                "RESTART IDENTITY CASCADE"
            )
        )
        connection.execute(text("ALTER SEQUENCE quote_number_seq RESTART WITH 1"))
        connection.execute(
            text(
                "UPDATE business_profiles SET trade_name='Climatech Original', "
                "phone='+55 71 3000-0000', email='contato@original.test', "
                "address='Rua Original, 10', timezone='America/Bahia', "
                "updated_at=:now, version=1 WHERE id=1"
            ),
            {"now": NOW},
        )
    migration_factory = sessionmaker(migration, expire_on_commit=False)
    actor = User(
        id=uuid4(),
        name="Admin CL04",
        email_normalized="admin.cl04@example.com",
        password_hash=hash_password(PASSWORD),
        role="ADMIN",
        status="ACTIVE",
        must_change_password=False,
        temporary_password_expires_at=None,
        password_changed_at=NOW,
        created_at=NOW,
        updated_at=NOW,
        version=1,
    )
    customer = Client(
        id=uuid4(),
        name="Cliente Histórico",
        phone="+55 71 99999-1111",
        email="cliente@example.com",
        address="Rua do Cliente, 20",
        notes="PII-CANARY-NOTES",
        status="ACTIVE",
        archived_at=None,
        created_at=NOW,
        updated_at=NOW,
        version=1,
    )
    with migration_factory() as session:
        session.add_all([actor, customer])
        session.commit()

    settings = ApiSettings().model_copy(
        update={"PUBLIC_BASE_URL": ORIGIN, "TRUSTED_ORIGINS": ORIGIN}
    )
    app = create_app(settings)
    clock = MutableClock(NOW)
    app.state.clock = clock
    factory = create_session_factory(app.state.engine)
    with TestClient(app, client=("198.51.100.40", 50000)) as browser:
        login = browser.post(
            "/api/v1/auth/login",
            json={"email": actor.email_normalized, "password": PASSWORD},
            headers={"Origin": ORIGIN, "X-ClientOps-Request": "browser-v1"},
        )
        assert login.status_code == 200, login.text
        yield QuoteHarness(
            browser,
            factory,
            migration_factory,
            clock,
            str(login.json()["data"]["csrf_token"]),
            actor.id,
            customer.id,
        )
    migration.dispose()


@pytest.mark.postgres
def test_draft_items_etag_search_and_validation(quotes_api: QuoteHarness) -> None:
    created, etag = quotes_api.create_quote()
    assert created["number"] == "ORC-000001"
    assert created["status"] == "DRAFT"
    assert created["items"][0]["quantity"] == "0.005"
    assert created["items"][0]["line_total"] == "0.01"
    assert created["subtotal"] == created["total"] == "0.01"
    quote_id = created["id"]
    item_id = created["items"][0]["id"]

    listing = quotes_api.client.get("/api/v1/quotes?q=Inspe%C3%A7%C3%A3o&sort=number")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["data"]] == [quote_id]
    number_search = quotes_api.client.get("/api/v1/quotes?q=ORC-000001")
    assert number_search.json()["data"][0]["id"] == quote_id
    assert quotes_api.client.get("/api/v1/quotes?sort=total").status_code == 422
    assert quotes_api.client.get("/api/v1/quotes?unknown=value").status_code == 422

    missing = quotes_api.client.patch(
        f"/api/v1/quotes/{quote_id}", json={"notes": "Nova"}, headers=quotes_api.headers
    )
    assert missing.status_code == 428
    invalid_null = quotes_api.client.patch(
        f"/api/v1/quotes/{quote_id}",
        json={"valid_until": None},
        headers={**quotes_api.headers, "If-Match": etag},
    )
    assert invalid_null.status_code == 422
    patched = quotes_api.client.patch(
        f"/api/v1/quotes/{quote_id}",
        json={
            "notes": None,
            "items": [
                {
                    "id": item_id,
                    "position": 1,
                    "description": "Inspeção atualizada",
                    "quantity": "2",
                    "unit_price": "180.00",
                }
            ],
        },
        headers={**quotes_api.headers, "If-Match": etag},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["data"]["notes"] is None
    assert patched.json()["data"]["items"][0]["id"] == item_id
    assert patched.json()["data"]["items"][0]["quantity"] == "2.000"
    assert patched.json()["data"]["total"] == "360.00"
    assert patched.headers["etag"] == '"v2"'

    stale = quotes_api.client.patch(
        f"/api/v1/quotes/{quote_id}",
        json={},
        headers={**quotes_api.headers, "If-Match": etag},
    )
    assert stale.status_code == 412
    assert stale.headers["etag"] == '"v2"'

    foreign, _ = quotes_api.create_quote(notes=None)
    foreign_item = {
        key: foreign["items"][0][key]
        for key in ("id", "position", "description", "quantity", "unit_price")
    }
    leak_safe = quotes_api.client.patch(
        f"/api/v1/quotes/{quote_id}",
        json={"items": [foreign_item]},
        headers={**quotes_api.headers, "If-Match": '"v2"'},
    )
    assert leak_safe.status_code == 404
    assert "foreign" not in leak_safe.text.lower()

    numeric = quotes_api.client.post(
        "/api/v1/quotes",
        json={
            "client_id": str(quotes_api.client_id),
            "valid_until": "2026-10-09",
            "items": [
                {
                    "position": 1,
                    "description": "Float proibido",
                    "quantity": 0.005,
                    "unit_price": 1.0,
                }
            ],
        },
        headers=quotes_api.headers,
    )
    assert numeric.status_code == 422


@pytest.mark.postgres
def test_send_public_projection_snapshot_and_idempotent_approval(
    quotes_api: QuoteHarness,
) -> None:
    created, etag = quotes_api.create_quote()
    issued, sent_etag = quotes_api.send_quote(created["id"], etag)
    assert sent_etag == '"v2"'
    assert issued["data"]["status"] == "SENT"
    assert issued["data"]["commercial_snapshot"]["business"]["trade_name"] == ("Climatech Original")
    share_url = issued["public_access"]["share_url"]
    parsed = urlsplit(share_url)
    assert parsed.query == ""
    assert parsed.path == "/q"
    assert parsed.fragment.startswith("token=")
    raw = parsed.fragment.removeprefix("token=")
    assert len(raw) == 43

    with quotes_api.factory() as session:
        access = session.scalar(select(QuotePublicAccess))
        assert access is not None
        assert access.bearer_hash == hashlib.sha256(raw.encode("ascii")).digest()
        serialized_rows = str(
            session.execute(
                select(Quote.commercial_snapshot, TimelineEvent.payload).join(
                    TimelineEvent, TimelineEvent.quote_id == Quote.id
                )
            ).all()
        )
        assert raw not in serialized_rows
        assert share_url not in serialized_rows

    public_headers = {"Authorization": f"Bearer {raw}", "Origin": ORIGIN}
    public = quotes_api.client.get("/api/v1/public/quote", headers=public_headers)
    assert public.status_code == 200, public.text
    public_data = public.json()["data"]
    assert set(public_data["client"]) == {"name"}
    assert public_data["client"] == {"name": "Cliente Histórico"}
    assert public_data["business"]["trade_name"] == "Climatech Original"
    assert public.headers["cache-control"] == "no-store"

    with quotes_api.migration_factory() as session:
        customer = session.get(Client, quotes_api.client_id)
        assert customer is not None
        customer.name = "Cliente Alterado Depois"
        customer.phone = "+55 71 98888-2222"
        session.execute(
            text(
                "UPDATE business_profiles SET trade_name='Climatech Nova', "
                "phone='+55 71 3111-1111', email='nova@example.test', "
                "address='Rua Nova', timezone='Pacific/Kiritimati', version=version+1 "
                "WHERE id=1"
            )
        )
        session.commit()
    historical = quotes_api.client.get("/api/v1/public/quote", headers=public_headers)
    assert historical.json()["data"]["client"]["name"] == "Cliente Histórico"
    assert historical.json()["data"]["business"]["trade_name"] == "Climatech Original"
    assert historical.json()["data"]["business_today"] == "2026-10-06"
    assert issued["data"]["commercial_snapshot"]["quote"]["business_timezone"] == "America/Bahia"

    quotes_api.clock.current += timedelta(minutes=1)
    approved = quotes_api.client.post(
        "/api/v1/public/quote/approve", json={"accept": True}, headers=public_headers
    )
    assert approved.status_code == 200, approved.text
    approved_at = approved.json()["data"]["approved_at"]
    repeated = quotes_api.client.post(
        "/api/v1/public/quote/approve", json={"accept": True}, headers=public_headers
    )
    assert repeated.status_code == 200
    assert repeated.json()["data"]["approved_at"] == approved_at
    assert (
        quotes_api.client.post(
            "/api/v1/public/quote/approve", json={"accept": False}, headers=public_headers
        ).status_code
        == 422
    )
    with quotes_api.factory() as session:
        quote = session.get(Quote, UUID(str(created["id"])))
        assert quote is not None and quote.status == "APPROVED" and quote.version == 3
        events = list(
            session.execute(
                select(TimelineEvent).where(
                    TimelineEvent.quote_id == quote.id,
                    TimelineEvent.event_type == "quote.approved",
                )
            ).scalars()
        )
        assert len(events) == 1
        assert events[0].actor_type == "CUSTOMER_QUOTE_LINK"


@pytest.mark.postgres
def test_public_invalid_uniform_expiry_rotate_revoke_cancel_duplicate(
    quotes_api: QuoteHarness,
) -> None:
    malformed_values = [None, "", "abc", "A" * 42, "A" * 44, "!" * 43]
    bodies = []
    for raw in malformed_values:
        headers = {} if raw is None else {"Authorization": f"Bearer {raw}"}
        response = quotes_api.client.get("/api/v1/public/quote", headers=headers)
        assert response.status_code == 401
        body = response.json()["error"]
        bodies.append((body["code"], body["message"]))
    assert len(set(bodies)) == 1

    created, etag = quotes_api.create_quote(valid_until="2026-10-05")
    issued, sent_etag = quotes_api.send_quote(created["id"], etag)
    access = issued["public_access"]
    raw = urlsplit(access["share_url"]).fragment.removeprefix("token=")
    public_headers = {"Authorization": f"Bearer {raw}", "Origin": ORIGIN}
    quotes_api.clock.current = datetime(2026, 10, 6, 3, 1, tzinfo=UTC)
    expired = quotes_api.client.get("/api/v1/public/quote", headers=public_headers)
    assert expired.status_code == 200
    assert expired.json()["data"]["is_expired"] is True
    denied = quotes_api.client.post(
        "/api/v1/public/quote/approve", json={"accept": True}, headers=public_headers
    )
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "QUOTE_EXPIRED"
    quotes_api.relogin()
    rotate_expired = quotes_api.client.post(
        f"/api/v1/quotes/{created['id']}/public-access",
        json={"expected_access_id": access["id"]},
        headers=quotes_api.headers,
    )
    assert rotate_expired.status_code == 409

    duplicate = quotes_api.client.post(
        f"/api/v1/quotes/{created['id']}/duplicate", json={}, headers=quotes_api.headers
    )
    assert duplicate.status_code == 201, duplicate.text
    duplicated = duplicate.json()["data"]
    assert duplicated["status"] == "DRAFT"
    assert duplicated["source_quote_id"] == created["id"]
    assert duplicated["number"] != created["number"]
    assert duplicated["commercial_snapshot"] is None
    assert duplicated["public_access"] is None
    assert duplicated["valid_until"] == "2026-10-20"

    cancelled = quotes_api.client.post(
        f"/api/v1/quotes/{created['id']}/cancel",
        json={"reason": "Prazo encerrado"},
        headers={**quotes_api.headers, "If-Match": sent_etag},
    )
    assert cancelled.status_code == 200, cancelled.text
    cancelled_etag = cancelled.headers["etag"]
    repeated = quotes_api.client.post(
        f"/api/v1/quotes/{created['id']}/cancel",
        json={"reason": "Outro motivo ignorado"},
        headers={**quotes_api.headers, "If-Match": cancelled_etag},
    )
    assert repeated.status_code == 200
    assert repeated.headers["etag"] == cancelled_etag
    assert repeated.json()["data"]["cancellation_reason"] == "Prazo encerrado"
    assert quotes_api.client.get("/api/v1/public/quote", headers=public_headers).status_code == 401


@pytest.mark.postgres
def test_admin_and_public_logo_contracts(quotes_api: QuoteHarness) -> None:
    created, etag = quotes_api.create_quote()
    assert quotes_api.client.get(f"/api/v1/quotes/{created['id']}/logo").status_code == 404
    issued, _ = quotes_api.send_quote(created["id"], etag)
    raw = urlsplit(issued["public_access"]["share_url"]).fragment.removeprefix("token=")
    assert (
        quotes_api.client.get(
            "/api/v1/public/quote/logo", headers={"Authorization": f"Bearer {raw}"}
        ).status_code
        == 404
    )
    assert (
        quotes_api.client.get(
            "/api/v1/public/quote/logo", headers={"Authorization": "Bearer " + "A" * 43}
        ).status_code
        == 401
    )
