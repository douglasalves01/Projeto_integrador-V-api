from pathlib import Path
from unittest.mock import patch

from app.services.model_loader import ModelLoader, VERSION_FILE


def test_read_version_from_data_models() -> None:
    loader = ModelLoader()
    version = loader._read_version()
    assert version.startswith("hybrid-v")


def test_singleton_instance() -> None:
    a = ModelLoader()
    b = ModelLoader()
    assert a is b


def test_reload_models_calls_load() -> None:
    loader = ModelLoader()
    with patch.object(loader, "load", return_value=True) as mock_load:
        assert loader.reload_models() is True
        mock_load.assert_called_once()


def test_resolve_model_dir_skips_empty_directory(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    models_dir = tmp_path / "data" / "models"
    empty_dir.mkdir()
    models_dir.mkdir(parents=True)
    (models_dir / "content_based.pkl").write_bytes(b"cb")
    (models_dir / "als_model.pkl").write_bytes(b"cf")

    loader = ModelLoader()
    with patch("app.services.model_loader.settings") as mock_settings:
        mock_settings.MODEL_PATH = str(empty_dir)
        with patch("app.services.model_loader.DEFAULT_MODELS_DIR", models_dir):
            resolved = loader._resolve_model_dir()

    assert resolved == models_dir
