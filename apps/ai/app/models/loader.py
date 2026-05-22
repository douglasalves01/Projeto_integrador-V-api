"""Backward-compatible entrypoint delegating to the service model loader."""

from typing import Any

from app.services.model_loader import model_loader


def load_models() -> dict[str, Any]:
    model_loader.load()
    return model_loader.as_dict()
