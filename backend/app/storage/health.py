from __future__ import annotations

import os
import secrets
import stat
from contextlib import suppress
from pathlib import Path


class StorageProbeError(RuntimeError):
    pass


def probe_private_storage(root_value: str) -> None:
    root = Path(root_value)
    if not root.is_absolute():
        raise StorageProbeError("invalid_storage_root")
    try:
        root_stat = root.lstat()
        if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
            raise StorageProbeError("invalid_storage_root")
        if root.resolve(strict=True) != root:
            raise StorageProbeError("storage_root_contains_symlink")
        if stat.S_IMODE(root_stat.st_mode) & 0o077:
            raise StorageProbeError("storage_permissions_too_broad")
    except OSError as error:
        raise StorageProbeError("storage_root_unavailable") from error

    directory_fd: int | None = None
    file_fd: int | None = None
    filename = f".clientops-ready-{secrets.token_hex(16)}"
    expected = secrets.token_bytes(32)
    created = False
    try:
        directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        file_fd = os.open(
            filename,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        created = True
        os.write(file_fd, expected)
        os.fsync(file_fd)
        os.close(file_fd)
        file_fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        actual = os.read(file_fd, len(expected) + 1)
        if actual != expected:
            raise StorageProbeError("storage_readback_failed")
    except OSError as error:
        raise StorageProbeError("storage_probe_failed") from error
    finally:
        if file_fd is not None:
            with suppress(OSError):
                os.close(file_fd)
        if directory_fd is not None:
            if created:
                try:
                    os.unlink(filename, dir_fd=directory_fd)
                except OSError as error:
                    raise StorageProbeError("storage_cleanup_failed") from error
            os.close(directory_fd)
