# Runbook — VOD AI Service (LLM + clássico)

## Treinar modelos

### VodRec-Transformer (batch)

```bash
# Exportar interações do MySQL para parquet (ou usar dump em data/raw/)
python scripts/train_vodrec.py \
  --interactions data/processed/interactions.parquet \
  --output-dir models/vodrec \
  --epochs 15
```

Meta: `HR@10 >= 0.65` em hold-out (ver `models/vodrec/metrics.json`).

### VodChat (LoRA)

Use o notebook `notebooks/07_vodchat_lora_finetune.ipynb` (GPU). Saída: `models/vodchat/vodchat-lora-final/`.

### Clássico (TF-IDF + ALS)

```bash
python scripts/train_offline.py --full
python scripts/evaluate.py --k 10
```

## Deploy

```bash
export VOD_AI_HOST=user@production
export VOD_ADMIN_KEY=<AI_API_KEY>
./scripts/deploy_models.sh vodrec-v1.1.0
```

O script envia `models/` para o servidor e chama `POST /api/v1/admin/reload-models`.

Alternativa manual:

```bash
docker compose restart ai-service
# ou
curl -X POST http://localhost:8000/api/v1/admin/reload-models \
  -H "X-AI-API-Key: $AI_API_KEY"
```

## Reverter versão anterior

1. Restaurar tarball anterior em `models/vodrec/` e `models/vodchat/`.
2. Ajustar `VERSION.txt` se necessário.
3. `POST /api/v1/admin/reload-models`.

Mantenha pelo menos duas versões em `incoming/` no servidor.

## Monitorar

| Sinal | Onde |
|-------|------|
| Latência HTTP | Logs JSON `latency_ms`, Prometheus histogram |
| Modelos carregados | `GET /health`, `GET /api/v1/llm/info` |
| HR@10 offline | `scripts/evaluate.py` (cron semanal) |
| HR@10 produção | Amostragem: comparar recs vs. próximas views (futuro) |

Alertas sugeridos:

- P95 `/llm/recommendations` > 2s (sem explanation)
- `vod_ai_model_loaded == 0` por > 5 min
- Falha no workflow `train-vodrec.yml`

## Troubleshooting

### LLM não carrega no startup

Log: `LLM models not loaded; classic recommender remains available`.

1. Verificar paths: `VODREC_MODEL_PATH`, `VODREC_VOCAB_PATH`.
2. Confirmar volume Docker: `./models:/app/models:ro`.
3. `LLM_ENABLED=true` no `.env`.
4. Testar: `curl /api/v1/llm/info` → `"loaded": false`.

### VodChat 503 no chat

- `VODCHAT_ENABLED=false` ou adapter ausente.
- GPU/RAM insuficiente — usar `VODCHAT_GGUF_PATH` + llama-cpp.

### Recomendações LLM vazias

- Usuário sem histórico → esperado; backend deve usar fallback popularidade.
- Catálogo desatualizado → `POST /api/v1/admin/reload-catalog`.

### Retreino CI falhou

Ver artifact `vodrec-models` no GitHub Actions e logs de `HitRate@10`.
