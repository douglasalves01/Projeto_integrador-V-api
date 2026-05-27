# Guia de Integração — Aplicação do Usuário

## Visão Geral

Este documento descreve todos os endpoints disponíveis para o perfil **USER**.
O usuário pode se registrar, navegar pelo catálogo, assistir vídeos, buscar
(inclusive por semântica), favoritar, receber recomendações personalizadas e
conversar com o assistente VodChat.

**Base URL:** `http://localhost:8001`  
**Documentação interativa:** `http://localhost:8001/docs`

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
- `email`: formato válido
- `password`: 8 a 128 caracteres
- `plan_id`: UUID de um plano existente (veja `GET /plans`)

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

---

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

O `access_token` expira em **30 minutos**. O `refresh_token` expira em **7 dias**.

---

### Renovar Token

```
POST /auth/refresh
```

**Body:**
```json
{
  "refresh_token": "eyJ..."
}
```

**Resposta (200):** mesmo formato do login.

---

## Header obrigatório

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
      "title": "Interestelar",
      "description": "Uma equipe de astronautas viaja por um buraco de minhoca...",
      "url": "/videos/uuid/stream",
      "duration_seconds": 9720,
      "release_date": "2014-11-07",
      "age_rating": "12",
      "genres": [{"id": "uuid", "name": "Ficção Científica"}],
      "categories": [{"id": "uuid", "name": "Filmes"}],
      "created_at": "2025-01-01T00:00:00",
      "updated_at": "2025-01-01T00:00:00"
    }
  ],
  "total": 49,
  "page": 1,
  "page_size": 20,
  "total_pages": 3
}
```

---

### Buscar Vídeos

```
GET /videos/search?q=texto&genre_id=uuid&category_id=uuid&semantic=false&page=1&page_size=20
```

**Parâmetros (todos opcionais):**

| Parâmetro     | Tipo    | Padrão | Descrição                                                         |
|---------------|---------|--------|-------------------------------------------------------------------|
| `q`           | string  | —      | Texto de busca                                                    |
| `genre_id`    | UUID    | —      | Filtrar por gênero                                                |
| `category_id` | UUID    | —      | Filtrar por categoria                                             |
| `semantic`    | boolean | false  | Busca semântica por significado em vez de substring do título     |

**Busca clássica** (`semantic=false`): encontra vídeos cujo título contenha o texto.

**Busca semântica** (`semantic=true`): usa embeddings de linguagem para encontrar
vídeos semanticamente relacionados à consulta, mesmo que o título não contenha
as palavras exatas.

```
GET /videos/search?q=heroi+viajando+no+tempo&semantic=true
```

> A busca semântica requer que os embeddings tenham sido indexados pelo admin
> (`POST /admin/index-embeddings` no serviço IA). Se indisponível, cai
> automaticamente na busca clássica.

> Toda busca com `q` registra uma interação `SEARCH` usada pelo sistema de recomendação.

**Resposta (200):** mesmo formato da listagem de vídeos.

---

### Assistir Vídeo

```
GET /videos/{video_id}/watch
```

**Resposta (200):** objeto do vídeo.

> Cria automaticamente uma sessão de visualização e registra uma interação `CLICK`.
> Guarde o ID da sessão retornado para enviar atualizações de progresso.

---

### Streaming do Vídeo (MP4)

```
GET /videos/{video_id}/stream
```

Serve o arquivo de vídeo com suporte a **HTTP Range** — compatível com a tag
`<video>` do HTML e players nativos.

```html
<video controls>
  <source src="http://localhost:8001/videos/{video_id}/stream" type="video/mp4">
</video>
```

Ou para retomar de um ponto específico:

```
GET /videos/{video_id}/stream
Range: bytes=1048576-
```

> Este endpoint não exige autenticação para compatibilidade com players de vídeo
> que não enviam o header `Authorization`.

---

## Sessões de Visualização

### Atualizar Progresso

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

> Envie atualizações periódicas (ex: a cada 30s) para manter o progresso sincronizado.
> Registra uma interação `WATCH` e **invalida o cache de recomendações** do usuário
> — a próxima chamada a `GET /recommendations` recalcula com os dados mais recentes.

**Campos calculados automaticamente:**

| Campo | Cálculo |
|---|---|
| `percentage_watched` | `watch_time / duration_seconds` |
| `completed` | `percentage_watched >= 0.9` |
| `abandoned` | `percentage_watched < 0.1` |

---

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
      "watch_time_seconds": 9720,
      "percentage_watched": 100.0,
      "completed": true,
      "abandoned": false,
      "updated_at": "2025-01-01T14:42:00"
    }
  ],
  "total": 25,
  "page": 1,
  "page_size": 20,
  "total_pages": 2
}
```

---

## Favoritos

### Adicionar

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

### Remover

```
DELETE /favorites/{video_id}
```

**Resposta:** `204 No Content`

### Listar

```
GET /favorites?page=1&page_size=20
```

**Resposta (200):** lista paginada de favoritos.

---

## Recomendações Personalizadas

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
    "relevance_score": 0.94,
    "explanation": "Recommended based on: genre affinity (Ficção Científica), popularity.",
    "created_at": "2025-01-01T00:00:00"
  }
]
```

**Como funciona (transparente ao app):**

1. **Cache Redis** — se as recomendações foram geradas nos últimos 5 minutos,
   retorna do banco instantaneamente sem reprocessar.
2. **IA (VodRec-Transformer)** — se o usuário tem 5 ou mais vídeos assistidos,
   usa o modelo de recomendação sequencial treinado.
3. **Fallback clássico** — scoring por afinidade de gênero, categoria,
   popularidade e histórico de busca. Sempre disponível, mesmo com IA offline.

O cache é invalidado automaticamente ao atualizar uma sessão de visualização.

---

## Chat com Assistente (VodChat)

```
POST /chat
```

**Body:**
```json
{
  "message": "Quais filmes de ação você me recomenda com heróis?"
}
```

**Resposta (200):**
```json
{
  "reply": "Com base no seu histórico, você pode gostar de 'Mad Max: Estrada da Fúria' e 'John Wick'. Ambos têm heróis de ação intensos com ótima cinematografia.",
  "fallback": false
}
```

**Resposta quando IA está indisponível:**
```json
{
  "reply": "Desculpe, o assistente está temporariamente indisponível. Tente novamente em instantes.",
  "fallback": true
}
```

> O VodChat conhece o catálogo completo e o histórico de visualização do usuário.
> Use `fallback: true` para exibir uma mensagem de indisponibilidade no app.

**Boas práticas:**
- Verifique `fallback: true` antes de exibir a resposta
- Limite mensagens a 2000 caracteres
- O histórico de conversa **não é mantido entre chamadas** — cada `POST /chat`
  é stateless; inclua contexto na mensagem se necessário

---

## Gêneros e Categorias

### Listar Gêneros

```
GET /genres?page=1&page_size=20
```

**Resposta (200):**
```json
{
  "items": [
    {"id": "uuid", "name": "Ação", "created_at": "...", "updated_at": "..."}
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

**Resposta (200):** mesmo formato de gêneros.

---

## Planos

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
      "description": "Acesso completo com qualidade 4K",
      "price": 49.90,
      "created_at": "...",
      "updated_at": "..."
    }
  ],
  "total": 3,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

> Use esta listagem na tela de cadastro para o usuário escolher um plano.

---

## Fluxo Típico de Uso

```
1.  GET  /plans                          → listar planos
2.  POST /auth/register                  → criar conta
3.  POST /auth/login                     → obter tokens
4.  GET  /videos                         → navegar catálogo
5.  GET  /videos/search?q=...            → busca clássica
6.  GET  /videos/search?q=...&semantic=true → busca semântica
7.  GET  /videos/{id}/watch              → iniciar sessão (guarda session_id)
8.  GET  /videos/{id}/stream             → reproduzir vídeo (tag <video>)
9.  PATCH /watch-sessions/{session_id}   → atualizar progresso (a cada 30s)
10. POST /favorites/{video_id}           → favoritar
11. GET  /recommendations                → recomendações personalizadas
12. POST /chat                           → conversar com assistente
13. GET  /watch-history                  → histórico do usuário
14. POST /auth/refresh                   → renovar token quando expirar
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
| 400 | Requisição malformada |
| 401 | Token inválido ou expirado |
| 403 | Permissão insuficiente |
| 404 | Recurso não encontrado |
| 409 | Conflito (ex: email já cadastrado) |
| 416 | Range inválido (streaming) |
| 422 | Dados de entrada inválidos |
| 500 | Erro interno do servidor |
