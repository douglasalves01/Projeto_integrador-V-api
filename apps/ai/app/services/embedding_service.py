"""Servico de embeddings textuais para busca semantica.

Usa sentence-transformers com o modelo `paraphrase-multilingual-MiniLM-L12-v2`
(384 dims, suporta portugues). Carregamento lazy — so instancia na primeira chamada.
"""
from __future__ import annotations

import logging
from typing import Sequence

logger = logging.getLogger(__name__)

_encoder = None
_MODEL_ID = "paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384


def _get_encoder():
    global _encoder
    if _encoder is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Carregando SentenceTransformer (%s)", _MODEL_ID)
        _encoder = SentenceTransformer(_MODEL_ID)
    return _encoder


def encode(text: str) -> list[float]:
    """Retorna embedding 384-dim para o texto fornecido."""
    return _get_encoder().encode(text, normalize_embeddings=True).tolist()


def encode_batch(texts: Sequence[str]) -> list[list[float]]:
    """Encoda multiplos textos em batch (mais eficiente que chamadas individuais)."""
    return _get_encoder().encode(list(texts), normalize_embeddings=True, show_progress_bar=False).tolist()


def get_embedding_stats(db) -> dict[str, int]:
    """Contagens do catálogo para diagnostico de index-embeddings."""
    from sqlalchemy import text

    total_videos = db.execute(text("SELECT COUNT(*) FROM videos")).scalar() or 0
    total_with_embeddings = db.execute(
        text("SELECT COUNT(*) FROM videos WHERE description_embedding IS NOT NULL")
    ).scalar() or 0
    pending = max(0, int(total_videos) - int(total_with_embeddings))
    return {
        "total_videos": int(total_videos),
        "total_with_embeddings": int(total_with_embeddings),
        "pending": pending,
    }


def index_videos_in_db(db) -> int:
    """Gera embeddings para todos os videos sem embedding e salva no Postgres.

    Usa a sessao sincrona (psycopg) padrao do servico IA.
    Retorna o numero de videos indexados nesta execucao (0 = nada pendente).
    """
    from sqlalchemy import text

    rows = db.execute(
        text("""
            SELECT id, title, description
            FROM videos
            WHERE description_embedding IS NULL
            ORDER BY created_at
        """)
    ).fetchall()

    if not rows:
        return 0

    texts = [
        f"{row.title}. {row.description or ''}"
        for row in rows
    ]
    embeddings = encode_batch(texts)

    for row, emb in zip(rows, embeddings):
        vec_str = "[" + ",".join(str(v) for v in emb) + "]"
        db.execute(
            text("UPDATE videos SET description_embedding = CAST(:vec AS vector) WHERE id = :id"),
            {"vec": vec_str, "id": str(row.id)},
        )

    db.commit()
    logger.info("Indexados %d videos com embeddings", len(rows))
    return len(rows)
