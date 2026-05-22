"""Validador automatico dos requisitos de IA do PDF (Secao 8.3).

Roda checks objetivos e gera relatorio PASS/FAIL. Exit code != 0 se algum
requisito CRITICO falhar — pode ser usado em CI.

Requisitos:
  RFIA01 — Acuracia (HitRate@10) >= 0.70
  RFIA02 — Latencia P95 <= 2000 ms
  RFIA03 — Sistema so ativa apos >= 5 conteudos assistidos (cold start)
  RFIA04 — Perfil do usuario e atualizado a cada nova interacao

Uso:
    python scripts/validate_requirements.py
    python scripts/validate_requirements.py --metrics models/vodrec/metrics.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.orchestrator import (  # noqa: E402
    COLD_START_THRESHOLD,
    PopularityFallback,
    RecommendationOrchestrator,
)
from app.models.vodrec_transformer import VodRecRecommender  # noqa: E402


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--metrics", default="models/vodrec/metrics.json")
    p.add_argument("--model", default="models/vodrec/model.pt")
    p.add_argument("--vocab", default="models/vodrec/vocab.json")
    p.add_argument("--contents", default="data/contents.parquet")
    p.add_argument("--interactions", default="data/interactions.parquet")
    p.add_argument("--threshold-hr10", type=float, default=0.70)
    p.add_argument("--threshold-latency-ms", type=float, default=2000.0)
    return p.parse_args()


class Check:
    def __init__(self, code: str, name: str):
        self.code = code
        self.name = name
        self.passed = False
        self.detail: dict = {}

    def fail(self, detail: dict) -> None:
        self.passed = False
        self.detail = detail

    def ok(self, detail: dict) -> None:
        self.passed = True
        self.detail = detail

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "status": "PASS" if self.passed else "FAIL",
            "detail": self.detail,
        }


def check_rfia01(args, metrics) -> Check:
    """RFIA01 — Acuracia. HR@10 do VodRec deve ser >= alvo."""
    chk = Check("RFIA01", "Acuracia (HitRate@10 >= 0.70)")
    results = metrics.get("results", [])
    vodrec = next((r for r in results if r["model"] == "VodRec-Transformer"), None)
    if vodrec is None:
        chk.fail({"reason": "Nao encontrei resultados do VodRec-Transformer em metrics.json"})
        return chk
    hr10 = float(vodrec["hit_rate@10"])
    if hr10 >= args.threshold_hr10:
        chk.ok({
            "measured_hr10": hr10,
            "target": args.threshold_hr10,
            "vs_popularity": hr10 / max(1e-9, next(r["hit_rate@10"] for r in results if r["model"] == "Popularity")),
            "vs_random": hr10 / max(1e-9, next(r["hit_rate@10"] for r in results if r["model"] == "Random")),
        })
    else:
        chk.fail({"measured_hr10": hr10, "target": args.threshold_hr10})
    return chk


def check_rfia02(args, metrics) -> Check:
    """RFIA02 — Latencia P95 <= 2s."""
    chk = Check("RFIA02", "Latencia (P95 <= 2000 ms)")
    lat = metrics.get("latency_cpu_ms", {})
    p95 = lat.get("p95")
    if p95 is None:
        chk.fail({"reason": "metrics.json sem 'latency_cpu_ms.p95'"})
        return chk
    if p95 <= args.threshold_latency_ms:
        chk.ok({
            "measured_p95_ms": p95,
            "p50_ms": lat.get("p50"),
            "p99_ms": lat.get("p99"),
            "target_ms": args.threshold_latency_ms,
            "samples": lat.get("n_samples"),
        })
    else:
        chk.fail({"measured_p95_ms": p95, "target_ms": args.threshold_latency_ms})
    return chk


def check_rfia03(args) -> Check:
    """RFIA03 — Cold start: usuarios com < 5 views nao usam VodRec, vao para PopularityFallback."""
    chk = Check("RFIA03", "Cold start (< 5 views usa PopularityFallback)")

    # Carrega componentes
    rec = VodRecRecommender.load(args.model, args.vocab)
    contents_df = pd.read_parquet(args.contents)
    catalog = {int(r["content_id"]): {"title": r["title"], "genres": list(r["genres"])}
               for _, r in contents_df.iterrows()}
    pop = PopularityFallback({cid: 1 for cid in catalog})  # ranking estatico
    orch = RecommendationOrchestrator(rec, vodchat=None, catalog=catalog, popularity=pop)

    # Caso 1: usuario sem historico -> empty_history
    r0 = orch.recommend([], k=10)
    case_empty = r0["strategy"] == "empty_history" and r0["recommendations"] == []

    # Caso 2: usuario com 3 views -> cold_start
    cids = list(catalog.keys())[:3]
    r1 = orch.recommend(cids, k=10)
    case_cold = r1["strategy"] == "cold_start" and len(r1["recommendations"]) > 0

    # Caso 3: usuario com 10 views -> vodrec
    cids10 = list(catalog.keys())[:10]
    r2 = orch.recommend(cids10, k=10)
    case_full = r2["strategy"] == "vodrec"

    all_ok = case_empty and case_cold and case_full
    detail = {
        "threshold": COLD_START_THRESHOLD,
        "empty_history_returns_empty": case_empty,
        "below_threshold_uses_popularity": case_cold,
        "above_threshold_uses_vodrec": case_full,
        "strategies_observed": [r0["strategy"], r1["strategy"], r2["strategy"]],
    }
    if all_ok:
        chk.ok(detail)
    else:
        chk.fail(detail)
    return chk


def check_rfia04(args) -> Check:
    """RFIA04 — Perfil atualizado a cada nova interacao.

    Como o VodRec nao usa um 'perfil' persistido (a sequencia DO USUARIO E O PERFIL),
    o teste verifica que: ao adicionar uma nova interacao ao historico, a saida do
    modelo MUDA — ou seja, o sistema reage ao novo evento sem retreino.
    """
    chk = Check("RFIA04", "Perfil atualizado a cada interacao (saida varia com novo evento)")

    rec = VodRecRecommender.load(args.model, args.vocab)
    contents_df = pd.read_parquet(args.contents)
    cids = list(contents_df["content_id"].head(20).astype(int).tolist())

    history_before = cids[:8]
    history_after = cids[:8] + [cids[8]]  # +1 nova interacao
    recs_before = [c for c, _ in rec.recommend(history_before, k=10)]
    recs_after = [c for c, _ in rec.recommend(history_after, k=10)]

    differs = recs_before != recs_after
    overlap = len(set(recs_before) & set(recs_after))
    if differs:
        chk.ok({
            "before_top10": recs_before,
            "after_top10": recs_after,
            "overlap": overlap,
            "reactive": True,
        })
    else:
        chk.fail({
            "reason": "Recomendacoes nao mudaram apos nova interacao",
            "before_top10": recs_before,
            "after_top10": recs_after,
        })
    return chk


def check_seq_authoring(args) -> Check:
    """Check bonus: confere autoria — modelo construido em PyTorch puro.

    Analisa LINHAS DE IMPORT (nao docstrings) do vodrec_transformer.py.
    """
    import ast
    chk = Check("AUTH", "Modelo construido (sem sklearn/implicit/transformers no nucleo)")
    src = Path("app/models/vodrec_transformer.py").read_text()
    tree = ast.parse(src)

    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                imports.add(n.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split(".")[0])

    forbidden = {"sklearn", "implicit", "xgboost", "transformers", "lightgbm"}
    found = imports & forbidden

    # Verifica que as classes proprias existem
    class_names = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    required_classes = {"MultiHeadSelfAttention", "FeedForward",
                         "TransformerBlock", "VodRecTransformer"}
    missing_classes = required_classes - class_names

    if not found and not missing_classes:
        chk.ok({
            "imports": sorted(imports),
            "classes_proprias": sorted(required_classes),
            "evidence": "Apenas torch/PyTorch nativo + std-lib. Sem libs de ML pronta.",
        })
    else:
        chk.fail({
            "imports": sorted(imports),
            "forbidden_imports_found": sorted(found),
            "missing_required_classes": sorted(missing_classes),
        })
    return chk


def main() -> int:
    args = parse_args()

    try:
        with open(args.metrics) as f:
            metrics = json.load(f)
    except FileNotFoundError:
        print(f"[erro] {args.metrics} nao existe. Rode primeiro: python scripts/train_and_evaluate.py")
        return 2

    checks = [
        check_rfia01(args, metrics),
        check_rfia02(args, metrics),
        check_rfia03(args),
        check_rfia04(args),
        check_seq_authoring(args),
    ]

    # Relatorio em texto
    print("\n" + "=" * 70)
    print("VALIDACAO DE REQUISITOS — VOD-IA")
    print("=" * 70)
    for c in checks:
        flag = "PASS" if c.passed else "FAIL"
        print(f"  [{flag}] {c.code} — {c.name}")
        for k, v in c.detail.items():
            print(f"          {k}: {v}")
        print()

    n_passed = sum(1 for c in checks if c.passed)
    n_total = len(checks)
    print(f"  Resultado: {n_passed}/{n_total} checks passaram")
    print("=" * 70 + "\n")

    # Salva JSON
    report = {
        "checks": [c.to_dict() for c in checks],
        "summary": {
            "passed": n_passed,
            "total": n_total,
            "ok": n_passed == n_total,
        },
    }
    out = Path("reports/requirements_validation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"[report] {out}\n")

    return 0 if n_passed == n_total else 1


if __name__ == "__main__":
    raise SystemExit(main())
