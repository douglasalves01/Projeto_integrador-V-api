"""Tests for RecommendationOrchestrator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.models.orchestrator import RecommendationOrchestrator


@pytest.fixture
def mock_vodrec() -> MagicMock:
    vodrec = MagicMock()
    vodrec.recommend.return_value = [(10, 0.9), (20, 0.7)]
    return vodrec


@pytest.fixture
def catalog() -> dict[int, dict]:
    return {
        10: {"title": "Filme A", "genres": ["Ação"]},
        20: {"title": "Filme B", "genres": ["Comédia"]},
    }


class TestRecommendationOrchestrator:
    def test_recommend_fills_catalog_metadata(
        self, mock_vodrec: MagicMock, catalog: dict[int, dict]
    ) -> None:
        orch = RecommendationOrchestrator(vodrec=mock_vodrec, vodchat=None, catalog=catalog)
        result = orch.recommend([1, 2, 3], k=2, with_explanation=False)

        assert result["strategy"] == "cold_start"
        assert len(result["recommendations"]) == 2
        assert result["recommendations"][0]["title"] == "Filme A"
        assert result["recommendations"][0]["genres"] == ["Ação"]

    def test_without_vodchat_no_reason_on_explanation_request(
        self, mock_vodrec: MagicMock, catalog: dict[int, dict]
    ) -> None:
        orch = RecommendationOrchestrator(vodrec=mock_vodrec, vodchat=None, catalog=catalog)
        result = orch.recommend([1], k=2, with_explanation=True)

        assert result["recommendations"][0]["reason"] is None
        assert result["top_explanation"] is None

    def test_vodchat_fills_reason_when_available(
        self, mock_vodrec: MagicMock, catalog: dict[int, dict]
    ) -> None:
        vodchat = MagicMock()
        vodchat.explain.return_value = "Porque você gosta de ação"
        orch = RecommendationOrchestrator(vodrec=mock_vodrec, vodchat=vodchat, catalog=catalog)
        result = orch.recommend([1, 2], k=2, with_explanation=True)

        assert result["recommendations"][0]["reason"] == "Porque você gosta de ação"
        vodchat.explain.assert_called_once()

    def test_chat_requires_vodchat(self, mock_vodrec: MagicMock) -> None:
        orch = RecommendationOrchestrator(vodrec=mock_vodrec, vodchat=None)
        with pytest.raises(RuntimeError, match="VodChat"):
            orch.chat("Olá")

    def test_set_catalog_updates_vodchat_known_titles(
        self, mock_vodrec: MagicMock, catalog: dict[int, dict]
    ) -> None:
        vodchat = MagicMock()
        orch = RecommendationOrchestrator(
            vodrec=mock_vodrec, vodchat=vodchat, catalog={}
        )
        orch.set_catalog(catalog)
        vodchat.update_known_titles.assert_called_once_with(["Filme A", "Filme B"])
