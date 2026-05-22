"""Gera um dataset sintetico realista para treinar/avaliar o VodRec-Transformer.

Modelo do mundo simulado:
- Cada usuario tem 1..3 generos favoritos. 70% das interacoes vem deles,
  30% sao descoberta aleatoria.
- Conteudos favoritos sao assistidos com completion alto (Beta(8,2)); itens
  fora do gosto, baixo (Beta(2,4)).
- Sequencia temporal preservada (started_at crescente por usuario).

Saidas (em data/):
- contents.parquet     : catalogo (content_id, title, description, genres, ...)
- users.parquet        : usuarios (sem PII; _fav_genres descartado no final)
- interactions.parquet : interacoes (user_id, content_id, started_at,
                                     completion, rating_implicit, ...)

Uso:
    python scripts/generate_dataset.py --n-users 2000 --n-contents 1500 \
        --avg-interactions 40 --seed 42 --out-dir data
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np
import pandas as pd


GENRES = [
    "Acao", "Aventura", "Comedia", "Drama", "FiccaoCientifica", "Terror",
    "Suspense", "Romance", "Documentario", "Animacao", "Fantasia", "Crime",
    "Misterio", "Historico", "Musical",
]
CATEGORIES = ["Filme", "Serie", "Documentario", "Curta"]
TITLE_WORDS = [
    "Vinganca", "Sombra", "Coracao", "Lua", "Cidade", "Imperio", "Cacador",
    "Estrela", "Reino", "Destino", "Eclipse", "Tormenta", "Ultima", "Primeira",
    "Lenda", "Cronica", "Segredo", "Promessa", "Aurora", "Crepusculo", "Inverno",
    "Verao", "Caminho", "Heroi", "Vilao", "Anjo", "Demonio", "Profecia",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--n-users", type=int, default=2000)
    p.add_argument("--n-contents", type=int, default=1500)
    p.add_argument("--avg-interactions", type=int, default=40)
    p.add_argument("--std-interactions", type=int, default=15)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out-dir", type=str, default="data")
    p.add_argument("--fav-bias", type=float, default=0.70,
                   help="Probabilidade de uma interacao vir do genero favorito (0..1)")
    return p.parse_args()


def generate(args: argparse.Namespace) -> None:
    random.seed(args.seed)
    np.random.seed(args.seed)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ----- CONTENTS -----
    contents = []
    for cid in range(1, args.n_contents + 1):
        n_g = random.choices([1, 2, 3], weights=[0.3, 0.5, 0.2])[0]
        genres = random.sample(GENRES, n_g)
        cat = random.choice(CATEGORIES)
        title = " ".join(random.sample(TITLE_WORDS, random.randint(2, 4)))
        contents.append({
            "content_id": cid,
            "title": title,
            "description": f"Sinopse de {title} no genero {' '.join(genres)}.",
            "duration_sec": random.choice([1800, 2700, 3600, 5400, 7200]),
            "release_year": random.randint(1990, 2025),
            "genres": genres,
            "categories": [cat],
        })
    contents_df = pd.DataFrame(contents)

    # Mapa: genero -> lista de content_ids
    genre_to_cids: dict[str, list[int]] = {g: [] for g in GENRES}
    for _, row in contents_df.iterrows():
        for g in row["genres"]:
            genre_to_cids[g].append(int(row["content_id"]))

    # ----- USERS + INTERACTIONS -----
    users = []
    interactions = []
    base_time = pd.Timestamp("2025-01-01")

    for uid in range(1, args.n_users + 1):
        n_fav = random.choices([1, 2, 3], weights=[0.2, 0.6, 0.2])[0]
        fav_genres = random.sample(GENRES, n_fav)

        users.append({"user_id": uid, "_fav_genres": fav_genres})

        n_int = max(3, int(np.random.normal(args.avg_interactions, args.std_interactions)))
        seen: set[int] = set()
        for t in range(n_int):
            # `--fav-bias`% favorito, resto descoberta
            if random.random() < args.fav_bias:
                g = random.choice(fav_genres)
                pool = genre_to_cids[g]
            else:
                pool = contents_df["content_id"].tolist()
            unseen = [c for c in pool if c not in seen]
            if not unseen:
                break
            cid = random.choice(unseen)
            seen.add(cid)

            c_row = contents_df.loc[contents_df.content_id == cid].iloc[0]
            c_genres = c_row["genres"]
            is_fav = any(g in fav_genres for g in c_genres)
            # completion enviesado por preferencia
            completion = float(np.clip(
                np.random.beta(8 if is_fav else 2, 2 if is_fav else 4), 0.0, 1.0
            ))

            duration_sec = int(c_row["duration_sec"])
            watched_sec = int(completion * duration_sec)
            started_at = base_time + pd.Timedelta(days=uid * 30 + t,
                                                   minutes=random.randint(0, 1440))
            finished = 1 if completion > 0.9 else 0
            # revisited e sempre 0 nesse dataset (cada user ve cada conteudo 1x)
            rating_implicit = float(np.clip(0.6 * completion + 0.1 * finished, 0.0, 1.0))

            interactions.append({
                "user_id": uid,
                "content_id": cid,
                "watched_sec": watched_sec,
                "total_sec": duration_sec,
                "completion": round(completion, 4),
                "finished": finished,
                "rating_implicit": rating_implicit,
                "started_at": started_at,
            })

    users_df = pd.DataFrame(users)
    interactions_df = pd.DataFrame(interactions)

    # Salvar (sem PII)
    contents_df.to_parquet(out_dir / "contents.parquet", index=False)
    users_df.drop(columns=["_fav_genres"]).to_parquet(
        out_dir / "users.parquet", index=False
    )
    interactions_df.to_parquet(out_dir / "interactions.parquet", index=False)

    # Ground truth de preferencias (para debug/sanity)
    pd.DataFrame({
        "user_id": users_df["user_id"],
        "fav_genres": users_df["_fav_genres"],
    }).to_parquet(out_dir / "ground_truth.parquet", index=False)

    print("Dataset gerado em", out_dir)
    print(f"  contents:     {len(contents_df):>6}")
    print(f"  users:        {len(users_df):>6}")
    print(f"  interactions: {len(interactions_df):>6}")
    pos = (interactions_df["rating_implicit"] >= 0.4).sum()
    print(f"  positivas (rating>=0.4): {pos} ({pos/len(interactions_df)*100:.1f}%)")
    print(f"  views/user mean: {interactions_df.groupby('user_id').size().mean():.1f}")


if __name__ == "__main__":
    generate(parse_args())
