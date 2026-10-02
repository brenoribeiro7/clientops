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
CL02_JOBS = REQUIRED_JOBS | {
    "cl01-gate",
    "identity-integration",
    "identity-security",
    "identity-e2e",
}
CL03_JOBS = CL02_JOBS | {"cl02-gate", "clients-integration", "clients-e2e"}


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


@pytest.mark.artifacts
def test_security_foundation_resets_identity_before_https_browser_checks() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")
    job = content.split("  security-foundation:\n", maxsplit=1)[1].split(
        "  cl01-gate:\n", maxsplit=1
    )[0]
    tls_start = job.index("-f compose.tls.yaml up -d")
    reset = job.index("seed_test_identity --reset", tls_start)
    https_check = job.index("CLIENTOPS_E2E_BASE_URL=https://web:8443", reset)
    assert tls_start < reset < https_check


@pytest.mark.artifacts
def test_cl02_gate_inspects_every_required_result_and_rejects_non_success() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")
    gate = content.split("  cl02-gate:\n", maxsplit=1)[1]
    assert "if: ${{ always() }}" in gate
    for job in CL02_JOBS:
        assert f"- {job}" in gate
        assert f"${{{{ needs.{job}.result }}}}" in gate
    assert 'test "$result" = success' in gate


@pytest.mark.artifacts
def test_cl03_jobs_preserve_browser_matrix_and_gate_every_prior_result() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")
    assert len(re.findall(r"^  [a-z0-9-]+:\n", content, re.MULTILINE)) == 14
    security = content.split("  security-foundation:\n", maxsplit=1)[1].split(
        "  cl01-gate:\n", maxsplit=1
    )[0]
    assert "--grep-invert @cl03" in security
    clients_e2e = content.split("  clients-e2e:\n", maxsplit=1)[1].split(
        "  cl03-gate:\n", maxsplit=1
    )[0]
    assert "--grep @cl03" in clients_e2e
    gate = content.split("  cl03-gate:\n", maxsplit=1)[1]
    assert "if: ${{ always() }}" in gate
    for job in CL03_JOBS:
        assert f"- {job}" in gate
        assert f"${{{{ needs.{job}.result }}}}" in gate
    assert 'test "$result" = success' in gate
