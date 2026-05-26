"""Gera interacoes sinteticas SOBRE o catalogo real (49 videos brasileiros).

Diferenca para `generate_dataset.py`:
- NAO inventa videos — usa o `contents.parquet` gerado por ingest_real_dataset.py
- Bias por categoria primaria (genres[0])
- Cada usuario tem 1-2 categorias favoritas e ~30-60 interacoes
- Preserva ordem temporal

Saida: data/interactions.parquet + data/users.parquet
"""
from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--contents-in", default="data/contents.parquet")
    p.add_argument("--out-dir", default="data")
    p.add_argument("--n-users", type=int, default=800)
    p.add_argument("--avg-interactions", type=int, default=40)
    p.add_argument("--std-interactions", type=int, default=12)
    p.add_argument("--fav-bias", type=float, default=0.85)
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)

    contents_df = pd.read_parquet(args.contents_in)
    contents_df["primary_category"] = contents_df["genres"].apply(lambda g: g[0])

    cat_to_cids: dict[str, list[int]] = {}
    for _, r in contents_df.iterrows():
        cat_to_cids.setdefault(r["primary_category"], []).append(int(r["content_id"]))

    categories = sorted(cat_to_cids.keys())
    print(f"[gen] {len(contents_df)} videos em {len(categories)} categorias: {categories}")

    base_time = datetime(2025, 1, 1)
    interactions = []

    for uid in range(1, args.n_users + 1):
        # Cada usuario tem 1 ou 2 categorias favoritas
        n_fav = random.choice([1, 2, 2])
        # Categorias com poucos itens (Educacao=1, Arte=2) viram favoritas menos
        # frequentemente para evitar dataset enviesado para minorias.
        weights = [len(cat_to_cids[c]) for c in categories]
        favs = random.choices(categories, weights=weights, k=n_fav)
        favs = list(dict.fromkeys(favs))  # remove duplicates preservando ordem

        n_int = max(5, int(np.random.normal(args.avg_interactions,
                                              args.std_interactions)))
        seen: set[int] = set()

        for t in range(n_int):
            # `fav_bias`% chance de vir do favorito; o resto descoberta
            if random.random() < args.fav_bias:
                cat = random.choice(favs)
                pool = cat_to_cids[cat]
            else:
                pool = contents_df["content_id"].tolist()

            unseen = [c for c in pool if c not in seen]
            if not unseen:
                # quando esgotar o favorito, abre para todo o catalogo
                unseen = [c for c in contents_df["content_id"] if c not in seen]
                if not unseen:
                    break

            cid = random.choice(unseen)
            seen.add(cid)

            row = contents_df.loc[contents_df.content_id == cid].iloc[0]
            is_fav = row["primary_category"] in favs
            # completion bem maior para favoritos
            completion = float(np.clip(
                np.random.beta(8 if is_fav else 2, 2 if is_fav else 4),
                0.0, 1.0,
            ))
            duration = int(row["duration_sec"]) or 600
            watched = int(completion * duration)
            started_at = base_time + timedelta(days=uid * 5 + t,
                                                 minutes=random.randint(0, 1440))
            finished = 1 if completion > 0.9 else 0
            rating_implicit = float(np.clip(
                0.6 * completion + 0.1 * finished, 0.0, 1.0
            ))
            interactions.append({
                "user_id": uid,
                "content_id": int(cid),
                "watched_sec": watched,
                "total_sec": duration,
                "completion": round(completion, 4),
                "finished": finished,
                "rating_implicit": rating_implicit,
                "started_at": started_at,
            })

    interactions_df = pd.DataFrame(interactions)
    users_df = pd.DataFrame({"user_id": list(range(1, args.n_users + 1))})

    out_dir = Path(args.out_dir)
    interactions_df.to_parquet(out_dir / "interactions.parquet", index=False)
    users_df.to_parquet(out_dir / "users.parquet", index=False)

    pos = (interactions_df["rating_implicit"] >= 0.4).mean()
    print()
    print(f"[gen] interacoes: {len(interactions_df):,}")
    print(f"      usuarios:   {users_df.shape[0]:,}")
    print(f"      views/user mean: {interactions_df.groupby('user_id').size().mean():.1f}")
    print(f"      positivas (>=0.4): {pos*100:.1f}%")
    print(f"      saved: {out_dir/'interactions.parquet'}")


if __name__ == "__main__":
    main()
