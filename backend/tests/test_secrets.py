from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]


def _local_secrets() -> list[str]:
    env_file = ROOT / ".local" / "compose.env"
    if not env_file.exists():
        pytest.skip("local Compose environment is absent")
    values = []
    for line in env_file.read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.endswith("PASSWORD") or name.endswith("KEY"):
            values.append(value)
    return values


@pytest.mark.artifacts
def test_secrets_are_absent_from_frontend_and_image_history() -> None:
    frontend = b"".join(
        path.read_bytes() for path in (ROOT / "frontend" / "dist").rglob("*") if path.is_file()
    ).decode("utf-8", errors="ignore")
    histories = "\n".join(
        subprocess.run(
            ["docker", "history", "--no-trunc", image],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        for image in ("clientops-api", "clientops-web")
    )
    logs = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            "infra/images.env",
            "--env-file",
            ".local/compose.env",
            "logs",
            "--no-color",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    for secret in _local_secrets():
        assert secret not in frontend
        assert secret not in histories
        assert secret not in logs
