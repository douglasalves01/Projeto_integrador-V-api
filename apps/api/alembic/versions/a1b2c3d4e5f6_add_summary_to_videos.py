"""add_summary_to_videos

Adiciona coluna `summary` (texto) em videos. Preenchida offline pelo serviço de
IA (VodChat) via `apps/ai/scripts/generate_summaries.py`.

Revision ID: a1b2c3d4e5f6
Revises: e3f7a1b2c4d5
Create Date: 2026-05-31 21:30:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "e3f7a1b2c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE videos ADD COLUMN IF NOT EXISTS summary text")


def downgrade() -> None:
    op.execute("ALTER TABLE videos DROP COLUMN IF EXISTS summary")
