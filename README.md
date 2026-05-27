# Plataforma VOD — Monorepo

Monorepo do Projeto Integrador V (PUC-Campinas) com três aplicações que
compartilham o mesmo Postgres:

```
.
├── apps/
│   ├── api/         FastAPI async — auth, catálogo, streaming, recomendações, chat
│   ├── ai/          FastAPI + PyTorch — VodRec-Transformer, VodChat, embeddings
│   └── analytics/   Jobs SQL/pandas — top vídeos, retenção, efetividade das recs
├── packages/
│   └── shared/      Schemas Pydantic compartilhados (vod_shared)
├── infra/
│   ├── docker-compose.yml
│   ├── api.Dockerfile          ← roda migrations automaticamente no boot
│   ├── ai.Dockerfile
│   ├── analytics.Dockerfile
│   └── entrypoint-api.sh       ← alembic upgrade head → uvicorn
├── docs/
│   ├── INTEGRACAO_USUARIO.md
│   └── INTEGRACAO_ADMIN.md
├── Makefile
└── .env.example
```

---

## Início rápido

```bash
cp .env.example .env
make setup          # sobe containers + seeds (~3-5 min, migrations automáticas)
```

Pronto. Não há passo manual de migration.

| Serviço | URL local |
|---|---|
| API (Swagger) | http://localhost:8001/docs |
| IA (info) | http://localhost:8002/api/v1/llm/info |
| Postgres | localhost:5432 |
| Redis | localhost:6379 |

**Credenciais de demo:**

| Perfil | Email | Senha |
|---|---|---|
| Admin | admin@streaming.com | admin123 |
| Usuário | demo@streaming.com | demo1234 |

---

## Arquitetura

```
                        ┌─────────────────────────────────┐
                        │            API (8001)            │
                        │  FastAPI async + SQLAlchemy      │
                        │                                  │
  Cliente ──────────────►  Auth · Vídeos · Favoritos      │
                        │  Recomendações · Chat · Busca    │
                        │                                  │
                        │  Cache Redis ◄──────────────┐   │
                        └──────────┬──────────────────┼───┘
                                   │ HTTP              │
                        ┌──────────▼──────────────┐   │
                        │      IA (8002)           │   │
                        │  FastAPI + PyTorch       │   │
                        │                          │   │
                        │  VodRec-Transformer      ├───┘
                        │  VodChat (TinyLlama LoRA)│
                        │  Embeddings semânticos   │
                        └──────────┬───────────────┘
                                   │
                        ┌──────────▼───────────────┐
                        │   Postgres 16 (único)    │
                        │   Redis 7                │
                        └──────────────────────────┘
```

### Fluxo de recomendação

```
GET /recommendations
  └── RecommendationService
        ├── [1] Redis cache hit? → retorna do banco sem recomputar (TTL 5 min)
        ├── [2] IA disponível? → AIClient → /llm/recommendations/{id}
        │         └── VodRec-Transformer → top-K (≥5 views) ou popularidade
        └── [3] Fallback clássico → scoring gênero/categoria/popularidade
```

### Fluxo de busca semântica

```
GET /videos/search?q=heroi+no+espaço&semantic=true
  └── VideoService._search_semantic()
        ├── AIClient.encode(q) → POST /embeddings/encode → vetor 384-dim
        └── VideoRepository.search_by_embedding() → pgvector <=> cosine
```

### Fluxo do chat

```
POST /chat  {"message": "..."}
  └── ChatRouter
        └── AIClient.chat() → POST /llm/chat/{user_id}
              └── VodChat (TinyLlama + LoRA) com histórico do usuário
```

---

## Funcionalidades de IA

| Feature | Onde mora | Como ativar |
|---|---|---|
| Recomendação VodRec | apps/ai | automático (≥5 views) |
| Recomendação clássica | apps/api | fallback sempre ativo |
| Cache de recomendações | Redis (API) | automático, TTL 5 min |
| Chat contextual (VodChat) | apps/ai | `VODCHAT_ENABLED=true` |
| Busca semântica | pgvector + apps/ai | indexar + `?semantic=true` |
| Explicação de recomendação | apps/ai | `with_explanation=true` |

### Ativar busca semântica

```bash
# 1. Rodar migration (cria extensão pgvector + coluna)
make db.migrate

# 2. Indexar vídeos (gera embeddings e salva no Postgres)
curl -X POST http://localhost:8002/api/v1/admin/index-embeddings \
  -H "X-AI-API-Key: $AI_API_KEY"

# 3. Buscar
GET /videos/search?q=aventura+no+espaço&semantic=true
```

---

## Stack

| Camada | Tecnologia | Detalhe |
|---|---|---|
| Banco | Postgres 16 | único banco — asyncpg na API, psycopg3 na IA |
| Busca semântica | pgvector | extensão Postgres, índice IVFFlat cosine |
| Cache | Redis 7 | recomendações (API) + inferências (IA) |
| API | FastAPI + SQLAlchemy 2 async | Alembic roda no boot via entrypoint |
| IA — recomendação | VodRec-Transformer (PyTorch puro) | decoder-only, treinado do zero |
| IA — chat/explicação | VodChat (TinyLlama + LoRA / GGUF) | suporte a GPU e CPU quantizado |
| IA — embeddings | sentence-transformers | `paraphrase-multilingual-MiniLM-L12-v2` (384 dims, suporta pt-BR) |
| Analytics | pandas + SQL | jobs CLI, gera CSV |
| Contratos | pydantic via `vod_shared` | evita drift entre apps |

---

## Variáveis de ambiente principais

| Variável | Quem usa | Descrição |
|---|---|---|
| `DATABASE_URL` | API, IA | Postgres compartilhado |
| `SECRET_KEY` | API | JWT — **deve ser igual a `JWT_SECRET` da IA** |
| `JWT_SECRET` | IA | mesmo valor de `SECRET_KEY` |
| `REDIS_URL` | API, IA | `redis://redis:6379/0` |
| `AI_SERVICE_URL` | API | onde a API encontra a IA |
| `AI_ENABLED` | API | desliga caminho LLM, usa só scoring clássico |
| `SEMANTIC_SEARCH_ENABLED` | API | habilita `?semantic=true` na busca |
| `VODCHAT_ENABLED` | IA | habilita VodChat (pesado em CPU sem GPU) |
| `RECS_CACHE_TTL` | API | TTL do cache de recomendações em segundos (default 300) |

Veja `.env.example` para a lista completa.

---

## Comandos úteis

```bash
make setup              # primeira vez: containers + migrations + seeds
make compose.up         # sobe stack (migrations automáticas no boot)
make compose.down       # derruba tudo
make compose.logs       # tails dos logs
make compose.analytics  # roda jobs analytics (oneshot)

make api.run            # uvicorn da API localmente (porta 8001)
make ai.run             # uvicorn da IA localmente (porta 8002)
make ai.train           # treina VodRec-Transformer
make ai.validate        # valida RFIA01-04

make db.migrate         # aplica migrations manualmente (dev local)
make db.revision NAME="descricao"  # nova migration

make test               # toda a suite pytest
make lint               # ruff em tudo
make format             # ruff format
```

---

## Documentação de integração

| Documento | Para quem |
|---|---|
| [docs/INTEGRACAO_USUARIO.md](docs/INTEGRACAO_USUARIO.md) | App do usuário final |
| [docs/INTEGRACAO_ADMIN.md](docs/INTEGRACAO_ADMIN.md) | Painel administrativo |
