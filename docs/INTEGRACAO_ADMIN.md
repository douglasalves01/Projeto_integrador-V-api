# Guia de Integração — Painel Administrativo

## Visão Geral

Este documento descreve todos os endpoints disponíveis para o perfil **ADMIN**.
O admin gerencia conteúdo, usuários, planos, relatórios analíticos e controla
os modelos de IA (recomendação, chat, embeddings semânticos).

**Base URL da API:** `http://localhost:8001`  
**Base URL do serviço IA:** `http://localhost:8002/api/v1`  
**Documentação interativa:** `http://localhost:8001/docs`

---

## Autenticação

Todos os endpoints (exceto login) exigem:

```
Authorization: Bearer <access_token>
```

Endpoints do **serviço IA** com prefixo `/admin` exigem adicionalmente:

```
X-AI-API-Key: <AI_API_KEY>
```

### Login

```
POST /auth/login
```

**Body:**
```json
{
  "email": "admin@streaming.com",
  "password": "admin123"
}
```

**Resposta (200):**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

O `access_token` expira em **30 minutos**. Use `POST /auth/refresh` para renovar.

---

## Gerenciamento de Usuários

### Listar Usuários

```
GET /users?page=1&page_size=20
```

**Resposta (200):**
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "João Silva",
      "email": "joao@email.com",
      "role": "USER",
      "plan_id": "uuid",
      "is_active": true,
      "created_at": "2025-01-01T00:00:00"
    }
  ],
  "total": 50,
  "page": 1,
  "page_size": 20,
  "total_pages": 3
}
```

### Desativar Usuário

```
PATCH /users/{user_id}/deactivate
```

**Resposta (200):** objeto do usuário com `is_active: false`.

---

## Gerenciamento de Vídeos

### Criar Vídeo

```
POST /videos
```

**Body:**
```json
{
  "title": "Interestelar",
  "description": "Uma equipe de astronautas viaja por um buraco de minhoca...",
  "url": "https://cdn.example.com/interstelar.mp4",
  "duration_seconds": 9720,
  "genre_ids": ["uuid-ficcao-cientifica"],
  "category_ids": ["uuid-filmes"],
  "release_date": "2014-11-07",
  "age_rating": "12"
}
```

**Valores válidos para `age_rating`:** `L`, `10`, `12`, `14`, `16`, `18`

**Resposta (201):** objeto completo do vídeo com gêneros e categorias.

> Após criar vídeos novos, execute a **indexação de embeddings** para incluí-los
> na busca semântica (ver seção IA — Busca Semântica abaixo).

### Atualizar Vídeo

```
PUT /videos/{video_id}
```

**Body (todos os campos opcionais):**
```json
{
  "title": "Novo título",
  "description": "Nova descrição",
  "duration_seconds": 9800,
  "genre_ids": ["uuid-genero"],
  "category_ids": ["uuid-categoria"],
  "age_rating": "14"
}
```

### Deletar Vídeo

```
DELETE /videos/{video_id}
```

**Resposta:** `204 No Content`

---

## Gerenciamento de Gêneros

### Criar

```
POST /genres
```

**Body:** `{"name": "Ficção Científica"}`  
**Resposta (201):** `{"id": "uuid", "name": "Ficção Científica", "created_at": "...", "updated_at": "..."}`

### Atualizar

```
PUT /genres/{genre_id}
```

**Body:** `{"name": "Novo Nome"}`

### Deletar

```
DELETE /genres/{genre_id}
```

**Resposta:** `204 No Content`

---

## Gerenciamento de Categorias

### Criar

```
POST /categories
```

**Body:** `{"name": "Filmes"}`  
**Resposta (201):** `{"id": "uuid", "name": "Filmes", "created_at": "...", "updated_at": "..."}`

### Atualizar

```
PUT /categories/{category_id}
```

**Body:** `{"name": "Novo Nome"}`

### Deletar

```
DELETE /categories/{category_id}
```

**Resposta:** `204 No Content`

---

## Gerenciamento de Planos

### Criar

```
POST /plans
```

**Body:**
```json
{
  "name": "Premium",
  "description": "Acesso completo com qualidade 4K e múltiplas telas",
  "price": 49.90
}
```

### Atualizar

```
PUT /plans/{plan_id}
```

**Body (todos os campos opcionais):**
```json
{
  "name": "Enterprise",
  "description": "Plano corporativo",
  "price": 99.90
}
```

### Deletar

```
DELETE /plans/{plan_id}
```

**Resposta:** `204 No Content`

---

## Logs de Interação

```
GET /admin/interactions?page=1&page_size=20
```

**Filtros disponíveis:**

| Parâmetro          | Tipo     | Descrição                                            |
|--------------------|----------|------------------------------------------------------|
| `user_id`          | UUID     | Filtrar por usuário                                  |
| `interaction_type` | string   | `CLICK`, `WATCH`, `SEARCH`, `FAVORITE`, `UNFAVORITE` |
| `video_id`         | UUID     | Filtrar por vídeo                                    |
| `start_date`       | datetime | Data inicial (ISO 8601)                              |
| `end_date`         | datetime | Data final (ISO 8601)                                |

**Resposta (200):**
```json
{
  "items": [
    {
      "id": "uuid",
      "user_id": "uuid",
      "video_id": "uuid",
      "interaction_type": "SEARCH",
      "search_query": "heroi no espaço",
      "metadata": {"semantic": true},
      "created_at": "2025-01-01T12:00:00"
    }
  ],
  "total": 2500,
  "page": 1,
  "page_size": 20,
  "total_pages": 125
}
```

> O campo `metadata.semantic` indica se a busca foi semântica ou clássica —
> útil para medir adoção da feature de busca semântica.

---

## Recomendações (Visão Admin)

```
GET /admin/recommendations?page=1&page_size=20
```

**Resposta (200):**
```json
{
  "items": [
    {
      "id": "uuid",
      "user_id": "uuid",
      "video_id": "uuid",
      "relevance_score": 0.94,
      "explanation": "Recommended based on: genre affinity (Ficção Científica), popularity.",
      "created_at": "2025-01-01T00:00:00"
    }
  ],
  "total": 500,
  "page": 1,
  "page_size": 20,
  "total_pages": 25
}
```

> O campo `explanation` indica a origem: `"ai"` (VodRec-Transformer),
> `"cold_start"` (popularidade via IA), ou texto descritivo (scoring clássico).

---

## Relatórios Analíticos

Todos os relatórios aceitam `start_date` e `end_date` opcionais (ISO 8601).

### Relatório de Uso

```
GET /admin/reports/usage?start_date=2025-01-01T00:00:00&end_date=2025-12-31T23:59:59
```

**Resposta (200):**
```json
{
  "total_users": 150,
  "active_users": 120,
  "total_watch_sessions": 5000,
  "average_watch_time_seconds": 1800.5
}
```

### Vídeos Mais Assistidos

```
GET /admin/reports/most-watched?limit=10
```

**Resposta (200):**
```json
[
  {"video_id": "uuid", "title": "Interestelar", "count": 350}
]
```

### Taxa de Abandono por Vídeo

```
GET /admin/reports/abandonment?limit=10
```

**Resposta (200):**
```json
[
  {"video_id": "uuid", "title": "Vídeo Longo", "abandonment_rate": 0.75}
]
```

> `abandonment_rate` = proporção de sessões onde o usuário assistiu menos de 10%.
> Use este relatório para identificar conteúdos com problemas de engajamento.

### Gêneros Mais Populares

```
GET /admin/reports/popular-genres?limit=10
```

**Resposta (200):**
```json
[
  {"genre_id": "uuid", "name": "Ficção Científica", "total_watch_time_seconds": 86400}
]
```

### Usuários Mais Ativos

```
GET /admin/reports/active-users?limit=10
```

**Resposta (200):**
```json
[
  {"user_id": "uuid", "name": "João Silva", "email": "joao@email.com", "interaction_count": 250}
]
```

---

## IA — Busca Semântica (pgvector)

A busca semântica permite que usuários encontrem vídeos por significado, não
apenas por palavras exatas. Requer dois passos de configuração:

### 1. Aplicar migration do pgvector

```bash
make db.migrate
```

Isso cria a extensão `vector` no Postgres e adiciona a coluna
`description_embedding vector(384)` na tabela `videos`.

### 2. Indexar embeddings dos vídeos

```
POST http://localhost:8002/api/v1/admin/index-embeddings
X-AI-API-Key: <AI_API_KEY>
```

**Resposta (200):**
```json
{
  "indexed": 49,
  "status": "ok"
}
```

- Gera embeddings 384-dim para todos os vídeos ainda não indexados.
- Execute novamente após **criar novos vídeos** para incluí-los na busca.
- Vídeos já indexados são ignorados (idempotente).
- O modelo usado é `paraphrase-multilingual-MiniLM-L12-v2` (suporta português).

### Verificar status de indexação

Consulte quantos vídeos têm embedding via SQL:

```sql
SELECT COUNT(*) FROM videos WHERE description_embedding IS NOT NULL;
```

---

## IA — Modelos (Reload sem Restart)

Os modelos VodRec e VodChat podem ser atualizados em produção sem derrubar o
container. Todos os endpoints abaixo pertencem ao **serviço IA** e exigem
`X-AI-API-Key`.

### Ver informações dos modelos carregados

```
GET http://localhost:8002/api/v1/llm/info
```

**Resposta (200):**
```json
{
  "loaded": true,
  "vodrec": {
    "num_params": 2097152,
    "vocab_size": 410,
    "d_model": 128,
    "n_layers": 4,
    "n_heads": 4,
    "max_seq_len": 128
  },
  "vodchat": {
    "loaded": true,
    "backend": "transformers"
  }
}
```

### Recarregar modelos do disco

```
POST http://localhost:8002/api/v1/admin/reload-models
X-AI-API-Key: <AI_API_KEY>
```

Use após substituir os artefatos em `apps/ai/models/` sem reiniciar o container.

**Resposta (200):**
```json
{
  "status": "ok",
  "info": { "loaded": true, "vodrec": {...}, "vodchat": {...} }
}
```

### Recarregar catálogo de vídeos

```
POST http://localhost:8002/api/v1/admin/reload-catalog
X-AI-API-Key: <AI_API_KEY>
```

Atualiza os títulos e gêneros em memória usados pelo VodChat para gerar
explicações de recomendações. Execute após adicionar/modificar vídeos.

**Resposta (200):**
```json
{
  "status": "ok",
  "item_count": 49
}
```

### Ver versão dos artefatos

```
GET http://localhost:8002/api/v1/admin/model-version
X-AI-API-Key: <AI_API_KEY>
```

**Resposta (200):**
```json
{
  "vodrec_version": "vodrec-v1.0.0",
  "vodchat_version": null
}
```

---

## Fluxo de Operação — Dia a Dia

### Adicionar novos vídeos

```
1. POST /videos                              → cria o vídeo na API
2. POST /admin/index-embeddings (serviço IA) → indexa embedding para busca semântica
3. POST /admin/reload-catalog  (serviço IA)  → atualiza catálogo em memória do VodChat
```

### Atualizar modelo VodRec (após novo treinamento)

```bash
# 1. Treinar
make ai.train

# 2. Validar
make ai.validate

# 3. Recarregar sem downtime
curl -X POST http://localhost:8002/api/v1/admin/reload-models \
  -H "X-AI-API-Key: $AI_API_KEY"
```

### Monitorar saúde da stack

```bash
# Logs em tempo real
make compose.logs

# Saúde da API
curl http://localhost:8001/docs

# Saúde da IA + modelo carregado
curl http://localhost:8002/api/v1/llm/info

# Jobs de analytics (retention, top vídeos, efetividade das recs)
make compose.analytics
```

---

## Paginação

Todos os endpoints de listagem suportam:

| Parâmetro   | Padrão | Mínimo | Máximo |
|-------------|--------|--------|--------|
| `page`      | 1      | 1      | —      |
| `page_size` | 20     | 1      | 100    |

A resposta sempre inclui: `items`, `total`, `page`, `page_size`, `total_pages`.

---

## Códigos de Erro

| Código | Significado |
|--------|-------------|
| 401 | Token inválido, expirado, ou `X-AI-API-Key` incorreta |
| 403 | Permissão insuficiente (não é admin) |
| 404 | Recurso não encontrado |
| 409 | Conflito (ex: nome de gênero duplicado) |
| 422 | Dados de entrada inválidos |
| 503 | Serviço IA indisponível ou modelos não carregados |
| 500 | Erro interno do servidor |
