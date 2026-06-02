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

# Categorias que realmente existem no acervo (apps/ai/data/categories.json).
CATALOG_CATEGORIES = (
    "Natureza",
    "Culinária",
    "Música",
    "Esporte",
    "Tecnologia",
    "Turismo",
    "Educação",
    "Ciência",
    "Saúde",
    "Arte",
)

# Generos de filme/serie que o usuario costuma pedir mas que NAO existem no
# acervo educativo. Usado para responder com honestidade em vez de empurrar
# vizinhos semanticos fora de contexto (ex.: documentario de natureza).
_OUT_OF_CATALOG_GENRES = frozenset(
    {
        "acao",
        "aventura",
        "terror",
        "horror",
        "comedia",
        "drama",
        "suspense",
        "romance",
        "ficcao",
        "guerra",
        "faroeste",
        "policial",
        "policia",
        "crime",
        "thriller",
        "anime",
        "animacao",
        "novela",
    }
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
        "indica",
        "indicar",
        "indique",
        "sugira",
        "legal",
        "hoje",
        "agora",
        "noite",
        "tarde",
        "manha",
        "falem",
        "fale",
        "falar",
        "fala",
        "que",
        "a",
    }
)

# Palavras de contexto social/temporal — nao sao temas do catalogo educativo.
_CONTEXT_ONLY_WORDS = frozenset(
    {
        "namorada",
        "namorado",
        "namoro",
        "casal",
        "familia",
        "amigo",
        "amiga",
        "amigos",
        "crianca",
        "criancas",
        "filho",
        "filhos",
        "esposa",
        "esposo",
        "marido",
        "mulher",
        "homem",
        "pessoa",
        "pessoas",
        "galera",
        "turma",
    }
)

_PREFIX_PATTERNS = (
    r"^o que assistir\s+",
    r"^o que ver\s+",
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


def _matches_catalog_topic(word: str) -> bool:
    """True se a palavra for tema real do acervo (natureza, musica, culinaria...)."""
    normalized = _normalize(word)
    if normalized in _CATALOG_TOPIC_ROOTS:
        return True
    for root, synonyms in _TOPIC_SYNONYMS.items():
        if normalized == root or normalized.startswith(root) or root.startswith(normalized):
            return True
        if any(
            normalized in syn or syn.startswith(normalized) or normalized.startswith(syn)
            for syn in synonyms
            if len(syn) >= 4
        ):
            return True
    for category in CATALOG_CATEGORIES:
        category_norm = _normalize(category)
        if normalized in category_norm or category_norm.startswith(normalized):
            return True
    return False


def has_catalog_topic(message: str) -> bool:
    """Indica se a mensagem cita um tema pesquisavel no catalogo."""
    query = _extract_normalized_query(message)
    keywords = topic_keywords(query)
    if not keywords:
        return False
    if all(keyword in _CONTEXT_ONLY_WORDS for keyword in keywords):
        return False
    return any(_matches_catalog_topic(keyword) for keyword in keywords)


def should_attach_videos(message: str) -> bool:
    """Indica se a mensagem parece pedido de descoberta de conteúdo."""
    stripped = message.strip()
    if len(stripped) < 3 or is_greeting_only(stripped):
        return False
    if should_use_personalized_recommendations(stripped):
        return False
    return has_catalog_topic(stripped)


def is_recommendation_request(message: str) -> bool:
    """Detecta pedidos genéricos do tipo "o que assistir hoje?"."""
    normalized = _normalize(message)
    generic_hints = (
        "o que assistir",
        "o que ver",
        "me indica",
        "me recomende",
        "recomend",
        "sugira",
        "algo legal",
        "assistir hoje",
        "ver hoje",
    )
    return any(hint in normalized for hint in generic_hints)


def should_use_personalized_recommendations(message: str) -> bool:
    """Pedidos abertos sem tema de catalogo — usa recomendacoes do usuario."""
    stripped = message.strip()
    if len(stripped) < 3 or is_greeting_only(stripped):
        return False
    if has_catalog_topic(stripped):
        return False
    return is_recommendation_request(stripped) or bool(
        re.search(r"\b(ver|assistir|recomend|indic|sugir)\b", _normalize(stripped))
    )


def _extract_normalized_query(message: str) -> str:
    normalized = _normalize(message.strip())
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
    return re.sub(r"\s+", " ", normalized).strip(" .,!?:;")


def extract_search_query(message: str) -> str:
    """Extrai o tema da mensagem (ex.: 'policia', 'culinaria') para busca no catalogo."""
    keywords = topic_keywords(_extract_normalized_query(message))
    if not keywords:
        return ""
    if all(keyword in _CONTEXT_ONLY_WORDS for keyword in keywords):
        return ""
    catalog_keywords = [keyword for keyword in keywords if _matches_catalog_topic(keyword)]
    if catalog_keywords:
        return " ".join(catalog_keywords)
    return ""


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

_CATALOG_TOPIC_ROOTS = frozenset(_TOPIC_SYNONYMS.keys()) | {
    _normalize(category) for category in CATALOG_CATEGORIES
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


def is_out_of_catalog_genre(search_query: str) -> bool:
    """True se o pedido for um genero de filme/serie inexistente no acervo.

    Evita responder 'filmes de acao' com documentarios de natureza (vizinhos
    semanticos), retornando uma mensagem honesta com as categorias reais.
    """
    keywords = topic_keywords(search_query)
    if not keywords:
        return False
    # So bloqueia quando TODO o tema cai em generos fora do catalogo. Assim
    # pedidos validos ("python", "futebol") seguem o fluxo normal.
    return all(word in _OUT_OF_CATALOG_GENRES for word in keywords)


def video_matches_topic(title: str, description: str | None, keywords: list[str]) -> bool:
    if not keywords:
        return True
    haystack = _normalize(f"{title} {description or ''}")
    # Match por palavra inteira evita falso-positivo de substring
    # (ex.: 'acao' dentro de 'acaonome' ou termos genericos soltos).
    return any(
        re.search(rf"\b{re.escape(keyword)}\b", haystack) for keyword in keywords
    )
