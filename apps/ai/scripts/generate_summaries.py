#!/usr/bin/env python3
"""Backfill OFFLINE de resumos de video usando o VodChat (TinyLlama + LoRA).

Le os videos do Postgres compartilhado, gera um resumo curto a partir da
descricao e grava na coluna `videos.summary`. Roda uma vez (ou apos novos
ingests). NAO deve rodar online por request — TinyLlama em CPU e lento.

Uso (dentro do container `ai`):
    docker compose -f infra/docker-compose.yml exec ai \
        python scripts/generate_summaries.py            # so os que faltam
    docker compose -f infra/docker-compose.yml exec ai \
        python scripts/generate_summaries.py --force    # regenera todos
    docker compose -f infra/docker-compose.yml exec ai \
        python scripts/generate_summaries.py --limit 5  # teste rapido
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.models.platform_adapter import VideoRO  # noqa: E402
from app.services.summarizer import extractive_summary  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gera resumos de video (offline)")
    parser.add_argument(
        "--engine",
        choices=["extractive", "vodchat"],
        default="extractive",
        help=(
            "Motor de resumo. 'extractive' (padrao): limpa a descricao e pega as "
            "frases-chave, instantaneo. 'vodchat': usa o TinyLlama-LoRA (lento em "
            "CPU e, neste fine-tune, baixa qualidade para resumo)."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenera o resumo mesmo para videos que ja tem um.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Processa no maximo N videos (util para teste).",
    )
    parser.add_argument(
        "--min-description-chars",
        type=int,
        default=40,
        help="Ignora videos com descricao menor que isso.",
    )
    return parser.parse_args()


def _load_vodchat():
    from app.models.vodchat import VodChat

    settings = get_settings()
    logger.info(
        "Carregando VodChat para sumarizacao",
        adapter=settings.VODCHAT_ADAPTER_PATH,
        base_model=settings.VODCHAT_BASE_MODEL,
        gguf=settings.VODCHAT_GGUF_PATH,
    )
    vodchat = VodChat(
        adapter_path=settings.VODCHAT_ADAPTER_PATH,
        base_model_id=settings.VODCHAT_BASE_MODEL,
        gguf_path=settings.VODCHAT_GGUF_PATH,
        max_new_tokens=settings.VODCHAT_MAX_NEW_TOKENS,
        max_time_seconds=settings.VODCHAT_MAX_TIME_SECONDS,
        use_title_constraints=False,  # resumo nao precisa do filtro anti-alucinacao de titulos
    )
    vodchat.load()
    logger.info("VodChat carregado", backend=vodchat.backend)
    return vodchat


def main() -> int:
    args = parse_args()
    setup_logging()

    vodchat = _load_vodchat() if args.engine == "vodchat" else None

    def summarize(title: str, description: str) -> str:
        if vodchat is not None:
            return vodchat.summarize(title, description).strip()
        return extractive_summary(title, description).strip()

    processed = 0
    skipped = 0
    failed = 0

    with SessionLocal() as db:
        query = db.query(VideoRO).order_by(VideoRO.created_at.asc())
        videos = query.all()
        logger.info("Videos no catalogo", total=len(videos))

        for video in videos:
            if args.limit is not None and processed >= args.limit:
                break

            if video.summary and not args.force:
                skipped += 1
                continue

            description = (video.description or "").strip()
            if len(description) < args.min_description_chars:
                logger.warning(
                    "Pulando: descricao curta demais",
                    video_id=str(video.id),
                    title=video.title,
                    chars=len(description),
                )
                skipped += 1
                continue

            try:
                summary = summarize(video.title, description)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Falha ao resumir", video_id=str(video.id), error=str(exc))
                failed += 1
                continue

            if not summary:
                logger.warning("Resumo vazio, ignorando", video_id=str(video.id))
                failed += 1
                continue

            db.execute(
                text(
                    "UPDATE videos SET summary = :summary, updated_at = now() "
                    "WHERE id = :video_id"
                ),
                {"summary": summary, "video_id": str(video.id)},
            )
            db.commit()
            processed += 1
            logger.info(
                "Resumo gerado",
                video_id=str(video.id),
                title=video.title[:60],
                summary_chars=len(summary),
            )

    logger.info(
        "Backfill concluido",
        engine=args.engine,
        processed=processed,
        skipped=skipped,
        failed=failed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
