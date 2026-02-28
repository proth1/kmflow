"""Alembic environment configuration for async SQLAlchemy.

Supports both offline (SQL generation) and online (direct DB) migration modes.
Uses the async engine from the application configuration.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
import sqlalchemy as sa
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from sqlalchemy.dialects.postgresql import named_types as _pg_named_types

from src.core.database import Base
import src.core.models  # noqa: F401 — import the package to auto-register all models with Base.metadata

# Alembic Config object
config = context.config

# ---------------------------------------------------------------------------
# Patch: force checkfirst=True for PostgreSQL enum type creation.
#
# When ORM models are imported (above), their sa.Enum columns register
# _on_table_create event listeners on the metadata tables.  During Alembic
# migrations the same table names appear in op.create_table(), which triggers
# these listeners and causes "type already exists" errors.
#
# By overriding _on_table_create to always set checkfirst=True, we let PG
# gracefully skip creation if the type was already emitted by an earlier
# explicit CREATE TYPE or by a previous table in the same migration.
# ---------------------------------------------------------------------------
_orig_on_table_create = _pg_named_types.NamedType._on_table_create


def _patched_on_table_create(self, target, bind, **kw):  # type: ignore[no-untyped-def]
    kw["checkfirst"] = True
    return _orig_on_table_create(self, target, bind, **kw)


_pg_named_types.NamedType._on_table_create = _patched_on_table_create  # type: ignore[assignment]

# Override sqlalchemy.url from DATABASE_URL env var if set, so alembic.ini
# does not need to contain real credentials.
database_url = os.environ.get("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

# Set up logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# MetaData for autogenerate support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Generates SQL scripts without connecting to the database.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):  # type: ignore[no-untyped-def]
    """Execute migrations with the given connection."""
    # Set RLS bypass parameter so FK and policy operations don't fail
    # when Row-Level Security is enabled on engagement-scoped tables.
    connection.execute(sa.text("SET app.current_engagement_id = '00000000-0000-0000-0000-000000000000'"))
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode using async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
