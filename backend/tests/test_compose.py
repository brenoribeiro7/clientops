from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).parents[2]


def _inspect(container: str) -> dict[str, Any]:
    result = subprocess.run(
        ["docker", "inspect", container],
        check=True,
        capture_output=True,
        text=True,
    )
    return cast(dict[str, Any], json.loads(result.stdout)[0])


@pytest.mark.compose
def test_only_web_is_published_and_mounts_are_separated() -> None:
    api = _inspect("clientops-api-1")
    db = _inspect("clientops-db-1")
    web = _inspect("clientops-web-1")
    assert api["Config"]["User"] == "10001:10001"
    assert web["Config"]["User"] == "101:101"
    assert api["HostConfig"]["PortBindings"] == {}
    assert db["HostConfig"]["PortBindings"] == {}
    assert "8080/tcp" in web["HostConfig"]["PortBindings"]
    web_mounts = {mount["Destination"] for mount in web["Mounts"]}
    api_mounts = {mount["Destination"] for mount in api["Mounts"]}
    assert "/var/lib/clientops/private" not in web_mounts
    assert "/var/lib/clientops/private" in api_mounts


@pytest.mark.compose
def test_proxy_routes_and_internal_readiness_boundary() -> None:
    with urllib.request.urlopen("http://127.0.0.1:8080/q/deep", timeout=5) as response:
        assert response.status == 200
        assert "script-src 'self'" in response.headers["Content-Security-Policy"]
    with pytest.raises(urllib.error.HTTPError) as captured:
        urllib.request.urlopen("http://127.0.0.1:8080/api/v1/health/ready", timeout=5)
    assert captured.value.code == 404


@pytest.mark.artifacts
def test_proxy_access_log_omits_query_string() -> None:
    config = (ROOT / "infra" / "nginx" / "nginx.conf").read_text(encoding="utf-8")
    log_format = config.split("log_format clientops", maxsplit=1)[1].split(";", maxsplit=1)[0]
    assert "$request_method $uri $server_protocol" in log_format
    assert '"$request "' not in log_format
    assert "$request_uri" not in log_format
    assert "$args" not in log_format
