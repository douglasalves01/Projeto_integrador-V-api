"""Ingere o dataset real de 49 videos brasileiros para o formato canonico
esperado pelo VodRec.

Entrada (em apps/ai/data/raw/):
    NN_slug/
        metadata.json   <-- titulo, descricao, tags, categorias, duracao_seg, ...
    log_downloads.json

Saida:
    apps/ai/data/contents.parquet    (49 linhas, schema canonico)
    apps/ai/data/categories.json     (mapeamento slug -> categoria inferida)

Categorias inferidas (dominio do dataset, nao YouTube):
    Culinaria, Musica, Esporte, Natureza, Tecnologia, Ciencia,
    Arte, Saude, Educacao, Cultura, Turismo
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Heuristica de categorizacao a partir de titulo + tags + query
# ---------------------------------------------------------------------------

CATEGORY_RULES: list[tuple[str, list[str]]] = [
    # (categoria, palavras-chave que ATIVAM ela — match em titulo/tags/query/descricao)
    # Ordem importa: regras mais especificas em cima.
    ("Natureza",    ["cachoeira", "amazonia", "pantanal", "animais", "passaros",
                      "passaro", "sabia", "peixe", "onca", "abelhas",
                      "fauna", "flora", "selvagem"]),
    ("Culinaria",   ["receita", "como fazer brigadeiro", "como fazer coxinha",
                      "coxinha", "feijoada", "brigadeiro", "pao de queijo",
                      "acai", "cozinha", "comida"]),
    ("Musica",      ["samba", "funk", "bossa", "baiao", "forro", "musica",
                      "violao", "batida instrumental"]),
    ("Esporte",     ["futebol", "gol", "volei", "skate", "surf", "capoeira",
                      "manobra"]),
    ("Turismo",     ["lencois maranhenses", "christ redentor", "ouro preto",
                      "carnaval", "paisagem", "patrimonio", "rio de janeiro",
                      "salvador"]),
    ("Tecnologia", ["programacao", "python", "html", "css", "5g", "tutorial",
                      "inteligencia artificial", "excel", "planilha"]),
    ("Ciencia",     ["chuva", "universo", "vulcao", "eclipse", "sistema solar",
                      "planetas", "experimento", "coracao", "curiosidades"]),
    ("Arte",        ["pintura", "aquarela", "vela aromatica", "macrame",
                      "croche", "artesanato", "reciclagem"]),
    ("Saude",       ["meditacao", "yoga", "alongamento", "exercicio",
                      "saude mental", "fitness"]),
    ("Educacao",    ["historia do brasil", "resumo", "explicacao", "explic"]),
    ("Cultura",     ["brasil", "brasileiro", "nordestino", "mineiro"]),  # fallback amplo
]


def infer_category(metadata: dict) -> str:
    """Retorna a primeira categoria interna que casa com tags/titulo/query."""
    haystack = " ".join([
        metadata.get("titulo", ""),
        metadata.get("descricao", "")[:300],
        " ".join(metadata.get("tags", []) or []),
        metadata.get("query", ""),
        metadata.get("pasta", ""),
    ]).lower()
    haystack = re.sub(r"[áàâã]", "a", haystack)
    haystack = re.sub(r"[éê]", "e", haystack)
    haystack = re.sub(r"[íì]", "i", haystack)
    haystack = re.sub(r"[óôõ]", "o", haystack)
    haystack = re.sub(r"[úü]", "u", haystack)
    haystack = haystack.replace("ç", "c")

    for category, keywords in CATEGORY_RULES:
        if any(k in haystack for k in keywords):
            return category
    return "Outros"


def infer_secondary_tags(metadata: dict) -> list[str]:
    """Pega ate 5 tags relevantes do metadata para serem `genres` secundarios."""
    tags = metadata.get("tags") or []
    # Filtra tags muito genericas
    blacklist = {"video", "youtube", "br", "brasil", "novo"}
    cleaned = [t for t in tags if t and t.lower() not in blacklist]
    return cleaned[:5]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--raw-dir", default="data/raw")
    p.add_argument("--out-dir", default="data")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    raw_dir = Path(args.raw_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    categories_map: dict[str, str] = {}

    folders = sorted([d for d in raw_dir.iterdir()
                       if d.is_dir() and (d / "metadata.json").exists()])
    print(f"[ingest] {len(folders)} pastas encontradas em {raw_dir}")

    for folder in folders:
        meta = json.loads((folder / "metadata.json").read_text())
        if meta.get("status") != "ok":
            print(f"[skip] {folder.name} (status={meta.get('status')})")
            continue

        category = infer_category(meta)
        tags = infer_secondary_tags(meta)
        # `genres` interno = categoria principal + tags secundarias relevantes
        genres = [category] + [t.capitalize() for t in tags if len(t) <= 30][:3]

        rows.append({
            "content_id": int(meta["index"]),
            "title": meta.get("titulo", folder.name),
            "description": (meta.get("descricao") or "")[:500],
            "duration_sec": int(meta.get("duracao_seg") or 0),
            "release_year": int((meta.get("data_upload") or "20240101")[:4]),
            "genres": genres,
            "categories": meta.get("categorias") or ["Filme"],
            "external_url": meta.get("url"),
            "views_youtube": int(meta.get("visualizacoes") or 0),
            "likes_youtube": int(meta.get("likes") or 0),
            "folder": folder.name,
        })
        categories_map[folder.name] = category

    df = pd.DataFrame(rows).sort_values("content_id").reset_index(drop=True)
    df.to_parquet(out_dir / "contents.parquet", index=False)

    (out_dir / "categories.json").write_text(
        json.dumps(categories_map, ensure_ascii=False, indent=2)
    )

    # Sumario por categoria
    print()
    print(f"[ingest] contents salvo: {out_dir/'contents.parquet'}  ({len(df)} linhas)")
    print("[ingest] distribuicao por categoria:")
    counts = df["genres"].apply(lambda g: g[0]).value_counts()
    for cat, n in counts.items():
        print(f"  {cat:15s} {n:>3}")
    print()
    print("Exemplos:")
    for _, r in df.head(5).iterrows():
        print(f"  [{r['content_id']:2d}] {r['title'][:55]:<55} | {r['genres']}")


if __name__ == "__main__":
    main()
