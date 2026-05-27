"""add_pgvector_embedding_to_videos

Adiciona extensao pgvector e coluna description_embedding (384 dims) em videos.
Para preencher os embeddings: POST /api/v1/admin/index-embeddings no servico IA.

Revision ID: e3f7a1b2c4d5
Revises: dfe4beb5fd17
Create Date: 2026-05-27 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "e3f7a1b2c4d5"
down_revision: Union[str, None] = "dfe4beb5fd17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE videos ADD COLUMN IF NOT EXISTS description_embedding vector(384)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_videos_embedding "
        "ON videos USING ivfflat (description_embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_videos_embedding")
    op.execute("ALTER TABLE videos DROP COLUMN IF EXISTS description_embedding")
