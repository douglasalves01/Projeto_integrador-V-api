# Novas Features — Evolução IA

Funcionalidades adicionadas na sprint de evolução de IA. Todas construídas sobre
a stack existente sem quebrar endpoints anteriores.

---

## 1. Cache de Recomendações (Redis)

**Endpoint afetado:** `GET /recommendations`

Antes, cada chamada recomputava o scoring completo. Agora:

1. Verifica flag no Redis (`api:recs:{user_id}`, TTL 5 min)
2. Se existe → retorna do banco sem reprocessar
3. Se não existe → computa, persiste e marca o cache

O cache é **invalidado automaticamente** ao chamar `PATCH /watch-sessions/{id}`.

**Configuração:**
```env
REDIS_URL=redis://localhost:6379/0
RECS_CACHE_TTL=300   # segundos
```

---

## 2. Fix de Performance — N+1 Queries

**Impacto interno** (sem mudança de contrato).

O scoring clássico de recomendação executava uma query SQL por sessão de watch
para calcular afinidade de gênero e categoria. Com 100 sessões = 200 queries extras.

Substituído por duas queries batch com `GROUP BY + JOIN`:

```
ANTES: 1 query por sessão × N sessões = N queries
DEPOIS: 1 query para todos os gêneros + 1 para todas as categorias = 2 queries
```

---

## 3. Chat com Assistente (VodChat)

**Endpoint novo:** `POST /chat`

Conversa com o VodChat (TinyLlama + LoRA), que conhece o catálogo e o histórico
do usuário. Requer autenticação.

**Request:**
```json
{
  "message": "Quais filmes de ação você me recomenda?"
}
```

**Response (200):**
```json
{
  "reply": "Com base no seu histórico, você pode gostar de 'Mad Max: Estrada da Fúria'...",
  "fallback": false
}
```

**Response quando IA indisponível:**
```json
{
  "reply": "Desculpe, o assistente está temporariamente indisponível.",
  "fallback": true
}
```

- Limite de 2000 caracteres por mensagem
- Stateless — cada chamada é independente
- Nunca retorna erro 5xx: falha silenciosa com `fallback: true`

---

## 4. Busca Semântica (pgvector)

**Endpoint afetado:** `GET /videos/search`

Novo parâmetro `semantic=true` ativa busca por significado em vez de substring.

```
GET /videos/search?q=heroi+viajando+no+tempo&semantic=true
```

Funciona mesmo que nenhum título contenha as palavras exatas. Se a IA estiver
indisponível, cai automaticamente na busca clássica por título.

**Pré-requisitos (one-time setup):**

```bash
# 1. Aplicar migration (cria extensão pgvector + coluna + índice)
make db.migrate

# 2. Indexar embeddings de todos os vídeos
curl -X POST http://localhost:8002/api/v1/admin/index-embeddings \
  -H "X-AI-API-Key: $AI_API_KEY"
```

Após criar novos vídeos, re-execute o índice para incluí-los.

**Como funciona:**
```
query do usuário
  └── AIClient.encode(q) → vetor 384-dim (sentence-transformers, pt-BR)
        └── VideoRepository.search_by_embedding()
              └── SELECT ... ORDER BY embedding <=> query_vector  (pgvector cosine)
```

---

## 5. Endpoint de Embeddings (serviço IA)

Dois novos endpoints no serviço IA (`http://localhost:8002/api/v1`):

### Gerar embedding de texto

```
GET /embeddings/encode?q=texto
```

**Response (200):**
```json
{
  "embedding": [0.023, -0.145, ...],
  "dim": 384
}
```

### Indexar vídeos no Postgres

```
POST /admin/index-embeddings
X-AI-API-Key: <AI_API_KEY>
```

**Response (200):**
```json
{
  "indexed": 49,
  "status": "ok"
}
```

Idempotente — ignora vídeos já indexados, processa só os novos.

---

## 6. Migrations Automáticas no Boot

Antes era necessário rodar `make db.migrate` manualmente após subir os containers.
Agora o container da API executa as migrations antes de iniciar o servidor.

**Fluxo do boot:**
```
docker compose up
  └── db healthy?
        └── redis healthy?
              └── alembic upgrade head   ← automático
                    └── uvicorn app.main:app
```

Se uma migration falhar, o container para com erro visível nos logs — comportamento
seguro que impede a API de subir com schema desatualizado.

---

## 7. Redis conectado na API (Docker)

O serviço `api` no `docker-compose.yml` agora:

- Recebe `REDIS_URL: redis://redis:6379/0` como variável de ambiente
- Aguarda o Redis estar saudável antes de iniciar (`depends_on: condition: service_healthy`)

Antes o Redis era usado apenas pelo serviço IA.
