"""Heurísticas para anexar busca de vídeos à resposta do chat."""
from __future__ import annotations

import re
import unicodedata

_GREETINGS = frozenset(
    {
        "oi",
        "ola",
        "olá",
        "hey",
        "hi",
        "hello",
        "bom dia",
        "boa tarde",
        "boa noite",
        "e ai",
        "e aí",
        "tudo bem",
        "obrigado",
        "obrigada",
        "valeu",
    }
)

_DISCOVER_HINTS = (
    "video",
    "vídeo",
    "filme",
    "serie",
    "série",
    "assistir",
    "ver ",
    "mostre",
    "mostra",
    "recomend",
    "sugest",
    "catalogo",
    "catálogo",
    "culinaria",
    "culinária",
    "receita",
    "cozinha",
    "documentario",
    "documentário",
    "natureza",
    "esporte",
    "musica",
    "música",
    "policia",
    "policial",
)

_TOPIC_STOPWORDS = frozenset(
    {
        "de",
        "da",
        "do",
        "dos",
        "das",
        "em",
        "no",
        "na",
        "nos",
        "nas",
        "para",
        "com",
        "sem",
        "sobre",
        "video",
        "videos",
        "filme",
        "filmes",
        "serie",
        "series",
        "quero",
        "ver",
        "algo",
        "uns",
        "umas",
        "assistir",
        "recomende",
        "recomendar",
        "recomenda",
        "indique",
        "sugira",
        "falem",
        "fale",
        "falar",
        "fala",
        "que",
    }
)

_PREFIX_PATTERNS = (
    r"^quero assistir\s+",
    r"^quero videos de\s+",
    r"^quero video de\s+",
    r"^quero filmes de\s+",
    r"^quero filme de\s+",
    r"^gostaria de ver\s+",
    r"^quero ver\s+",
    r"^me recomende\s+",
    r"^me indique\s+",
    r"^me sugira\s+",
    r"^me mostre\s+",
    r"^mostre\s+",
    r"^procuro\s+",
    r"^busco\s+",
    r"^videos sobre\s+",
    r"^vídeos sobre\s+",
    r"^video sobre\s+",
    r"^vídeo sobre\s+",
    r"^filmes sobre\s+",
    r"^algo sobre\s+",
)

# Removidos apos prefixos regex (ordem: frases mais longas primeiro).
_FILLER_PHRASES = (
    "videos que falem sobre",
    "videos que fale sobre",
    "videos que falam sobre",
    "video que falem sobre",
    "que falem sobre",
    "que fale sobre",
    "que falam sobre",
    "videos que",
    "video que",
    "videos de",
    "video de",
    "filmes de",
    "filme de",
    "recomende videos",
    "recomendar videos",
    "assistir videos",
    "assistir video",
)


def _normalize(text: str) -> str:
    lowered = text.strip().lower()
    normalized = unicodedata.normalize("NFD", lowered)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def is_greeting_only(message: str) -> bool:
    normalized = _normalize(message)
    if not normalized:
        return True
    return normalized in _GREETINGS or len(normalized) < 4


def should_attach_videos(message: str) -> bool:
    """Indica se a mensagem parece pedido de descoberta de conteúdo."""
    stripped = message.strip()
    if len(stripped) < 3 or is_greeting_only(stripped):
        return False
    normalized = _normalize(stripped)
    if any(hint in normalized for hint in _DISCOVER_HINTS):
        return True
    # Mensagens longas costumam ser pedidos abertos ("quero algo leve para hoje").
    return len(normalized.split()) >= 4


def extract_search_query(message: str) -> str:
    """Extrai o tema da mensagem (ex.: 'policia', 'culinaria') para busca no catalogo."""
    query = message.strip()
    normalized = _normalize(query)

    for pattern in _PREFIX_PATTERNS:
        normalized = re.sub(pattern, "", normalized, flags=re.IGNORECASE)

    for phrase in _FILLER_PHRASES:
        normalized = normalized.replace(phrase, " ")

    normalized = re.sub(
        r"^(videos|video|filmes|filme|series|serie)\s+",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"\s+", " ", normalized).strip(" .,!?:;")

    keywords = topic_keywords(normalized)
    if keywords:
        return " ".join(keywords)
    if len(normalized) >= 3:
        return normalized
    return query


_TOPIC_SYNONYMS: dict[str, tuple[str, ...]] = {
    "natureza": (
        "natureza",
        "amazonia",
        "amazonica",
        "floresta",
        "selvagem",
        "fauna",
        "pantanal",
        "documentario",
        "animal",
        "animais",
        "ambient",
        "bioma",
        "chuva",
        "agua",
        "rio amazonas",
    ),
    "culinaria": (
        "culinaria",
        "receita",
        "receitas",
        "cozinha",
        "cozinhar",
        "chef",
        "comida",
        "culinario",
        "gastronom",
        "ingredientes",
        "feijoada",
        "brigadeiro",
    ),
    "esporte": ("esporte", "esportes", "futebol", "jogo", "atleta", "campeonato"),
    "musica": ("musica", "musical", "cantor", "banda", "show", "concerto"),
    "policia": (
        "policia",
        "policiais",
        "policial",
        "polici",
        "crime",
        "investigacao",
        "investigador",
        "detetive",
    ),
}


def topic_keywords(search_query: str) -> list[str]:
    """Termos principais extraidos da query (ex.: natureza, culinaria)."""
    return [
        word
        for word in _normalize(search_query).split()
        if len(word) >= 3 and word not in _TOPIC_STOPWORDS
    ]


def expand_topic_keywords(search_query: str) -> list[str]:
    """Inclui sinonimos para match em titulo/descricao (ex. natureza -> amazonia, floresta)."""
    base = topic_keywords(search_query)
    expanded: set[str] = set(base)
    normalized_query = _normalize(search_query)

    for topic, synonyms in _TOPIC_SYNONYMS.items():
        if topic in base or topic in normalized_query:
            expanded.update(synonyms)
        elif any(syn in normalized_query for syn in synonyms if len(syn) >= 5):
            expanded.update(synonyms)

    return sorted(expanded)


def video_matches_topic(title: str, description: str | None, keywords: list[str]) -> bool:
    if not keywords:
        return True
    haystack = _normalize(f"{title} {description or ''}")
    return any(keyword in haystack for keyword in keywords)
