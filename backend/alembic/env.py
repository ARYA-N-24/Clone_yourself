"""
Alembic environment configuration for async SQLAlchemy with asyncpg.

Reads DATABASE_URL from environment variables (via python-dotenv),
converts it to the async format, and runs migrations using AsyncEngine.
"""

import asyncio
import os
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Load environment variables from .env file (if present)
load_dotenv()

# This is the Alembic Config object, which provides access to the values
# within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import the SQLAlchemy Base and set target_metadata so Alembic can
# detect schema changes for autogenerate support.
from models.db_models import Base  # noqa: E402

target_metadata = Base.metadata


def get_database_url() -> str:
    """
    Read DATABASE_URL from environment and convert to async format.

    Replaces 'postgresql://' with 'postgresql+asyncpg://' so that
    SQLAlchemy uses the asyncpg driver.
    """
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Please set it before running Alembic migrations."
        )
    # Convert sync postgres URL to async asyncpg URL
    url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    # Also handle postgres:// shorthand (e.g. from Heroku/Render)
    url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine.
    Calls to context.execute() emit the given string to the script output.
    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Execute migrations within a synchronous connection context."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Run migrations in 'online' mode using an async engine.

    Creates an AsyncEngine from the configuration, connects, and runs
    migrations via run_sync() to bridge the async/sync boundary.
    """
    # Override the sqlalchemy.url in the alembic config with our async URL
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migration mode — runs the async coroutine."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
