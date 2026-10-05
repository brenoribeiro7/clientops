from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import Clock
from app.core.config import ApiSettings
from app.core.db import create_session_factory
from app.core.errors import FoundationError
from app.core.rate_limits import RateRule
from app.main import create_app
from app.modules.business.models import BusinessProfile
from app.modules.business.schemas import BusinessProfilePatch
from app.modules.business.service import update_profile
from app.modules.clients.models import Client
from app.modules.clients.service import set_client_archived
from app.modules.identity.models import User
from app.modules.identity.passwords import hash_password
from app.modules.quotes.models import Quote, QuotePublicAccess
from app.modules.quotes.schemas import QuotePatch
from app.modules.quotes.service import (
    approve_quote,
    cancel_quote,
    duplicate_quote,
    patch_quote,
    revoke_access,
    rotate_access,
    run_command,
    send_quote,
)
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


@pytest.mark.postgres
def test_quote_routes_require_admin_origin_csrf_and_json(quotes_api: QuoteHarness) -> None:
    with quotes_api.migration_factory() as session:
        actor = session.get(User, quotes_api.actor_id)
        assert actor is not None
        actor.role = "TECHNICIAN"
        session.commit()
    denied = quotes_api.client.get(f"/api/v1/quotes/{uuid4()}")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "FORBIDDEN"
    with quotes_api.migration_factory() as session:
        actor = session.get(User, quotes_api.actor_id)
        assert actor is not None
        actor.role = "ADMIN"
        session.commit()

    payload = {"client_id": str(quotes_api.client_id), "valid_until": "2026-10-10"}
    missing_origin = quotes_api.client.post(
        "/api/v1/quotes", json=payload, headers={"X-CSRF-Token": quotes_api.csrf}
    )
    assert missing_origin.status_code == 403
    missing_csrf = quotes_api.client.post(
        "/api/v1/quotes", json=payload, headers={"Origin": ORIGIN}
    )
    assert missing_csrf.status_code == 403
    wrong_media = quotes_api.client.post(
        "/api/v1/quotes",
        content='{"client_id":"00000000-0000-0000-0000-000000000000","valid_until":"2026-10-10"}',
        headers={**quotes_api.headers, "Content-Type": "text/plain"},
    )
    assert wrong_media.status_code == 415
    assert (
        quotes_api.client.get(
            "/api/v1/public/quote/logo", headers={"Authorization": "Bearer " + "A" * 43}
        ).status_code
        == 401
    )


@pytest.mark.postgres
def test_send_requires_complete_profile_and_active_client(quotes_api: QuoteHarness) -> None:
    profile_values = {
        "trade_name": "Climatech Original",
        "phone": "+55 71 3000-0000",
        "email": "contato@original.test",
        "address": "Rua Original, 10",
        "timezone": "America/Bahia",
    }
    for field in profile_values:
        created, etag = quotes_api.create_quote()
        with quotes_api.migration_factory() as session:
            session.execute(
                text(f"UPDATE business_profiles SET {field}=NULL, version=version+1 WHERE id=1")
            )
            session.commit()
        denied = quotes_api.client.post(
            f"/api/v1/quotes/{created['id']}/send",
            json={},
            headers={**quotes_api.headers, "If-Match": etag},
        )
        assert denied.status_code == 409
        assert denied.json()["error"]["code"] == "BUSINESS_PROFILE_INCOMPLETE"
        assert denied.json()["error"]["details"]["missing_fields"] == [field]
        with quotes_api.factory() as session:
            quote = session.get(Quote, UUID(str(created["id"])))
            assert quote is not None and quote.status == "DRAFT" and quote.version == 1
            assert (
                session.scalar(
                    select(QuotePublicAccess).where(QuotePublicAccess.quote_id == quote.id)
                )
                is None
            )
            assert (
                session.scalar(
                    select(TimelineEvent).where(
                        TimelineEvent.quote_id == quote.id,
                        TimelineEvent.event_type == "quote.sent",
                    )
                )
                is None
            )
        with quotes_api.migration_factory() as session:
            session.execute(
                text(f"UPDATE business_profiles SET {field}=:value, version=version+1 WHERE id=1"),
                {"value": profile_values[field]},
            )
            session.commit()

    created, etag = quotes_api.create_quote()
    with quotes_api.migration_factory() as session:
        customer = session.get(Client, quotes_api.client_id)
        assert customer is not None
        customer.status = "ARCHIVED"
        customer.archived_at = quotes_api.clock.current
        session.commit()
    denied = quotes_api.client.post(
        f"/api/v1/quotes/{created['id']}/send",
        json={},
        headers={**quotes_api.headers, "If-Match": etag},
    )
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "CLIENT_ARCHIVED"
    new_denied = quotes_api.client.post(
        "/api/v1/quotes",
        json={"client_id": str(quotes_api.client_id), "valid_until": "2026-10-10"},
        headers=quotes_api.headers,
    )
    assert new_denied.status_code == 409


@pytest.mark.postgres
def test_access_rotation_revoke_exact_expiry_and_auth_boundaries(
    quotes_api: QuoteHarness,
) -> None:
    created, etag = quotes_api.create_quote()
    issued, _ = quotes_api.send_quote(created["id"], etag)
    first = issued["public_access"]
    first_raw = urlsplit(first["share_url"]).fragment.removeprefix("token=")

    mismatch = quotes_api.client.post(
        f"/api/v1/quotes/{created['id']}/public-access",
        json={"expected_access_id": str(uuid4())},
        headers=quotes_api.headers,
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "ACCESS_CHANGED"
    rotated = quotes_api.client.post(
        f"/api/v1/quotes/{created['id']}/public-access",
        json={"expected_access_id": first["id"]},
        headers=quotes_api.headers,
    )
    assert rotated.status_code == 200, rotated.text
    second = rotated.json()["data"]
    second_raw = urlsplit(second["share_url"]).fragment.removeprefix("token=")
    assert second_raw != first_raw
    assert (
        quotes_api.client.get(
            "/api/v1/public/quote", headers={"Authorization": f"Bearer {first_raw}"}
        ).status_code
        == 401
    )
    assert (
        quotes_api.client.get(
            "/api/v1/public/quote", headers={"Authorization": f"Bearer {second_raw}"}
        ).status_code
        == 200
    )

    other, _ = quotes_api.create_quote()
    cross_quote = quotes_api.client.post(
        f"/api/v1/quotes/{other['id']}/public-access/{second['id']}/revoke",
        json={},
        headers=quotes_api.headers,
    )
    assert cross_quote.status_code == 404
    revoke_path = f"/api/v1/quotes/{created['id']}/public-access/{second['id']}/revoke"
    revoked = quotes_api.client.post(revoke_path, json={}, headers=quotes_api.headers)
    assert revoked.status_code == 200
    repeated = quotes_api.client.post(revoke_path, json={}, headers=quotes_api.headers)
    assert repeated.status_code == 200
    assert repeated.json() == revoked.json()
    assert (
        quotes_api.client.get(
            "/api/v1/public/quote", headers={"Authorization": f"Bearer {second_raw}"}
        ).status_code
        == 401
    )

    expiring, expiring_etag = quotes_api.create_quote()
    expiring_issue, _ = quotes_api.send_quote(expiring["id"], expiring_etag)
    expiring_raw = urlsplit(expiring_issue["public_access"]["share_url"]).fragment.removeprefix(
        "token="
    )
    quotes_api.clock.current = datetime.fromisoformat(
        expiring_issue["public_access"]["expires_at"].replace("Z", "+00:00")
    )
    boundary = quotes_api.client.get(
        "/api/v1/public/quote", headers={"Authorization": f"Bearer {expiring_raw}"}
    )
    assert boundary.status_code == 401
    assert boundary.json()["error"]["code"] == "PUBLIC_ACCESS_INVALID"

    anonymous = quotes_api.client.get(
        f"/api/v1/quotes/{uuid4()}", cookies={"clientops_session_dev": ""}
    )
    assert anonymous.status_code == 401
    bearer_is_not_private_auth = quotes_api.client.get(
        f"/api/v1/quotes/{uuid4()}",
        headers={"Authorization": f"Bearer {expiring_raw}"},
        cookies={"clientops_session_dev": ""},
    )
    assert bearer_is_not_private_auth.status_code == 401


@pytest.mark.postgres
def test_public_rate_limit_order_origin_and_fail_closed(
    quotes_api: QuoteHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    install = RateRule("cl04_public_install_test", 1, 60)
    ip = RateRule("cl04_public_ip_test", 100, 60)
    bearer = RateRule("cl04_public_bearer_test", 100, 60)
    monkeypatch.setattr("app.modules.quotes.router.PUBLIC_QUOTE_GET_INSTALLATION", install)
    monkeypatch.setattr("app.modules.quotes.router.PUBLIC_QUOTE_GET_IP", ip)
    monkeypatch.setattr("app.modules.quotes.router.PUBLIC_QUOTE_GET_BEARER", bearer)
    first = quotes_api.client.get("/api/v1/public/quote")
    assert first.status_code == 401
    second = quotes_api.client.get("/api/v1/public/quote")
    assert second.status_code == 429
    assert int(second.headers["retry-after"]) > 0
    with quotes_api.factory() as session:
        assert (
            session.scalar(
                text("SELECT count(*) FROM rate_limit_buckets WHERE rule='cl04_public_bearer_test'")
            )
            == 0
        )

    created, etag = quotes_api.create_quote()
    issued, _ = quotes_api.send_quote(created["id"], etag)
    raw = urlsplit(issued["public_access"]["share_url"]).fragment.removeprefix("token=")
    missing_origin = quotes_api.client.post(
        "/api/v1/public/quote/approve",
        json={"accept": True},
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert missing_origin.status_code == 403
    wrong_content = quotes_api.client.post(
        "/api/v1/public/quote/approve",
        content='{"accept":true}',
        headers={"Authorization": f"Bearer {raw}", "Origin": ORIGIN, "Content-Type": "text/plain"},
    )
    assert wrong_content.status_code == 415

    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise SQLAlchemyError("rate database unavailable")

    monkeypatch.setattr("app.modules.quotes.router.consume", unavailable)
    failed = quotes_api.client.get(
        "/api/v1/public/quote", headers={"Authorization": f"Bearer {raw}"}
    )
    assert failed.status_code == 503
    assert failed.json()["error"]["code"] == "TEMPORARILY_UNAVAILABLE"


def _race(left: object, right: object) -> list[str]:
    barrier = Barrier(3)

    def execute(operation: object) -> str:
        barrier.wait(timeout=10)
        try:
            operation()  # type: ignore[operator]
        except FoundationError as error:
            return error.code
        return "OK"

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(execute, left)
        second = pool.submit(execute, right)
        barrier.wait(timeout=10)
        return [first.result(timeout=30), second.result(timeout=30)]


@pytest.mark.postgres
def test_quote_draft_send_and_duplicate_races(quotes_api: QuoteHarness) -> None:
    created, etag = quotes_api.create_quote()
    quote_id = UUID(str(created["id"]))

    def patch(notes: str) -> None:
        with quotes_api.factory() as session:
            patch_quote(
                session,
                quote_id=quote_id,
                patch=QuotePatch(notes=notes),
                if_match=etag,
                actor_user_id=quotes_api.actor_id,
                now=quotes_api.clock.current,
            )

    assert sorted(_race(lambda: patch("A"), lambda: patch("B"))) == ["OK", "VERSION_CONFLICT"]
    with quotes_api.factory() as session:
        saved = session.get(Quote, quote_id)
        assert saved is not None and saved.version == 2 and saved.notes in {"A", "B"}
        assert (
            session.scalar(
                select(func.count())
                .select_from(TimelineEvent)
                .where(
                    TimelineEvent.quote_id == quote_id, TimelineEvent.event_type == "quote.updated"
                )
            )
            == 1
        )

    items_quote, items_etag = quotes_api.create_quote()
    items_id = UUID(str(items_quote["id"]))

    def replace(description: str) -> None:
        with quotes_api.factory() as session:
            patch_quote(
                session,
                quote_id=items_id,
                patch=QuotePatch.model_validate(
                    {
                        "items": [
                            {
                                "position": 1,
                                "description": description,
                                "quantity": "1.000",
                                "unit_price": "10.00",
                            }
                        ]
                    }
                ),
                if_match=items_etag,
                actor_user_id=quotes_api.actor_id,
                now=quotes_api.clock.current,
            )

    assert sorted(_race(lambda: replace("Item A"), lambda: replace("Item B"))) == [
        "OK",
        "VERSION_CONFLICT",
    ]
    with quotes_api.factory() as session:
        saved = session.scalar(select(Quote).where(Quote.id == items_id))
        assert saved is not None and saved.version == 2
        assert len(saved.items) == 1 and saved.items[0].description in {"Item A", "Item B"}

    sendable, send_etag = quotes_api.create_quote()
    send_id = UUID(str(sendable["id"]))

    def send() -> None:
        with quotes_api.factory() as session:
            send_quote(
                session,
                quote_id=send_id,
                if_match=send_etag,
                actor_user_id=quotes_api.actor_id,
                now=quotes_api.clock.current,
                settings=quotes_api.client.app.state.settings,
            )

    assert sorted(_race(send, send)) == ["OK", "VERSION_CONFLICT"]
    with quotes_api.factory() as session:
        saved = session.get(Quote, send_id)
        assert saved is not None and saved.status == "SENT" and saved.version == 2
        assert (
            session.scalar(
                select(func.count())
                .select_from(QuotePublicAccess)
                .where(
                    QuotePublicAccess.quote_id == send_id, QuotePublicAccess.revoked_at.is_(None)
                )
            )
            == 1
        )

    source, _ = quotes_api.create_quote()
    source_id = UUID(str(source["id"]))
    numbers: list[int] = []

    def duplicate() -> None:
        with quotes_api.factory() as session:
            model = duplicate_quote(
                session,
                quote_id=source_id,
                actor_user_id=quotes_api.actor_id,
                now=quotes_api.clock.current,
            )
            numbers.append(model.number)

    assert _race(duplicate, duplicate) == ["OK", "OK"]
    assert len(set(numbers)) == 2


@pytest.mark.postgres
def test_public_approval_and_access_races(quotes_api: QuoteHarness) -> None:
    def sent_quote() -> tuple[UUID, bytes, UUID]:
        created, etag = quotes_api.create_quote()
        issued, _ = quotes_api.send_quote(created["id"], etag)
        raw = urlsplit(issued["public_access"]["share_url"]).fragment.removeprefix("token=")
        return (
            UUID(str(created["id"])),
            hashlib.sha256(raw.encode("ascii")).digest(),
            UUID(str(issued["public_access"]["id"])),
        )

    quote_id, digest, _ = sent_quote()

    def approve(target_digest: bytes) -> None:
        with quotes_api.factory() as session:
            approve_quote(session, digest=target_digest, now=quotes_api.clock.current)

    assert _race(lambda: approve(digest), lambda: approve(digest)) == ["OK", "OK"]
    with quotes_api.factory() as session:
        saved = session.get(Quote, quote_id)
        assert saved is not None and saved.status == "APPROVED" and saved.version == 3
        assert (
            session.scalar(
                select(func.count())
                .select_from(TimelineEvent)
                .where(
                    TimelineEvent.quote_id == quote_id, TimelineEvent.event_type == "quote.approved"
                )
            )
            == 1
        )

    quote_id, digest, _ = sent_quote()

    def cancel() -> None:
        with quotes_api.factory() as session:
            cancel_quote(
                session,
                quote_id=quote_id,
                reason="Corrida",
                if_match='"v2"',
                actor_user_id=quotes_api.actor_id,
                now=quotes_api.clock.current,
            )

    assert _race(lambda: approve(digest), cancel).count("OK") == 1
    with quotes_api.factory() as session:
        saved = session.get(Quote, quote_id)
        assert saved is not None and saved.status in {"APPROVED", "CANCELLED"}

    quote_id, digest, access_id = sent_quote()

    def rotate(target_quote_id: UUID, expected: UUID) -> None:
        with quotes_api.factory() as session:
            rotate_access(
                session,
                quote_id=target_quote_id,
                expected_access_id=expected,
                actor_user_id=quotes_api.actor_id,
                now=quotes_api.clock.current,
                settings=quotes_api.client.app.state.settings,
            )

    assert _race(lambda: approve(digest), lambda: rotate(quote_id, access_id)).count("OK") == 1

    quote_id, _, access_id = sent_quote()
    assert sorted(
        _race(lambda: rotate(quote_id, access_id), lambda: rotate(quote_id, access_id))
    ) == [
        "ACCESS_CHANGED",
        "OK",
    ]
    with quotes_api.factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(QuotePublicAccess)
                .where(
                    QuotePublicAccess.quote_id == quote_id, QuotePublicAccess.revoked_at.is_(None)
                )
            )
            == 1
        )

    quote_id, _, access_id = sent_quote()

    def revoke() -> None:
        with quotes_api.factory() as session:
            revoke_access(
                session,
                quote_id=quote_id,
                access_id=access_id,
                actor_user_id=quotes_api.actor_id,
                now=quotes_api.clock.current,
            )

    assert _race(lambda: rotate(quote_id, access_id), revoke) == ["OK", "OK"]
    with quotes_api.factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(QuotePublicAccess)
                .where(
                    QuotePublicAccess.quote_id == quote_id, QuotePublicAccess.revoked_at.is_(None)
                )
            )
            == 1
        )

    quote_id, _, access_id = sent_quote()
    outcomes = _race(cancel, lambda: rotate(quote_id, access_id))
    assert outcomes.count("OK") in {1, 2}
    with quotes_api.factory() as session:
        saved = session.get(Quote, quote_id)
        assert saved is not None and saved.status == "CANCELLED"
        assert (
            session.scalar(
                select(func.count())
                .select_from(QuotePublicAccess)
                .where(
                    QuotePublicAccess.quote_id == quote_id, QuotePublicAccess.revoked_at.is_(None)
                )
            )
            == 0
        )


@pytest.mark.postgres
def test_send_serializes_with_client_archive_and_profile_update(
    quotes_api: QuoteHarness,
) -> None:
    created, etag = quotes_api.create_quote()
    quote_id = UUID(str(created["id"]))

    def send() -> None:
        with quotes_api.factory() as session:
            send_quote(
                session,
                quote_id=quote_id,
                if_match=etag,
                actor_user_id=quotes_api.actor_id,
                now=quotes_api.clock.current,
                settings=quotes_api.client.app.state.settings,
            )

    def archive() -> None:
        with quotes_api.factory() as session:
            set_client_archived(
                session,
                client_id=quotes_api.client_id,
                archived=True,
                if_match='"v1"',
                actor_user_id=quotes_api.actor_id,
                now=quotes_api.clock.current,
            )

    outcomes = _race(send, archive)
    assert outcomes.count("OK") in {1, 2}
    assert set(outcomes) <= {"OK", "CLIENT_ARCHIVED"}
    with quotes_api.factory() as session:
        quote = session.get(Quote, quote_id)
        client = session.get(Client, quotes_api.client_id)
        assert quote is not None and client is not None and client.status == "ARCHIVED"
        assert quote.status == ("SENT" if outcomes.count("OK") == 2 else "DRAFT")

    with quotes_api.migration_factory() as session:
        client = session.get(Client, quotes_api.client_id)
        assert client is not None
        client.status = "ACTIVE"
        client.archived_at = None
        client.version += 1
        session.commit()

    created, etag = quotes_api.create_quote()
    quote_id = UUID(str(created["id"]))

    def send_profile_race() -> None:
        with quotes_api.factory() as session:
            send_quote(
                session,
                quote_id=quote_id,
                if_match=etag,
                actor_user_id=quotes_api.actor_id,
                now=quotes_api.clock.current,
                settings=quotes_api.client.app.state.settings,
            )

    def update_business() -> None:
        with quotes_api.factory() as session:
            update_profile(
                session,
                patch=BusinessProfilePatch(
                    trade_name="Climatech Atualizada",
                    timezone="Asia/Tokyo",
                    acknowledge_timezone_change=True,
                ),
                if_match='"v1"',
                actor_user_id=quotes_api.actor_id,
                now=quotes_api.clock.current,
            )

    assert _race(send_profile_race, update_business) == ["OK", "OK"]
    with quotes_api.factory() as session:
        quote = session.get(Quote, quote_id)
        assert quote is not None and quote.commercial_snapshot is not None
        snapshot = quote.commercial_snapshot
        pair = (
            snapshot["business"]["trade_name"],
            snapshot["quote"]["business_timezone"],
        )
        assert pair in {
            ("Climatech Original", "America/Bahia"),
            ("Climatech Atualizada", "Asia/Tokyo"),
        }


@pytest.mark.postgres
def test_real_deadlock_retries_the_complete_transaction(quotes_api: QuoteHarness) -> None:
    first, _ = quotes_api.create_quote()
    second, _ = quotes_api.create_quote()
    first_id = UUID(str(first["id"]))
    second_id = UUID(str(second["id"]))
    barrier = Barrier(3)
    attempts: list[int] = []

    def lock_in_order(primary: UUID, secondary: UUID) -> None:
        with quotes_api.factory() as session:
            count = 0

            def operation() -> None:
                nonlocal count
                count += 1
                session.execute(
                    select(Quote).where(Quote.id == primary).with_for_update()
                ).scalar_one()
                if count == 1:
                    barrier.wait(timeout=10)
                session.execute(
                    select(Quote).where(Quote.id == secondary).with_for_update()
                ).scalar_one()
                session.commit()

            run_command(session, operation)
            attempts.append(count)

    with ThreadPoolExecutor(max_workers=2) as pool:
        left = pool.submit(lock_in_order, first_id, second_id)
        right = pool.submit(lock_in_order, second_id, first_id)
        barrier.wait(timeout=10)
        left.result(timeout=30)
        right.result(timeout=30)
    assert sorted(attempts) == [1, 2]


@pytest.mark.postgres
@pytest.mark.parametrize("operation", ["approve", "rotate"])
def test_timezone_change_serializes_before_public_decision(
    quotes_api: QuoteHarness, operation: str
) -> None:
    with quotes_api.migration_factory() as session:
        profile = session.get(BusinessProfile, 1)
        assert profile is not None
        profile.timezone = "America/Bahia"
        session.commit()
    created, etag = quotes_api.create_quote(valid_until="2026-10-05")
    issued, _ = quotes_api.send_quote(created["id"], etag)
    raw = urlsplit(issued["public_access"]["share_url"]).fragment.removeprefix("token=")
    digest = hashlib.sha256(raw.encode("ascii")).digest()
    quote_id = UUID(str(created["id"]))
    access_id = UUID(str(issued["public_access"]["id"]))
    race_now = datetime(2026, 10, 6, 2, 30, tzinfo=UTC)
    engine = quotes_api.factory.kw["bind"]
    blocked = Event()

    def before_execute(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        if "FROM business_profiles" in statement and "FOR UPDATE" in statement:
            blocked.set()

    def decide() -> str:
        with quotes_api.factory() as session:
            try:
                if operation == "approve":
                    approve_quote(session, digest=digest, now=race_now)
                else:
                    rotate_access(
                        session,
                        quote_id=quote_id,
                        expected_access_id=access_id,
                        actor_user_id=quotes_api.actor_id,
                        now=race_now,
                        settings=quotes_api.client.app.state.settings,
                    )
            except FoundationError as error:
                return error.code
        return "OK"

    with quotes_api.migration_factory() as holder:
        profile = holder.get(BusinessProfile, 1, with_for_update=True)
        assert profile is not None
        profile.timezone = "Asia/Tokyo"
        event.listen(engine, "before_cursor_execute", before_execute)
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(decide)
                assert blocked.wait(timeout=10)
                holder.commit()
                assert future.result(timeout=30) == "QUOTE_EXPIRED"
        finally:
            event.remove(engine, "before_cursor_execute", before_execute)

    with quotes_api.factory() as session:
        saved = session.get(Quote, quote_id)
        assert saved is not None and saved.status == "SENT"
        assert saved.commercial_snapshot is not None
        assert saved.commercial_snapshot["quote"]["business_timezone"] == "America/Bahia"
        assert (
            session.scalar(
                select(func.count())
                .select_from(QuotePublicAccess)
                .where(
                    QuotePublicAccess.quote_id == quote_id, QuotePublicAccess.revoked_at.is_(None)
                )
            )
            == 1
        )
