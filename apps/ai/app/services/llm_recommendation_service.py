"""Service layer para os modelos LLM proprios (VodRec + VodChat).

Substitui (ou complementa) o `recommendation_service.py` classico que usa
TF-IDF + ALS. Os endpoints do FastAPI chamam essas funcoes.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings  # type: ignore
from app.models.orchestrator import RecommendationOrchestrator
from app.models.vodchat import VodChat
from app.models.vodrec_transformer import VodRecRecommender

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Singleton loader (chamado no startup do FastAPI)
# ---------------------------------------------------------------------------


_ORCHESTRATOR: RecommendationOrchestrator | None = None


def get_orchestrator() -> RecommendationOrchestrator:
    """Retorna o orchestrator carregado em memoria. Levanta se nao foi carregado."""
    if _ORCHESTRATOR is None:
        raise RuntimeError(
            "Orchestrator nao foi carregado. Chame load_llm_models() no startup."
        )
    return _ORCHESTRATOR


def reload_llm_models(
    catalog: dict[int, dict] | None = None,
    load_vodchat: bool | None = None,
) -> dict:
    """Hot-reload VodRec/VodChat from configured paths."""
    global _ORCHESTRATOR
    previous = _ORCHESTRATOR
    get_model_info.cache_clear()

    settings = get_settings()
    use_vodchat = settings.VODCHAT_ENABLED if load_vodchat is None else load_vodchat

    try:
        load_llm_models(load_vodchat=use_vodchat)
        if catalog is not None:
            update_catalog(catalog)
        return {"status": "ok", "info": get_model_info()}
    except Exception as exc:
        _ORCHESTRATOR = previous
        get_model_info.cache_clear()
        logger.exception("reload_llm_models failed")
        return {"status": "error", "detail": str(exc)}


def load_llm_models(
    vodrec_model_path: str | Path | None = None,
    vodrec_vocab_path: str | Path | None = None,
    vodchat_adapter_path: str | Path | None = None,
    vodchat_base_model_id: str | None = None,
    vodchat_gguf_path: str | Path | None = None,
    catalog: dict[int, dict] | None = None,
    load_vodchat: bool = True,
) -> RecommendationOrchestrator:
    """Carrega os dois modelos e monta o orchestrator. Idempotente.

    Le defaults das settings se os parametros vierem None.
    """
    global _ORCHESTRATOR

    settings = get_settings()

    vodrec_model_path = vodrec_model_path or settings.VODREC_MODEL_PATH
    vodrec_vocab_path = vodrec_vocab_path or settings.VODREC_VOCAB_PATH
    vodchat_adapter_path = vodchat_adapter_path or settings.VODCHAT_ADAPTER_PATH
    vodchat_base_model_id = vodchat_base_model_id or settings.VODCHAT_BASE_MODEL
    vodchat_gguf_path = vodchat_gguf_path or settings.VODCHAT_GGUF_PATH

    if not Path(vodrec_model_path).exists() or not Path(vodrec_vocab_path).exists():
        raise FileNotFoundError(
            f"VodRec artifacts missing: {vodrec_model_path}, {vodrec_vocab_path}"
        )

    logger.info("Carregando VodRec-Transformer de %s", vodrec_model_path)
    vodrec = VodRecRecommender.load(
        model_path=vodrec_model_path,
        vocab_path=vodrec_vocab_path,
    )
    logger.info(
        "VodRec carregado: %d parametros, vocab=%d",
        vodrec.model.num_params(),
        len(vodrec.content_to_token),
    )

    vodchat: VodChat | None = None
    if load_vodchat:
        try:
            logger.info("Carregando VodChat (LoRA adapter de %s)", vodchat_adapter_path)
            vodchat = VodChat(
                adapter_path=vodchat_adapter_path,
                base_model_id=vodchat_base_model_id,
                gguf_path=vodchat_gguf_path,
            )
            vodchat.load()
            logger.info("VodChat carregado (backend=%s)", vodchat.backend)
        except Exception as exc:
            logger.warning(
                "Falhou ao carregar VodChat (%s). Continuando sem chat/explanation.",
                exc,
            )
            vodchat = None

    _ORCHESTRATOR = RecommendationOrchestrator(
        vodrec=vodrec,
        vodchat=vodchat,
        catalog=catalog or {},
    )
    return _ORCHESTRATOR


def update_catalog(catalog: dict[int, dict]) -> None:
    """Atualiza o catalogo em memoria (titles, genres) para o orchestrator."""
    if _ORCHESTRATOR is None:
        raise RuntimeError("Orchestrator nao carregado")
    _ORCHESTRATOR.set_catalog(catalog)


# ---------------------------------------------------------------------------
# High-level service functions usadas pelos endpoints
# ---------------------------------------------------------------------------


def get_recommendations(
    history_content_ids: list[int],
    k: int = 20,
    with_explanation: bool = False,
) -> dict:
    """Endpoint principal: GET /recommendations/{user_id}."""
    orch = get_orchestrator()
    return orch.recommend(
        history_content_ids=history_content_ids,
        k=k,
        with_explanation=with_explanation,
    )


def chat_message(
    user_message: str,
    history_content_ids: list[int] | None = None,
) -> dict:
    """Endpoint /chat/{user_id}."""
    orch = get_orchestrator()
    text = orch.chat(user_message=user_message, history_content_ids=history_content_ids)
    return {"reply": text}


@lru_cache(maxsize=1)
def get_model_info() -> dict:
    """Metadados dos modelos carregados — usado pelo /llm/info."""
    if _ORCHESTRATOR is None:
        return {"loaded": False, "vodrec": None, "vodchat": {"loaded": False}}
    info = {
        "loaded": True,
        "vodrec": {
            "num_params": _ORCHESTRATOR.vodrec.model.num_params(),
            "vocab_size": _ORCHESTRATOR.vodrec.config.vocab_size,
            "d_model": _ORCHESTRATOR.vodrec.config.d_model,
            "n_layers": _ORCHESTRATOR.vodrec.config.n_layers,
            "n_heads": _ORCHESTRATOR.vodrec.config.n_heads,
            "max_seq_len": _ORCHESTRATOR.vodrec.config.max_seq_len,
        },
        "vodchat": {
            "loaded": _ORCHESTRATOR.vodchat is not None,
            "backend": _ORCHESTRATOR.vodchat.backend if _ORCHESTRATOR.vodchat else None,
        },
    }
    return info
