# Integração — App do Usuário (novidades)

Guia rápido do que mudou para o **app do usuário** e como consumir. Cobre duas
entregas recentes:

1. **Chatbot mais honesto e relevante** (`POST /chat`)
2. **Resumo do vídeo** (`summary`) nas respostas de catálogo/player

**Base URL:** `http://localhost:8001`
**Auth:** `Authorization: Bearer <access_token>` (login em `POST /auth/login`)
**Docs interativas:** `http://localhost:8001/docs`

> Os contratos de auth, catálogo, favoritos e recomendações continuam iguais —
> veja `docs/INTEGRACAO_USUARIO.md`. Aqui só está o **delta**.

---

## 1. Chatbot — `POST /chat`

### Request

```
POST /chat
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{ "message": "quero videos de natureza" }
```

- `message`: 1 a 2000 caracteres.

### Response (200)

```json
{
  "reply": "Separei estes vídeos sobre natureza:\n1. AMAZÔNIA SELVAGEM...",
  "fallback": false,
  "videos": [
    {
      "id": "00000000-0000-0000-0000-000000000002",
      "title": "AMAZÔNIA SELVAGEM | DOCUMENTÁRIO...",
      "description": "A floresta amazônica é o berço...",
      "url": "/videos/00000000-0000-0000-0000-000000000002/stream",
      "duration_seconds": 1803
    }
  ],
  "search_query": "natureza",
  "catalog_empty": false
}
```

| Campo | Tipo | Para que serve na UI |
|-------|------|----------------------|
| `reply` | string | Texto a exibir no balão do assistente |
| `fallback` | bool | `true` = resposta veio do modo de contingência (IA indisponível). UI pode mostrar um aviso discreto, mas o `reply` continua válido |
| `videos` | lista | Cards de vídeo sugeridos. Use `id` para abrir o player (`/videos/{id}/stream`) |
| `search_query` | string\|null | Tema detectado na mensagem (ex.: `"natureza"`) |
| `catalog_empty` | bool | `true` = não há vídeos para o tema pedido. Renderize só o `reply`, sem grade de cards |

### O que mudou no comportamento

- **Gêneros de filme que não existem no acervo** (ação, terror, comédia, drama,
  suspense, romance, aventura, ficção, guerra, policial, anime, novela…) agora
  retornam uma resposta **honesta**, listando as categorias reais, em vez de
  empurrar vídeos fora de contexto. Nesse caso vem `catalog_empty: true` e
  `videos: []`.

  Exemplo — `{"message": "quero filmes de ação"}`:

  ```json
  {
    "reply": "Não trabalhamos com \"acao\" — nosso acervo é de vídeos educativos e culturais brasileiros, não de filmes por gênero.\n\nAs categorias disponíveis são: Natureza, Culinária, Música, Esporte, Tecnologia, Turismo, Educação, Ciência, Saúde, Arte.\n\nTente pedir, por exemplo: \"vídeos de natureza\", \"receitas de culinária\" ou \"tutoriais de tecnologia\".",
    "fallback": false,
    "videos": [],
    "search_query": "acao",
    "catalog_empty": true
  }
  ```

- **Match mais preciso**: a busca por tema passou a casar palavra inteira e
  ignora termos genéricos, então não traz mais vídeo de assunto diferente.

### Recomendações de UI

- Sempre renderize `reply`. Se `videos` estiver vazio, **não** mostre grade.
- Quando `catalog_empty: true`, trate como resposta informativa (sem cards) e,
  se quiser, ofereça atalhos para as categorias citadas.
- Saudações curtas ("oi") não trazem vídeos — é esperado (`videos: []`,
  `search_query: null`).
- O chat pode demorar alguns segundos; mostre indicador de digitação. Há timeout
  no backend — se estourar, vem `fallback: true` com mensagem padrão (a UI nunca
  fica "pendurada").

---

## 2. Resumo do vídeo — campo `summary`

Foi adicionado o campo **`summary`** (string, pode ser `null`) ao objeto de
vídeo. Ele aparece em **todas** as respostas que retornam vídeo:

- `GET /videos` (lista paginada)
- `GET /videos/search`
- `GET /videos/{id}/watch`

### Exemplo — `GET /videos/{id}/watch`

```json
{
  "id": "00000000-0000-0000-0000-000000000002",
  "title": "AMAZÔNIA SELVAGEM | DOCUMENTÁRIO...",
  "description": "A floresta amazônica é o berço de animais incríveis...",
  "summary": "A floresta amazônica é o berço de animais incríveis. Neste documentário da Amazônia selvagem... Onça pintada, jacaré, sucuri, tucano, arara, tatu e muitos outros animais selvagens fazem parte…",
  "url": "/videos/00000000-0000-0000-0000-000000000002/stream",
  "duration_seconds": 1803,
  "release_date": null,
  "age_rating": null,
  "genres": [],
  "categories": [],
  "created_at": "2026-05-27T00:00:00",
  "updated_at": "2026-05-31T21:32:49"
}
```

| Campo | Tipo | Observação |
|-------|------|-----------|
| `summary` | string\|null | Resumo curto (2–3 frases) do conteúdo. Pode ser `null` para alguns itens (descrição muito curta) |
| `description` | string\|null | Texto completo original (já existia) |

### Recomendações de UI

- Na tela de detalhe/player, exiba `summary` como **descrição curta** acima do
  texto completo (`description`), ou em destaque ("Resumo").
- **Sempre trate `null`**: se `summary == null`, caia para `description` (ou
  oculte a seção). Nem todo vídeo tem resumo.
- Em cards/listagem, `summary` (quando existir) é ótimo para preview de 2 linhas.

> O resumo é **pré-gerado e salvo** no backend (não é calculado a cada request),
> então não há custo extra de latência para o app.
