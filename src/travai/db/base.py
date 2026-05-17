"""SQLAlchemy bas-klasser och gemensamma mixins."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Bas-klass för alla ORM-modeller."""


class UUIDPrimaryKey:
    """Mixin för UUID-primärnyckel som genereras klient-sida.

    Vi använder uuid4 (random) eftersom det räcker för våra volymer.
    Om vi senare behöver tids-sorterbara IDs (för bättre indexering)
    kan vi byta till uuid7 utan schemaändring.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """Lägger till created_at och updated_at automatiskt."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
