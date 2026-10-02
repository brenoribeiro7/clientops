from __future__ import annotations

import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import cast

import pytest

ROOT = Path(__file__).parents[2]
COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    "infra/images.env",
    "--env-file",
    ".local/compose.env",
]


def _compose(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*COMPOSE, *arguments],
        cwd=ROOT,
        check=check,
        capture_output=True,
        text=True,
    )


def _url_status(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return cast(int, response.status)
    except urllib.error.HTTPError as error:
        return error.code


def _internal_ready_status() -> int:
    probe = (
        "import urllib.error,urllib.request; "
        "request=urllib.request.Request("
        "'http://127.0.0.1:8000/api/v1/health/ready',headers={'Host':'api'}); "
        "\ntry:\n urllib.request.urlopen(request,timeout=3); print(200)"
        "\nexcept urllib.error.HTTPError as error:\n print(error.code)"
    )
    result = _compose("exec", "-T", "api", "python", "-c", probe)
    return int(result.stdout.strip())


def _wait_for_internal_ready(expected: int, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    last_status: int | None = None
    while time.monotonic() < deadline:
        try:
            last_status = _internal_ready_status()
        except (subprocess.CalledProcessError, ValueError):
            last_status = None
        if last_status == expected:
            return
        time.sleep(0.5)
    raise AssertionError(f"readiness did not become {expected}; last status was {last_status}")


def _database_revision() -> str:
    result = _compose(
        "exec",
        "-T",
        "db",
        "psql",
        "-U",
        "clientops_bootstrap",
        "-d",
        "clientops",
        "-Atc",
        "SELECT version_num FROM alembic_version",
    )
    return result.stdout.strip()


@pytest.mark.compose
def test_database_outage_keeps_liveness_and_blocks_readiness() -> None:
    try:
        _compose("stop", "db")
        assert _url_status("http://127.0.0.1:8080/api/v1/health/live") == 200
        _wait_for_internal_ready(503)
    finally:
        _compose("up", "-d", "--wait", "--wait-timeout", "90", "db")
    _wait_for_internal_ready(200)


@pytest.mark.compose
def test_named_volumes_survive_container_recreation() -> None:
    marker = "/var/lib/clientops/private/.cl01-persistence-probe"
    expected_revision = _database_revision()
    _compose(
        "exec",
        "-T",
        "api",
        "sh",
        "-c",
        f"umask 077; printf foundation-persistence > {marker}",
    )
    try:
        _compose("down")
        _compose("up", "-d", "--wait", "--wait-timeout", "180")
        stored = _compose("exec", "-T", "api", "cat", marker).stdout
        mode = _compose("exec", "-T", "api", "stat", "-c", "%a", marker).stdout.strip()
        assert stored == "foundation-persistence"
        assert mode == "600"
        assert _database_revision() == expected_revision == "0002_identity_sessions_security"
    finally:
        _compose("exec", "-T", "api", "rm", "-f", marker, check=False)
