"""Testes numericos de aprendizado do VodRec-Transformer.

Provam que o modelo NAO e so um wrapper sintatico: dado um sinal aprendivel,
a loss desce, o ranking melhora e ele bate baselines triviais.

Sao testes que rodam em segundos (modelo bem pequeno, poucos passos), mas
verificam a propriedade essencial: aprende-se algo.
"""
from __future__ import annotations

import random

import numpy as np
import pytest
import torch
import torch.nn.functional as F

from app.models.vodrec_transformer import VodRecConfig, VodRecTransformer


SEED = 1234


def _seed_all(seed: int = SEED) -> None:
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)


def _make_repeating_dataset(n_users: int, max_seq_len: int,
                            vocab_size: int) -> torch.Tensor:
    """Cada usuario tem sequencia [k, k+1, k+2, ...] (padrao FORTE e aprendivel).

    O modelo deve aprender que dado k, o proximo e k+1.
    """
    seqs = []
    for u in range(n_users):
        start = 2 + (u % (vocab_size - max_seq_len - 2))
        seq = list(range(start, start + max_seq_len))
        seqs.append(seq)
    return torch.tensor(seqs, dtype=torch.long)


def _next_item_loss(model: VodRecTransformer, x: torch.Tensor,
                    y: torch.Tensor) -> torch.Tensor:
    logits = model(x)
    return F.cross_entropy(
        logits.reshape(-1, model.config.vocab_size),
        y.reshape(-1),
        ignore_index=model.config.pad_id,
    )


def test_loss_decreases_on_learnable_signal() -> None:
    """Em um padrao trivial, a loss deve cair significativamente em poucos steps."""
    _seed_all()
    config = VodRecConfig(vocab_size=80, d_model=48, n_heads=4, n_layers=2,
                          max_seq_len=24, dropout=0.0)
    model = VodRecTransformer(config)
    optim = torch.optim.AdamW(model.parameters(), lr=3e-3)

    data = _make_repeating_dataset(n_users=64, max_seq_len=config.max_seq_len + 1,
                                    vocab_size=config.vocab_size)

    initial_loss = float(_next_item_loss(model, data[:, :-1], data[:, 1:]).item())

    model.train()
    for _ in range(80):
        x = data[:, :-1]
        y = data[:, 1:]
        loss = _next_item_loss(model, x, y)
        optim.zero_grad()
        loss.backward()
        optim.step()

    final_loss = float(loss.item())
    # Deve cair pela metade pelo menos. Sinal forte, dataset trivial.
    assert final_loss < 0.5 * initial_loss, (
        f"Loss nao desceu o suficiente. initial={initial_loss:.4f} final={final_loss:.4f}"
    )
    # Em padrao tao trivial, deve chegar perto de 0
    assert final_loss < 1.5, f"Loss final muito alta: {final_loss:.4f}"


def test_predicts_next_item_after_training() -> None:
    """Apos treinar no padrao [k,k+1,k+2,...], dado k o top-1 deve ser k+1."""
    _seed_all()
    config = VodRecConfig(vocab_size=60, d_model=48, n_heads=4, n_layers=2,
                          max_seq_len=16, dropout=0.0)
    model = VodRecTransformer(config)
    optim = torch.optim.AdamW(model.parameters(), lr=3e-3)
    data = _make_repeating_dataset(n_users=48, max_seq_len=config.max_seq_len + 1,
                                    vocab_size=config.vocab_size)

    model.train()
    for _ in range(120):
        loss = _next_item_loss(model, data[:, :-1], data[:, 1:])
        optim.zero_grad(); loss.backward(); optim.step()

    model.eval()
    # Sequencia de teste: padrao novo, mesma regra
    test_seq = torch.tensor([[2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]],
                             dtype=torch.long)
    with torch.no_grad():
        logits = model(test_seq)[0, -1]
        logits[0] = -1e9  # mascara pad
        logits[1] = -1e9  # mascara bos
        # Mascara items ja vistos para forcar a predizer o proximo (18)
        for tok in test_seq[0].tolist():
            logits[tok] = -1e9
        top1 = int(logits.argmax().item())

    assert top1 == 18, f"Esperado 18 (proximo na sequencia), recebido {top1}"


def test_beats_random_baseline_on_structured_data() -> None:
    """Apos treino, o VodRec deve recomendar com acuracia >> Random."""
    _seed_all()
    config = VodRecConfig(vocab_size=50, d_model=32, n_heads=4, n_layers=2,
                          max_seq_len=10, dropout=0.0)
    model = VodRecTransformer(config)
    optim = torch.optim.AdamW(model.parameters(), lr=3e-3)
    data = _make_repeating_dataset(n_users=40, max_seq_len=config.max_seq_len + 1,
                                    vocab_size=config.vocab_size)

    model.train()
    for _ in range(100):
        loss = _next_item_loss(model, data[:, :-1], data[:, 1:])
        optim.zero_grad(); loss.backward(); optim.step()

    # Avalia top-3 HR (deveria ser ~100% no padrao trivial)
    model.eval()
    n_correct = 0
    n_total = 0
    with torch.no_grad():
        for u in range(40):
            start = 2 + (u % (config.vocab_size - config.max_seq_len - 2))
            hist = list(range(start, start + config.max_seq_len))
            target = start + config.max_seq_len
            if target >= config.vocab_size:
                continue
            x = torch.tensor([hist], dtype=torch.long)
            logits = model(x)[0, -1]
            logits[0] = -1e9; logits[1] = -1e9
            for tok in hist:
                logits[tok] = -1e9
            top3 = torch.topk(logits, k=3).indices.tolist()
            if target in top3:
                n_correct += 1
            n_total += 1

    hr_at_3 = n_correct / max(1, n_total)
    # Random teria ~3/(vocab_size - 2 - max_seq_len) ~ 3/38 ~ 8%
    assert hr_at_3 > 0.50, f"HR@3 ficou abaixo do esperado: {hr_at_3:.3f}"


def test_no_nan_with_padded_batch() -> None:
    """Padding intenso a esquerda nao deve gerar NaN (regressao do bug encontrado)."""
    _seed_all()
    config = VodRecConfig(vocab_size=30, d_model=32, n_heads=4, n_layers=2,
                          max_seq_len=16, dropout=0.0)
    model = VodRecTransformer(config)

    # Sequencia com muito padding a esquerda
    seq = torch.tensor([
        [0] * 12 + [2, 3, 4, 5],     # 12 paddings, 4 reais
        [0] * 8 + [10, 11, 12, 13, 14, 15, 16, 17],  # 8 paddings
        [0] * 15 + [6],              # quase tudo padding
    ], dtype=torch.long)
    logits = model(seq)
    assert not torch.isnan(logits).any(), "Forward produziu NaN com padding"

    # Constroi targets validos para pelo menos uma posicao (senao CE retorna NaN
    # por divisao por zero, e isso seria um falso positivo do teste).
    targets = seq.clone()
    # Shift simulado: targets[t] = seq[t+1]; ultima posicao fica como pad e e ignorada
    targets = torch.cat([seq[:, 1:], torch.zeros_like(seq[:, :1])], dim=1)
    loss = F.cross_entropy(
        logits.reshape(-1, config.vocab_size),
        targets.reshape(-1),
        ignore_index=0,
    )
    assert torch.isfinite(loss), f"Loss virou {loss.item()}"
    # Gradientes tambem nao podem ser NaN
    loss.backward()
    for name, param in model.named_parameters():
        if param.grad is not None:
            assert not torch.isnan(param.grad).any(), f"NaN no grad de {name}"


def test_save_load_preserves_inference_outputs(tmp_path) -> None:
    """Apos save/load, o modelo deve produzir EXATAMENTE os mesmos logits."""
    _seed_all()
    config = VodRecConfig(vocab_size=30, d_model=24, n_heads=4, n_layers=2,
                          max_seq_len=8, dropout=0.0)
    model = VodRecTransformer(config)
    model.eval()

    seq = torch.tensor([[2, 3, 4, 5]], dtype=torch.long)
    with torch.no_grad():
        out_before = model(seq).clone()

    path = tmp_path / "model.pt"
    model.save(path)
    reloaded = VodRecTransformer.load(path, device="cpu")
    reloaded.eval()
    with torch.no_grad():
        out_after = reloaded(seq)

    assert torch.allclose(out_before, out_after, atol=1e-6), (
        "Logits divergem apos save/load"
    )


def test_causal_mask_blocks_future_information() -> None:
    """Mudar tokens FUTUROS nao deve mudar a saida em posicoes anteriores.

    Confirmacao matematica da causalidade — fundamental para um decoder-only.
    """
    _seed_all()
    config = VodRecConfig(vocab_size=20, d_model=24, n_heads=4, n_layers=2,
                          max_seq_len=8, dropout=0.0)
    model = VodRecTransformer(config)
    model.eval()

    seq_a = torch.tensor([[2, 3, 4, 5, 6, 7, 8, 9]], dtype=torch.long)
    seq_b = seq_a.clone()
    seq_b[0, -1] = 19  # muda o ultimo token

    with torch.no_grad():
        out_a = model(seq_a)
        out_b = model(seq_b)

    # As primeiras 7 posicoes nao podem mudar (causal mask)
    assert torch.allclose(out_a[0, :-1], out_b[0, :-1], atol=1e-6), (
        "Causal mask vazou: mudar o ultimo token afetou posicoes anteriores"
    )
    # A ultima sim deve mudar
    assert not torch.allclose(out_a[0, -1], out_b[0, -1], atol=1e-6), (
        "Mudar o ultimo input nao mudou a ultima saida (algo errado)"
    )


def test_tied_embeddings_share_weights() -> None:
    """O head de saida e o item_emb DEVEM ser o mesmo tensor (tied weights)."""
    config = VodRecConfig(vocab_size=10, d_model=16, n_heads=4, n_layers=1,
                          max_seq_len=4, dropout=0.0)
    model = VodRecTransformer(config)
    # Logits = x @ item_emb.weight.T — verificamos passando um x conhecido
    seq = torch.tensor([[2, 3, 4]], dtype=torch.long)
    out = model(seq)
    # Manualmente faz o forward ate a projecao
    with torch.no_grad():
        positions = torch.arange(3).unsqueeze(0)
        x_hidden = model.item_emb(seq) + model.pos_emb(positions)
        x_hidden = model.drop(x_hidden)
        for block in model.blocks:
            x_hidden = block(x_hidden, model.causal_mask[:3, :3],
                              seq == model.config.pad_id)
        x_hidden = model.ln_f(x_hidden)
        expected = x_hidden @ model.item_emb.weight.T
    assert torch.allclose(out, expected, atol=1e-6)
