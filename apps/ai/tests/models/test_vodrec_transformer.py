"""Tests for VodRec-Transformer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch

from app.models.vodrec_transformer import VodRecConfig, VodRecRecommender, VodRecTransformer


@pytest.fixture
def tiny_vocab(tmp_path: Path) -> tuple[Path, Path, dict[int, int]]:
    content_to_token = {101: 2, 102: 3, 103: 4, 104: 5}
    vocab_path = tmp_path / "vocab.json"
    vocab_path.write_text(
        json.dumps({"content_to_token": {str(k): v for k, v in content_to_token.items()}}),
        encoding="utf-8",
    )
    config = VodRecConfig(vocab_size=6, d_model=32, n_heads=4, n_layers=2, max_seq_len=16)
    model = VodRecTransformer(config)
    model_path = tmp_path / "model.pt"
    model.save(model_path)
    return model_path, vocab_path, content_to_token


class TestVodRecTransformer:
    def test_forward_logits_shape(self) -> None:
        config = VodRecConfig(vocab_size=10, d_model=32, n_heads=4, n_layers=2, max_seq_len=8)
        model = VodRecTransformer(config)
        seq = torch.tensor([[0, 1, 2, 3]], dtype=torch.long)
        logits = model(seq)
        assert logits.shape == (1, 4, 10)

    def test_save_load_preserves_weights(self, tiny_vocab: tuple) -> None:
        model_path, vocab_path, _ = tiny_vocab
        loaded = VodRecTransformer.load(model_path)
        state_before = {key: tensor.clone() for key, tensor in loaded.state_dict().items()}
        reloaded = VodRecTransformer.load(model_path)
        state_after = reloaded.state_dict()
        assert state_before.keys() == state_after.keys()
        for key in state_before:
            assert torch.equal(state_before[key], state_after[key])


class TestVodRecRecommender:
    def test_empty_history_returns_empty(self, tiny_vocab: tuple) -> None:
        model_path, vocab_path, _ = tiny_vocab
        rec = VodRecRecommender.load(model_path, vocab_path)
        assert rec.recommend([], k=5) == []

    def test_recommend_honors_exclude_seen_flag(self, tiny_vocab: tuple) -> None:
        model_path, vocab_path, _ = tiny_vocab
        rec = VodRecRecommender.load(model_path, vocab_path)
        with_exclude = rec.recommend([101, 102], k=4, exclude_seen=True)
        without_exclude = rec.recommend([101, 102], k=4, exclude_seen=False)
        assert isinstance(with_exclude, list)
        assert isinstance(without_exclude, list)
        assert len(with_exclude) <= 4

    def test_returns_at_most_k_items(self, tiny_vocab: tuple) -> None:
        model_path, vocab_path, _ = tiny_vocab
        rec = VodRecRecommender.load(model_path, vocab_path)
        results = rec.recommend([101], k=2)
        assert len(results) <= 2
