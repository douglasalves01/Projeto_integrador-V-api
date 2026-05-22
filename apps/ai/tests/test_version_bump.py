import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRAIN_SCRIPT = PROJECT_ROOT / "scripts" / "train_offline.py"


def _load_train_module():
    spec = importlib.util.spec_from_file_location("train_offline", TRAIN_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_bump_version_increments_patch() -> None:
    train = _load_train_module()
    assert train.bump_version("hybrid-v1.2.3") == "hybrid-v1.2.4"
    assert train.bump_version(None) == "hybrid-v1.0.0"
    assert train.bump_version("invalid") == "hybrid-v1.0.0"
