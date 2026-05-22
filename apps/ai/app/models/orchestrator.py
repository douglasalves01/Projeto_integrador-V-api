"""RecommendationOrchestrator: combina VodRec-Transformer (ranking) com VodChat
(explicacoes/conversa) e implementa as politicas de cold start (RFIA03).

Estrategia de switching baseada em quantos conteudos o usuario assistiu:

    | total_views        | estrategia       | quem ranqueia                      |
    |--------------------|------------------|------------------------------------|
    | 0 (sem historico)  | empty_history    | retorna [] (caller usa popularity) |
    | 1..4               | cold_start       | PopularityFallback                 |
    | >= 5               | vodrec           | VodRecTransformer                  |

Atende RFIA03 ("recomendacao ativada apenas com >= 5 conteudos assistidos").
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Sequence

from app.models.vodchat import VodChat
from app.models.vodrec_transformer import VodRecRecommender


COLD_START_THRESHOLD = 5  # RFIA03 — minimo de conteudos para ativar VodRec


@dataclass
class Recommendation:
    content_id: int
    score: float
    title: str | None = None
    genres: list[str] = field(default_factory=list)
    reason: str | None = None


# ---------------------------------------------------------------------------
# Popularity fallback (usado em cold start)
# ---------------------------------------------------------------------------


class PopularityFallback:
    """Ranking estatico calculado a partir do catalogo + histograma de visualizacoes.

    Recebe um dicionario { content_id: view_count } para ordenar os mais populares.
    Caso o histograma esteja vazio, usa a ordem do catalogo (estavel mas neutra).
    """

    def __init__(self, view_counts: dict[int, int] | None = None) -> None:
        self.view_counts = view_counts or {}
        self._ranking: list[int] = []
        self._rebuild()

    def update(self, view_counts: dict[int, int]) -> None:
        self.view_counts = view_counts
        self._rebuild()

    def _rebuild(self) -> None:
        if self.view_counts:
            self._ranking = [
                cid for cid, _ in sorted(
                    self.view_counts.items(), key=lambda kv: kv[1], reverse=True
                )
            ]
        else:
            self._ranking = []

    def recommend(
        self,
        history_content_ids: Sequence[int],
        catalog_content_ids: Sequence[int],
        k: int,
        exclude_seen: bool = True,
    ) -> list[tuple[int, float]]:
        seen = set(history_content_ids) if exclude_seen else set()

        base = self._ranking or list(catalog_content_ids)
        # Garante que itens com 0 views ainda apareçam (cauda longa)
        already = set(base)
        base = base + [c for c in catalog_content_ids if c not in already]

        total = max(1, sum(self.view_counts.values()))
        recs: list[tuple[int, float]] = []
        for cid in base:
            if cid in seen:
                continue
            score = self.view_counts.get(cid, 0) / total
            recs.append((cid, score))
            if len(recs) >= k:
                break
        return recs


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


class RecommendationOrchestrator:
    """Combina VodRec + VodChat + politica de cold start."""

    def __init__(
        self,
        vodrec: VodRecRecommender,
        vodchat: VodChat | None = None,
        catalog: dict[int, dict] | None = None,
        popularity: PopularityFallback | None = None,
        cold_start_threshold: int = COLD_START_THRESHOLD,
    ) -> None:
        self.vodrec = vodrec
        self.vodchat = vodchat
        self.catalog = catalog or {}
        self.popularity = popularity or PopularityFallback()
        self.cold_start_threshold = cold_start_threshold

    # ------------------------------------------------------------------
    # Catalog helpers
    # ------------------------------------------------------------------

    def set_catalog(self, catalog: dict[int, dict]) -> None:
        self.catalog = catalog
        if self.vodchat is not None:
            titles = [
                str(item["title"])
                for item in catalog.values()
                if item.get("title")
            ]
            self.vodchat.update_known_titles(titles)

    def set_popularity(self, view_counts: dict[int, int]) -> None:
        self.popularity.update(view_counts)

    def _title_for(self, content_id: int) -> str:
        item = self.catalog.get(content_id, {})
        return str(item.get("title", f"content_{content_id}"))

    def _genres_for(self, content_id: int) -> list[str]:
        item = self.catalog.get(content_id, {})
        return list(item.get("genres", []))

    # ------------------------------------------------------------------
    # Strategy resolution (RFIA03)
    # ------------------------------------------------------------------

    def _resolve_strategy(self, total_views: int) -> str:
        if total_views == 0:
            return "empty_history"
        if total_views < self.cold_start_threshold:
            return "cold_start"
        return "vodrec"

    # ------------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------------

    def recommend(
        self,
        history_content_ids: Sequence[int],
        k: int = 20,
        with_explanation: bool = False,
        temperature: float = 1.0,
    ) -> dict:
        history_content_ids = list(history_content_ids)
        total = len(history_content_ids)
        strategy = self._resolve_strategy(total)

        if strategy == "empty_history":
            ranked: list[tuple[int, float]] = []
        elif strategy == "cold_start":
            ranked = self.popularity.recommend(
                history_content_ids,
                catalog_content_ids=list(self.catalog.keys()),
                k=k,
                exclude_seen=True,
            )
        else:
            ranked = self.vodrec.recommend(
                history_content_ids,
                k=k,
                exclude_seen=True,
                temperature=temperature,
            )

        recommendations: list[Recommendation] = [
            Recommendation(
                content_id=cid,
                score=score,
                title=self._title_for(cid),
                genres=self._genres_for(cid),
            )
            for cid, score in ranked
        ]

        # Explicacao opcional via VodChat (so faz sentido se houver recomendacao)
        top_explanation: str | None = None
        if (
            with_explanation
            and recommendations
            and self.vodchat is not None
            and strategy in ("vodrec", "cold_start")
        ):
            top = recommendations[0]
            history_titles = [self._title_for(c) for c in history_content_ids[-8:]]
            try:
                top_explanation = self.vodchat.explain(
                    history_titles=history_titles,
                    recommended_title=top.title or "",
                    recommended_genres=top.genres,
                )
                recommendations[0].reason = top_explanation
            except Exception as exc:  # pragma: no cover
                top_explanation = None
                recommendations[0].reason = (
                    f"(explicacao indisponivel: {exc.__class__.__name__})"
                )

        return {
            "model_version": "vodrec-v1.0+vodchat-v1.0",
            "strategy": strategy,
            "total_views": total,
            "cold_start_threshold": self.cold_start_threshold,
            "recommendations": [
                {
                    "content_id": r.content_id,
                    "score": r.score,
                    "title": r.title,
                    "genres": r.genres,
                    "reason": r.reason,
                }
                for r in recommendations
            ],
            "top_explanation": top_explanation,
        }

    def chat(
        self,
        user_message: str,
        history_content_ids: Sequence[int] | None = None,
    ) -> str:
        if self.vodchat is None:
            raise RuntimeError("VodChat nao carregado neste orchestrator.")
        history_titles = (
            [self._title_for(c) for c in (history_content_ids or [])[-8:]] or None
        )
        return self.vodchat.chat(user_message=user_message, history_titles=history_titles)

    # ------------------------------------------------------------------
    # Utilidades para inspecao
    # ------------------------------------------------------------------

    def genre_weights_from_history(self, history_content_ids: Sequence[int]) -> dict[str, float]:
        """Deriva `genre_weights` (Secao 6 do PDF) a partir do historico do usuario.

        Util para a UI mostrar 'voce gosta de Acao, Aventura, ...'.
        """
        counter: Counter[str] = Counter()
        for cid in history_content_ids:
            for g in self._genres_for(cid):
                counter[g] += 1
        total = sum(counter.values())
        if total == 0:
            return {}
        return {g: c / total for g, c in counter.most_common()}
