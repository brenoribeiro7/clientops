from __future__ import annotations

from pathlib import Path

import pytest

from app.storage.health import StorageProbeError, probe_private_storage


def test_probe_round_trips_and_cleans_up(tmp_path: Path) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    probe_private_storage(str(root))
    assert list(root.iterdir()) == []


def test_probe_rejects_broad_permissions(tmp_path: Path) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o755)
    with pytest.raises(StorageProbeError, match="storage_permissions_too_broad"):
        probe_private_storage(str(root))


def test_probe_rejects_symlink_root(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(actual, target_is_directory=True)
    with pytest.raises(StorageProbeError, match="invalid_storage_root"):
        probe_private_storage(str(link))
