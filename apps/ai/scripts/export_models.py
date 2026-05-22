#!/usr/bin/env python3
"""Compress trained model artifacts for production upload (S3/storage)."""

from __future__ import annotations

import argparse
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logging import setup_logging  # noqa: E402

DEFAULT_MODELS_DIR = PROJECT_ROOT / "data" / "models"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "exports"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export data/models as tar.gz archive")
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=DEFAULT_MODELS_DIR,
        help="Directory containing trained artifacts",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output tar.gz path (default: data/exports/models-YYYYMMDD-HHMMSS.tar.gz)",
    )
    return parser.parse_args()


def export_models(models_dir: Path, output_path: Path) -> Path:
    if not models_dir.exists():
        raise FileNotFoundError(f"Models directory not found: {models_dir}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tarfile.open(output_path, "w:gz") as archive:
        for file_path in sorted(models_dir.rglob("*")):
            if file_path.is_file():
                archive.add(file_path, arcname=file_path.relative_to(models_dir.parent))

    logger.info(
        "Model archive created",
        source=str(models_dir),
        output=str(output_path),
        size_mb=round(output_path.stat().st_size / (1024 * 1024), 2),
    )
    return output_path


def main() -> int:
    setup_logging()
    args = parse_args()

    models_dir = args.models_dir.resolve()
    if args.output is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        output_path = DEFAULT_OUTPUT_DIR / f"models-{timestamp}.tar.gz"
    else:
        output_path = args.output.resolve()

    try:
        export_models(models_dir, output_path)
    except FileNotFoundError as exc:
        logger.error(str(exc))
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
