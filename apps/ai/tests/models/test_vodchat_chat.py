"""VodChat.chat — contexto de historico no system prompt."""
from app.models.vodchat import VodChat


def test_chat_keeps_user_message_clean_and_puts_history_in_system():
    vodchat = VodChat.__new__(VodChat)
    vodchat._loaded = True
    captured: dict[str, str] = {}

    def fake_generate(user_message: str, system_prompt: str = "") -> str:
        captured["user"] = user_message
        captured["system"] = system_prompt
        return "ok"

    vodchat._generate = fake_generate  # type: ignore[method-assign]

    vodchat.chat(
        "quero videos de culinaria",
        history_titles=["Pao de queijo", "Feijoada"],
    )

    assert captured["user"] == "quero videos de culinaria"
    assert "Pao de queijo" in captured["system"]
    assert "Historico recente do usuario" not in captured["user"]
