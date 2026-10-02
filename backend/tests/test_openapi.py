import json
import subprocess
import sys
from pathlib import Path

from app.cli.export_openapi import generated_schema


def test_openapi_generation_is_deterministic_and_cl02_scoped() -> None:
    first = generated_schema()
    second = generated_schema()
    assert first == second
    schema = json.loads(first)
    assert set(schema["paths"]) == {
        "/api/v1/auth/change-password",
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/session",
        "/api/v1/business-profile",
        "/api/v1/health/live",
        "/api/v1/health/ready",
        "/api/v1/users",
        "/api/v1/users/{user_id}",
        "/api/v1/users/{user_id}/disable",
        "/api/v1/users/{user_id}/enable",
        "/api/v1/users/{user_id}/reset-password",
    }
    assert schema["components"]["securitySchemes"]["cookieAuth"] == {
        "in": "cookie",
        "name": "__Host-clientops_session",
        "type": "apiKey",
    }
    assert b"Quote" not in first


def test_openapi_check_rejects_a_stale_copy(tmp_path: Path) -> None:
    stale = tmp_path / "openapi.json"
    stale.write_text("{}\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "app.cli.export_openapi", "--check", str(stale)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "desatualizada" in result.stderr
