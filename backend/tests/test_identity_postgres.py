from __future__ import annotations

import os
import pty
import select as io_select
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import Clock
from app.core.config import ApiSettings
from app.core.db import create_session_factory
from app.core.errors import FoundationError
from app.core.rate_limits import LOGIN_IP, RateRule, consume
from app.main import create_app
from app.modules.business.models import BusinessProfile
from app.modules.business.schemas import BusinessProfilePatch
from app.modules.business.service import update_profile
from app.modules.identity.models import Session as SessionModel
from app.modules.identity.models import User
from app.modules.identity.passwords import hash_password, verify_password
from app.modules.identity.service import authenticate, change_password, is_active, mutate_user
from app.modules.timeline.models import TimelineEvent

ORIGIN = "http://localhost:8080"
LOGIN_HEADERS = {"Origin": ORIGIN, "X-ClientOps-Request": "browser-v1"}
NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


@dataclass
class MutableClock(Clock):
    current: datetime

    def now_utc(self) -> datetime:
        return self.current


@dataclass
class Harness:
    client: TestClient
    factory: sessionmaker[Session]
    settings: ApiSettings
    clock: MutableClock
    engine: Engine
    csrf: str | None = None

    def user(
        self,
        *,
        email: str,
        password: str,
        role: str = "ADMIN",
        status: str = "ACTIVE",
        temporary: bool = False,
        name: str = "Test User",
    ) -> User:
        user = User(
            id=uuid4(),
            name=name,
            email_normalized=email,
            password_hash=hash_password(password),
            role=role,
            status=status,
            must_change_password=temporary,
            temporary_password_expires_at=(self.clock.current + timedelta(hours=24))
            if temporary
            else None,
            password_changed_at=self.clock.current,
            created_at=self.clock.current,
            updated_at=self.clock.current,
            version=1,
        )
        with self.factory() as session:
            session.add(user)
            session.commit()
        return user

    def login(self, email: str, password: str) -> dict[str, object]:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
            headers=LOGIN_HEADERS,
        )
        assert response.status_code == 200, response.text
        data: dict[str, object] = response.json()["data"]
        self.csrf = str(data["csrf_token"])
        return data

    def mutation_headers(self, etag: str | None = None) -> dict[str, str]:
        assert self.csrf is not None
        headers = {"Origin": ORIGIN, "X-CSRF-Token": self.csrf}
        if etag is not None:
            headers["If-Match"] = etag
        return headers


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is required")
    return value


def _tty_cli(module: str, arguments: list[str], password: str) -> tuple[int, bytes]:
    master, slave = pty.openpty()
    command = ["python", "-m", module, *arguments]
    assert password not in " ".join(command)
    process = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    output = bytearray()
    try:
        for prompt in (b"Password:", b"Confirm password:"):
            while prompt not in output:
                ready, _, _ = io_select.select([master], [], [], 10)
                assert ready, "CLI did not prompt on TTY"
                output.extend(os.read(master, 4096))
            os.write(master, password.encode() + b"\n")
        status = process.wait(timeout=20)
        while io_select.select([master], [], [], 0)[0]:
            try:
                output.extend(os.read(master, 4096))
            except OSError:
                break
    finally:
        os.close(master)
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
    assert password.encode() not in output
    return status, bytes(output)


@pytest.fixture
def identity() -> Iterator[Harness]:
    migration = create_engine(_required("MIGRATION_DATABASE_URL"))
    with migration.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE timeline_events, sessions, rate_limit_buckets, users "
                "RESTART IDENTITY CASCADE"
            )
        )
        connection.execute(
            text(
                "UPDATE business_profiles SET trade_name=NULL, phone=NULL, email=NULL, "
                "address=NULL, timezone=NULL, updated_at=CURRENT_TIMESTAMP, version=1 WHERE id=1"
            )
        )
    settings = ApiSettings().model_copy(
        update={"PUBLIC_BASE_URL": ORIGIN, "TRUSTED_ORIGINS": ORIGIN}
    )
    app = create_app(settings)
    clock = MutableClock(NOW)
    app.state.clock = clock
    factory = create_session_factory(app.state.engine)
    with TestClient(app, client=("198.51.100.10", 50000)) as client:
        yield Harness(client, factory, settings, clock, app.state.engine)
    migration.dispose()


@pytest.mark.postgres
def test_login_cookie_hash_origin_csrf_and_logout(identity: Harness) -> None:
    identity.user(email="admin@example.com", password="Long secure password 2026")
    missing_origin = identity.client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "Long secure password 2026"},
        headers={"X-ClientOps-Request": "browser-v1"},
    )
    assert missing_origin.status_code == 403
    data = identity.login(" ADMIN@example.com ", "Long secure password 2026")
    raw = identity.client.cookies["clientops_session_dev"]
    assert len(raw) == 43
    with identity.factory() as session:
        stored = session.scalar(select(SessionModel))
        assert stored is not None
        assert stored.bearer_hash != raw.encode()
        assert len(stored.bearer_hash) == 32
    session_response = identity.client.get("/api/v1/auth/session")
    assert session_response.status_code == 200
    assert session_response.headers["cache-control"] == "no-store"
    csrf = str(data["csrf_token"])
    failed = identity.client.post("/api/v1/auth/logout", json={}, headers={"Origin": ORIGIN})
    assert failed.status_code == 403
    logout = identity.client.post(
        "/api/v1/auth/logout",
        json={},
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
    )
    assert logout.status_code == 204
    assert identity.client.get("/api/v1/auth/session").status_code == 401
    repeated = identity.client.post(
        "/api/v1/auth/logout",
        json={},
        headers={"Origin": ORIGIN, "X-ClientOps-Request": "browser-v1"},
    )
    assert repeated.status_code == 204


@pytest.mark.postgres
def test_disabled_unknown_and_expired_temporary_logins_are_uniform(identity: Harness) -> None:
    identity.user(
        email="disabled@example.com",
        password="Disabled account password",
        status="DISABLED",
    )
    expired = identity.user(
        email="expired@example.com",
        password="Expired temporary password",
        temporary=True,
    )
    with identity.factory() as session:
        model = session.get(User, expired.id)
        assert model is not None
        model.temporary_password_expires_at = NOW
        session.commit()
    attempts = [
        ("disabled@example.com", "Disabled account password"),
        ("expired@example.com", "Expired temporary password"),
        ("unknown@example.com", "Unknown account password"),
    ]
    for email, password in attempts:
        response = identity.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
            headers=LOGIN_HEADERS,
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.postgres
def test_forced_password_change_rotates_session(identity: Harness) -> None:
    user = identity.user(
        email="tech@example.com",
        password="Temporary password 2026",
        role="TECHNICIAN",
        temporary=True,
    )
    data = identity.login("tech@example.com", "Temporary password 2026")
    old_raw = identity.client.cookies["clientops_session_dev"]
    assert identity.client.get("/api/v1/business-profile").json()["error"]["code"] == (
        "PASSWORD_CHANGE_REQUIRED"
    )
    changed = identity.client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "Temporary password 2026",
            "new_password": "A new permanent password 🔐 2026",
        },
        headers={"Origin": ORIGIN, "X-CSRF-Token": str(data["csrf_token"])},
    )
    assert changed.status_code == 200, changed.text
    assert identity.client.cookies["clientops_session_dev"] != old_raw
    with identity.factory() as session:
        saved = session.get(User, user.id)
        assert saved is not None and not saved.must_change_password
        assert verify_password(saved.password_hash, "A new permanent password 🔐 2026")
        sessions = list(
            session.execute(select(SessionModel).where(SessionModel.user_id == user.id)).scalars()
        )
        assert len(sessions) == 2
        assert sum(item.revoked_at is None for item in sessions) == 1
    forbidden = identity.client.get("/api/v1/business-profile")
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.postgres
def test_session_cap_ignores_expired_and_serializes_sixth_logins(identity: Harness) -> None:
    user = identity.user(email="cap@example.com", password="Session cap password 2026")
    for _ in range(5):
        with identity.factory() as session:
            authenticate(
                session,
                email=user.email_normalized,
                password="Session cap password 2026",
                now=identity.clock.current,
                settings=identity.settings,
            )
    identity.clock.current += timedelta(seconds=1)
    barrier = Barrier(3)

    def login() -> None:
        barrier.wait(timeout=10)
        with identity.factory() as session:
            authenticate(
                session,
                email=user.email_normalized,
                password="Session cap password 2026",
                now=identity.clock.current,
                settings=identity.settings,
            )

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(login)
        second = pool.submit(login)
        barrier.wait(timeout=10)
        first.result(timeout=30)
        second.result(timeout=30)
    with identity.factory() as session:
        models = list(
            session.execute(select(SessionModel).where(SessionModel.user_id == user.id)).scalars()
        )
        assert (
            sum(
                is_active(item, identity.clock.current, identity.settings.SESSION_IDLE_SECONDS)
                for item in models
            )
            == 5
        )


@pytest.mark.postgres
def test_session_boundaries_and_expired_sessions_do_not_consume_cap(identity: Harness) -> None:
    user = identity.user(email="boundary@example.com", password="Boundary password 2026")
    with identity.factory() as session:
        for index in range(4):
            session.add(
                SessionModel(
                    id=uuid4(),
                    user_id=user.id,
                    bearer_hash=bytes([index]) * 32,
                    created_at=NOW,
                    last_seen_at=NOW,
                    absolute_expires_at=NOW + timedelta(hours=12),
                    revoked_at=None,
                    revocation_reason=None,
                )
            )
        session.add(
            SessionModel(
                id=uuid4(),
                user_id=user.id,
                bearer_hash=b"x" * 32,
                created_at=NOW - timedelta(hours=13),
                last_seen_at=NOW - timedelta(hours=13),
                absolute_expires_at=NOW,
                revoked_at=None,
                revocation_reason=None,
            )
        )
        session.commit()
        absolute = session.scalar(select(SessionModel).where(SessionModel.bearer_hash == b"x" * 32))
        assert absolute is not None and not is_active(absolute, NOW, 1800)
    with identity.factory() as session:
        authenticate(
            session,
            email=user.email_normalized,
            password="Boundary password 2026",
            now=NOW,
            settings=identity.settings,
        )
    with identity.factory() as session:
        models = list(session.scalars(select(SessionModel).where(SessionModel.user_id == user.id)))
        assert sum(is_active(item, NOW, 1800) for item in models) == 5
        idle = models[0]
        idle.last_seen_at = NOW - timedelta(seconds=1800)
        assert not is_active(idle, NOW, 1800)


@pytest.mark.postgres
def test_session_read_does_not_touch_but_private_command_does(identity: Harness) -> None:
    identity.user(email="touch@example.com", password="Session touch password 2026")
    identity.login("touch@example.com", "Session touch password 2026")
    with identity.factory() as session:
        model = session.scalar(select(SessionModel))
        assert model is not None
        original = model.last_seen_at
    identity.clock.current = NOW + timedelta(seconds=identity.settings.SESSION_TOUCH_SECONDS + 1)
    assert identity.client.get("/api/v1/auth/session").status_code == 200
    with identity.factory() as session:
        model = session.scalar(select(SessionModel))
        assert model is not None and model.last_seen_at == original
    assert identity.client.get("/api/v1/business-profile").status_code == 200
    with identity.factory() as session:
        model = session.scalar(select(SessionModel))
        assert model is not None and model.last_seen_at == identity.clock.current


@pytest.mark.postgres
def test_legacy_session_overflow_revokes_all_but_four_before_login(identity: Harness) -> None:
    user = identity.user(email="legacy@example.com", password="Legacy sessions password")
    with identity.factory() as session:
        for index in range(7):
            session.add(
                SessionModel(
                    id=uuid4(),
                    user_id=user.id,
                    bearer_hash=index.to_bytes(32),
                    created_at=NOW - timedelta(microseconds=7 - index),
                    last_seen_at=NOW,
                    absolute_expires_at=NOW + timedelta(hours=12),
                    revoked_at=None,
                    revocation_reason=None,
                )
            )
        session.commit()
    with identity.factory() as session:
        authenticate(
            session,
            email=user.email_normalized,
            password="Legacy sessions password",
            now=NOW + timedelta(seconds=1),
            settings=identity.settings,
        )
    with identity.factory() as session:
        models = list(session.scalars(select(SessionModel).where(SessionModel.user_id == user.id)))
        assert sum(is_active(model, NOW + timedelta(seconds=1), 1800) for model in models) == 5
        revoked = [model for model in models if model.revocation_reason == "SESSION_LIMIT"]
        assert len(revoked) == 3


@pytest.mark.postgres
def test_five_active_plus_expired_revokes_oldest_active_only(identity: Harness) -> None:
    user = identity.user(email="five@example.com", password="Five sessions password 2026")
    active_ids: list[UUID] = []
    expired_id = uuid4()
    with identity.factory() as session:
        for index in range(5):
            session_id = uuid4()
            active_ids.append(session_id)
            session.add(
                SessionModel(
                    id=session_id,
                    user_id=user.id,
                    bearer_hash=index.to_bytes(32),
                    created_at=NOW - timedelta(minutes=5 - index),
                    last_seen_at=NOW,
                    absolute_expires_at=NOW + timedelta(hours=12),
                    revoked_at=None,
                    revocation_reason=None,
                )
            )
        session.add(
            SessionModel(
                id=expired_id,
                user_id=user.id,
                bearer_hash=b"e" * 32,
                created_at=NOW - timedelta(hours=13),
                last_seen_at=NOW - timedelta(hours=13),
                absolute_expires_at=NOW,
                revoked_at=None,
                revocation_reason=None,
            )
        )
        session.commit()
    with identity.factory() as session:
        authenticate(
            session,
            email=user.email_normalized,
            password="Five sessions password 2026",
            now=NOW,
            settings=identity.settings,
        )
    with identity.factory() as session:
        oldest = session.get(SessionModel, active_ids[0])
        expired = session.get(SessionModel, expired_id)
        models = list(session.scalars(select(SessionModel).where(SessionModel.user_id == user.id)))
        assert oldest is not None and oldest.revocation_reason == "SESSION_LIMIT"
        assert expired is not None and expired.revoked_at is None
        assert sum(is_active(item, NOW, 1800) for item in models) == 5


@pytest.mark.postgres
def test_business_profile_partial_complete_and_timezone_contract(identity: Harness) -> None:
    identity.user(email="admin@example.com", password="Business profile password")
    identity.login("admin@example.com", "Business profile password")
    initial = identity.client.get("/api/v1/business-profile")
    assert initial.status_code == 200
    assert initial.json()["data"]["missing_fields"] == [
        "trade_name",
        "phone",
        "email",
        "address",
        "timezone",
    ]
    assert initial.json()["data"]["business_today"] is None
    missing_version = identity.client.patch(
        "/api/v1/business-profile",
        json={"trade_name": "No version"},
        headers=identity.mutation_headers(),
    )
    assert missing_version.status_code == 428
    stale_version = identity.client.patch(
        "/api/v1/business-profile",
        json={"trade_name": "Stale version"},
        headers=identity.mutation_headers('"v999"'),
    )
    assert stale_version.status_code == 412
    partial = identity.client.patch(
        "/api/v1/business-profile",
        json={"timezone": "America/Bahia"},
        headers=identity.mutation_headers(initial.headers["etag"]),
    )
    assert partial.status_code == 200, partial.text
    body = partial.json()["data"]
    assert not body["is_complete"]
    assert body["business_timezone"] == "America/Bahia"
    assert body["business_today"] == "2026-06-01"
    remove_timezone = identity.client.patch(
        "/api/v1/business-profile",
        json={"timezone": None},
        headers=identity.mutation_headers(partial.headers["etag"]),
    )
    assert remove_timezone.status_code == 422
    complete = identity.client.patch(
        "/api/v1/business-profile",
        json={
            "trade_name": "ClientOps Test",
            "phone": "+55 71 3000-0000",
            "email": "contact@example.com",
            "address": "Salvador, BA",
        },
        headers=identity.mutation_headers(partial.headers["etag"]),
    )
    assert complete.status_code == 200 and complete.json()["data"]["is_complete"]
    regression = identity.client.patch(
        "/api/v1/business-profile",
        json={"address": None},
        headers=identity.mutation_headers(complete.headers["etag"]),
    )
    assert regression.status_code == 422
    no_ack = identity.client.patch(
        "/api/v1/business-profile",
        json={"timezone": "UTC"},
        headers=identity.mutation_headers(complete.headers["etag"]),
    )
    assert no_ack.status_code == 422
    changed = identity.client.patch(
        "/api/v1/business-profile",
        json={"timezone": "UTC", "acknowledge_timezone_change": True},
        headers=identity.mutation_headers(complete.headers["etag"]),
    )
    assert changed.status_code == 200


@pytest.mark.postgres
def test_user_management_secrets_revocation_and_last_admin(identity: Harness) -> None:
    admin = identity.user(email="admin@example.com", password="User management password")
    session_data = identity.login("admin@example.com", "User management password")
    created = identity.client.post(
        "/api/v1/users",
        json={"name": "Technician", "email": "Tech+one@example.com"},
        headers=identity.mutation_headers(),
    )
    assert created.status_code == 201, created.text
    temporary = created.json()["temporary_password"]
    technician_id = UUID(created.json()["data"]["id"])
    assert len(temporary) == 32 and created.headers["cache-control"] == "no-store"
    detail = identity.client.get(f"/api/v1/users/{technician_id}")
    disabled = identity.client.post(
        f"/api/v1/users/{technician_id}/disable",
        json={},
        headers=identity.mutation_headers(detail.headers["etag"]),
    )
    assert disabled.status_code == 200
    enabled = identity.client.post(
        f"/api/v1/users/{technician_id}/enable",
        json={},
        headers=identity.mutation_headers(disabled.headers["etag"]),
    )
    assert enabled.status_code == 200
    reset = identity.client.post(
        f"/api/v1/users/{technician_id}/reset-password",
        json={},
        headers=identity.mutation_headers(enabled.headers["etag"]),
    )
    assert reset.status_code == 200
    assert reset.json()["temporary_password"] != temporary
    own = identity.client.get(f"/api/v1/users/{admin.id}")
    self_disable = identity.client.post(
        f"/api/v1/users/{admin.id}/disable",
        json={},
        headers=identity.mutation_headers(own.headers["etag"]),
    )
    assert self_disable.status_code == 409
    with identity.factory() as session:
        tech = session.get(User, technician_id)
        assert tech is not None and tech.status == "ACTIVE" and tech.must_change_password
        assert not verify_password(tech.password_hash, temporary)
        assert session.scalar(select(func.count()).select_from(TimelineEvent)) == 4
    logout = identity.client.post(
        "/api/v1/auth/logout",
        json={},
        headers={"Origin": ORIGIN, "X-CSRF-Token": str(session_data["csrf_token"])},
    )
    assert logout.status_code == 204


@pytest.mark.postgres
def test_reset_revokes_sessions_and_does_not_enable_disabled_user(identity: Harness) -> None:
    admin = identity.user(email="admin@example.com", password="Admin reset password")
    technician = identity.user(
        email="disabled@example.com",
        password="Old disabled password",
        role="TECHNICIAN",
        status="DISABLED",
    )
    with identity.factory() as session:
        session.add(
            SessionModel(
                id=uuid4(),
                user_id=technician.id,
                bearer_hash=b"r" * 32,
                created_at=NOW,
                last_seen_at=NOW,
                absolute_expires_at=NOW + timedelta(hours=12),
                revoked_at=None,
                revocation_reason=None,
            )
        )
        session.commit()
    with identity.factory() as session:
        actor = session.get(User, admin.id)
        assert actor is not None
        saved, temporary = mutate_user(
            session,
            target_id=technician.id,
            actor=actor,
            now=NOW,
            if_match='"v1"',
            action="reset",
        )
        assert saved.status == "DISABLED"
        assert temporary is not None and len(temporary) == 32
    with identity.factory() as session:
        stored_session = session.scalar(
            select(SessionModel).where(SessionModel.user_id == technician.id)
        )
        assert stored_session is not None
        assert stored_session.revocation_reason == "PASSWORD_RESET"


@pytest.mark.postgres
def test_two_admin_disables_preserve_one_active_admin(identity: Harness) -> None:
    first = identity.user(email="one@example.com", password="First admin password")
    second = identity.user(email="two@example.com", password="Second admin password")
    barrier = Barrier(3)

    def disable(target: UUID, actor_id: UUID) -> str:
        barrier.wait(timeout=10)
        with identity.factory() as session:
            actor = session.get(User, actor_id)
            assert actor is not None
            try:
                mutate_user(
                    session,
                    target_id=target,
                    actor=actor,
                    now=NOW,
                    if_match='"v1"',
                    action="disable",
                )
            except FoundationError as error:
                return error.code
            return "OK"

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(disable, second.id, first.id)
        two = pool.submit(disable, first.id, second.id)
        barrier.wait(timeout=10)
        results = {one.result(timeout=20), two.result(timeout=20)}
    assert results == {"OK", "LAST_ADMIN_REQUIRED"}
    with identity.factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(User)
                .where(User.role == "ADMIN", User.status == "ACTIVE")
            )
            == 1
        )


@pytest.mark.postgres
def test_rate_limit_uses_independent_hmac_buckets_per_ip(identity: Harness) -> None:
    identity.user(email="wrong@example.com", password="Rate limit password")
    for index in range(10):
        response = identity.client.post(
            "/api/v1/auth/login",
            json={"email": "missing@example.com", "password": "incorrect password"},
            headers={
                **LOGIN_HEADERS,
                "X-Forwarded-For": "203.0.113.77" if index % 2 else "2001:db8::77",
            },
        )
        assert response.status_code == 401
    limited = identity.client.post(
        "/api/v1/auth/login",
        json={"email": "missing@example.com", "password": "incorrect password"},
        headers=LOGIN_HEADERS,
    )
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0
    with identity.factory() as session:
        consume(session, identity.settings, LOGIN_IP, "2001:db8::2", NOW)
    with identity.factory() as session:
        buckets = list(session.execute(text("SELECT rule, key_hash FROM rate_limit_buckets")))
        assert buckets
        assert all(len(row.key_hash) == 32 for row in buckets)
        assert all(b"missing@example.com" not in row.key_hash for row in buckets)
        assert (
            session.scalar(text("SELECT count FROM rate_limit_buckets WHERE rule='login_email'"))
            == 11
        )
        assert (
            session.scalar(
                text("SELECT count FROM rate_limit_buckets WHERE rule='login_installation'")
            )
            == 11
        )
        assert (
            session.scalar(
                text(
                    "SELECT count(DISTINCT key_hash) FROM rate_limit_buckets WHERE rule='login_ip'"
                )
            )
            == 2
        )
        assert sorted(
            session.scalars(text("SELECT count FROM rate_limit_buckets WHERE rule='login_ip'"))
        ) == [1, 11]


@pytest.mark.postgres
def test_private_rate_limiter_database_failure_returns_503(
    identity: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity.user(email="admin@example.com", password="Rate failure password 2026")
    identity.login("admin@example.com", "Rate failure password 2026")

    def fail_consume(*_args: object, **_kwargs: object) -> None:
        raise SQLAlchemyError("simulated limiter failure")

    monkeypatch.setattr("app.modules.identity.dependencies.consume", fail_consume)
    response = identity.client.get("/api/v1/business-profile")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "TEMPORARILY_UNAVAILABLE"


@pytest.mark.postgres
def test_rate_limit_denial_counts_and_new_window_starts_clean(identity: Harness) -> None:
    rule = RateRule("boundary_test", 2, 60)
    for _ in range(2):
        with identity.factory() as session:
            consume(session, identity.settings, rule, "same-client", NOW)
    with identity.factory() as session, pytest.raises(FoundationError) as captured:
        consume(session, identity.settings, rule, "same-client", NOW)
    assert captured.value.status_code == 429
    assert captured.value.headers is not None
    assert int(captured.value.headers["Retry-After"]) > 0
    with identity.factory() as session:
        assert session.scalar(text("SELECT count FROM rate_limit_buckets")) == 3
    next_window = NOW + timedelta(seconds=60)
    with identity.factory() as session:
        consume(session, identity.settings, rule, "same-client", next_window)
    with identity.factory() as session:
        counts = list(
            session.scalars(text("SELECT count FROM rate_limit_buckets ORDER BY window_start"))
        )
    assert counts == [3, 1]


@pytest.mark.postgres
def test_reset_admin_bucket_counts_denied_requests(identity: Harness) -> None:
    identity.user(email="admin@example.com", password="Admin limiter password 2026")
    technician = identity.user(
        email="tech@example.com",
        password="Technician limiter password 2026",
        role="TECHNICIAN",
    )
    identity.login("admin@example.com", "Admin limiter password 2026")
    detail = identity.client.get(f"/api/v1/users/{technician.id}")
    assert detail.status_code == 200
    headers = identity.mutation_headers(detail.headers["etag"])
    for index in range(10):
        response = identity.client.post(
            f"/api/v1/users/{technician.id}/reset-password", json={}, headers=headers
        )
        assert response.status_code == (200 if index == 0 else 412)
    limited = identity.client.post(
        f"/api/v1/users/{technician.id}/reset-password", json={}, headers=headers
    )
    assert limited.status_code == 429 and int(limited.headers["retry-after"]) > 0
    with identity.factory() as session:
        assert (
            session.scalar(text("SELECT count FROM rate_limit_buckets WHERE rule='reset_admin'"))
            == 11
        )


@pytest.mark.postgres
def test_private_user_bucket_counts_denied_requests(
    identity: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity.user(email="admin@example.com", password="Private limiter password 2026")
    identity.login("admin@example.com", "Private limiter password 2026")
    monkeypatch.setattr(
        "app.modules.identity.dependencies.PRIVATE_USER", RateRule("private_user", 2, 300)
    )
    for _ in range(2):
        assert identity.client.get("/api/v1/business-profile").status_code == 200
    private_limited = identity.client.get("/api/v1/business-profile")
    assert private_limited.status_code == 429
    with identity.factory() as session:
        assert (
            session.scalar(text("SELECT count FROM rate_limit_buckets WHERE rule='private_user'"))
            == 3
        )


@pytest.mark.postgres
def test_login_racing_disable_finishes_with_no_active_session(identity: Harness) -> None:
    admin = identity.user(email="admin@example.com", password="Admin race password")
    technician = identity.user(
        email="race@example.com", password="Technician race password", role="TECHNICIAN"
    )
    barrier = Barrier(3)

    def login() -> str:
        barrier.wait(timeout=10)
        with identity.factory() as session:
            try:
                authenticate(
                    session,
                    email=technician.email_normalized,
                    password="Technician race password",
                    now=NOW,
                    settings=identity.settings,
                )
            except FoundationError as error:
                return error.code
            return "OK"

    def disable() -> str:
        barrier.wait(timeout=10)
        with identity.factory() as session:
            actor = session.get(User, admin.id)
            assert actor is not None
            mutate_user(
                session,
                target_id=technician.id,
                actor=actor,
                now=NOW,
                if_match='"v1"',
                action="disable",
            )
        return "OK"

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        login_result = pool.submit(login)
        disable_result = pool.submit(disable)
        barrier.wait(timeout=10)
        assert disable_result.result(timeout=30) == "OK"
        assert login_result.result(timeout=30) in {"OK", "INVALID_CREDENTIALS"}
    with identity.factory() as session:
        saved = session.get(User, technician.id)
        models = list(
            session.scalars(select(SessionModel).where(SessionModel.user_id == technician.id))
        )
        assert saved is not None and saved.status == "DISABLED"
        assert not any(is_active(model, NOW, 1800) for model in models)


@pytest.mark.postgres
def test_concurrent_profile_patch_and_rate_bucket_updates_are_serialized(
    identity: Harness,
) -> None:
    actor = identity.user(email="admin@example.com", password="Profile race password")
    profile_barrier = Barrier(3)

    def patch_profile(name: str) -> str:
        profile_barrier.wait(timeout=10)
        with identity.factory() as session:
            try:
                update_profile(
                    session,
                    patch=BusinessProfilePatch(trade_name=name),
                    if_match='"v1"',
                    actor_user_id=actor.id,
                    now=NOW,
                )
            except FoundationError as error:
                return error.code
            return "OK"

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(patch_profile, "First")
        second = pool.submit(patch_profile, "Second")
        profile_barrier.wait(timeout=10)
        assert {first.result(timeout=20), second.result(timeout=20)} == {
            "OK",
            "VERSION_CONFLICT",
        }

    rule = RateRule("concurrency_test", 100, 60)
    workers = 12
    rate_barrier = Barrier(workers + 1)

    def increment(index: int) -> None:
        rate_barrier.wait(timeout=10)
        with identity.factory() as session:
            consume(session, identity.settings, rule, "same-key", NOW)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(increment, index) for index in range(workers)]
        rate_barrier.wait(timeout=10)
        for future in futures:
            future.result(timeout=20)
    with identity.factory() as session:
        assert (
            session.scalar(
                text("SELECT count FROM rate_limit_buckets WHERE rule='concurrency_test'")
            )
            == workers
        )


@pytest.mark.postgres
def test_touch_racing_revoke_never_revives_the_session(identity: Harness) -> None:
    admin = identity.user(email="admin@example.com", password="Touch race password")
    technician = identity.user(
        email="touch@example.com", password="Technician touch password", role="TECHNICIAN"
    )
    with identity.factory() as session:
        _, issued = authenticate(
            session,
            email=technician.email_normalized,
            password="Technician touch password",
            now=NOW,
            settings=identity.settings,
        )
        session_id = issued.model.id
    barrier = Barrier(3)
    later = NOW + timedelta(seconds=61)

    def touch() -> None:
        barrier.wait(timeout=10)
        with identity.factory() as session:
            session.execute(
                update(SessionModel)
                .where(
                    SessionModel.id == session_id,
                    SessionModel.revoked_at.is_(None),
                    SessionModel.last_seen_at > later - timedelta(seconds=1800),
                    SessionModel.last_seen_at <= later - timedelta(seconds=60),
                )
                .values(last_seen_at=later)
            )
            session.commit()

    def revoke() -> None:
        barrier.wait(timeout=10)
        with identity.factory() as session:
            actor = session.get(User, admin.id)
            target = session.get(User, technician.id)
            assert actor is not None and target is not None
            mutate_user(
                session,
                target_id=target.id,
                actor=actor,
                now=later,
                if_match='"v1"',
                action="disable",
            )

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        touched = pool.submit(touch)
        revoked = pool.submit(revoke)
        barrier.wait(timeout=10)
        touched.result(timeout=20)
        revoked.result(timeout=20)
    with identity.factory() as session:
        saved = session.get(SessionModel, session_id)
        assert saved is not None and saved.revoked_at == later
        assert not is_active(saved, later, 1800)


@pytest.mark.postgres
def test_two_resets_and_two_disables_use_resource_versions(identity: Harness) -> None:
    admin = identity.user(email="admin@example.com", password="Mutation race password")
    technician = identity.user(
        email="mutate@example.com", password="Technician mutation password", role="TECHNICIAN"
    )

    def race(action: str, version: int) -> list[tuple[str, str | None]]:
        barrier = Barrier(3)

        def mutate() -> tuple[str, str | None]:
            barrier.wait(timeout=10)
            with identity.factory() as session:
                actor = session.get(User, admin.id)
                assert actor is not None
                try:
                    _, secret = mutate_user(
                        session,
                        target_id=technician.id,
                        actor=actor,
                        now=NOW,
                        if_match=f'"v{version}"',
                        action=action,
                    )
                except FoundationError as error:
                    return error.code, None
                return "OK", secret

        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(mutate)
            second = pool.submit(mutate)
            barrier.wait(timeout=10)
            return [first.result(timeout=30), second.result(timeout=30)]

    resets = race("reset", 1)
    assert sorted(code for code, _ in resets) == ["OK", "VERSION_CONFLICT"]
    issued = next(secret for code, secret in resets if code == "OK")
    assert issued is not None
    with identity.factory() as session:
        saved = session.get(User, technician.id)
        assert saved is not None and verify_password(saved.password_hash, issued)
        current_version = saved.version
    disables = race("disable", current_version)
    assert sorted(code for code, _ in disables) == ["OK", "VERSION_CONFLICT"]
    with identity.factory() as session:
        saved = session.get(User, technician.id)
        assert saved is not None and saved.status == "DISABLED"


@pytest.mark.postgres
def test_login_racing_reset_leaves_old_password_and_session_invalid(identity: Harness) -> None:
    admin = identity.user(email="admin@example.com", password="Admin login reset password")
    technician = identity.user(
        email="login-reset@example.com",
        password="Old login reset password",
        role="TECHNICIAN",
    )
    barrier = Barrier(3)

    def login() -> str:
        barrier.wait(timeout=10)
        with identity.factory() as session:
            try:
                authenticate(
                    session,
                    email=technician.email_normalized,
                    password="Old login reset password",
                    now=NOW,
                    settings=identity.settings,
                )
            except FoundationError as error:
                return error.code
            return "OK"

    def reset() -> str:
        barrier.wait(timeout=10)
        with identity.factory() as session:
            actor = session.get(User, admin.id)
            assert actor is not None
            mutate_user(
                session,
                target_id=technician.id,
                actor=actor,
                now=NOW,
                if_match='"v1"',
                action="reset",
            )
        return "OK"

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        login_result = pool.submit(login)
        reset_result = pool.submit(reset)
        barrier.wait(timeout=10)
        assert reset_result.result(timeout=30) == "OK"
        assert login_result.result(timeout=30) in {"OK", "INVALID_CREDENTIALS"}
    with identity.factory() as session:
        saved = session.get(User, technician.id)
        models = list(
            session.scalars(select(SessionModel).where(SessionModel.user_id == technician.id))
        )
        assert saved is not None
        assert not verify_password(saved.password_hash, "Old login reset password")
        assert not any(is_active(model, NOW, 1800) for model in models)


@pytest.mark.postgres
def test_password_change_serializes_with_private_profile_command(identity: Harness) -> None:
    user = identity.user(email="admin@example.com", password="Old private command password")
    identity.login("admin@example.com", "Old private command password")
    profile = identity.client.get("/api/v1/business-profile")
    assert profile.status_code == 200
    private_started = Event()
    engine = identity.engine

    def before_execute(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        if "FOR UPDATE" in statement and "FROM users" in statement:
            private_started.set()

    def private_patch() -> int:
        response = identity.client.patch(
            "/api/v1/business-profile",
            json={"trade_name": "Must not commit"},
            headers=identity.mutation_headers(profile.headers["etag"]),
        )
        return int(response.status_code)

    from concurrent.futures import ThreadPoolExecutor

    with (
        identity.factory() as locked,
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="private-command") as pool,
    ):
        locked.execute(select(User).where(User.id == user.id).with_for_update())
        event.listen(engine, "before_cursor_execute", before_execute)
        try:
            future = pool.submit(private_patch)
            assert private_started.wait(timeout=10)
        finally:
            event.remove(engine, "before_cursor_execute", before_execute)
        try:
            changed, _issued = change_password(
                locked,
                user_id=user.id,
                current_password="Old private command password",
                new_password="A new private command password 2026!",
                now=NOW,
                settings=identity.settings,
            )
            assert changed.version == 2
            assert future.result(timeout=10) == 401
        finally:
            if not future.done():
                future.cancel()
    with identity.factory() as session:
        saved = session.get(BusinessProfile, 1)
        assert saved is not None and saved.trade_name is None
        assert (
            session.scalar(
                select(func.count())
                .select_from(SessionModel)
                .where(SessionModel.user_id == user.id, SessionModel.revoked_at.is_(None))
            )
            == 1
        )


@pytest.mark.postgres
def test_admin_cli_tty_bootstrap_additional_and_reset(identity: Harness) -> None:
    first_password = "First operator password 2026!"
    first_args = ["--name", "First Admin", "--email", "first.admin@example.com"]
    non_tty = subprocess.run(
        ["python", "-m", "app.cli.create_admin", *first_args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert non_tty.returncode != 0 and "interactive TTY" in non_tty.stderr
    status, output = _tty_cli("app.cli.create_admin", first_args, first_password)
    assert status == 0 and b"Admin created" in output
    second_args = ["--name", "Second Admin", "--email", "second.admin@example.com"]
    status, output = _tty_cli("app.cli.create_admin", second_args, "Second operator password 2026!")
    assert status != 0 and b"--additional" in output
    status, output = _tty_cli(
        "app.cli.create_admin",
        [*second_args, "--additional"],
        "Second operator password 2026!",
    )
    assert status == 0 and b"Admin created" in output
    with identity.factory() as session:
        first = session.scalar(
            select(User).where(User.email_normalized == "first.admin@example.com")
        )
        second = session.scalar(
            select(User).where(User.email_normalized == "second.admin@example.com")
        )
        assert first is not None and second is not None
        assert verify_password(first.password_hash, first_password)
        first_id, second_id = first.id, second.id
    identity.login("first.admin@example.com", first_password)
    reset_password = "Reset operator password 2026!"
    status, output = _tty_cli(
        "app.cli.reset_password", ["--email", "first.admin@example.com"], reset_password
    )
    assert status == 0 and b"sessions revoked" in output
    with identity.factory() as session:
        first = session.get(User, first_id)
        issued = session.scalar(select(SessionModel).where(SessionModel.user_id == first_id))
        second = session.get(User, second_id)
        assert first is not None and second is not None and issued is not None
        assert verify_password(first.password_hash, reset_password)
        assert issued.revocation_reason == "OPERATOR_PASSWORD_RESET"
        mutate_user(
            session,
            target_id=first_id,
            actor=second,
            now=NOW,
            if_match=f'"v{first.version}"',
            action="disable",
        )
    status, _output = _tty_cli(
        "app.cli.reset_password",
        ["--email", "first.admin@example.com"],
        "Disabled account reset password 2026!",
    )
    assert status == 0
    with identity.factory() as session:
        first = session.get(User, first_id)
        assert first is not None and first.status == "DISABLED"
        assert verify_password(first.password_hash, "Disabled account reset password 2026!")
