"""Config do VodChat (Fase B — tokens e env)."""
from app.core.config import Settings


def test_vodchat_max_new_tokens_default():
    settings = Settings()
    assert settings.VODCHAT_MAX_NEW_TOKENS == 160


def test_vodchat_max_new_tokens_from_env(monkeypatch):
    monkeypatch.setenv("VODCHAT_MAX_NEW_TOKENS", "200")
    settings = Settings()
    assert settings.VODCHAT_MAX_NEW_TOKENS == 200
