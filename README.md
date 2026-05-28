# Plataforma VOD com Recomendação Inteligente

Monorepo do **Projeto Integrador V** (PUC-Campinas): plataforma de **Video on Demand (VOD)** com catálogo, streaming, histórico de visualização, favoritos, recomendações personalizadas (modelo de IA + fallback clássico), busca semântica e chatbot contextual.

Três aplicações compartilham o **mesmo PostgreSQL** e usam **Redis** para cache:

```
.
├── apps/
│   ├── api/         # FastAPI async — REST principal (auth, catálogo, streaming, recs, chat)
│   ├── ai/          # FastAPI + PyTorch — VodRec-Transformer, VodChat, embeddings
│   └── analytics/   # Jobs SQL/pandas — relatórios offline (CSV/JSON)
├── packages/
│   └── shared/      # Schemas Pydantic compartilhados (vod_shared)
├── infra/
│   ├── docker-compose.yml
│   ├── api.Dockerfile
│   ├── ai.Dockerfile
│   ├── analytics.Dockerfile
│   └── entrypoint-api.sh    # alembic upgrade head → uvicorn
├── docs/                    # Guias de integração para frontends
├── scripts/                 # Utilitários (ex.: otimização de vídeos)
├── Makefile
└── .env.example
```

---

## Índice

1. [Visão geral](#visão-geral)
2. [Início rápido](#início-rápido)
3. [Arquitetura](#arquitetura)
4. [Stack tecnológica](#stack-tecnológica)
5. [Modelo de dados](#modelo-de-dados)
6. [Categorias e gêneros](#categorias-e-gêneros)
7. [Autenticação e autorização](#autenticação-e-autorização)
8. [API principal (porta 8001)](#api-principal-porta-8001)
9. [Serviço de IA (porta 8002)](#serviço-de-ia-porta-8002)
10. [Analytics](#analytics)
11. [Variáveis de ambiente](#variáveis-de-ambiente)
12. [Comandos úteis](#comandos-úteis)
13. [Documentação adicional](#documentação-adicional)

---

## Visão geral

O sistema simula uma plataforma de streaming educacional/entretenimento com foco em conteúdo brasileiro. As principais capacidades são:


| Área                  | Descrição                                                                                                  |
| --------------------- | ---------------------------------------------------------------------------------------------------------- |
| **Usuários e planos** | Cadastro, login JWT, perfis `USER` e `ADMIN`, planos de assinatura (Basic, Standard, Premium no seed demo) |
| **Catálogo**          | Vídeos com título, descrição, URL, duração, gêneros, categorias, classificação etária                      |
| **Streaming**         | Servir MP4 locais com suporte a HTTP Range (`206 Partial Content`)                                         |
| **Engajamento**       | Sessões de watch, favoritos, log de interações (CLICK, SEARCH, WATCH, FAVORITE, UNFAVORITE)                |
| **Recomendações**     | VodRec-Transformer (IA) quando há histórico suficiente; fallback por scoring clássico; cache Redis 5 min   |
| **Busca**             | Texto + filtros por gênero/categoria; modo semântico via pgvector + embeddings                             |
| **Chat**              | VodChat (TinyLlama + LoRA) com histórico derivado das `watch_sessions`                                     |
| **Admin**             | CRUD de catálogo/taxonomia, relatórios de uso, listagem de interações, indexação de embeddings             |


**Dataset real:** ~49 vídeos em `apps/ai/data/raw/` (MP4 + `metadata.json`), ingeridos para `contents.parquet` e seedados no Postgres com UUIDs determinísticos (`UUID(int=content_id)`), alinhados ao vocabulário do VodRec.

---

## Início rápido

```bash
cp .env.example .env
make setup    # sobe Docker, migrations, seeds e indexação de embeddings (~3–5 min)
```


| Serviço               | URL local                                                                      |
| --------------------- | ------------------------------------------------------------------------------ |
| API (Swagger)         | [http://localhost:8001/docs](http://localhost:8001/docs)                       |
| IA (info dos modelos) | [http://localhost:8002/api/v1/llm/info](http://localhost:8002/api/v1/llm/info) |
| Postgres              | `localhost:5432`                                                               |
| Redis                 | `localhost:6379`                                                               |


### Credenciais de demonstração


| Perfil  | E-mail                | Senha      |
| ------- | --------------------- | ---------- |
| Admin   | `admin@streaming.com` | `admin123` |
| Usuário | `demo@streaming.com`  | `demo1234` |


### Autenticar no Swagger

1. `POST /auth/login` com e-mail e senha.
2. Copiar `access_token`.
3. Clicar em **Authorize** e informar: `Bearer <access_token>`.

---

## Arquitetura

```
                        ┌──────────────────────────────────────┐
                        │         API — apps/api (8001)         │
                        │  FastAPI + SQLAlchemy 2 (async)       │
                        │                                       │
  Cliente (web/mobile) ─┤  Auth · Vídeos · Favoritos · Planos   │
                        │  Recomendações · Chat · Relatórios    │
                        │                                       │
                        │  Cache Redis ◄────────────────────┐   │
                        └──────────────┬──────────────────┼───┘
                                       │ HTTP (JWT + API key) │
                        ┌──────────────▼──────────────────┐   │
                        │      IA — apps/ai (8002)       │   │
                        │  FastAPI + PyTorch             │   │
                        │                                │   │
                        │  VodRec-Transformer            ├───┘
                        │  VodChat (TinyLlama LoRA)      │
                        │  Embeddings (sentence-transformers)│
                        └──────────────┬───────────────────┘
                                       │
                        ┌──────────────▼───────────────────┐
                        │  Postgres 16 + pgvector            │
                        │  Redis 7                           │
                        └────────────────────────────────────┘

  Analytics (profile oneshot) ──► mesmo Postgres ──► CSV/JSON em reports/
```

### Fluxo de recomendação

```
GET /recommendations  (Bearer JWT)
  └── RecommendationService
        ├── [0] Redis: recomendações “frescas”? → retorna do banco (TTL 5 min)
        ├── [1] IA disponível? → GET /api/v1/llm/recommendations/{user_id}
        │         └── VodRec-Transformer (≥5 interações) ou popularidade
        └── [2] Fallback clássico → scoring gênero/categoria/popularidade/recência
```

### Fluxo de busca semântica

```
GET /videos/search?q=...&semantic=true
  └── VideoService
        ├── AIClient → GET /embeddings/encode?q=...
        └── VideoRepository.search_by_embedding()  (pgvector, cosine)
```

### Fluxo do chat

```
POST /chat  {"message": "..."}
  └── ChatRouter → AIClient → POST /llm/chat/{user_id}
        └── VodChat + histórico das watch_sessions
        └── Se IA falhar: resposta de fallback (HTTP 200, fallback=true)
```

### Boot da API (Docker)

`infra/entrypoint-api.sh` executa `alembic upgrade head` antes do Uvicorn — migrations automáticas no container.

---

## Stack tecnológica


| Camada            | Tecnologia                                          | Uso                                          |
| ----------------- | --------------------------------------------------- | -------------------------------------------- |
| Banco             | PostgreSQL 16 (`pgvector/pgvector`)                 | Dados transacionais + vetores 384-dim        |
| Cache             | Redis 7                                             | Recomendações (API), inferências (IA)        |
| API               | FastAPI 0.115, Uvicorn, SQLAlchemy 2 async, Alembic | REST principal                               |
| Auth              | python-jose (JWT HS256), passlib/bcrypt             | Access + refresh rotativo                    |
| HTTP cliente      | httpx                                               | Integração API → IA com circuit breaker      |
| IA — recomendação | VodRec-Transformer (PyTorch)                        | Sequência de visualizações → próximos vídeos |
| IA — chat         | VodChat (TinyLlama 1.1B + LoRA / GGUF opcional)     | Assistente contextual                        |
| IA — embeddings   | `paraphrase-multilingual-MiniLM-L12-v2`             | 384 dims, pt-BR                              |
| Busca vetorial    | pgvector (IVFFlat, distância cosseno)               | `videos.embedding`                           |
| Analytics         | pandas + SQL                                        | Jobs CLI exportáveis                         |
| Contratos         | `packages/shared` (Pydantic)                        | Evitar drift entre apps                      |
| Testes            | pytest, hypothesis, testcontainers                  | API e IA                                     |
| Qualidade         | ruff                                                | lint + format                                |


---

## Modelo de dados

Entidades principais (Postgres):


| Tabela             | Descrição                                                                      |
| ------------------ | ------------------------------------------------------------------------------ |
| `plans`            | Planos de assinatura (nome, descrição, preço)                                  |
| `users`            | Usuários (`role`: USER | ADMIN, `plan_id`, `is_active`)                        |
| `refresh_tokens`   | Hash SHA-256 do refresh token (rotação single-use)                             |
| `genres`           | Gêneros (N:N com vídeos via `video_genres`)                                    |
| `categories`       | Categorias editoriais (N:N via `video_categories`)                             |
| `videos`           | Catálogo; coluna `embedding` (vector 384) após indexação                       |
| `watch_sessions`   | Sessão de reprodução (`watch_time_seconds`, `percentage_watched`, `completed`) |
| `favorites`        | Favoritos por usuário/vídeo                                                    |
| `interaction_logs` | Telemetria: CLICK, SEARCH, WATCH, FAVORITE, UNFAVORITE                         |
| `recommendations`  | Recomendações materializadas (`relevance_score`, `explanation`)                |


Relacionamentos: um vídeo tem vários gêneros e categorias; um usuário tem muitas sessões, favoritos, interações e recomendações.

---

## Categorias e gêneros

### Categorias (dataset real)

No catálogo brasileiro (`apps/ai/scripts/ingest_real_dataset.py`), as categorias são **inferidas por heurística** a partir de título, tags e descrição:


| Categoria      | Exemplos de conteúdo                                       |
| -------------- | ---------------------------------------------------------- |
| **Natureza**   | Cachoeiras, Amazônia, Pantanal, animais                    |
| **Culinária**  | Receitas (brigadeiro, coxinha, feijoada, açaí)             |
| **Música**     | Samba, forró, bossa nova, funk                             |
| **Esporte**    | Futebol, vôlei, surf, capoeira, skate                      |
| **Turismo**    | Lençóis Maranhenses, Cristo Redentor, Ouro Preto, carnaval |
| **Tecnologia** | Python, IA, 5G, Excel, HTML/CSS                            |
| **Ciência**    | Chuva, vulcão, eclipse, sistema solar, experimentos        |
| **Arte**       | Aquarela, crochê, macramê, artesanato                      |
| **Saúde**      | Meditação, yoga, alongamento, saúde mental                 |
| **Educação**   | História do Brasil, explicações didáticas                  |
| **Cultura**    | Fallback amplo (temas brasileiros gerais)                  |
| **Outros**     | Quando nenhuma regra casa                                  |


O mapeamento slug → categoria também fica em `apps/ai/data/categories.json`.

### Gêneros

Gêneros vêm das **tags** de cada `metadata.json` no dataset (valores livres, únicos por nome no banco). Exemplos típicos: temas do vídeo original (documentário, tutorial, música, etc.).

### Seed sintético (`seed_data`)

Para ambiente sem parquet: 4 gêneros (Science Fiction, Drama, Comedy, Action) e 4 categorias (Documentary, Short Film, Series, Feature Film) + 5 vídeos de exemplo.

### Taxonomia via API

Admins podem criar/editar/remover categorias e gêneros pelos endpoints `/categories` e `/genres`. Usuários autenticados apenas listam.

---

## Autenticação e autorização

### Esquema JWT (API)


| Token       | Validade   | Claims principais                        | Uso                                                            |
| ----------- | ---------- | ---------------------------------------- | -------------------------------------------------------------- |
| **Access**  | 30 minutos | `sub` (user UUID), `role`, `type=access` | Header `Authorization: Bearer ...` em rotas protegidas         |
| **Refresh** | 7 dias     | `sub`, `type=refresh`, `jti`             | `POST /auth/refresh` — rotação: token antigo revogado no banco |


- Algoritmo: **HS256**
- Segredo: `SECRET_KEY` (API) = `JWT_SECRET` (IA) — **devem ser idênticos**
- Senhas: bcrypt via passlib
- Registro exige `plan_id` válido (corpo `UserCreate`)

### Papéis (`UserRole`)


| Papel     | Permissões                                                                                                 |
| --------- | ---------------------------------------------------------------------------------------------------------- |
| **USER**  | Catálogo, watch, favoritos, recomendações, chat, histórico, busca                                          |
| **ADMIN** | Tudo do USER + CRUD catálogo/taxonomia/planos, relatórios, interações, listar usuários, indexar embeddings |


### Rotas públicas (sem Bearer)


| Rota                            | Motivo                                                       |
| ------------------------------- | ------------------------------------------------------------ |
| `POST /auth/register`           | Cadastro                                                     |
| `POST /auth/login`              | Login                                                        |
| `POST /auth/refresh`            | Renovação                                                    |
| `GET /videos/{video_id}/stream` | Players HTML5 nem sempre enviam `Authorization` em `<video>` |


> Em produção, proteger streaming com token na query string ou cookie assinado.

### Serviço de IA


| Mecanismo          | Onde                                                                           |
| ------------------ | ------------------------------------------------------------------------------ |
| **JWT do usuário** | Endpoints `/llm/`* — mesmo token da API; usuário só acessa o próprio `user_id` |
| **X-AI-API-Key**   | Chamadas servidor-a-servidor (API → IA), admin IA (`/admin/`* na IA)           |
| **Admin JWT**      | `POST /admin/index-embeddings` na API (proxy para IA)                          |


### Formato de erro comum

- `401` — token inválido, expirado, usuário inativo ou refresh revogado
- `403` — papel insuficiente (ex.: USER em rota ADMIN)

### Paginação

Listagens paginadas retornam:

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 20,
  "total_pages": 0
}
```

Query params: `page` (≥1), `page_size` (1–100, padrão 20).

---

## API principal (porta 8001)

Base URL local: `http://localhost:8001`  
Documentação interativa: `/docs` e `/redoc`

Legenda de auth: **Público** | **User** | **Admin**

---

### Auth — prefixo `/auth`


| Método | Rota             | Auth    | Descrição                                                                                  |
| ------ | ---------------- | ------- | ------------------------------------------------------------------------------------------ |
| POST   | `/auth/register` | Público | Cria usuário (`name`, `email`, `password`, `plan_id`). Retorna `UserResponse` (201).       |
| POST   | `/auth/login`    | Público | Valida credenciais. Retorna `access_token`, `refresh_token`, `token_type=bearer`.          |
| POST   | `/auth/refresh`  | Público | Body: `{ "refresh_token": "..." }`. Emite novo par de tokens; invalida o refresh anterior. |


---

### Users — prefixo `/users`


| Método | Rota                          | Auth  | Descrição                                       |
| ------ | ----------------------------- | ----- | ----------------------------------------------- |
| GET    | `/users/me`                   | User  | Perfil do usuário autenticado.                  |
| GET    | `/users`                      | Admin | Lista usuários paginada.                        |
| PATCH  | `/users/{user_id}/deactivate` | Admin | Desativa conta (não pode desativar a si mesmo). |


---

### Videos — prefixo `/videos`


| Método | Rota                        | Auth    | Descrição                                                                                                                          |
| ------ | --------------------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| POST   | `/videos`                   | Admin   | Cria vídeo (título, descrição, url, duração, `genre_ids`, `category_ids`, opcional `release_date`, `age_rating` L/10/12/14/16/18). |
| GET    | `/videos`                   | User    | Lista catálogo paginado.                                                                                                           |
| GET    | `/videos/search`            | User    | Busca com `q`, `genre_id`, `category_id`, `semantic` (bool). Registra interação SEARCH se `q` informado.                           |
| GET    | `/videos/{video_id}/watch`  | User    | Detalhes para reprodução; cria `watch_session`; log CLICK.                                                                         |
| PUT    | `/videos/{video_id}`        | Admin   | Atualiza metadados do vídeo.                                                                                                       |
| DELETE | `/videos/{video_id}`        | Admin   | Remove vídeo (204).                                                                                                                |
| GET    | `/videos/{video_id}/stream` | Público | Stream MP4 com Range (206) ou arquivo completo (200). URL típica após seed: aponta para este endpoint.                             |


**Busca (`/videos/search`):**

- `semantic=false` (padrão): busca textual SQL (título/descrição) + filtros.
- `semantic=true`: requer `SEMANTIC_SEARCH_ENABLED=true` e embeddings indexados; usa similaridade vetorial.

---

### Genres — prefixo `/genres`


| Método | Rota                 | Auth  | Descrição               |
| ------ | -------------------- | ----- | ----------------------- |
| POST   | `/genres`            | Admin | Cria gênero (`name`).   |
| GET    | `/genres`            | User  | Lista gêneros paginada. |
| PUT    | `/genres/{genre_id}` | Admin | Renomeia gênero.        |
| DELETE | `/genres/{genre_id}` | Admin | Remove gênero (204).    |


---

### Categories — prefixo `/categories`


| Método | Rota                        | Auth  | Descrição                  |
| ------ | --------------------------- | ----- | -------------------------- |
| POST   | `/categories`               | Admin | Cria categoria (`name`).   |
| GET    | `/categories`               | User  | Lista categorias paginada. |
| PUT    | `/categories/{category_id}` | Admin | Atualiza nome.             |
| DELETE | `/categories/{category_id}` | Admin | Remove categoria (204).    |


---

### Plans — prefixo `/plans`


| Método | Rota               | Auth  | Descrição                                                   |
| ------ | ------------------ | ----- | ----------------------------------------------------------- |
| POST   | `/plans`           | Admin | Cria plano (`name`, `description`, `price`).                |
| GET    | `/plans`           | User  | Lista planos (necessário no registro para obter `plan_id`). |
| PUT    | `/plans/{plan_id}` | Admin | Atualiza plano.                                             |
| DELETE | `/plans/{plan_id}` | Admin | Remove plano (204).                                         |


---

### Favorites — prefixo `/favorites`


| Método | Rota                    | Auth | Descrição                              |
| ------ | ----------------------- | ---- | -------------------------------------- |
| POST   | `/favorites/{video_id}` | User | Adiciona favorito; log FAVORITE (201). |
| DELETE | `/favorites/{video_id}` | User | Remove favorito; log UNFAVORITE (204). |
| GET    | `/favorites`            | User | Lista favoritos do usuário paginada.   |


---

### Watch sessions — rotas na raiz


| Método | Rota                           | Auth | Descrição                                                                                                                      |
| ------ | ------------------------------ | ---- | ------------------------------------------------------------------------------------------------------------------------------ |
| GET    | `/watch-history`               | User | Histórico de sessões (`started_at`, `watch_time_seconds`, `percentage_watched`, vídeo).                                        |
| PATCH  | `/watch-sessions/{session_id}` | User | Atualiza `watch_time_seconds`; log WATCH; **invalida cache** de recomendações do usuário. Body: `{ "watch_time_seconds": N }`. |


> A sessão é criada automaticamente em `GET /videos/{id}/watch`.

---

### Recommendations


| Método | Rota                     | Auth  | Descrição                                                                                                                        |
| ------ | ------------------------ | ----- | -------------------------------------------------------------------------------------------------------------------------------- |
| GET    | `/recommendations`       | User  | Lista recomendações do usuário (`video_id`, `relevance_score`, `explanation`). Tenta IA → fallback clássico → persiste no banco. |
| GET    | `/admin/recommendations` | Admin | Todas as recomendações geradas (paginado).                                                                                       |


---

### Chat


| Método | Rota    | Auth | Descrição                                                                                                                                                |
| ------ | ------- | ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| POST   | `/chat` | User | Body: `{ "message": "..." }` (1–2000 chars). Resposta: `{ "reply": "...", "fallback": false }`. Se IA indisponível: `fallback=true` com mensagem padrão. |


---

### Admin — prefixo `/admin`


| Método | Rota                      | Auth  | Descrição                                                                                              |
| ------ | ------------------------- | ----- | ------------------------------------------------------------------------------------------------------ |
| GET    | `/admin/interactions`     | Admin | Lista logs de interação. Filtros: `user_id`, `interaction_type`, `video_id`, `start_date`, `end_date`. |
| POST   | `/admin/index-embeddings` | Admin | Dispara indexação semântica no serviço de IA (preenche `videos.embedding`).                            |


---

### Reports — prefixo `/admin/reports`

Todos exigem **Admin**. Filtros opcionais: `start_date`, `end_date` (ISO datetime).


| Método | Rota                            | Descrição                                               |
| ------ | ------------------------------- | ------------------------------------------------------- |
| GET    | `/admin/reports/usage`          | Métricas agregadas de uso no período (`UsageReport`).   |
| GET    | `/admin/reports/most-watched`   | Top vídeos por visualização (`limit` 1–100, padrão 10). |
| GET    | `/admin/reports/abandonment`    | Vídeos com maior taxa de abandono.                      |
| GET    | `/admin/reports/popular-genres` | Gêneros mais consumidos.                                |
| GET    | `/admin/reports/active-users`   | Usuários mais ativos.                                   |


---

## Serviço de IA (porta 8002)

Base URL: `http://localhost:8002/api/v1`  
Swagger: `http://localhost:8002/docs`

### LLM — prefixo `/api/v1/llm`


| Método | Rota                             | Auth                        | Descrição                                                                        |
| ------ | -------------------------------- | --------------------------- | -------------------------------------------------------------------------------- |
| GET    | `/llm/info`                      | Público                     | Status dos modelos VodRec/VodChat carregados.                                    |
| GET    | `/llm/recommendations/{user_id}` | JWT (próprio user ou admin) | Top-K do VodRec. Query: `k` (1–100), `with_explanation` (VodChat explica o top). |
| POST   | `/llm/chat/{user_id}`            | JWT                         | Chat VodChat. Body: `{ "message": "..." }`.                                      |


### Embeddings


| Método | Rota                       | Auth           | Descrição                                         |
| ------ | -------------------------- | -------------- | ------------------------------------------------- |
| GET    | `/embeddings/encode?q=...` | Público*       | Vetor 384-dim para texto (busca semântica).       |
| POST   | `/admin/index-embeddings`  | `X-AI-API-Key` | Indexa todos os vídeos sem embedding no Postgres. |


Na prática a API chama internamente com API key.

### Admin IA — prefixo `/api/v1/admin` (header `X-AI-API-Key`)


| Método | Rota                    | Descrição                                           |
| ------ | ----------------------- | --------------------------------------------------- |
| POST   | `/admin/reload-models`  | Recarrega VodRec/VodChat do disco.                  |
| POST   | `/admin/reload-catalog` | Recarrega catálogo em memória a partir do Postgres. |
| GET    | `/admin/model-version`  | Lê `VERSION.txt` dos artefatos.                     |


### Outros


| Método | Rota                         | Descrição                                                     |
| ------ | ---------------------------- | ------------------------------------------------------------- |
| GET    | `/health`                    | Health check detalhado (DB, Redis, modelos).                  |
| GET    | `/recommendations/{user_id}` | Recomendador clássico (TF-IDF/ALS) — legado, com cache Redis. |
| POST   | `/training`                  | Enfileira job de treino (API key).                            |
| GET    | `/training/status/{job_id}`  | Status do job de treino.                                      |


### Integração API → IA

O `AIClient` (`apps/api/app/integrations/ai_client.py`):

- Timeout ~2,5 s para recomendações (RFIA02)
- Circuit breaker: abre após 5 falhas, half-open em 30 s
- Repassa JWT do usuário nas rotas `/llm/`*
- Envia `X-AI-API-Key` quando configurado

---

## Analytics

App em `apps/analytics` — jobs **standalone** (sem cron embutido):

```bash
python -m analytics top_videos --days 30
python -m analytics retention --cohort-days 7
python -m analytics watch_funnel
python -m analytics churn_risk
python -m analytics rec_effectiveness
python -m analytics export_all
```

Via Docker:

```bash
make compose.analytics
```

Saídas em `apps/analytics/reports/`.

---

## Variáveis de ambiente

Veja `.env.example`. Principais:


| Variável                  | App                | Descrição                                        |
| ------------------------- | ------------------ | ------------------------------------------------ |
| `DATABASE_URL`            | API, IA, Analytics | Postgres (asyncpg na API, psycopg na IA)         |
| `SECRET_KEY`              | API                | JWT — **igual a `JWT_SECRET` na IA**             |
| `JWT_SECRET`              | IA                 | Mesmo valor de `SECRET_KEY`                      |
| `REDIS_URL`               | API, IA            | Cache                                            |
| `AI_SERVICE_URL`          | API                | Base da IA (ex.: `http://localhost:8002/api/v1`) |
| `AI_SERVICE_API_KEY`      | API                | Chave para chamadas à IA                         |
| `AI_ENABLED`              | API                | Se `false`, só recomendação clássica             |
| `SEMANTIC_SEARCH_ENABLED` | API                | Habilita `?semantic=true`                        |
| `RECS_CACHE_TTL`          | API                | TTL cache recomendações (s, padrão 300)          |
| `AI_API_KEY`              | IA                 | Protege rotas admin da IA                        |
| `LLM_ENABLED`             | IA                 | Carrega VodRec no boot                           |
| `VODCHAT_ENABLED`         | IA                 | Carrega VodChat (pesado em CPU)                  |
| `VODREC_MODEL_PATH`       | IA                 | Checkpoint PyTorch                               |
| `VIDEO_STORAGE_HOST_DIR`  | Docker             | Host path dos MP4 montado no container           |


---

## Comandos úteis

```bash
make help              # lista targets
make setup             # stack completa + seeds + embeddings
make compose.up        # sobe db + redis + api + ai
make compose.down
make compose.logs

make api.run           # API local :8001
make ai.run            # IA local :8002
make ai.train          # treina VodRec-Transformer
make ai.validate       # valida requisitos RFIA

make db.migrate        # alembic upgrade head (dev local)
make db.revision NAME="descricao"

make test              # pytest API + IA
make lint / make format
```

### Seeds manuais

```bash
docker compose -f infra/docker-compose.yml exec api python -m app.seeds.seed_real_catalog
docker compose -f infra/docker-compose.yml exec api python -m app.seeds.seed_demo_user
docker compose -f infra/docker-compose.yml exec api python -m app.seeds.update_video_urls_to_stream
```

### Ativar busca semântica manualmente

```bash
make db.migrate
# Como admin (via API):
curl -X POST http://localhost:8001/admin/index-embeddings \
  -H "Authorization: Bearer <access_token>"
```

---

## Funcionalidades de IA (resumo)


| Feature                | Onde          | Ativação                              |
| ---------------------- | ------------- | ------------------------------------- |
| Recomendação VodRec    | `apps/ai`     | Automático com histórico (IA no boot) |
| Recomendação clássica  | `apps/api`    | Fallback sempre ativo                 |
| Cache de recomendações | Redis (API)   | TTL 5 min (padrão)                    |
| Chat VodChat           | `apps/ai`     | `VODCHAT_ENABLED=true` (+ RAM/GPU)    |
| Busca semântica        | pgvector + IA | Indexar + `?semantic=true`            |
| Explicação de rec      | VodChat       | `with_explanation=true` na IA         |


---

## Documentação adicional


| Documento                                                | Público                       |
| -------------------------------------------------------- | ----------------------------- |
| [docs/INTEGRACAO_USUARIO.md](docs/INTEGRACAO_USUARIO.md) | App do usuário final          |
| [docs/INTEGRACAO_ADMIN.md](docs/INTEGRACAO_ADMIN.md)     | Painel administrativo         |
| [docs/INTEGRATION_FRONTS.md](docs/INTEGRATION_FRONTS.md) | Integração geral de frontends |
| [docs/NOVAS_FEATURES.md](docs/NOVAS_FEATURES.md)         | Features recentes             |
| [docs/APRESENTACAO_IA.md](docs/APRESENTACAO_IA.md)       | Apresentação dos modelos      |
| [apps/ai/README.md](apps/ai/README.md)                   | Detalhes do serviço de IA     |
| [apps/ai/docs/API.md](apps/ai/docs/API.md)               | Referência estendida da IA    |


---

## Licença e contexto acadêmico

Projeto acadêmico — PUC-Campinas, Projeto Integrador V. Para dúvidas de integração, consulte os guias em `docs/` e o Swagger em execução.