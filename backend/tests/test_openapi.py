import json
import subprocess
import sys
from pathlib import Path

from app.cli.export_openapi import generated_schema


def test_openapi_generation_is_deterministic_and_foundation_only() -> None:
    first = generated_schema()
    second = generated_schema()
    assert first == second
    schema = json.loads(first)
    assert set(schema["paths"]) == {"/api/v1/health/live", "/api/v1/health/ready"}
    assert b"User" not in first
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
