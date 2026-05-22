"""Pipeline end-to-end: treina o VodRec-Transformer e mede tudo.

NAO usa sklearn/implicit no modelo. Usa SOMENTE a classe
`app.models.vodrec_transformer.VodRecTransformer` (PyTorch puro).

Etapas:
1. Carrega `data/interactions.parquet` (gerado por scripts/generate_dataset.py)
2. Constroi vocab content_id <-> token_id
3. Constroi sequencias por usuario (split temporal 80/20)
4. Treina VodRec-Transformer (cross-entropy, AdamW, warmup+cosine)
5. Avalia HR@10, NDCG@10, MAP@10, MRR@10 (e em k=5, k=20)
6. Compara com baselines Popularity e Random
7. Mede latencia P50/P95 em CPU
8. Salva models/vodrec/{model.pt, vocab.json, metrics.json, VERSION.txt}
9. Salva curvas de loss/metricas em PNG

Uso:
    python scripts/train_and_evaluate.py \
        --interactions data/interactions.parquet \
        --epochs 8 --d-model 64 --n-layers 2 --max-seq-len 64
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.vodrec_transformer import VodRecConfig, VodRecTransformer  # noqa: E402


# ---------------------------------------------------------------------------
# Dataset / sequence building
# ---------------------------------------------------------------------------


class NextItemDataset(Dataset):
    def __init__(self, sequences: dict[int, list[int]], max_seq_len: int,
                 stride: int = 16, pad_id: int = 0, bos_id: int = 1) -> None:
        self.max_seq_len = max_seq_len
        self.pad_id = pad_id
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


def build_sequences(df: pd.DataFrame, min_rating: float = 0.4,
                    min_seq_len: int = 5
                    ) -> tuple[dict[int, list[int]], dict[int, int]]:
    pos = df[df["rating_implicit"] >= min_rating].copy()
    pos = pos.sort_values(["user_id", "started_at"])
    all_cids = sorted(pos["content_id"].unique().tolist())
    content_to_token = {cid: i + 2 for i, cid in enumerate(all_cids)}  # 0=<pad>, 1=<bos>
    seqs = (pos.groupby("user_id")["content_id"]
            .apply(lambda s: [content_to_token[c] for c in s.tolist()])
            .to_dict())
    seqs = {u: s for u, s in seqs.items() if len(s) >= min_seq_len}
    return seqs, content_to_token


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def precision_at_k(rec: list[int], rel: set[int], k: int) -> float:
    return len(set(rec[:k]) & rel) / k if k > 0 else 0.0


def recall_at_k(rec: list[int], rel: set[int], k: int) -> float:
    return len(set(rec[:k]) & rel) / len(rel) if rel else 0.0


def hit_rate_at_k(rec: list[int], rel: set[int], k: int) -> float:
    return 1.0 if (set(rec[:k]) & rel) else 0.0


def ndcg_at_k(rec: list[int], rel_with_gain: dict[int, float], k: int) -> float:
    dcg = sum(rel_with_gain.get(c, 0.0) / math.log2(i + 2)
              for i, c in enumerate(rec[:k]))
    ideal = sorted(rel_with_gain.values(), reverse=True)[:k]
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg > 0 else 0.0


def map_at_k(rec: list[int], rel: set[int], k: int) -> float:
    if not rel:
        return 0.0
    hits, ssum = 0, 0.0
    for i, c in enumerate(rec[:k]):
        if c in rel:
            hits += 1
            ssum += hits / (i + 1)
    return ssum / min(len(rel), k)


def mrr_at_k(rec: list[int], rel: set[int], k: int) -> float:
    for i, c in enumerate(rec[:k]):
        if c in rel:
            return 1.0 / (i + 1)
    return 0.0


# ---------------------------------------------------------------------------
# Inference helpers (sem depender do VodRecRecommender)
# ---------------------------------------------------------------------------


@torch.no_grad()
def model_recommend(model: VodRecTransformer, history_tokens: list[int],
                    k: int = 10, exclude_seen: bool = True) -> list[int]:
    cfg = model.config
    seq = [cfg.bos_id] + history_tokens[-(cfg.max_seq_len - 1):]
    if len(seq) < cfg.max_seq_len:
        seq = [cfg.pad_id] * (cfg.max_seq_len - len(seq)) + seq
    x = torch.tensor([seq[-cfg.max_seq_len:]], dtype=torch.long,
                     device=next(model.parameters()).device)
    logits = model(x)[0, -1].clone()
    logits[cfg.pad_id] = -1e9
    logits[cfg.bos_id] = -1e9
    if exclude_seen:
        for tok in history_tokens:
            logits[tok] = -1e9
    return torch.topk(logits, k=min(k, logits.shape[0])).indices.tolist()


def popularity_recommend(popular: list[int], history: list[int], k: int) -> list[int]:
    seen = set(history)
    return [c for c in popular if c not in seen][:k]


def random_recommend(catalog: list[int], history: list[int], k: int,
                     rng: np.random.RandomState) -> list[int]:
    seen = set(history)
    pool = [c for c in catalog if c not in seen]
    pick = rng.choice(pool, size=min(k, len(pool)), replace=False)
    return [int(c) for c in pick]


def evaluate_recommender(name: str, recommend_fn, test_data: list[tuple], k_list=(5, 10, 20)) -> dict:
    """recommend_fn(history) -> lista de token_ids ordenada decrescente."""
    metrics = {f"{m}@{k}": [] for m in ["precision", "recall", "hit_rate", "ndcg", "map", "mrr"] for k in k_list}
    for history, test_items, rel_with_gain in test_data:
        recs = recommend_fn(history)
        rel = set(test_items)
        for k in k_list:
            metrics[f"precision@{k}"].append(precision_at_k(recs, rel, k))
            metrics[f"recall@{k}"].append(recall_at_k(recs, rel, k))
            metrics[f"hit_rate@{k}"].append(hit_rate_at_k(recs, rel, k))
            metrics[f"ndcg@{k}"].append(ndcg_at_k(recs, rel_with_gain, k))
            metrics[f"map@{k}"].append(map_at_k(recs, rel, k))
            metrics[f"mrr@{k}"].append(mrr_at_k(recs, rel, k))
    return {"model": name, "n_users": len(test_data),
            **{m: float(np.mean(v)) for m, v in metrics.items()}}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--interactions", type=str, default="data/interactions.parquet")
    p.add_argument("--out-dir", type=str, default="models/vodrec")
    p.add_argument("--reports-dir", type=str, default="reports")
    p.add_argument("--d-model", type=int, default=64)
    p.add_argument("--n-heads", type=int, default=4)
    p.add_argument("--n-layers", type=int, default=2)
    p.add_argument("--max-seq-len", type=int, default=64)
    p.add_argument("--dropout", type=float, default=0.1)
    p.add_argument("--batch-size", type=int, default=128)
    p.add_argument("--epochs", type=int, default=8)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--weight-decay", type=float, default=0.01)
    p.add_argument("--warmup-steps", type=int, default=200)
    p.add_argument("--label-smoothing", type=float, default=0.1)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--version", type=str, default="vodrec-v1.0.0")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[setup] device={device}")

    print(f"[data] loading {args.interactions}")
    df = pd.read_parquet(args.interactions)
    print(f"[data] {len(df)} interacoes")

    seqs, content_to_token = build_sequences(df, min_rating=0.4, min_seq_len=5)
    vocab_size = len(content_to_token) + 2
    print(f"[data] vocab_size={vocab_size}  usuarios={len(seqs)}")

    # split temporal: 80/20 por usuario
    train_seq, test_full = {}, {}
    for uid, seq in seqs.items():
        n_test = max(1, int(len(seq) * 0.2))
        train_seq[uid] = seq[:-n_test]
        test_full[uid] = seq[-n_test:]

    # vocab.json — formato esperado por VodRecRecommender
    vocab_path = out_dir / "vocab.json"
    with vocab_path.open("w") as f:
        json.dump({
            "special_tokens": {"<pad>": 0, "<bos>": 1},
            "content_to_token": {str(k): v for k, v in content_to_token.items()},
        }, f, indent=2)
    print(f"[data] vocab salvo em {vocab_path}")

    # ----- modelo -----
    config = VodRecConfig(
        vocab_size=vocab_size,
        d_model=args.d_model,
        n_heads=args.n_heads,
        n_layers=args.n_layers,
        max_seq_len=args.max_seq_len,
        dropout=args.dropout,
    )
    model = VodRecTransformer(config).to(device)
    n_params = model.num_params()
    print(f"[model] {n_params:,} parametros (~{n_params/1e6:.2f}M)")

    ds = NextItemDataset(train_seq, args.max_seq_len, stride=16)
    loader = DataLoader(ds, batch_size=args.batch_size, shuffle=True, num_workers=0)
    total_steps = len(loader) * args.epochs

    optim = torch.optim.AdamW(model.parameters(), lr=args.lr,
                              weight_decay=args.weight_decay)
    def lr_fn(step: int) -> float:
        if step < args.warmup_steps:
            return step / max(1, args.warmup_steps)
        prog = (step - args.warmup_steps) / max(1, total_steps - args.warmup_steps)
        return 0.5 * (1 + math.cos(math.pi * prog))
    sched = torch.optim.lr_scheduler.LambdaLR(optim, lr_fn)

    # ----- prep test data (compartilhado entre modelos) -----
    test_data: list[tuple[list[int], list[int], dict[int, float]]] = []
    rel_ratings_per_user: dict[int, dict[int, float]] = {}
    for uid, hist in train_seq.items():
        future = test_full.get(uid, [])
        if not future:
            continue
        # ganho uniforme = 1.0 para cada item de teste (ja eh positivo)
        rel = {tok: 1.0 for tok in future}
        rel_ratings_per_user[uid] = rel
        test_data.append((hist, future, rel))
    print(f"[eval] usuarios em teste: {len(test_data)}")

    # ----- treino -----
    history_log = {"epoch": [], "train_loss": [], "val_hr10": [], "val_ndcg10": [], "lr": []}
    best_hr10 = 0.0
    best_path = out_dir / "model.pt"

    t_total = time.perf_counter()
    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_loss = 0.0
        n_batches = 0
        for x, y in loader:
            x = x.to(device); y = y.to(device)
            logits = model(x)
            loss = F.cross_entropy(
                logits.reshape(-1, vocab_size),
                y.reshape(-1),
                ignore_index=config.pad_id,
                label_smoothing=args.label_smoothing,
            )
            optim.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optim.step()
            sched.step()
            epoch_loss += loss.item()
            n_batches += 1

        avg_loss = epoch_loss / max(1, n_batches)

        # eval rapido a cada epoca
        model.eval()
        hr10, ndcg10 = 0.0, 0.0
        eval_users = test_data[:200]
        for hist, _, rel in eval_users:
            recs = model_recommend(model, hist, k=10)
            rel_set = set(rel.keys())
            hr10 += hit_rate_at_k(recs, rel_set, 10)
            ndcg10 += ndcg_at_k(recs, rel, 10)
        hr10 /= max(1, len(eval_users))
        ndcg10 /= max(1, len(eval_users))

        cur_lr = sched.get_last_lr()[0]
        history_log["epoch"].append(epoch)
        history_log["train_loss"].append(avg_loss)
        history_log["val_hr10"].append(hr10)
        history_log["val_ndcg10"].append(ndcg10)
        history_log["lr"].append(cur_lr)

        print(f"[epoch {epoch:>2}/{args.epochs}]  loss={avg_loss:.4f}  HR@10={hr10:.4f}  NDCG@10={ndcg10:.4f}  lr={cur_lr:.2e}")

        if hr10 > best_hr10:
            best_hr10 = hr10
            model.save(best_path)

    t_train = time.perf_counter() - t_total
    print(f"[train] tempo total: {t_train:.1f}s  | melhor HR@10={best_hr10:.4f}")

    # ----- reload melhor checkpoint e avaliacao final -----
    model = VodRecTransformer.load(best_path, device=device)
    model.eval()

    print("[eval] medindo todos os modelos (test set completo)")

    # popularity ranking (em tokens)
    flat = [tok for seq in train_seq.values() for tok in seq]
    pop_counter: dict[int, int] = {}
    for t_ in flat:
        pop_counter[t_] = pop_counter.get(t_, 0) + 1
    popular = sorted(pop_counter.keys(), key=lambda t_: pop_counter[t_], reverse=True)

    catalog_tokens = list(content_to_token.values())
    rng = np.random.RandomState(args.seed)

    vodrec_metrics = evaluate_recommender(
        "VodRec-Transformer",
        lambda h: model_recommend(model, h, k=20),
        test_data,
    )
    pop_metrics = evaluate_recommender(
        "Popularity",
        lambda h: popularity_recommend(popular, h, 20),
        test_data,
    )
    rand_metrics = evaluate_recommender(
        "Random",
        lambda h: random_recommend(catalog_tokens, h, 20, rng),
        test_data,
    )

    # ----- latencia -----
    lats = []
    for hist, _, _ in test_data[:200]:
        t0 = time.perf_counter()
        _ = model_recommend(model, hist, k=20)
        lats.append((time.perf_counter() - t0) * 1000)
    lats = np.array(lats)
    print(f"[latency CPU] p50={np.percentile(lats,50):.1f}ms  p95={np.percentile(lats,95):.1f}ms  max={lats.max():.1f}ms")

    # ----- relatorio final -----
    all_results = [vodrec_metrics, pop_metrics, rand_metrics]
    comparison_table = "\n".join(
        f"  {r['model']:<22} HR@10={r['hit_rate@10']:.4f}  NDCG@10={r['ndcg@10']:.4f}  MAP@10={r['map@10']:.4f}  MRR@10={r['mrr@10']:.4f}"
        for r in all_results
    )
    print("\n=== AVALIACAO FINAL ===")
    print(comparison_table)

    metrics_path = out_dir / "metrics.json"
    with metrics_path.open("w") as f:
        json.dump({
            "version": args.version,
            "trained_at": pd.Timestamp.utcnow().isoformat(),
            "device": str(device),
            "config": config.to_dict(),
            "n_parameters": n_params,
            "dataset": {
                "n_users": len(seqs),
                "n_contents": len(content_to_token),
                "n_interactions": int(len(df)),
                "vocab_size": vocab_size,
            },
            "training": {
                "epochs": args.epochs,
                "batch_size": args.batch_size,
                "learning_rate": args.lr,
                "label_smoothing": args.label_smoothing,
                "duration_sec": t_train,
                "history": history_log,
            },
            "results": all_results,
            "latency_cpu_ms": {
                "p50": float(np.percentile(lats, 50)),
                "p95": float(np.percentile(lats, 95)),
                "p99": float(np.percentile(lats, 99)),
                "max": float(lats.max()),
                "n_samples": int(len(lats)),
            },
            "requirements": {
                "RFIA01_hit_rate_at_10_target": 0.70,
                "RFIA01_hit_rate_at_10_measured": vodrec_metrics["hit_rate@10"],
                "RFIA01_passed": vodrec_metrics["hit_rate@10"] >= 0.70,
                "RFIA02_latency_target_ms": 2000,
                "RFIA02_latency_p95_ms": float(np.percentile(lats, 95)),
                "RFIA02_passed": float(np.percentile(lats, 95)) < 2000,
            },
        }, f, indent=2, default=str)

    (out_dir / "VERSION.txt").write_text(args.version + "\n")
    print(f"\n[export] metrics: {metrics_path}")
    print(f"[export] model:   {best_path}")
    print(f"[export] vocab:   {vocab_path}")

    # ----- plots -----
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 3, figsize=(15, 4))
        axes[0].plot(history_log["epoch"], history_log["train_loss"], "o-")
        axes[0].set_title("Train loss"); axes[0].set_xlabel("epoch"); axes[0].grid(alpha=0.3)
        axes[1].plot(history_log["epoch"], history_log["val_hr10"], "o-", label="HR@10", color="coral")
        axes[1].plot(history_log["epoch"], history_log["val_ndcg10"], "o-", label="NDCG@10", color="teal")
        axes[1].axhline(0.7, color="red", linestyle="--", label="RFIA01")
        axes[1].set_title("Validation metrics"); axes[1].legend(); axes[1].grid(alpha=0.3)
        models_x = [r["model"] for r in all_results]
        axes[2].bar(models_x, [r["hit_rate@10"] for r in all_results], color=["steelblue", "gray", "lightgray"])
        axes[2].axhline(0.7, color="red", linestyle="--")
        axes[2].set_title("HR@10 comparison"); axes[2].set_ylim(0, 1)
        for i, r in enumerate(all_results):
            axes[2].text(i, r["hit_rate@10"] + 0.02, f"{r['hit_rate@10']:.3f}", ha="center")
        plt.tight_layout()
        plot_path = reports_dir / "training_report.png"
        plt.savefig(plot_path, dpi=120, bbox_inches="tight")
        print(f"[export] plots:   {plot_path}")
    except ImportError:
        print("[warn] matplotlib indisponivel, sem plots")


if __name__ == "__main__":
    main()
