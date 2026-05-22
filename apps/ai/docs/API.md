# API — VOD AI Service

Base URL local: `http://localhost:8000`

- **OpenAPI JSON:** [openapi.json](./openapi.json) (regenerar: `python scripts/export_openapi.py`)
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

## Autenticação

| Tipo | Header | Rotas |
|------|--------|-------|
| JWT (usuário) | `Authorization: Bearer <token>` | `/api/v1/recommendations/*`, `/api/v1/profile/*` |
| API Key (ops) | `X-AI-API-Key: <AI_API_KEY>` | `/api/v1/train*` |

O JWT deve conter `sub` ou `user_id` (mesmo segredo `JWT_SECRET` do backend externo). Ver [INTEGRATION_BACKEND.md](./INTEGRATION_BACKEND.md).

## Endpoints

### Observabilidade

#### `GET /metrics`

Métricas Prometheus (text/plain).

```bash
curl -s http://localhost:8000/metrics | head -30
```

Métricas expostas:

- `vod_ai_http_requests_total{method,path,status}`
- `vod_ai_http_request_duration_seconds_bucket{method,path,le}`
- `vod_ai_model_loaded`
- `vod_ai_model_info{version,loaded}`

#### `GET /health` e `GET /api/v1/health`

Status de MySQL, Redis e modelos carregados.

```bash
curl -s http://localhost:8000/health | jq
```

Resposta (exemplo):

```json
{
  "status": "healthy",
  "service": "vod-ai-service",
  "model_version": "hybrid-v1.0.0",
  "models_loaded": true,
  "mysql": {"status": "up"},
  "redis": {"status": "up"}
}
```

### Recomendações

#### `GET /api/v1/recommendations/{user_id}?k=20`

| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|--------|-----------|
| `user_id` | path int | — | ID do usuário (deve coincidir com o JWT) |
| `k` | query int | 20 | Quantidade de itens (1–100) |

```bash
export TOKEN="<jwt>"
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/recommendations/1?k=10" | jq
```

Resposta 200 (`RecommendationResponse`):

```json
{
  "user_id": 1,
  "model_version": "hybrid-v1.0.0",
  "strategy": "transition",
  "total_views": 12,
  "generated_at": "2026-05-22T15:00:00Z",
  "recommendations": [
    {"content_id": 4, "score": 0.82, "reason": "Similar ao seu histórico em Ação"}
  ]
}
```

Erros comuns:

| Status | Causa |
|--------|-------|
| 401 | Token inválido ou ausente |
| 403 | `user_id` diferente do token |
| 404 | Usuário não existe |
| 503 | Modelos não carregados |

### Perfil

#### `POST /api/v1/profile/{user_id}/update`

Body (`InteractionUpdate`):

```json
{
  "content_id": 4,
  "watched_sec": 900,
  "total_sec": 3600,
  "ended_at": "2026-05-22T12:00:00Z"
}
```

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content_id":4,"watched_sec":900,"total_sec":3600,"ended_at":"2026-05-22T12:00:00Z"}' \
  http://localhost:8000/api/v1/profile/1/update | jq
```

Invalida cache `recs:{user_id}:*` no Redis.

### Treino (batch)

#### `POST /api/v1/train`

Enfileira retreino offline (background).

```bash
export AI_KEY="<AI_API_KEY>"
curl -s -X POST -H "X-AI-API-Key: $AI_KEY" \
  http://localhost:8000/api/v1/train | jq
```

Resposta:

```json
{"status": "queued", "job_id": "a1b2c3d4-..."}
```

#### `GET /api/v1/train/status/{job_id}`

```bash
curl -s -H "X-AI-API-Key: $AI_KEY" \
  http://localhost:8000/api/v1/train/status/<job_id> | jq
```

## Headers de rastreamento

| Header | Direção | Descrição |
|--------|---------|-----------|
| `X-Request-ID` | Request (opcional) / Response | Correlaciona logs e traces |
| `Authorization` | Request | JWT Bearer |
| `X-AI-API-Key` | Request | Chave de treino |

## Códigos de erro globais

| Status | `detail` típico |
|--------|-----------------|
| 404 | `User {id} not found` / `Content {id} not found` |
| 500 | `Internal server error` (sem stack trace se `DEBUG=false`) |
| 504 | `Database operation timed out` |

## LLM (VodRec + VodChat)

Prefixo: `/api/v1/llm`

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/llm/recommendations/{user_id}?k=20&with_explanation=false` | Ranking VodRec-Transformer |
| `POST` | `/llm/chat/{user_id}` | Chat VodChat (`{"message": "..."}`) |
| `GET` | `/llm/info` | Metadados dos modelos LLM carregados |

```bash
# Recomendações LLM (<2s sem explanation)
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/llm/recommendations/1?k=10"

# Com explicação VodChat (3–5s — usar em background na UI)
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/llm/recommendations/1?k=10&with_explanation=true"

# Chat
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"Quero um filme de ação leve"}' \
  http://localhost:8000/api/v1/llm/chat/1

curl -s http://localhost:8000/api/v1/llm/info | jq
```

## Admin (hot-reload)

| Método | Rota | Auth |
|--------|------|------|
| `POST` | `/api/v1/admin/reload-models` | `X-AI-API-Key` |
| `POST` | `/api/v1/admin/reload-catalog` | `X-AI-API-Key` |
| `GET` | `/api/v1/admin/model-version` | `X-AI-API-Key` |

## OpenTelemetry

Com `OTEL_ENABLED=true`, spans HTTP são exportados para `OTEL_EXPORTER_ENDPOINT` (OTLP HTTP). Endpoints `/metrics` e `/health` são excluídos do auto-instrumentação.
