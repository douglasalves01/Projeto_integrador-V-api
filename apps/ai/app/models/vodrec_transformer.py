"""VodRec-Transformer: Decoder-only Transformer construído em PyTorch puro para
next-item prediction sobre o catálogo VOD.

Este modulo NAO usa scikit-learn, NAO usa implicit, NAO usa transformers da
Hugging Face. Toda a arquitetura (multi-head attention, blocos transformer,
loop de inferencia) e implementada aqui.

Treine o modelo no notebook 06_vodrec_transformer.ipynb e carregue aqui via
`VodRecTransformer.load(path)`.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import torch
import torch.nn as nn
import torch.nn.functional as F

# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------


class MultiHeadSelfAttention(nn.Module):
    """Multi-head self-attention com causal masking e padding mask."""

    def __init__(self, d_model: int, n_heads: int, dropout: float = 0.1) -> None:
        super().__init__()
        if d_model % n_heads != 0:
            raise ValueError("d_model deve ser divisivel por n_heads")
        self.d_model = d_model
        self.n_heads = n_heads
        self.d_head = d_model // n_heads
        self.qkv = nn.Linear(d_model, 3 * d_model)
        self.proj = nn.Linear(d_model, d_model)
        self.dropout = nn.Dropout(dropout)

    def forward(
        self,
        x: torch.Tensor,
        attn_mask: torch.Tensor | None = None,
        key_padding_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        B, T, C = x.shape
        q, k, v = self.qkv(x).chunk(3, dim=-1)
        q = q.view(B, T, self.n_heads, self.d_head).transpose(1, 2)
        k = k.view(B, T, self.n_heads, self.d_head).transpose(1, 2)
        v = v.view(B, T, self.n_heads, self.d_head).transpose(1, 2)

        scores = (q @ k.transpose(-2, -1)) / math.sqrt(self.d_head)
        if attn_mask is not None:
            scores = scores.masked_fill(attn_mask == 0, float("-inf"))
        if key_padding_mask is not None:
            scores = scores.masked_fill(
                key_padding_mask.unsqueeze(1).unsqueeze(1), float("-inf")
            )

        attn = F.softmax(scores, dim=-1)
        # Quando uma query e padding, TODAS as suas keys validas podem estar
        # mascaradas (causal + key_padding combinados), gerando NaN. As saidas
        # dessas queries nao contam para a loss (ignore_index=pad), mas o NaN
        # propaga via backprop. Zerar e a forma correta e estavel.
        attn = torch.nan_to_num(attn, nan=0.0)
        attn = self.dropout(attn)
        out = attn @ v
        out = out.transpose(1, 2).contiguous().view(B, T, C)
        return self.proj(out)


class FeedForward(nn.Module):
    def __init__(self, d_model: int, d_ff: int | None = None, dropout: float = 0.1) -> None:
        super().__init__()
        d_ff = d_ff or 4 * d_model
        self.net = nn.Sequential(
            nn.Linear(d_model, d_ff),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(d_ff, d_model),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class TransformerBlock(nn.Module):
    """Bloco estilo GPT: pre-LayerNorm + residual."""

    def __init__(self, d_model: int, n_heads: int, dropout: float = 0.1) -> None:
        super().__init__()
        self.ln1 = nn.LayerNorm(d_model)
        self.attn = MultiHeadSelfAttention(d_model, n_heads, dropout)
        self.ln2 = nn.LayerNorm(d_model)
        self.ff = FeedForward(d_model, dropout=dropout)
        self.dropout = nn.Dropout(dropout)

    def forward(
        self,
        x: torch.Tensor,
        attn_mask: torch.Tensor | None = None,
        key_padding_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        x = x + self.dropout(self.attn(self.ln1(x), attn_mask, key_padding_mask))
        x = x + self.dropout(self.ff(self.ln2(x)))
        return x


# ---------------------------------------------------------------------------
# Main model
# ---------------------------------------------------------------------------


@dataclass
class VodRecConfig:
    vocab_size: int
    d_model: int = 128
    n_heads: int = 4
    n_layers: int = 4
    max_seq_len: int = 128
    dropout: float = 0.1
    pad_id: int = 0
    bos_id: int = 1

    @classmethod
    def from_dict(cls, d: dict) -> "VodRecConfig":
        keys = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in keys})

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}  # type: ignore[attr-defined]


class VodRecTransformer(nn.Module):
    """Decoder-only Transformer para recomendacao sequencial.

    Treine com next-item prediction (CE loss sobre logits shiftados).
    Os tokens 0 e 1 sao especiais (<pad>, <bos>).
    Os tokens 2..V+1 sao mapeamentos para content_ids do catalogo.
    """

    def __init__(self, config: VodRecConfig) -> None:
        super().__init__()
        self.config = config
        c = config

        self.item_emb = nn.Embedding(c.vocab_size, c.d_model, padding_idx=c.pad_id)
        self.pos_emb = nn.Embedding(c.max_seq_len, c.d_model)
        self.drop = nn.Dropout(c.dropout)
        self.blocks = nn.ModuleList(
            [TransformerBlock(c.d_model, c.n_heads, c.dropout) for _ in range(c.n_layers)]
        )
        self.ln_f = nn.LayerNorm(c.d_model)
        self.register_buffer(
            "causal_mask",
            torch.tril(torch.ones(c.max_seq_len, c.max_seq_len)).bool(),
        )
        self.apply(self._init_weights)

    def _init_weights(self, module: nn.Module) -> None:
        if isinstance(module, nn.Linear):
            nn.init.normal_(module.weight, std=0.02)
            if module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            nn.init.normal_(module.weight, std=0.02)

    def num_params(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    def forward(self, seq: torch.Tensor) -> torch.Tensor:
        """seq: (B, T) com token ids. Retorna logits (B, T, V) com tied embeddings."""
        B, T = seq.shape
        if T > self.config.max_seq_len:
            raise ValueError(f"Seq len {T} > max {self.config.max_seq_len}")

        positions = torch.arange(T, device=seq.device).unsqueeze(0).expand(B, T)
        x = self.item_emb(seq) + self.pos_emb(positions)
        x = self.drop(x)

        causal = self.causal_mask[:T, :T]
        key_padding_mask = seq == self.config.pad_id

        for block in self.blocks:
            x = block(x, causal, key_padding_mask)
        x = self.ln_f(x)
        logits = x @ self.item_emb.weight.T
        return logits

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {"model_state_dict": self.state_dict(), "config": self.config.to_dict()},
            path,
        )

    @classmethod
    def load(cls, path: str | Path, device: str | torch.device | None = None) -> "VodRecTransformer":
        path = Path(path)
        device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        ckpt = torch.load(path, map_location=device)
        config = VodRecConfig.from_dict(ckpt["config"])
        model = cls(config).to(device)
        model.load_state_dict(ckpt["model_state_dict"])
        model.eval()
        return model


# ---------------------------------------------------------------------------
# Inference helper
# ---------------------------------------------------------------------------


class VodRecRecommender:
    """Wrapper de inferencia sobre VodRecTransformer.

    Mantem o mapeamento content_id <-> token_id (vocab) e fornece o metodo
    `recommend(history_content_ids, k=20)` usado pelos endpoints.
    """

    def __init__(
        self,
        model: VodRecTransformer,
        content_to_token: dict[int, int],
        device: torch.device | str | None = None,
    ) -> None:
        self.model = model
        self.config = model.config
        self.content_to_token = {int(k): int(v) for k, v in content_to_token.items()}
        self.token_to_content = {v: k for k, v in self.content_to_token.items()}
        self.device = torch.device(device) if device else next(model.parameters()).device

    @classmethod
    def load(cls, model_path: str | Path, vocab_path: str | Path,
             device: str | torch.device | None = None) -> "VodRecRecommender":
        vocab_path = Path(vocab_path)
        with vocab_path.open() as f:
            vocab = json.load(f)
        content_to_token = {int(k): int(v) for k, v in vocab["content_to_token"].items()
                            if not k.startswith("<")}
        model = VodRecTransformer.load(model_path, device=device)
        return cls(model, content_to_token, device=device)

    # ------------------------------------------------------------------
    # Inference API
    # ------------------------------------------------------------------

    def _encode_history(self, history_content_ids: Sequence[int]) -> torch.Tensor:
        """Converte content_ids -> token_ids, prepend <bos>, pad a esquerda."""
        cfg = self.config
        tokens = [cfg.bos_id]
        for cid in history_content_ids:
            tok = self.content_to_token.get(int(cid))
            if tok is not None:
                tokens.append(tok)

        # trunca aos ultimos max_seq_len
        if len(tokens) > cfg.max_seq_len:
            tokens = tokens[-cfg.max_seq_len:]

        # pad a esquerda
        pad_len = cfg.max_seq_len - len(tokens)
        if pad_len > 0:
            tokens = [cfg.pad_id] * pad_len + tokens

        return torch.tensor([tokens], dtype=torch.long, device=self.device)

    @torch.no_grad()
    def recommend(
        self,
        history_content_ids: Sequence[int],
        k: int = 20,
        exclude_seen: bool = True,
        temperature: float = 1.0,
    ) -> list[tuple[int, float]]:
        """Retorna lista de (content_id, probabilidade) ordenada decrescentemente."""
        if not history_content_ids:
            return []

        x = self._encode_history(history_content_ids)
        logits = self.model(x)[0, -1] / max(temperature, 1e-6)

        # mascara tokens especiais
        logits[self.config.pad_id] = -1e9
        logits[self.config.bos_id] = -1e9

        if exclude_seen:
            for cid in history_content_ids:
                tok = self.content_to_token.get(int(cid))
                if tok is not None:
                    logits[tok] = -1e9

        probs = F.softmax(logits, dim=-1)
        # limita k ao numero de tokens validos
        k = min(k, probs.shape[0])
        topv, topi = torch.topk(probs, k=k)

        recs: list[tuple[int, float]] = []
        for tok, prob in zip(topi.tolist(), topv.tolist()):
            cid = self.token_to_content.get(int(tok))
            if cid is not None:
                recs.append((cid, float(prob)))
        return recs

    @torch.no_grad()
    def score_for_content(
        self,
        history_content_ids: Sequence[int],
        content_id: int,
    ) -> float:
        """Probabilidade de um content_id especifico ser o proximo."""
        x = self._encode_history(history_content_ids)
        logits = self.model(x)[0, -1]
        probs = F.softmax(logits, dim=-1)
        tok = self.content_to_token.get(int(content_id))
        if tok is None:
            return 0.0
        return float(probs[tok].item())
