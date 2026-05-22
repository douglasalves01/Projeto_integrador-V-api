# Plataforma VOD — Monorepo

Monorepo do Projeto Integrador V (PUC-Campinas) com 3 aplicacoes que
compartilham o mesmo Postgres:

```
.
├── apps/
│   ├── api/         FastAPI + Postgres async (auth, usuarios, videos, recs)
│   ├── ai/          FastAPI + PyTorch — VodRec-Transformer e VodChat
│   └── analytics/   Jobs SQL/pandas (top videos, retention, efetividade das recs)
├── packages/
│   └── shared/      Schemas Pydantic compartilhados (vod_shared)
├── infra/
│   ├── docker-compose.yml
│   ├── api.Dockerfile
│   ├── ai.Dockerfile
│   └── analytics.Dockerfile
├── docs/
├── Makefile
└── .env.example
```

## Como sobe

```bash
cp .env.example .env
make install            # instala deps de todos os apps
make db.migrate         # alembic da API
make compose.up         # sobe db + api + ai
```

API em <http://localhost:8001>. IA em <http://localhost:8002>.

## Fluxo de uma recomendacao

```
Cliente → GET /recommendations         (API, port 8001)
            ↓
         RecommendationService
            ↓
         AIClient (com circuit breaker)
            ↓
         GET /llm/recommendations/{user_id}   (IA, port 8002)
            ↓
         VodRec-Transformer + (opcional) VodChat
            ↓
         Postgres ← le watch_sessions
            ↓
         resposta JSON com top-K
```

Se a IA falhar / timeout / circuito aberto, a API cai no algoritmo
classico (genero/categoria/popularidade) — usuario nao percebe.

## Stack

| Camada | Tecnologia | Por que |
|---|---|---|
| Banco unico | Postgres 16 (asyncpg na API, psycopg3 na IA) | Sem duplicacao de dados; um schema, um alembic |
| Cache | Redis 7 | Cache de inferencias da IA |
| API | FastAPI + SQLAlchemy 2 async + Alembic | Padrao moderno |
| IA | FastAPI + PyTorch puro | VodRec-Transformer treinado do zero |
| Analytics | pandas + SQL via psycopg3 | Jobs CLI, gera CSV |
| Contratos | pydantic via `vod_shared` | Evita drift entre apps |

## Comandos uteis (Makefile)

```bash
make api.run            # uvicorn da API
make ai.run             # uvicorn da IA
make ai.train           # treina VodRec
make ai.validate        # valida RFIA01-04
make analytics.run      # roda todos os jobs analiticos
make test               # roda todos os pytests
make lint               # ruff em tudo
make compose.up         # docker compose
make compose.analytics  # roda jobs analytics dentro do compose
```

## Variaveis de ambiente

Veja `.env.example`. As principais:
- `DATABASE_URL` — Postgres compartilhado
- `SECRET_KEY` / `JWT_SECRET` — **devem ser iguais** entre API e IA (a IA
  valida os JWTs que a API emite)
- `AI_SERVICE_URL` — onde a API encontra a IA (default `http://ai:8000`)
- `AI_ENABLED` — desliga o caminho LLM e usa so o scoring classico
- `VODCHAT_ENABLED` — liga/desliga o LLM textual (pesado em CPU)
