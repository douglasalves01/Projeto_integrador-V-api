# Model Card — VOD-IA

> Cartão de modelo com **métricas reais medidas** (não placeholders). Última atualização vinculada a `models/vodrec/VERSION.txt`.

---

## Identificação

| Campo | Valor |
|---|---|
| **Sistema** | VOD-IA — Recomendação para plataforma de streaming sob demanda |
| **Modelos** | VodRec-Transformer (recomendação) + VodChat (explicações) + PopularityFallback (cold start) |
| **Versão** | `vodrec-v1.0.0` |
| **Treinado em** | 2026-05-22 (CPU) |
| **Framework** | PyTorch puro (sem scikit-learn / implicit / transformers para o motor de recomendação) |

---

## 1. VodRec-Transformer (recomendador principal)

### Arquitetura

Decoder-only Transformer **construído do zero** em `app/models/vodrec_transformer.py`. Inspirado em SASRec (Kang & McAuley, 2018) e GPT (Radford et al., 2019).

| Hiperparâmetro | Valor |
|---|---|
| `d_model` | 128 |
| `n_heads` | 4 |
| `n_layers` | 3 |
| `max_seq_len` | 80 |
| Vocabulary size (catálogo + tokens especiais) | 402 |
| Parâmetros treináveis | **656.768** (~0.66M) |
| Tied embeddings (input ↔ output) | sim |
| Causal mask | sim (triangular inferior) |
| Padding mask | sim, com `nan_to_num` para queries de padding |

**Componentes implementados pelo time** (não wrappers de biblioteca):
- `MultiHeadSelfAttention` — QKV projection, scaled dot-product, masking, head merge.
- `FeedForward` — GELU MLP 4x.
- `TransformerBlock` — pre-LayerNorm + residual.
- `VodRecTransformer` — embeddings tied + bloco stack + projeção final.

Imports do módulo: `torch`, `torch.nn`, `torch.nn.functional`, `json`, `math`, `pathlib`, `typing`, `dataclasses`. **Validado por `scripts/validate_requirements.py` (check AUTH PASS).**

### Dados

Dataset sintético com modelagem de gosto realista (gerado por `scripts/generate_dataset.py`):

| Estatística | Valor |
|---|---|
| Usuários | 1.499 |
| Conteúdos (catálogo) | 400 |
| Interações totais | 73.511 |
| Interações positivas (rating ≥ 0.4) | 55.969 (76,1%) |
| Views médias por usuário | 49 |
| Gêneros | 15 |
| Bias por gênero favorito | 85% |
| Split | temporal 80/20 por usuário |

### Treino

| Item | Valor |
|---|---|
| Loss | Cross-entropy + label smoothing 0.1 |
| Optimizer | AdamW lr=1e-3, wd=0.01 |
| LR schedule | Linear warmup (100 steps) + cosine decay |
| Batch size | 128 |
| Epochs | 20 |
| Gradient clipping | 1.0 |
| Tempo total | 103 segundos em CPU (Apple Silicon) |
| Loss inicial | 6.00 |
| Loss final | 4.97 |

### Métricas (medidas no test set completo — 1.499 usuários)

| Modelo | HR@5 | HR@10 | HR@20 | NDCG@10 | MAP@10 | MRR@10 |
|---|---|---|---|---|---|---|
| **VodRec-Transformer** | **0.556** | **0.742** | **0.899** | **0.210** | **0.112** | **0.347** |
| Popularity (baseline) | 0.161 | 0.265 | 0.453 | 0.037 | 0.013 | 0.084 |
| Random (baseline) | 0.101 | 0.185 | 0.326 | 0.026 | 0.010 | 0.063 |
| **VodRec vs Popularity** | **3.5×** | **2.8×** | 2.0× | 5.7× | 8.5× | 4.1× |
| **VodRec vs Random** | **5.5×** | **4.0×** | 2.8× | 8.0× | 11× | 5.5× |

### Latência (CPU)

| Percentil | ms |
|---|---|
| P50 | 1.88 |
| P95 | 2.49 |
| P99 | 3.19 |
| Max | (≈3.5) |

Amostra de 200 inferências. **800× abaixo do orçamento de 2000ms** do RFIA02.

### Embeddings aprendidos (análise semântica)

Roda `scripts/analyze_embeddings.py`. Resultado no checkpoint atual:

| Métrica | Valor |
|---|---|
| Itens válidos | 400 |
| Norma média dos embeddings | 0.391 (std 0.019) |
| kNN intra-gênero @10 | **0.540** |
| Baseline aleatório | 0.068 |
| **Lift** | **7.92×** |

Conclusão: os embeddings agrupam itens do mesmo gênero **7.9× mais que aleatório**. O modelo aprendeu semântica de domínio. Plot: `reports/embeddings_visualization.png`.

---

## 2. VodChat (explicações em linguagem natural)

### Identificação

| Campo | Valor |
|---|---|
| Modelo base | TinyLlama-1.1B-Chat-v1.0 (open-source, **não treinado por nós**) |
| Técnica | LoRA (Low-Rank Adaptation), r=16, alpha=32 |
| Target modules | q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj |
| Dataset de fine-tuning | 3.000 exemplos sintéticos com 5 templates (`notebooks/07_vodchat_lora_finetune.ipynb`) |
| Quantização opcional | GGUF Q4_K_M via llama.cpp |

### Anti-alucinação

`app/models/vodchat_constraints.py`:
1. **TitleAnchoredLogitsProcessor** — penaliza continuações que não são prefixo de nenhum título do catálogo enquanto há aspas abertas.
2. **filter_unknown_titles** — substitui menções entre aspas/asteriscos que não casam com nenhum título por "um título do catálogo".

Validado por `tests/models/test_vodchat_constraints.py` (7 testes, todos passam).

### Posição honesta

VodChat **não é construído do zero**. É **adaptação de domínio** via LoRA sobre um modelo open-source. Para defesa em banca: apresente como "fine-tuning supervisionado sobre TinyLlama para conversação especializada em catálogo VOD".

---

## 3. Orchestrator + PopularityFallback

`app/models/orchestrator.py` decide qual modelo usar:

| `total_views` | Estratégia | Componente |
|---|---|---|
| 0 | `empty_history` | Retorna lista vazia (caller faz fallback) |
| 1–4 | `cold_start` | `PopularityFallback` |
| ≥ 5 | `vodrec` | VodRec-Transformer |

Atende **RFIA03** ("recomendação ativa após 5 conteúdos") sem ambiguidade.

`RecommendationOrchestrator.genre_weights_from_history()` deriva pesos por gênero a partir do histórico — atende **Seção 6** do PDF ("classificação de gostos pessoais") com uma representação interpretável para a UI.

---

## 4. Validação dos requisitos do PDF

Executar:
```bash
python scripts/validate_requirements.py
```

Saída atual (todos PASS):

```
[PASS] RFIA01 — Acuracia (HitRate@10 >= 0.70)
        measured_hr10: 0.7418
        vs_popularity: 2.80×
        vs_random: 4.01×

[PASS] RFIA02 — Latencia (P95 <= 2000 ms)
        measured_p95_ms: 2.49
        p50_ms: 1.88
        p99_ms: 3.19

[PASS] RFIA03 — Cold start (< 5 views usa PopularityFallback)
        threshold: 5
        empty_history_returns_empty: True
        below_threshold_uses_popularity: True
        above_threshold_uses_vodrec: True

[PASS] RFIA04 — Perfil atualizado a cada interacao
        before_top10 != after_top10 (overlap=1/10)
        reactive: True

[PASS] AUTH — Modelo construido (sem sklearn/implicit/transformers no nucleo)
        imports: ['torch', 'json', 'math', 'pathlib', 'typing', 'dataclasses']
```

---

## 5. Limitações conhecidas

1. **Cold start de itens novos**: conteúdos sem nenhuma visualização não têm embedding bem aprendido. Mitigação: PopularityFallback prioriza populares; periodicamente re-treinar o modelo inclui novos itens.
2. **Dataset sintético**: as métricas atuais foram medidas em dados sintéticos com bias controlado. Quando dados reais estiverem disponíveis, **re-treine antes de garantir RFIA01 em produção**.
3. **Filter bubble**: o modelo aprende a recomendar o que combina com o histórico — pode reforçar gostos existentes. Mitigação futura: diversification re-ranking (ainda não implementado).
4. **VodChat em CPU**: TinyLlama em CPU sem quantização gera ~2-5s para 100 tokens. Em produção, usar GGUF Q4_K_M (cabe nos 2s do RFIA02 mesmo com explicação).
5. **Dataset gerado com bias forte (85%)**: HR@10 = 0.74 em produção real costuma cair (literatura: 0.15-0.35 em catálogos reais). O threshold do RFIA01 (0.70) é generoso para o cenário sintético; para produção, considere reavaliar e tunar o modelo (mais camadas, mais épocas, mais dados).

---

## 6. Considerações éticas

- **Sem features sensíveis**: o modelo só usa `content_id` e tempo. Não usa gênero/idade/etnia do usuário.
- **Sem alucinação de catálogo**: VodChat tem constrained decoding para não inventar títulos.
- **Auditoria**: cada recomendação pode ser logada em `recommendation_events` para análise posterior.
- **Reprodutibilidade**: seeds fixos em `generate_dataset.py` e `train_and_evaluate.py`. Métricas em `models/vodrec/metrics.json`.

---

## 7. Reproduzir as métricas

```bash
# 1) Gerar dataset
python scripts/generate_dataset.py --n-users 1500 --n-contents 400 \
    --avg-interactions 50 --fav-bias 0.85 --seed 42 --out-dir data

# 2) Treinar
python scripts/train_and_evaluate.py --interactions data/interactions.parquet \
    --epochs 20 --d-model 128 --n-heads 4 --n-layers 3 --max-seq-len 80 \
    --batch-size 128 --lr 1e-3 --warmup-steps 100

# 3) Analisar embeddings
python scripts/analyze_embeddings.py

# 4) Validar requisitos
python scripts/validate_requirements.py

# 5) Rodar testes
pytest tests/models/test_vodrec_training.py tests/models/test_vodchat_constraints.py -v
```

Tempo total: ~3 minutos em CPU.
