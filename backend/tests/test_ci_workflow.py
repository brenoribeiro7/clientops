from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
REQUIRED_JOBS = {
    "backend-quality",
    "frontend-quality",
    "database-migration",
    "contract-drift",
    "compose-smoke",
    "security-foundation",
}


@pytest.mark.artifacts
def test_ci_workflow_has_pinned_actions_and_no_bypass_patterns() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")
    assert "permissions:\n  contents: read" in content
    assert "pull_request_target" not in content
    assert "continue-on-error" not in content
    assert "paths:" not in content
    action_references = re.findall(r"uses:\s+([^\s#]+)", content)
    assert action_references
    for reference in action_references:
        _, separator, revision = reference.rpartition("@")
        assert separator == "@"
        assert re.fullmatch(r"[0-9a-f]{40}", revision)


@pytest.mark.artifacts
def test_cl01_gate_inspects_every_required_result_and_rejects_non_success() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")
    gate = content.split("  cl01-gate:\n", maxsplit=1)[1]
    assert "if: ${{ !cancelled() }}" in gate
    for job in REQUIRED_JOBS:
        assert f"- {job}" in gate
        assert f"${{{{ needs.{job}.result }}}}" in gate
    assert 'test "$result" = success' in gate
