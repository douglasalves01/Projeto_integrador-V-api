"""Testes do filtro post-hoc anti-alucinacao do VodChat.

A LogitsProcessor depende de transformers/PyTorch tokenizer e nao e
testavel sem o modelo real. O filtro post-hoc (regex-based) e testado
aqui isoladamente.
"""
from __future__ import annotations

import pytest

from app.models.vodchat_constraints import (
    _TitleVocabIndex,
    filter_unknown_titles,
)


KNOWN = {"Vinganca Sombra", "Eclipse Tormenta", "Reino Destino"}


def test_known_title_passes_through():
    text = 'Recomendei *Vinganca Sombra* porque combina com o seu gosto.'
    out = filter_unknown_titles(text, KNOWN)
    assert "Vinganca Sombra" in out
    assert "um titulo do catalogo" not in out


def test_unknown_title_is_replaced():
    text = 'Voce vai adorar *Titulo Inexistente* — perfeito para hoje.'
    out = filter_unknown_titles(text, KNOWN)
    assert "Titulo Inexistente" not in out
    assert "um titulo do catalogo" in out


def test_case_insensitive_match():
    text = 'Sugiro "VINGANCA SOMBRA" como prioridade.'
    out = filter_unknown_titles(text, KNOWN)
    # O match deve passar mesmo com diferenca de case
    assert "VINGANCA SOMBRA" in out
    assert "um titulo do catalogo" not in out


def test_mixed_known_and_unknown():
    text = 'Top 2: *Reino Destino* e *Filme Fake*.'
    out = filter_unknown_titles(text, KNOWN)
    assert "Reino Destino" in out
    assert "Filme Fake" not in out
    assert "um titulo do catalogo" in out


def test_empty_known_titles_returns_text_unchanged():
    text = 'Voce assistiu *Qualquer Coisa* ontem?'
    out = filter_unknown_titles(text, set())
    assert out == text


def test_text_without_quotes_unchanged():
    text = "Sem aspas neste texto, nenhum titulo mencionado explicitamente."
    out = filter_unknown_titles(text, KNOWN)
    assert out == text


def test_vocab_index_starts_with():
    idx = _TitleVocabIndex.build(["Vinganca Sombra", "Vinganca Eterna", "Reino"])
    assert idx.any_starts_with("vin") is True
    assert idx.any_starts_with("Vinganca Sombra") is True
    assert idx.any_starts_with("vinganca e") is True
    assert idx.any_starts_with("xyz") is False
    # Vazio sempre passa (qualquer titulo "comeca com vazio")
    assert idx.any_starts_with("") is True
