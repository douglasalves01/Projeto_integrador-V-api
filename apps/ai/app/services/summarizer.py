"""Resumo extrativo de descricoes de video (sem LLM).

Pensado para descricoes de YouTube: remove ruido (links, hashtags, emojis,
marcas de tempo, chamadas promocionais) e seleciona as primeiras frases
relevantes. Deterministico, instantaneo e fiel ao texto original — ideal para
o acervo atual, onde a descricao ja foi escrita pelo autor do video.
"""

from __future__ import annotations

import re

_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_HASHTAG = re.compile(r"#\S+")
_TIMESTAMP_LINE = re.compile(r"^\s*\d{1,2}:\d{2}(?::\d{2})?\b.*$", re.MULTILINE)
_INLINE_TIMESTAMP = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")
_EMOJI = re.compile(
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff\u2190-\u21ff\u2700-\u27bf]",
    flags=re.UNICODE,
)
_PROMO = re.compile(
    r"(?i)\b(inscreva|inscrever|se inscreve|curta|deixe seu like|like|compartilhe|"
    r"link na bio|link abaixo|pix|whatsapp|cupom|promo|promocao|compre|adquira|"
    r"e-?book|baixe|clique aqui|telegram|instagram|tiktok|facebook|canal|"
    r"ingredientes|modo de preparo)\b"
)
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_MENTION = re.compile(r"@\w+")


def _clean(text: str) -> str:
    text = _URL.sub(" ", text)
    text = _HASHTAG.sub(" ", text)
    text = _MENTION.sub(" ", text)
    text = _TIMESTAMP_LINE.sub(" ", text)
    text = _INLINE_TIMESTAMP.sub(" ", text)
    text = _EMOJI.sub(" ", text)
    # Descarta linhas curtas/promocionais (CTA, listas de ingredientes, etc.).
    kept_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if len(stripped) < 15:
            continue
        if _PROMO.search(stripped):
            continue
        kept_lines.append(stripped)
    text = " ".join(kept_lines)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extractive_summary(
    title: str,
    description: str | None,
    max_sentences: int = 3,
    max_chars: int = 320,
) -> str:
    """Retorna um resumo curto extraido da descricao (ou string vazia)."""
    cleaned = _clean(description or "")
    if not cleaned:
        return ""

    sentences = [s.strip() for s in _SENT_SPLIT.split(cleaned) if len(s.strip()) >= 20]
    if not sentences:
        truncated = cleaned[:max_chars].rstrip()
        return truncated + ("…" if len(cleaned) > max_chars else "")

    selected: list[str] = []
    total = 0
    for sentence in sentences[:max_sentences]:
        selected.append(sentence)
        total += len(sentence)
        if total >= max_chars:
            break

    summary = " ".join(selected)
    if len(summary) > max_chars:
        summary = summary[:max_chars].rstrip() + "…"
    return summary
