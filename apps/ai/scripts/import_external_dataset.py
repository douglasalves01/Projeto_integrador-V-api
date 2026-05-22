"""Conversor de dataset externo para o schema esperado pelo VodRec.

Aceita CSV, JSON, JSONL ou Parquet com qualquer nomenclatura de colunas e
converte para o trio canonico (contents.parquet, interactions.parquet,
users.parquet) usado pelo treino.

Schema canonico de interacoes (saida):
    user_id        int64
    content_id     int64
    watched_sec    int64    (opcional, default = total_sec)
    total_sec      int64    (opcional)
    completion     float64  (derivado se faltar)
    finished       int      (1 se completion > 0.9)
    rating_implicit float64 (derivado se faltar)
    started_at     datetime (obrigatorio para split temporal)

Schema canonico de contents (saida):
    content_id     int64
    title          str
    description    str (opcional, gerado a partir do title)
    duration_sec   int (default 3600)
    release_year   int (default 2020)
    genres         list[str] (default [])
    categories     list[str] (default ['Filme'])

Exemplo de uso:

    # Pelo input + mapeamento explicito
    python scripts/import_external_dataset.py \\
        --interactions-in raw/views.csv \\
        --contents-in    raw/movies.csv \\
        --map-user-id userId \\
        --map-content-id movieId \\
        --map-started-at timestamp \\
        --map-completion watch_pct \\
        --map-title title \\
        --map-genres genres_pipe \\
        --genres-sep "|" \\
        --out-dir data/

    # Caso "MovieLens-like" rapido
    python scripts/import_external_dataset.py \\
        --interactions-in ml-latest-small/ratings.csv \\
        --contents-in ml-latest-small/movies.csv \\
        --preset movielens \\
        --out-dir data/

Apos converter, treinar:

    python scripts/train_and_evaluate.py \\
        --interactions data/interactions.parquet \\
        --epochs 20 --version vodrec-v2.0.0
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------


def read_any(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    suf = p.suffix.lower()
    if suf == ".parquet":
        return pd.read_parquet(p)
    if suf == ".csv":
        return pd.read_csv(p)
    if suf == ".tsv":
        return pd.read_csv(p, sep="\t")
    if suf == ".jsonl" or suf == ".ndjson":
        return pd.read_json(p, lines=True)
    if suf == ".json":
        return pd.read_json(p)
    raise ValueError(f"Formato desconhecido: {suf}")


# ---------------------------------------------------------------------------
# Presets — atalhos para datasets publicos comuns
# ---------------------------------------------------------------------------


PRESETS = {
    "movielens": {
        "interactions": {
            "user_id": "userId",
            "content_id": "movieId",
            "started_at": "timestamp",     # timestamp epoch
            "rating": "rating",            # 0.5..5.0 → vamos normalizar
            "rating_scale": (0.5, 5.0),
            "timestamp_unit": "s",
        },
        "contents": {
            "content_id": "movieId",
            "title": "title",
            "genres": "genres",
            "genres_sep": "|",
        },
    },
    # Acrescente outros aqui quando aparecerem (ContentWise, Yelp, etc.)
}


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------


def _get(row: pd.Series, key: str | None, default: Any = None) -> Any:
    if key is None:
        return default
    return row[key] if key in row.index else default


def normalize_started_at(s: pd.Series, unit: str | None) -> pd.Series:
    """Converte qualquer formato de tempo para datetime64."""
    if pd.api.types.is_datetime64_any_dtype(s):
        return s
    if unit:
        return pd.to_datetime(s, unit=unit, errors="coerce")
    # tenta como string ISO; fallback para epoch
    parsed = pd.to_datetime(s, errors="coerce")
    if parsed.isna().mean() > 0.5:
        parsed = pd.to_datetime(s, unit="s", errors="coerce")
    return parsed


def _to_int_id(series: pd.Series) -> tuple[pd.Series, dict | None]:
    """Garante que a coluna seja int64. Se for string/uuid, factoriza e
    devolve o mapeamento original -> int para auditoria.
    """
    if pd.api.types.is_integer_dtype(series):
        return series.astype("int64"), None
    codes, uniques = pd.factorize(series, sort=True)
    mapping = {str(orig): int(code) + 1 for code, orig in enumerate(uniques)}
    return pd.Series(codes + 1, index=series.index, dtype="int64"), mapping


def convert_interactions(
    df: pd.DataFrame,
    *,
    map_user_id: str,
    map_content_id: str,
    map_started_at: str,
    map_completion: str | None = None,
    map_watched_sec: str | None = None,
    map_total_sec: str | None = None,
    map_rating: str | None = None,
    rating_scale: tuple[float, float] | None = None,
    timestamp_unit: str | None = None,
) -> tuple[pd.DataFrame, dict]:
    out = pd.DataFrame(index=df.index)
    out["user_id"], user_map = _to_int_id(df[map_user_id])
    out["content_id"], content_map = _to_int_id(df[map_content_id])
    out["started_at"] = normalize_started_at(df[map_started_at], timestamp_unit)
    id_maps = {"user_id_map": user_map, "content_id_map": content_map}

    # Derivar completion
    if map_completion and map_completion in df.columns:
        out["completion"] = df[map_completion].astype(float).clip(0.0, 1.0)
    elif map_watched_sec and map_total_sec and {map_watched_sec, map_total_sec} <= set(df.columns):
        out["watched_sec"] = df[map_watched_sec].astype("int64")
        out["total_sec"] = df[map_total_sec].astype("int64").clip(lower=1)
        out["completion"] = (out["watched_sec"] / out["total_sec"]).clip(0.0, 1.0)
    elif map_rating and map_rating in df.columns:
        # Normaliza rating explicito para 0..1 e usa como proxy de completion
        if rating_scale is None:
            rating_scale = (df[map_rating].min(), df[map_rating].max())
        lo, hi = rating_scale
        if hi <= lo:
            raise ValueError(f"rating_scale invalido: {rating_scale}")
        out["completion"] = ((df[map_rating].astype(float) - lo) / (hi - lo)).clip(0.0, 1.0)
    else:
        # Sem sinal — assume completion 1.0 (so 'visualizou')
        out["completion"] = 1.0

    if "watched_sec" not in out:
        out["total_sec"] = out.get("total_sec", 3600)
        out["watched_sec"] = (out["completion"] * out["total_sec"]).astype("int64")
    out["finished"] = (out["completion"] > 0.9).astype(int)
    # rating_implicit = 0.6 * completion + 0.1 * finished (formula do dataset original)
    out["rating_implicit"] = (0.6 * out["completion"] + 0.1 * out["finished"]).clip(0.0, 1.0)

    # Limpa nulos no started_at (linhas sem timestamp nao tem ordem)
    n0 = len(out)
    out = out.dropna(subset=["started_at"])
    if len(out) < n0:
        print(f"[warn] removidas {n0-len(out)} linhas sem started_at parseavel")

    out = out[["user_id", "content_id", "watched_sec", "total_sec",
                "completion", "finished", "rating_implicit", "started_at"]]
    return out, id_maps


def convert_contents(
    df: pd.DataFrame,
    *,
    map_content_id: str,
    map_title: str | None = None,
    map_description: str | None = None,
    map_duration_sec: str | None = None,
    map_release_year: str | None = None,
    map_genres: str | None = None,
    map_categories: str | None = None,
    genres_sep: str = "|",
    categories_sep: str = "|",
    content_id_map: dict | None = None,
) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    # Reusa o mesmo factorize feito nas interacoes (se fornecido), garantindo
    # que content_id em contents.parquet e interactions.parquet bate.
    if content_id_map is not None:
        out["content_id"] = df[map_content_id].astype(str).map(content_id_map)
        out = out.dropna(subset=["content_id"])
        out["content_id"] = out["content_id"].astype("int64")
        # Re-alinha df para o mesmo subset
        df = df.loc[out.index]
    else:
        out["content_id"], _ = _to_int_id(df[map_content_id])
    out["title"] = (df[map_title] if map_title and map_title in df.columns
                    else out["content_id"].apply(lambda c: f"Content_{c}")).astype(str)
    out["description"] = (df[map_description] if map_description and map_description in df.columns
                          else out["title"].apply(lambda t: f"Sinopse de {t}.")).astype(str)
    out["duration_sec"] = (df[map_duration_sec] if map_duration_sec and map_duration_sec in df.columns
                            else 3600).astype("int64", errors="ignore") if isinstance(out.get("duration_sec"), pd.Series) else (
        df[map_duration_sec].astype("int64") if map_duration_sec and map_duration_sec in df.columns
        else pd.Series([3600] * len(df), dtype="int64")
    )
    out["release_year"] = (
        df[map_release_year].astype("int64") if map_release_year and map_release_year in df.columns
        else pd.Series([2020] * len(df), dtype="int64")
    )

    def _split(s: Any, sep: str) -> list[str]:
        if isinstance(s, list):
            return s
        if isinstance(s, str) and s.strip():
            return [x.strip() for x in s.split(sep) if x.strip()]
        return []

    if map_genres and map_genres in df.columns:
        out["genres"] = df[map_genres].apply(lambda v: _split(v, genres_sep))
    else:
        out["genres"] = [[] for _ in range(len(df))]

    if map_categories and map_categories in df.columns:
        out["categories"] = df[map_categories].apply(lambda v: _split(v, categories_sep))
    else:
        out["categories"] = [["Filme"] for _ in range(len(df))]

    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                 description=__doc__)
    p.add_argument("--interactions-in", required=True)
    p.add_argument("--contents-in", default=None,
                   help="Arquivo de contents/movies. Se omitido, gera contents a partir das interactions.")
    p.add_argument("--out-dir", default="data")
    p.add_argument("--preset", choices=list(PRESETS.keys()), default=None,
                   help="Preset para datasets conhecidos (movielens, ...).")

    # Mapeamento manual — usado quando nao ha preset
    p.add_argument("--map-user-id", default=None)
    p.add_argument("--map-content-id", default=None)
    p.add_argument("--map-started-at", default=None)
    p.add_argument("--map-completion", default=None)
    p.add_argument("--map-watched-sec", default=None)
    p.add_argument("--map-total-sec", default=None)
    p.add_argument("--map-rating", default=None)
    p.add_argument("--rating-min", type=float, default=None)
    p.add_argument("--rating-max", type=float, default=None)
    p.add_argument("--timestamp-unit", default=None,
                   help="'s' ou 'ms' para epochs; None tenta auto-detectar.")

    p.add_argument("--map-title", default=None)
    p.add_argument("--map-description", default=None)
    p.add_argument("--map-duration-sec", default=None)
    p.add_argument("--map-release-year", default=None)
    p.add_argument("--map-genres", default=None)
    p.add_argument("--map-categories", default=None)
    p.add_argument("--genres-sep", default="|")
    p.add_argument("--categories-sep", default="|")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[load] interactions: {args.interactions_in}")
    inter_raw = read_any(args.interactions_in)
    print(f"  shape={inter_raw.shape}  colunas={list(inter_raw.columns)}")

    # Aplica preset se selecionado
    if args.preset:
        cfg = PRESETS[args.preset]
        i_cfg = cfg["interactions"]
        interactions_df, id_maps = convert_interactions(
            inter_raw,
            map_user_id=i_cfg["user_id"],
            map_content_id=i_cfg["content_id"],
            map_started_at=i_cfg["started_at"],
            map_rating=i_cfg.get("rating"),
            rating_scale=i_cfg.get("rating_scale"),
            timestamp_unit=i_cfg.get("timestamp_unit"),
        )
    else:
        if not (args.map_user_id and args.map_content_id and args.map_started_at):
            raise SystemExit("Sem --preset, voce precisa fornecer --map-user-id, "
                             "--map-content-id e --map-started-at.")
        rating_scale = None
        if args.rating_min is not None and args.rating_max is not None:
            rating_scale = (args.rating_min, args.rating_max)
        interactions_df, id_maps = convert_interactions(
            inter_raw,
            map_user_id=args.map_user_id,
            map_content_id=args.map_content_id,
            map_started_at=args.map_started_at,
            map_completion=args.map_completion,
            map_watched_sec=args.map_watched_sec,
            map_total_sec=args.map_total_sec,
            map_rating=args.map_rating,
            rating_scale=rating_scale,
            timestamp_unit=args.timestamp_unit,
        )

    print(f"[ok]  interactions normalized: {interactions_df.shape}")
    print(f"      completion mean: {interactions_df['completion'].mean():.3f}")
    print(f"      positivas (rating>=0.4): {(interactions_df['rating_implicit']>=0.4).mean()*100:.1f}%")

    # ---------- contents ----------
    if args.contents_in:
        print(f"[load] contents: {args.contents_in}")
        cont_raw = read_any(args.contents_in)
        print(f"  shape={cont_raw.shape}  colunas={list(cont_raw.columns)}")
        if args.preset:
            c_cfg = PRESETS[args.preset]["contents"]
            contents_df = convert_contents(
                cont_raw,
                map_content_id=c_cfg["content_id"],
                map_title=c_cfg.get("title"),
                map_genres=c_cfg.get("genres"),
                genres_sep=c_cfg.get("genres_sep", "|"),
                content_id_map=id_maps.get("content_id_map"),
            )
        else:
            contents_df = convert_contents(
                cont_raw,
                map_content_id=args.map_content_id,
                map_title=args.map_title,
                map_description=args.map_description,
                map_duration_sec=args.map_duration_sec,
                map_release_year=args.map_release_year,
                map_genres=args.map_genres,
                map_categories=args.map_categories,
                genres_sep=args.genres_sep,
                categories_sep=args.categories_sep,
                content_id_map=id_maps.get("content_id_map"),
            )
    else:
        # Gera contents minimo a partir dos content_ids vistos
        cids = sorted(interactions_df["content_id"].unique().tolist())
        contents_df = pd.DataFrame({
            "content_id": cids,
            "title": [f"Content_{c}" for c in cids],
            "description": [f"Sinopse de Content_{c}." for c in cids],
            "duration_sec": [3600] * len(cids),
            "release_year": [2020] * len(cids),
            "genres": [[] for _ in cids],
            "categories": [["Filme"] for _ in cids],
        })
        print(f"[info] contents gerados a partir das interactions ({len(cids)} itens)")

    # ---------- users (apenas IDs) ----------
    users_df = pd.DataFrame({
        "user_id": sorted(interactions_df["user_id"].unique().tolist())
    })

    # ---------- coerencia ----------
    seen_cids = set(interactions_df["content_id"].unique().tolist())
    cat_cids = set(contents_df["content_id"].unique().tolist())
    missing = seen_cids - cat_cids
    if missing:
        print(f"[warn] {len(missing)} content_ids estao em interactions mas nao em contents. "
              f"Filtrando interactions para usar apenas contents conhecidos.")
        interactions_df = interactions_df[interactions_df["content_id"].isin(cat_cids)]

    # ---------- save ----------
    contents_df.to_parquet(out_dir / "contents.parquet", index=False)
    users_df.to_parquet(out_dir / "users.parquet", index=False)
    interactions_df.to_parquet(out_dir / "interactions.parquet", index=False)

    summary = {
        "n_users": int(users_df.shape[0]),
        "n_contents": int(contents_df.shape[0]),
        "n_interactions": int(interactions_df.shape[0]),
        "views_per_user_mean": float(interactions_df.groupby("user_id").size().mean()),
        "completion_mean": float(interactions_df["completion"].mean()),
        "positive_rate": float((interactions_df["rating_implicit"] >= 0.4).mean()),
    }
    (out_dir / "dataset_summary.json").write_text(json.dumps(summary, indent=2))

    # Salva ID maps para auditoria/reversao (string original <-> int)
    if id_maps.get("user_id_map") or id_maps.get("content_id_map"):
        with (out_dir / "id_maps.json").open("w") as f:
            json.dump({k: v for k, v in id_maps.items() if v}, f, indent=2)

    print("\n[done] arquivos em", out_dir)
    for f in ["contents.parquet", "users.parquet", "interactions.parquet", "dataset_summary.json"]:
        path = out_dir / f
        print(f"  {f:30s}  {path.stat().st_size/1024:7.1f} KB")
    print("\nProximo passo:")
    print("  python scripts/train_and_evaluate.py --interactions data/interactions.parquet \\")
    print("      --epochs 20 --version vodrec-v2.0.0")


if __name__ == "__main__":
    main()
