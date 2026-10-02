from __future__ import annotations

import json
import subprocess
import sys

import pytest

from app.cli._identity import tty_password


def test_tty_password_refuses_non_interactive_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    with pytest.raises(RuntimeError, match="interactive TTY"):
        tty_password()


def test_argon2_benchmark_reports_real_samples_without_password_material() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "app.cli.benchmark_argon2", "--samples", "1"],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["parameters"] == {
        "algorithm": "argon2id",
        "memory_cost_kib": 65536,
        "time_cost": 3,
        "parallelism": 4,
        "salt_len": 16,
        "hash_len": 32,
    }
    assert payload["measured_samples"] == 1
    assert payload["hash_milliseconds"]["median"] > 0
    assert payload["verify_milliseconds"]["median"] > 0
    assert "password" not in result.stdout.lower()
