"""Alembic-miljö för TravAI.

Stödjer multipla scheman:
- public: rådata (tracks, races, starts, horses, persons, ...)
- features: materialiserade ML-features

include_schemas=True i context.configure() krävs för att autogenerate
ska upptäcka tabeller i features-schemat.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from travai.config import settings

# Importera alla modeller så de registreras på Base.metadata
from travai.db import models  # noqa: F401
from travai.db.base import Base
from travai.db.models import FEATURES_SCHEMA

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def include_object(
    object: object, name: str | None, type_: str, *args: object, **kwargs: object
) -> bool:
    """Filter som inkluderar både public och features tabeller."""
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Säkerställ att features-schemat finns innan migration kör
        from sqlalchemy import text

        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{FEATURES_SCHEMA}"'))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_schemas=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
