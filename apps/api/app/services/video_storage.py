"""Mapeia UUID de video → caminho do arquivo .mp4 no filesystem.

O mapping e construido na inicializacao lendo `contents.parquet` (gerado
pela IA). Cada `content_id` (int) -> `folder` (string) -> arquivo
`{VIDEO_STORAGE_DIR}/{folder}/video.mp4`.

O UUID determinístico segue a regra `UUID(int=content_id)`, então
extraimos o content_id como `uuid_obj.int`.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from uuid import UUID

logger = logging.getLogger(__name__)

# Onde os MP4s estao no container (montado via docker-compose)
VIDEO_STORAGE_DIR = Path(os.environ.get("VIDEO_STORAGE_DIR", "/app/videos_storage"))

# Parquet com o catalogo + folder (montado via volume)
CATALOG_PARQUET = Path(os.environ.get(
    "CATALOG_PARQUET", "/app/ai_data/contents.parquet"
))


_content_id_to_folder: dict[int, str] = {}
_loaded: bool = False


def load_mapping() -> int:
    """Carrega content_id → folder. Idempotente."""
    global _content_id_to_folder, _loaded
    if _loaded:
        return len(_content_id_to_folder)

    if not CATALOG_PARQUET.exists():
        logger.warning("contents.parquet nao encontrado em %s — streaming desativado", CATALOG_PARQUET)
        _loaded = True
        return 0

    try:
        import pandas as pd
    except ImportError:
        logger.warning("pandas nao instalado — streaming desativado")
        _loaded = True
        return 0

    df = pd.read_parquet(CATALOG_PARQUET)
    if "folder" not in df.columns or "content_id" not in df.columns:
        logger.warning("contents.parquet sem colunas content_id/folder")
        _loaded = True
        return 0

    _content_id_to_folder = {
        int(r["content_id"]): str(r["folder"])
        for _, r in df.iterrows()
        if r.get("folder")
    }
    _loaded = True
    logger.info("video_storage: %d arquivos mapeados", len(_content_id_to_folder))
    return len(_content_id_to_folder)


def resolve_video_path(video_id: UUID) -> Path | None:
    """Retorna o caminho do .mp4 ou None se nao existir."""
    load_mapping()
    content_id = video_id.int
    folder = _content_id_to_folder.get(content_id)
    if not folder:
        return None
    path = VIDEO_STORAGE_DIR / folder / "video.mp4"
    return path if path.is_file() else None


def is_available() -> bool:
    """True se o storage tem ao menos 1 arquivo mapeado."""
    load_mapping()
    return bool(_content_id_to_folder)
