# Guia de Integração — Aplicação do Usuário

## Visão Geral

Este documento descreve todos os endpoints disponíveis para o perfil **USER** na API de Streaming. O usuário pode se registrar, navegar pelo catálogo, assistir vídeos, gerenciar favoritos e receber recomendações personalizadas.

**Base URL:** `http://localhost:8000`

---

## Autenticação

### Registro

```
POST /auth/register
```

**Body:**
```json
{
  "name": "Maria Souza",
  "email": "maria@email.com",
  "password": "minha_senha_segura",
  "plan_id": "uuid-do-plano"
}
```

**Validações:**
- `name`: 1 a 100 caracteres
- `email`: formato válido de email
- `password`: 8 a 128 caracteres
- `plan_id`: UUID de um plano existente

**Resposta (201):**
```json
{
  "id": "uuid",
  "name": "Maria Souza",
  "email": "maria@email.com",
  "role": "USER",
  "plan_id": "uuid-do-plano",
  "is_active": true,
  "created_at": "2025-01-01T00:00:00"
}
```

### Login

```
POST /auth/login
```

**Body:**
```json
{
  "email": "maria@email.com",
  "password": "minha_senha_segura"
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

> O `access_token` expira em **30 minutos**. Use o refresh token para obter novos tokens sem precisar fazer login novamente. O `refresh_token` expira em **7 dias**.

---

## Header de Autenticação

Todos os endpoints abaixo exigem:

```
Authorization: Bearer <access_token>
```

---

## Perfil do Usuário

### Ver Meu Perfil

```
GET /users/me
```

**Resposta (200):**
```json
{
  "id": "uuid",
  "name": "Maria Souza",
  "email": "maria@email.com",
  "role": "USER",
  "plan_id": "uuid-do-plano",
  "is_active": true,
  "created_at": "2025-01-01T00:00:00"
}
```

---

## Catálogo de Vídeos

### Listar Vídeos

```
GET /videos?page=1&page_size=20
```

**Resposta (200):**
```json
{
  "items": [
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
  ],
  "total": 100,
  "page": 1,
  "page_size": 20,
  "total_pages": 5
}
```

### Buscar Vídeos

```
GET /videos/search?q=python&genre_id=uuid&category_id=uuid&page=1&page_size=20
```

**Parâmetros (todos opcionais):**

| Parâmetro     | Tipo   | Descrição                    |
|---------------|--------|------------------------------|
| `q`           | string | Texto de busca (título)      |
| `genre_id`    | UUID   | Filtrar por gênero           |
| `category_id` | UUID   | Filtrar por categoria        |

**Resposta (200):** Mesmo formato da listagem de vídeos.

> A busca registra automaticamente uma interação do tipo `SEARCH` quando o parâmetro `q` é informado.

### Assistir Vídeo

```
GET /videos/{video_id}/watch
```

**Resposta (200):**
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

> Este endpoint cria automaticamente uma sessão de visualização e registra uma interação do tipo `CLICK`.

---

## Sessões de Visualização

### Histórico de Visualização

```
GET /watch-history?page=1&page_size=20
```

**Resposta (200):**
```json
{
  "items": [
    {
      "id": "uuid",
      "user_id": "uuid",
      "video_id": "uuid",
      "started_at": "2025-01-01T12:00:00",
      "watch_time_seconds": 1200,
      "percentage_watched": 33.3,
      "completed": false,
      "abandoned": false,
      "updated_at": "2025-01-01T12:20:00"
    }
  ],
  "total": 25,
  "page": 1,
  "page_size": 20,
  "total_pages": 2
}
```

### Atualizar Progresso de Visualização

```
PATCH /watch-sessions/{session_id}
```

**Body:**
```json
{
  "watch_time_seconds": 1800
}
```

**Resposta (200):**
```json
{
  "id": "uuid",
  "user_id": "uuid",
  "video_id": "uuid",
  "started_at": "2025-01-01T12:00:00",
  "watch_time_seconds": 1800,
  "percentage_watched": 50.0,
  "completed": false,
  "abandoned": false,
  "updated_at": "2025-01-01T12:30:00"
}
```

> Envie atualizações periódicas do tempo assistido para manter o progresso do usuário sincronizado. Uma interação do tipo `WATCH` é registrada automaticamente.

---

## Favoritos

### Adicionar Favorito

```
POST /favorites/{video_id}
```

**Resposta (201):**
```json
{
  "id": "uuid",
  "user_id": "uuid",
  "video_id": "uuid",
  "created_at": "2025-01-01T00:00:00"
}
```

### Remover Favorito

```
DELETE /favorites/{video_id}
```

**Resposta:** `204 No Content`

### Listar Favoritos

```
GET /favorites?page=1&page_size=20
```

**Resposta (200):**
```json
{
  "items": [
    {
      "id": "uuid",
      "user_id": "uuid",
      "video_id": "uuid",
      "created_at": "2025-01-01T00:00:00"
    }
  ],
  "total": 10,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

---

## Recomendações

### Obter Recomendações Personalizadas

```
GET /recommendations
```

**Resposta (200):**
```json
[
  {
    "id": "uuid",
    "user_id": "uuid",
    "video_id": "uuid",
    "relevance_score": 0.95,
    "explanation": "Baseado no seu histórico de visualização de vídeos de Programação",
    "created_at": "2025-01-01T00:00:00"
  }
]
```

> As recomendações são geradas com base no histórico de interações do usuário (visualizações, buscas, favoritos).

---

## Gêneros e Categorias (Consulta)

### Listar Gêneros

```
GET /genres?page=1&page_size=20
```

**Resposta (200):**
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Ação",
      "created_at": "2025-01-01T00:00:00",
      "updated_at": "2025-01-01T00:00:00"
    }
  ],
  "total": 15,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

### Listar Categorias

```
GET /categories?page=1&page_size=20
```

**Resposta (200):**
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Programação",
      "created_at": "2025-01-01T00:00:00",
      "updated_at": "2025-01-01T00:00:00"
    }
  ],
  "total": 8,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

---

## Planos (Consulta)

### Listar Planos Disponíveis

```
GET /plans?page=1&page_size=20
```

**Resposta (200):**
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Premium",
      "description": "Acesso completo com qualidade 4K e múltiplas telas",
      "price": 49.90,
      "created_at": "2025-01-01T00:00:00",
      "updated_at": "2025-01-01T00:00:00"
    }
  ],
  "total": 3,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

> Use a listagem de planos para exibir as opções disponíveis na tela de registro.

---

## Fluxo Típico de Uso

```
1. GET /plans              → Listar planos disponíveis
2. POST /auth/register     → Criar conta com plano escolhido
3. POST /auth/login        → Obter tokens
4. GET /videos             → Navegar catálogo
5. GET /videos/search?q=   → Buscar vídeos
6. GET /videos/{id}/watch  → Iniciar visualização
7. PATCH /watch-sessions/{id} → Atualizar progresso
8. POST /favorites/{id}    → Favoritar vídeo
9. GET /recommendations    → Ver recomendações
10. GET /watch-history     → Consultar histórico
```

---

## Códigos de Erro Comuns

| Código | Significado                        |
|--------|------------------------------------|
| 401    | Token inválido ou expirado         |
| 404    | Recurso não encontrado             |
| 409    | Conflito (ex: email já cadastrado) |
| 422    | Dados de entrada inválidos         |
| 500    | Erro interno do servidor           |

---

## Paginação

Todos os endpoints de listagem suportam paginação:

| Parâmetro   | Padrão | Mínimo | Máximo |
|-------------|--------|--------|--------|
| `page`      | 1      | 1      | —      |
| `page_size` | 20     | 1      | 100    |

A resposta paginada sempre inclui: `items`, `total`, `page`, `page_size`, `total_pages`.
