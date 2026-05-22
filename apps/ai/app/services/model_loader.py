"""Singleton loader for ML recommendation models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from app.core.config import get_settings
from app.models.collaborative import CollaborativeRecommender
from app.models.content_based import ContentBasedRecommender
from app.models.hybrid import HybridRecommender

settings = get_settings()
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODELS_DIR = PROJECT_ROOT / "data" / "models"
VERSION_FILE = DEFAULT_MODELS_DIR / "VERSION.txt"

CB_FILENAMES = ("content_based.pkl", "content_based.joblib")
CF_FILENAMES = ("als_model.pkl", "collaborative.joblib")


class ModelLoader:
    """Loads and hot-reloads recommendation models from disk."""

    _instance: ModelLoader | None = None

    def __new__(cls) -> ModelLoader:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self.content_based: ContentBasedRecommender | None = None
        self.collaborative: CollaborativeRecommender | None = None
        self.hybrid: HybridRecommender | None = None
        self.current_model_version: str = settings.AI_MODEL_VERSION
        self._initialized = True

    @property
    def is_loaded(self) -> bool:
        return self.hybrid is not None

    def load(self) -> bool:
        """Load models from disk. Returns True on success."""
        self.current_model_version = self._read_version()
        model_dir = self._resolve_model_dir()

        if model_dir is None:
            self._clear_models()
            return False

        cb_path = self._find_artifact(model_dir, CB_FILENAMES)
        cf_path = self._find_artifact(model_dir, CF_FILENAMES)

        if cb_path is None or cf_path is None:
            logger.warning(
                "Model artifacts missing",
                model_dir=str(model_dir),
                content_based=str(cb_path),
                collaborative=str(cf_path),
            )
            self._clear_models()
            return False

        self.content_based = ContentBasedRecommender.load(str(cb_path))
        self.collaborative = CollaborativeRecommender.load(str(cf_path))
        self.hybrid = HybridRecommender(self.content_based, self.collaborative)

        logger.info(
            "Models loaded successfully",
            model_version=self.current_model_version,
            content_based=str(cb_path),
            collaborative=str(cf_path),
        )
        return True

    def reload_models(self) -> bool:
        """Re-load models after offline training without restarting the server."""
        logger.info("Reloading recommendation models")
        return self.load()

    def as_dict(self) -> dict[str, Any]:
        """Return loaded models as a dict (for app state compatibility)."""
        if not self.is_loaded:
            return {}
        return {
            "content_based": self.content_based,
            "collaborative": self.collaborative,
            "hybrid": self.hybrid,
            "model_version": self.current_model_version,
        }

    def _resolve_model_dir(self) -> Path | None:
        candidates = [
            Path(settings.MODEL_PATH),
            DEFAULT_MODELS_DIR,
        ]
        for directory in candidates:
            if not directory.exists():
                continue
            if (
                self._find_artifact(directory, CB_FILENAMES) is not None
                and self._find_artifact(directory, CF_FILENAMES) is not None
            ):
                return directory
        logger.warning(
            "Model directory not found",
            candidates=[str(p) for p in candidates],
        )
        return None

    @staticmethod
    def _find_artifact(model_dir: Path, filenames: tuple[str, ...]) -> Path | None:
        for name in filenames:
            path = model_dir / name
            if path.exists():
                return path
        return None

    def _read_version(self) -> str:
        candidates = (
            VERSION_FILE,
            Path(settings.MODEL_PATH) / "VERSION.txt",
            DEFAULT_MODELS_DIR / "VERSION.txt",
        )
        for path in candidates:
            if path.exists():
                version = path.read_text(encoding="utf-8").strip()
                if version:
                    return version

        return settings.AI_MODEL_VERSION

    def _clear_models(self) -> None:
        self.content_based = None
        self.collaborative = None
        self.hybrid = None


model_loader = ModelLoader()
