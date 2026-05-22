# VOD AI Service

Microserviço de recomendação para streaming VOD: API FastAPI, modelos híbridos (content-based + ALS) e cache Redis.

> **Escopo:** este repositório é **somente o AI Service**. O backend Node.js fica em outro repositório; ver [docs/INTEGRATION_BACKEND.md](docs/INTEGRATION_BACKEND.md) para o contrato de integração.

## Stack

- **Python 3.11** · **FastAPI** · **SQLAlchemy** · **Redis** · **implicit ALS**
- **Prometheus** (`/metrics`) · **OpenTelemetry** (opcional) · **Loguru** (JSON estruturado)

## Execução local (Docker)

```bash
cp .env.example .env
docker compose up --build
```

Health check:

```bash
curl -s http://localhost:8000/health | jq
```

Documentação interativa: http://localhost:8000/docs

## Testes

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest
```

Com cobertura (como no CI):

```bash
pytest --cov=app --cov-report=term-missing --cov-fail-under=60
```

## Treino offline

Requer MySQL com dados de interação (`ViewHistory`, catálogo, etc.):

```bash
# Treino completo (content-based + ALS + métricas + VERSION.txt)
python scripts/train_offline.py --full

# Apenas content-based (sem ALS)
python scripts/train_offline.py --cb-only
```

Artefatos em `data/models/`:

- `content_based.pkl`, `als_model.pkl`
- `metrics.json`, `VERSION.txt`

## Avaliação

```bash
python scripts/evaluate.py
python scripts/evaluate.py --k 10 --test-ratio 0.2
```

Meta RFIA01: **HitRate@10 ≥ 0,70** no conjunto de teste.

## Arquitetura

Visão detalhada do pipeline ML, switching híbrido e integração: [docs/ARQUITETURA_IA.md](docs/ARQUITETURA_IA.md).

## API e documentação

- Especificação OpenAPI: `docs/openapi.json` (gerar com `python scripts/export_openapi.py`)
- Guia com exemplos `curl`: [docs/API.md](docs/API.md)
- Model card: [docs/MODEL_CARD.md](docs/MODEL_CARD.md)

## Endpoints (resumo)

| Método | Rota | Auth | Descrição |
|--------|------|------|-----------|
| `GET` | `/health` | — | Saúde (MySQL, Redis, modelos) |
| `GET` | `/metrics` | — | Métricas Prometheus |
| `GET` | `/api/v1/health` | — | Mesmo health sob prefixo |
| `GET` | `/api/v1/recommendations/{user_id}` | JWT | Recomendações personalizadas |
| `POST` | `/api/v1/profile/{user_id}/update` | JWT | Atualiza perfil após visualização |
| `POST` | `/api/v1/train` | `X-AI-API-Key` | Enfileira retreino offline |
| `GET` | `/api/v1/train/status/{job_id}` | `X-AI-API-Key` | Status do job de treino |

### Exemplos `curl`

Substitua `TOKEN` (JWT emitido pelo backend externo) e `AI_KEY` (`AI_API_KEY` no `.env`).

```bash
# Health
curl -s http://localhost:8000/health

# Métricas Prometheus
curl -s http://localhost:8000/metrics | head -20

# Recomendações (k=20)
curl -s -H "Authorization: Bearer TOKEN" \
  "http://localhost:8000/api/v1/recommendations/1?k=20"

# Atualizar perfil após visualização
curl -s -X POST -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content_id":4,"watched_sec":900,"total_sec":3600,"ended_at":"2026-05-22T12:00:00Z"}' \
  http://localhost:8000/api/v1/profile/1/update

# Enfileirar treino
curl -s -X POST -H "X-AI-API-Key: AI_KEY" \
  http://localhost:8000/api/v1/train

# Status do treino
curl -s -H "X-AI-API-Key: AI_KEY" \
  http://localhost:8000/api/v1/train/status/<job_id>
```

## Observabilidade

Cada requisição HTTP registra log JSON com `request_id`, `user_id` (quando autenticado), `latency_ms`, `method`, `path` e `status_code`. O header `X-Request-ID` é propagado na resposta.

| Recurso | Configuração |
|---------|----------------|
| Prometheus | `GET /metrics` — contadores, histograma de latência, gauge/info do modelo |
| OpenTelemetry | `OTEL_ENABLED=true`, `OTEL_EXPORTER_ENDPOINT`, `OTEL_SERVICE_NAME` |
| Erros | 500 sem stack trace em produção (`DEBUG=false`); 404 usuário/conteúdo; 504 timeout DB |

## Variáveis de ambiente

Ver `.env.example`. Principais:

| Variável | Descrição |
|----------|-----------|
| `DATABASE_URL` | MySQL (SQLAlchemy) |
| `REDIS_URL` | Cache de recomendações |
| `JWT_SECRET` | Validação JWT (mesmo segredo do backend externo) |
| `AI_API_KEY` | Treino via API |
| `MODEL_PATH` | Diretório dos `.pkl` |
| `OTEL_ENABLED` | Tracing OTLP HTTP |
| `DB_CONNECT_TIMEOUT` / `DB_POOL_TIMEOUT` | Timeouts MySQL |

## Qualidade de código

```bash
pip install pre-commit ruff mypy
pre-commit install
pre-commit run --all-files
```

## Estrutura

```
app/           # API, core, modelos ML, services
data/models/   # Artefatos treinados
scripts/       # train_offline, evaluate, export_openapi
tests/         # pytest + SQLite in-memory
docs/          # API, arquitetura, integração backend, model card
```

## Modelos LLM (VodRec + VodChat)

Modelos **construídos no projeto** (PyTorch + LoRA), sem API externa de LLM:

- **VodRec-Transformer** — ranking sequencial (`GET /api/v1/llm/recommendations/{user_id}`)
- **VodChat** — explicações e chat (`POST /api/v1/llm/chat/{user_id}`)

Arquitetura: [docs/ARQUITETURA_LLM.md](docs/ARQUITETURA_LLM.md) · Runbook: [docs/RUNBOOK.md](docs/RUNBOOK.md)

```bash
# Treino VodRec (batch)
python scripts/train_vodrec.py --interactions data/processed/interactions.parquet --output-dir models/vodrec

# Deploy + hot-reload
./scripts/deploy_models.sh vodrec-v1.0.0
```

O fallback clássico (TF-IDF + ALS) permanece em `/api/v1/recommendations` se `LLM_ENABLED=false` ou artefatos ausentes.

## Integração com o backend

O backend é mantido em **repositório separado**. Quando estiver no ar, use o guia [docs/INTEGRATION_BACKEND.md](docs/INTEGRATION_BACKEND.md) (endpoints `/llm/*`, JWT, checklist).

## Desenvolvimento sem Docker

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
