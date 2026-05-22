"""Treino offline do VodRec-Transformer (CLI).

Replica o que o notebook 06 faz, mas em modo batch (ex: cron diario, GitHub
Action de re-treino).

Uso:
    python scripts/train_vodrec.py \
        --interactions data/interactions.parquet \
        --output-dir models/vodrec \
        --epochs 15 \
        --d-model 128 \
        --n-layers 4
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm

# permitir rodar como script standalone OU como modulo
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.vodrec_transformer import VodRecConfig, VodRecTransformer  # noqa: E402


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------


class NextItemDataset(Dataset):
    def __init__(self, sequences: dict[int, list[int]], max_seq_len: int,
                 stride: int = 32, pad_id: int = 0, bos_id: int = 1) -> None:
        self.max_seq_len = max_seq_len
        self.pad_id = pad_id
        self.bos_id = bos_id
        self.examples: list[list[int]] = []
        for seq in sequences.values():
            seq = [bos_id] + seq
            if len(seq) <= max_seq_len + 1:
                self.examples.append(seq)
            else:
                for start in range(0, len(seq) - max_seq_len, stride):
                    self.examples.append(seq[start:start + max_seq_len + 1])

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        seq = self.examples[idx]
        if len(seq) < self.max_seq_len + 1:
            seq = [self.pad_id] * (self.max_seq_len + 1 - len(seq)) + seq
        seq_t = torch.tensor(seq, dtype=torch.long)
        return seq_t[:-1], seq_t[1:]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def build_sequences(
    interactions_df: pd.DataFrame,
    min_rating: float = 0.4,
    min_seq_len: int = 3,
) -> tuple[dict[int, list[int]], dict[int, int]]:
    """Constroi sequencias por usuario e vocab (content_id -> token_id)."""
    pos = interactions_df[interactions_df["rating_implicit"] >= min_rating].copy()
    pos = pos.sort_values(["user_id", "started_at"])

    # Vocab: token 0 = <pad>, token 1 = <bos>, tokens 2..V+1 = content_ids
    all_content_ids = sorted(pos["content_id"].unique().tolist())
    content_to_token = {cid: i + 2 for i, cid in enumerate(all_content_ids)}

    sequences = (
        pos.groupby("user_id")["content_id"]
        .apply(lambda s: [content_to_token[c] for c in s.tolist()])
        .to_dict()
    )
    sequences = {u: s for u, s in sequences.items() if len(s) >= min_seq_len}
    return sequences, content_to_token


def lr_lambda(step: int, warmup: int, total: int) -> float:
    if step < warmup:
        return step / max(1, warmup)
    progress = (step - warmup) / max(1, total - warmup)
    return 0.5 * (1 + math.cos(math.pi * progress))


@torch.no_grad()
def evaluate_hr(model: VodRecTransformer, sequences: dict[int, list[int]],
                targets: dict[int, int], device: torch.device, k: int = 10,
                max_users: int = 500) -> tuple[float, float]:
    model.eval()
    hr, ndcg, n = 0, 0.0, 0
    cfg = model.config
    uids = list(targets.keys())[:max_users]
    for uid in uids:
        history = sequences.get(uid)
        target = targets[uid]
        if not history:
            continue
        seq = [cfg.bos_id] + history[-(cfg.max_seq_len - 1):]
        if len(seq) < cfg.max_seq_len:
            seq = [cfg.pad_id] * (cfg.max_seq_len - len(seq)) + seq
        x = torch.tensor([seq[-cfg.max_seq_len:]], dtype=torch.long, device=device)
        logits = model(x)[0, -1]
        logits[cfg.pad_id] = -1e9
        logits[cfg.bos_id] = -1e9
        for tok in history:
            logits[tok] = -1e9
        topk = torch.topk(logits, k=k).indices.tolist()
        if target in topk:
            hr += 1
            rank = topk.index(target)
            ndcg += 1.0 / math.log2(rank + 2)
        n += 1
    return hr / max(1, n), ndcg / max(1, n)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Treina VodRec-Transformer.")
    p.add_argument("--interactions", type=str, required=True,
                   help="parquet com colunas user_id, content_id, started_at, rating_implicit")
    p.add_argument("--output-dir", type=str, default="models/vodrec")
    p.add_argument("--d-model", type=int, default=128)
    p.add_argument("--n-heads", type=int, default=4)
    p.add_argument("--n-layers", type=int, default=4)
    p.add_argument("--max-seq-len", type=int, default=128)
    p.add_argument("--dropout", type=float, default=0.1)
    p.add_argument("--batch-size", type=int, default=256)
    p.add_argument("--epochs", type=int, default=15)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--weight-decay", type=float, default=0.01)
    p.add_argument("--warmup-steps", type=int, default=500)
    p.add_argument("--label-smoothing", type=float, default=0.1)
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Carregando interacoes de {args.interactions}")
    df = pd.read_parquet(args.interactions)
    print(f"  {len(df)} interacoes")

    sequences, content_to_token = build_sequences(df)
    vocab_size = len(content_to_token) + 2  # +2 para <pad> e <bos>
    print(f"  Vocab: {vocab_size} | Usuarios: {len(sequences)}")

    # split temporal por usuario
    train_seq, test_targets = {}, {}
    for uid, seq in sequences.items():
        n_test = max(1, int(len(seq) * 0.2))
        train_seq[uid] = seq[:-n_test]
        test_targets[uid] = seq[-1]

    # salva vocab
    with (out_dir / "vocab.json").open("w") as f:
        json.dump({
            "special_tokens": {"<pad>": 0, "<bos>": 1},
            "content_to_token": {str(k): v for k, v in content_to_token.items()},
        }, f, indent=2)

    config = VodRecConfig(
        vocab_size=vocab_size,
        d_model=args.d_model,
        n_heads=args.n_heads,
        n_layers=args.n_layers,
        max_seq_len=args.max_seq_len,
        dropout=args.dropout,
    )
    model = VodRecTransformer(config).to(device)
    print(f"Modelo: {model.num_params():,} parametros")

    ds = NextItemDataset(train_seq, args.max_seq_len)
    loader = DataLoader(ds, batch_size=args.batch_size, shuffle=True,
                        num_workers=2, pin_memory=(device.type == "cuda"))

    total_steps = len(loader) * args.epochs
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr,
                                  weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lambda s: lr_lambda(s, args.warmup_steps, total_steps)
    )

    best_hr = 0.0
    best_path = out_dir / "model.pt"

    for epoch in range(1, args.epochs + 1):
        model.train()
        total = 0.0
        pbar = tqdm(loader, desc=f"Epoch {epoch}/{args.epochs}")
        for x, y in pbar:
            x = x.to(device, non_blocking=True)
            y = y.to(device, non_blocking=True)
            logits = model(x)
            loss = F.cross_entropy(
                logits.reshape(-1, vocab_size),
                y.reshape(-1),
                ignore_index=config.pad_id,
                label_smoothing=args.label_smoothing,
            )
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            total += loss.item()
            pbar.set_postfix(loss=f"{loss.item():.3f}")

        hr, ndcg = evaluate_hr(model, train_seq, test_targets, device, k=10)
        print(f"  loss={total/len(loader):.4f}  HR@10={hr:.4f}  NDCG@10={ndcg:.4f}")

        if hr > best_hr:
            best_hr = hr
            model.save(best_path)
            print(f"  -> Salvou checkpoint (best HR@10 = {hr:.4f})")

    # versao + metricas
    (out_dir / "VERSION.txt").write_text("vodrec-v1.0.0")
    (out_dir / "metrics.json").write_text(
        json.dumps({"hr10": best_hr, "vocab_size": vocab_size,
                    "parameters": model.num_params()}, indent=2)
    )
    print(f"\nMelhor HR@10: {best_hr:.4f}  | salvo em {best_path}")


if __name__ == "__main__":
    main()
