from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import files
from threading import BoundedSemaphore

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.errors import FoundationError

PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)
DUMMY_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$LfqSys+HMnINWvJ7yGNMdA$"
    "47IgSZNN6GNIDX2773eZtRsO/IOkdmd9NvdseT23Xug"
)
_ARGON_SLOTS = BoundedSemaphore(2)


@contextmanager
def argon_slot() -> Iterator[None]:
    if not _ARGON_SLOTS.acquire(blocking=False):
        raise FoundationError(
            status_code=429,
            code="RATE_LIMITED",
            message="Capacidade de autenticação temporariamente atingida.",
            headers={"Retry-After": "1"},
        )
    try:
        yield
    finally:
        _ARGON_SLOTS.release()


def validate_permanent_password(password: str, *, current: str | None = None) -> None:
    if not 15 <= len(password) <= 128 or len(password.encode("utf-8")) > 512:
        raise ValueError("A senha deve ter entre 15 e 128 caracteres e até 512 bytes.")
    if current is not None and password == current:
        raise ValueError("A nova senha deve ser diferente da senha atual.")
    blocklist = {
        line
        for line in files("app.modules.identity.data")
        .joinpath("common-passwords-v1.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line and not line.startswith("#")
    }
    if password in blocklist:
        raise ValueError("Escolha uma senha menos comum.")


def hash_password(password: str) -> str:
    with argon_slot():
        return PASSWORD_HASHER.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    with argon_slot():
        try:
            return PASSWORD_HASHER.verify(stored_hash, password)
        except (VerifyMismatchError, InvalidHashError):
            return False


def needs_rehash(stored_hash: str) -> bool:
    try:
        return PASSWORD_HASHER.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return False
