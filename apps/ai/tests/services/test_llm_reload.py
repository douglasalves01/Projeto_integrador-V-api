"""Tests for LLM hot-reload safety."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services import llm_recommendation_service as svc


class TestReloadLlmModels:
    def test_failed_reload_restores_previous_orchestrator(self) -> None:
        previous = MagicMock(name="previous_orchestrator")
        svc._ORCHESTRATOR = previous
        svc.get_model_info.cache_clear()

        with patch.object(svc, "load_llm_models", side_effect=RuntimeError("load failed")):
            result = svc.reload_llm_models()

        assert result["status"] == "error"
        assert svc._ORCHESTRATOR is previous

    def test_successful_reload_replaces_orchestrator(self) -> None:
        new_orch = MagicMock(name="new_orchestrator")
        svc._ORCHESTRATOR = MagicMock(name="old")

        def _fake_load(**_kwargs):
            svc._ORCHESTRATOR = new_orch
            return new_orch

        with patch.object(svc, "load_llm_models", side_effect=_fake_load):
            result = svc.reload_llm_models()

        assert result["status"] == "ok"
        assert svc._ORCHESTRATOR is new_orch
