"""extend victory_margin to text and add countries

Revision ID: 853441074c95
Revises: 375e74056e1d
Create Date: 2026-05-19 20:12:52.199549

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "853441074c95"
down_revision: str | None = "375e74056e1d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "races",
        "victory_margin",
        existing_type=sa.VARCHAR(length=50),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "races",
        "victory_margin",
        existing_type=sa.Text(),
        type_=sa.VARCHAR(length=50),
        existing_nullable=True,
    )
