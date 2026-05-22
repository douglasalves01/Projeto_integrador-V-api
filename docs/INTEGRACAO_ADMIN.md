# Guia de Integração — Painel Administrativo

## Visão Geral

Este documento descreve todos os endpoints disponíveis para o perfil **ADMIN** na API de Streaming. O admin tem acesso completo ao gerenciamento de conteúdo, usuários e relatórios analíticos.

**Base URL:** `http://localhost:8000`

---

## Autenticação

Todos os endpoints (exceto login/register) exigem o header:

```
Authorization: Bearer <access_token>
```

### Login

```
POST /auth/login
```

**Body:**
```json
{
  "email": "admin@example.com",
  "password": "senha_segura"
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

### Refresh Token

```
POST /auth/refresh
```

**Body:**
```json
{
  "refresh_token": "eyJ..."
}
```

**Resposta (200):** Mesmo formato do login.

> O `access_token` expira em **30 minutos**. O `refresh_token` expira em **7 dias**.

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

**Resposta (200):** Retorna o objeto do usuário com `is_active: false`.

---

## Gerenciamento de Vídeos

### Criar Vídeo

```
POST /videos
```

**Body:**
```json
{
  "title": "Introdução ao Python",
  "description": "Aula introdutória sobre Python",
  "url": "https://cdn.example.com/video1.mp4",
  "duration_seconds": 3600,
  "genre_ids": ["uuid-genero-1", "uuid-genero-2"],
  "category_ids": ["uuid-categoria-1"],
  "release_date": "2025-06-15",
  "age_rating": "L"
}
```

**Valores válidos para `age_rating`:** `L`, `10`, `12`, `14`, `16`, `18`

**Resposta (201):**
```json
{
  "id": "uuid",
  "title": "Introdução ao Python",
  "description": "Aula introdutória sobre Python",
  "url": "https://cdn.example.com/video1.mp4",
  "duration_seconds": 3600,
  "release_date": "2025-06-15",
  "age_rating": "L",
  "genres": [{"id": "uuid", "name": "Educação"}],
  "categories": [{"id": "uuid", "name": "Programação"}],
  "created_at": "2025-01-01T00:00:00",
  "updated_at": "2025-01-01T00:00:00"
}
```

### Atualizar Vídeo

```
PUT /videos/{video_id}
```

**Body (todos os campos são opcionais):**
```json
{
  "title": "Novo título",
  "description": "Nova descrição",
  "url": "https://cdn.example.com/video1-v2.mp4",
  "duration_seconds": 4200,
  "genre_ids": ["uuid-genero-1"],
  "category_ids": ["uuid-categoria-1", "uuid-categoria-2"],
  "release_date": "2025-07-01",
  "age_rating": "12"
}
```

### Deletar Vídeo

```
DELETE /videos/{video_id}
```

**Resposta:** `204 No Content`

---

## Gerenciamento de Gêneros

### Criar Gênero

```
POST /genres
```

**Body:**
```json
{
  "name": "Ação"
}
```

**Resposta (201):**
```json
{
  "id": "uuid",
  "name": "Ação",
  "created_at": "2025-01-01T00:00:00",
  "updated_at": "2025-01-01T00:00:00"
}
```

### Atualizar Gênero

```
PUT /genres/{genre_id}
```

**Body:**
```json
{
  "name": "Aventura"
}
```

### Deletar Gênero

```
DELETE /genres/{genre_id}
```

**Resposta:** `204 No Content`

---

## Gerenciamento de Categorias

### Criar Categoria

```
POST /categories
```

**Body:**
```json
{
  "name": "Programação"
}
```

**Resposta (201):**
```json
{
  "id": "uuid",
  "name": "Programação",
  "created_at": "2025-01-01T00:00:00",
  "updated_at": "2025-01-01T00:00:00"
}
```

### Atualizar Categoria

```
PUT /categories/{category_id}
```

**Body:**
```json
{
  "name": "DevOps"
}
```

### Deletar Categoria

```
DELETE /categories/{category_id}
```

**Resposta:** `204 No Content`

---

## Gerenciamento de Planos

### Criar Plano

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

**Resposta (201):**
```json
{
  "id": "uuid",
  "name": "Premium",
  "description": "Acesso completo com qualidade 4K e múltiplas telas",
  "price": 49.90,
  "created_at": "2025-01-01T00:00:00",
  "updated_at": "2025-01-01T00:00:00"
}
```

### Atualizar Plano

```
PUT /plans/{plan_id}
```

**Body (todos os campos são opcionais):**
```json
{
  "name": "Enterprise",
  "description": "Plano corporativo com recursos ilimitados",
  "price": 99.90
}
```

### Deletar Plano

```
DELETE /plans/{plan_id}
```

**Resposta:** `204 No Content`

---

## Logs de Interação

### Listar Interações

```
GET /admin/interactions?page=1&page_size=20
```

**Parâmetros de filtro (opcionais):**

| Parâmetro         | Tipo     | Descrição                                      |
|-------------------|----------|------------------------------------------------|
| `user_id`         | UUID     | Filtrar por usuário                            |
| `interaction_type`| string   | Tipo: CLICK, WATCH, SEARCH, FAVORITE, UNFAVORITE |
| `video_id`        | UUID     | Filtrar por vídeo                              |
| `start_date`      | datetime | Data inicial (ISO 8601)                        |
| `end_date`        | datetime | Data final (ISO 8601)                          |

**Resposta (200):**
```json
{
  "items": [
    {
      "id": "uuid",
      "user_id": "uuid",
      "video_id": "uuid",
      "interaction_type": "CLICK",
      "search_query": null,
      "metadata": null,
      "created_at": "2025-01-01T12:00:00"
    }
  ],
  "total": 100,
  "page": 1,
  "page_size": 20,
  "total_pages": 5
}
```

---

## Recomendações (Visão Admin)

### Listar Todas as Recomendações

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
      "relevance_score": 0.95,
      "explanation": "Baseado no histórico de visualização",
      "created_at": "2025-01-01T00:00:00"
    }
  ],
  "total": 200,
  "page": 1,
  "page_size": 20,
  "total_pages": 10
}
```

---

## Relatórios Analíticos

Todos os relatórios aceitam os parâmetros opcionais `start_date` e `end_date` (formato ISO 8601).

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
  {
    "video_id": "uuid",
    "title": "Introdução ao Python",
    "count": 350
  }
]
```

### Taxa de Abandono

```
GET /admin/reports/abandonment?limit=10
```

**Resposta (200):**
```json
[
  {
    "video_id": "uuid",
    "title": "Vídeo Longo",
    "abandonment_rate": 0.75
  }
]
```

### Gêneros Mais Populares

```
GET /admin/reports/popular-genres?limit=10
```

**Resposta (200):**
```json
[
  {
    "genre_id": "uuid",
    "name": "Ação",
    "total_watch_time_seconds": 86400
  }
]
```

### Usuários Mais Ativos

```
GET /admin/reports/active-users?limit=10
```

**Resposta (200):**
```json
[
  {
    "user_id": "uuid",
    "name": "João Silva",
    "email": "joao@email.com",
    "interaction_count": 250
  }
]
```

---

## Códigos de Erro Comuns

| Código | Significado                          |
|--------|--------------------------------------|
| 401    | Token inválido ou expirado           |
| 403    | Permissão insuficiente (não é admin) |
| 404    | Recurso não encontrado               |
| 409    | Conflito (ex: email duplicado)       |
| 422    | Dados de entrada inválidos           |
| 500    | Erro interno do servidor             |

---

## Paginação

Todos os endpoints de listagem suportam paginação:

| Parâmetro   | Padrão | Mínimo | Máximo |
|-------------|--------|--------|--------|
| `page`      | 1      | 1      | —      |
| `page_size` | 20     | 1      | 100    |

A resposta paginada sempre inclui: `items`, `total`, `page`, `page_size`, `total_pages`.
