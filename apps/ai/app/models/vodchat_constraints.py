"""Constrained decoding para o VodChat — mitiga alucinacao de titulos.

Ideia: durante a geracao, sempre que o modelo abre aspas (entendendo como
intencao de mencionar um titulo), forcamos os proximos tokens a seguirem
APENAS por caminhos que reconstroem titulos existentes no catalogo.

Estrategia pratica (sem precisar de Trie complexa por padrao):

1. **Anchored title set**: cada titulo do catalogo e tokenizado uma unica vez.
2. **TitleEnforcerLogitsProcessor**: depois que o modelo emite uma aspa (")
   ou marcador de inicio de mencao, monitora os proximos tokens e penaliza
   aqueles que nao continuam algum titulo conhecido.
3. **PostHocFilter** (opcional): apos gerar, varre o texto e substitui
   trechos entre aspas que nao casam com nenhum titulo por uma resposta
   neutra ("um titulo do catalogo").

Para o caso de uso atual (explicar/recomendar com base em titulos enviados
no prompt), o aprendido pelo modelo costuma ser suficiente. Estas classes
existem como CAMADA DE SEGURANCA — defesa em profundidade.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

try:  # transformers e opcional para esta lib funcionar standalone
    import torch
    from transformers import LogitsProcessor
except ImportError:  # pragma: no cover
    torch = None  # type: ignore
    LogitsProcessor = object  # type: ignore


# ---------------------------------------------------------------------------
# Post-hoc filter (sem dependencia de transformers)
# ---------------------------------------------------------------------------


_QUOTED_RE = re.compile(r'[\"\'\*]([^\"\'\*]{2,80})[\"\'\*]')


def filter_unknown_titles(text: str, known_titles: set[str],
                          replacement: str = "um titulo do catalogo") -> str:
    """Substitui mencoes entre aspas/asteriscos que nao batem com o catalogo.

    Usa normalizacao case-insensitive + strip. Mantem o resto do texto intacto.
    """
    if not known_titles:
        return text
    known_norm = {t.strip().lower() for t in known_titles}

    def _repl(match: re.Match[str]) -> str:
        candidate = match.group(1).strip().lower()
        return match.group(0) if candidate in known_norm else replacement

    return _QUOTED_RE.sub(_repl, text)


# ---------------------------------------------------------------------------
# Streaming LogitsProcessor (depende de transformers)
# ---------------------------------------------------------------------------


@dataclass
class _TitleVocabIndex:
    """Pre-processa o conjunto de titulos para verificar prefixos rapidamente.

    Estrutura: dict {primeira_palavra_normalizada -> set[titulos]}.
    """
    by_first_word: dict[str, set[str]]
    all_norm: set[str]

    @classmethod
    def build(cls, titles: list[str]) -> "_TitleVocabIndex":
        by_first: dict[str, set[str]] = {}
        all_norm = set()
        for t in titles:
            norm = t.strip().lower()
            if not norm:
                continue
            all_norm.add(norm)
            first = norm.split(" ", 1)[0]
            by_first.setdefault(first, set()).add(norm)
        return cls(by_first_word=by_first, all_norm=all_norm)

    def any_starts_with(self, prefix: str) -> bool:
        prefix = prefix.strip().lower()
        if not prefix:
            return True
        return any(t.startswith(prefix) for t in self.all_norm)


class TitleAnchoredLogitsProcessor(LogitsProcessor):
    """Aplica penalidade leve a continuacoes que nao sao prefixo de nenhum titulo,
    APENAS quando estamos no meio de uma mencao com aspas abertas.

    Heuristica: e mais conservadora do que beam-search com Trie estrita, mas
    nao quebra fluencia. Penalidade default = -2.0 logit (ainda permite escapar
    se nada casar).
    """

    def __init__(self, tokenizer, titles: list[str], penalty: float = 2.0) -> None:
        if torch is None:
            raise RuntimeError("Requer 'transformers' instalado")
        self.tokenizer = tokenizer
        self.index = _TitleVocabIndex.build(titles)
        self.penalty = penalty

    def _inside_open_quote(self, decoded: str) -> tuple[bool, str]:
        """Retorna (estamos_em_quote, prefixo_atual_dentro_da_quote)."""
        # Pega os 200 chars finais (suficiente para o titulo mais longo).
        tail = decoded[-200:]
        # Detecta aspas/asteriscos pareadas
        opens = 0
        last_open_idx = -1
        for i, ch in enumerate(tail):
            if ch in '"\'*':
                opens += 1
                if opens % 2 == 1:
                    last_open_idx = i
        if opens % 2 == 1:
            return True, tail[last_open_idx + 1:].strip()
        return False, ""

    def __call__(self, input_ids, scores):
        # Decodifica a sequencia atual para entender se estamos dentro de "..."
        if input_ids.shape[0] != 1:
            # Para simplicidade, so funciona em batch=1 (caso comum em chat)
            return scores
        decoded = self.tokenizer.decode(input_ids[0], skip_special_tokens=True)
        inside, prefix = self._inside_open_quote(decoded)
        if not inside or len(prefix) < 2:
            return scores

        # Se ja temos um prefixo dentro de aspas, penaliza tokens que NAO
        # continuam para algum titulo conhecido.
        # Pegamos top-K candidatos e checamos o prefix expandido.
        K = 64
        topk = torch.topk(scores[0], k=K)
        for rank, tok_id in enumerate(topk.indices.tolist()):
            continuation = self.tokenizer.decode([tok_id])
            test_prefix = (prefix + continuation).strip().lower()
            if not self.index.any_starts_with(test_prefix):
                scores[0, tok_id] = scores[0, tok_id] - self.penalty
        return scores
