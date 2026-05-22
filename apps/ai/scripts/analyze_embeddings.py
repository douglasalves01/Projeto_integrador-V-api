"""Analise dos embeddings aprendidos pelo VodRec-Transformer.

Extrai a matriz `item_emb.weight` do checkpoint (V x d_model), projeta em 2D
com t-SNE e PCA, e colore por genero predominante. Se o modelo realmente
aprendeu semantica, conteudos do mesmo genero devem clusterizar.

Tambem mede:
- Coerencia por genero (kNN intra-genero vs aleatorio).
- Distribuicao da norma dos embeddings (modelo saudavel: distribuicao suave).

Uso:
    python scripts/analyze_embeddings.py \
        --model models/vodrec/model.pt \
        --vocab models/vodrec/vocab.json \
        --contents data/contents.parquet \
        --out reports/
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.vodrec_transformer import VodRecTransformer  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--model", type=str, default="models/vodrec/model.pt")
    p.add_argument("--vocab", type=str, default="models/vodrec/vocab.json")
    p.add_argument("--contents", type=str, default="data/contents.parquet")
    p.add_argument("--out", type=str, default="reports")
    p.add_argument("--perplexity", type=float, default=30.0)
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[load] modelo: {args.model}")
    model = VodRecTransformer.load(args.model, device="cpu")
    model.eval()
    emb = model.item_emb.weight.detach().cpu().numpy()  # (V, d_model)
    print(f"[load] embeddings: {emb.shape}")

    with open(args.vocab) as f:
        vocab = json.load(f)
    token_to_content = {int(v): int(k) for k, v in vocab["content_to_token"].items()}

    contents_df = pd.read_parquet(args.contents)
    cid_to_genres = dict(zip(contents_df["content_id"], contents_df["genres"]))

    # Filtra tokens validos (descarta <pad>, <bos>)
    valid_tokens = sorted(token_to_content.keys())
    valid_emb = emb[valid_tokens]            # (V', d_model)
    cids = [token_to_content[t] for t in valid_tokens]
    def _first_genre(cid):
        g = cid_to_genres.get(cid)
        if g is None:
            return "?"
        # pandas pode retornar np.array; converte e pega o primeiro
        g_list = list(g)
        return g_list[0] if g_list else "?"

    primary_genre = [_first_genre(c) for c in cids]
    genres_unique = sorted(set(primary_genre))
    print(f"[data] {len(valid_emb)} itens validos, {len(genres_unique)} generos unicos")

    # ----- Estatisticas das normas -----
    norms = np.linalg.norm(valid_emb, axis=1)
    print(f"[stats] norma media={norms.mean():.3f}  std={norms.std():.3f}  "
          f"min={norms.min():.3f}  max={norms.max():.3f}")

    # ----- kNN intra-genero vs aleatorio -----
    from sklearn.neighbors import NearestNeighbors
    knn = NearestNeighbors(n_neighbors=11, metric="cosine")  # 11 = self + 10 vizinhos
    knn.fit(valid_emb)
    _, indices = knn.kneighbors(valid_emb)

    intra_genre_hits = 0
    total_pairs = 0
    for i, neighbors in enumerate(indices):
        g_i = primary_genre[i]
        # Pula self (indice 0)
        for j in neighbors[1:]:
            if primary_genre[j] == g_i:
                intra_genre_hits += 1
            total_pairs += 1
    intra_genre_rate = intra_genre_hits / max(1, total_pairs)

    # Baseline aleatorio: P(mesmo genero) = sum(p_g^2) onde p_g e freq do genero
    counts = Counter(primary_genre)
    total = sum(counts.values())
    random_rate = sum((c / total) ** 2 for c in counts.values())

    print(f"[knn] intra-genre@10 = {intra_genre_rate:.3f}")
    print(f"[knn] baseline aleatorio = {random_rate:.3f}")
    print(f"[knn] LIFT = {intra_genre_rate / max(random_rate, 1e-9):.2f}x")

    # ----- t-SNE + PCA -----
    print("[viz] rodando t-SNE...")
    from sklearn.manifold import TSNE
    from sklearn.decomposition import PCA

    tsne = TSNE(
        n_components=2,
        perplexity=min(args.perplexity, max(5, len(valid_emb) // 4)),
        random_state=args.seed,
        init="pca",
        learning_rate="auto",
    )
    tsne_xy = tsne.fit_transform(valid_emb)

    pca = PCA(n_components=2, random_state=args.seed)
    pca_xy = pca.fit_transform(valid_emb)
    var_ratio = pca.explained_variance_ratio_
    print(f"[pca] variancia explicada PC1+PC2 = {var_ratio.sum()*100:.1f}%")

    # ----- Plots -----
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(16, 7))
        cmap = plt.colormaps.get_cmap("tab20")
        genre_to_color = {g: cmap(i % cmap.N) for i, g in enumerate(genres_unique)}
        colors = [genre_to_color[g] for g in primary_genre]

        axes[0].scatter(tsne_xy[:, 0], tsne_xy[:, 1], c=colors, s=14, alpha=0.7)
        axes[0].set_title(f"t-SNE dos embeddings VodRec (intra-genre@10 = {intra_genre_rate:.3f})")
        axes[0].set_xlabel("dim 1"); axes[0].set_ylabel("dim 2")

        axes[1].scatter(pca_xy[:, 0], pca_xy[:, 1], c=colors, s=14, alpha=0.7)
        axes[1].set_title(f"PCA (PC1+PC2 = {var_ratio.sum()*100:.1f}% var)")
        axes[1].set_xlabel("PC1"); axes[1].set_ylabel("PC2")

        # Legenda compartilhada (limita a 15 generos para nao poluir)
        handles = [plt.Line2D([0], [0], marker="o", color="w",
                              markerfacecolor=genre_to_color[g],
                              markersize=8, label=g)
                   for g in genres_unique[:15]]
        fig.legend(handles=handles, loc="lower center", ncol=8,
                   bbox_to_anchor=(0.5, -0.05))
        plt.tight_layout()
        out_path = out_dir / "embeddings_visualization.png"
        plt.savefig(out_path, dpi=130, bbox_inches="tight")
        print(f"[viz] salvo: {out_path}")
    except ImportError:
        print("[warn] matplotlib indisponivel — pulando plots")

    # ----- Relatorio JSON -----
    report_path = out_dir / "embeddings_analysis.json"
    with report_path.open("w") as f:
        json.dump({
            "n_items": int(len(valid_emb)),
            "n_genres": len(genres_unique),
            "embedding_dim": int(emb.shape[1]),
            "norm_stats": {
                "mean": float(norms.mean()),
                "std": float(norms.std()),
                "min": float(norms.min()),
                "max": float(norms.max()),
            },
            "knn_intra_genre_at_10": float(intra_genre_rate),
            "knn_random_baseline": float(random_rate),
            "knn_lift": float(intra_genre_rate / max(random_rate, 1e-9)),
            "pca_variance_top2": [float(v) for v in var_ratio],
            "genres_distribution": {g: int(c) for g, c in counts.most_common()},
        }, f, indent=2)
    print(f"[report] {report_path}")

    # Veredito didatico
    print()
    if intra_genre_rate > 2 * random_rate:
        print(f"✓ Os embeddings APRENDERAM semantica de genero: "
              f"itens proximos no espaco compartilham genero {intra_genre_rate*100:.1f}% das vezes "
              f"({intra_genre_rate/max(random_rate,1e-9):.1f}x acima do aleatorio).")
    else:
        print(f"✗ Os embeddings parecem aleatorios em relacao a genero. Considere treinar mais.")


if __name__ == "__main__":
    main()
