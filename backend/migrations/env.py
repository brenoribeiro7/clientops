from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

import app.models  # noqa: F401
from app.core.config import MigrationSettings
from app.core.db import metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata
MIGRATION_LOCK_ID = 1431197001


def run_migrations_offline() -> None:
    raise RuntimeError("migrations offline são proibidas; use uma conexão PostgreSQL real")


def run_migrations_online() -> None:
    settings = MigrationSettings()  # type: ignore[call-arg]
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = settings.MIGRATION_DATABASE_URL.get_secret_value()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection, connection.begin():
        connection.execute(text("SET LOCAL lock_timeout = '10s'"))
        connection.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": MIGRATION_LOCK_ID},
        )
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            transactional_ddl=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
