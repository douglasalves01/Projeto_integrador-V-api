# Integração — Painel Admin (novidades)

Guia rápido do que mudou para o **painel administrativo**. Cobre:

1. **Resumo executivo / insights de IA** (`GET /admin/reports/insights`)
2. **Engajamento por usuário** (`GET /admin/reports/user-engagement`)
3. **Geração de resumos dos vídeos** (script offline)

**Base URL da API:** `http://localhost:8001`
**Auth:** `Authorization: Bearer <access_token>` — perfil **ADMIN**
**Docs interativas:** `http://localhost:8001/docs`

> Os relatórios já existentes (`/admin/reports/usage`, `/most-watched`,
> `/abandonment`, `/popular-genres`, `/active-users`) continuam iguais — veja
> `docs/INTEGRACAO_ADMIN.md`. Aqui está só o **delta**.

Todos os endpoints abaixo exigem token de **ADMIN** (perfil `USER` recebe `403`).

---

## 1. Resumo executivo — `GET /admin/reports/insights`

Endpoint "tudo em um": agrega as métricas e devolve um **texto pronto de
insights** (`headline` + `highlights`) junto com os dados estruturados.

```
GET /admin/reports/insights?limit=5&start_date=2026-05-01&end_date=2026-05-31
Authorization: Bearer <access_token>
```

| Query param | Default | Descrição |
|-------------|---------|-----------|
| `limit` | `5` | Quantos itens em cada ranking (1–50) |
| `start_date` | — | Filtro opcional (ISO 8601) |
| `end_date` | — | Filtro opcional (ISO 8601) |

### Response (200)

```json
{
  "generated_at": "2026-05-31T21:36:41.640270Z",
  "period_start": null,
  "period_end": null,
  "headline": "13 visualizações de 1 usuários ativos, com 2min54s em média por sessão.",
  "highlights": [
    "Engajamento: 1/2 usuários ativos (50%) somaram 13 sessões de visualização.",
    "Tempo médio assistido por sessão: 2min54s; retenção média de 64% do vídeo e 62% das sessões concluídas até o fim.",
    "Vídeo mais assistido: \"Como se forma a chuva? - Ciclo da água\" com 2 visualizações.",
    "Gênero que mais prende: \"Culinaria\" lidera em tempo assistido (20min11s no total).",
    "Atenção: \"Confira 6 cachoeiras para conhecer no Brasil\" tem a maior taxa de abandono (100%) — candidato a revisão.",
    "Usuário mais engajado: Demo Viewer — 13 sessões, 37min46s assistidos (retenção média 64%)."
  ],
  "usage": {
    "total_users": 2,
    "active_users": 1,
    "total_watch_sessions": 13,
    "average_watch_time_seconds": 174.3
  },
  "average_percentage_watched": 0.6413,
  "completion_rate": 0.6153,
  "most_watched": [
    { "video_id": "uuid", "title": "...", "count": 2 }
  ],
  "highest_abandonment": [
    { "video_id": "uuid", "title": "...", "abandonment_rate": 1.0 }
  ],
  "popular_genres": [
    { "genre_id": "uuid", "name": "Culinaria", "total_watch_time_seconds": 1211 }
  ],
  "top_users": [
    {
      "user_id": "uuid",
      "name": "Demo Viewer",
      "email": "demo@streaming.com",
      "sessions": 13,
      "total_watch_time_seconds": 2266,
      "average_watch_time_seconds": 174.3,
      "average_percentage_watched": 0.6413
    }
  ]
}
```

### Campos

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `headline` | string | Frase-resumo do período |
| `highlights` | string[] | Bullets prontos para exibir (texto natural) |
| `usage` | objeto | Totais: usuários, ativos, sessões, tempo médio (s) |
| `average_percentage_watched` | float (0–1) | Retenção média (fração do vídeo assistida) |
| `completion_rate` | float (0–1) | Fração de sessões concluídas até o fim |
| `most_watched` | lista | Vídeos por nº de visualizações |
| `highest_abandonment` | lista | Vídeos por taxa de abandono (0–1) |
| `popular_genres` | lista | Gêneros por tempo total assistido (s) |
| `top_users` | lista | Usuários mais engajados (ver seção 2) |

### Recomendações de UI

- Renderize `headline` em destaque e `highlights` como lista de bullets — já
  vêm formatados, **não precisa montar frase no front**.
- Use os blocos (`most_watched`, `popular_genres`, etc.) para tabelas/gráficos.
- Converta as frações para %: `average_percentage_watched * 100`,
  `completion_rate * 100`, `abandonment_rate * 100`.
- Filtro de período: mande `start_date`/`end_date` em ISO (ex.:
  `2026-05-01T00:00:00`).

> **Importante:** os textos são gerados a partir dos **números reais**
> (deterministicamente), não por LLM. Logo, as estatísticas são sempre exatas —
> nada de números "alucinados". O endpoint é rápido (sem inferência de modelo).

---

## 2. Engajamento por usuário — `GET /admin/reports/user-engagement`

Responde "quanto tempo cada usuário permanece nos vídeos".

```
GET /admin/reports/user-engagement?limit=10&start_date=...&end_date=...
Authorization: Bearer <access_token>
```

### Response (200)

```json
[
  {
    "user_id": "uuid",
    "name": "Demo Viewer",
    "email": "demo@streaming.com",
    "sessions": 13,
    "total_watch_time_seconds": 2266,
    "average_watch_time_seconds": 174.3,
    "average_percentage_watched": 0.6413
  }
]
```

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `sessions` | int | Nº de watch sessions do usuário |
| `total_watch_time_seconds` | int | Tempo total assistido |
| `average_watch_time_seconds` | float | Tempo médio por sessão |
| `average_percentage_watched` | float (0–1) | Retenção média do usuário |

Ordenado por tempo total assistido (desc). Bom para tabela "usuários mais
engajados" com colunas de tempo e retenção.

---

## 3. Resumos dos vídeos (operação)

Os vídeos passaram a ter o campo `summary` (exposto no app). Ele é **pré-gerado
offline** e salvo no banco — não é calculado por request.

### Como gerar / regerar

Rode dentro do container `ai` (após novos ingests de catálogo):

```bash
# Gera só os que ainda não têm resumo (motor padrão: extrativo, instantâneo)
docker compose -f infra/docker-compose.yml exec ai \
  python scripts/generate_summaries.py

# Regenera todos
docker compose -f infra/docker-compose.yml exec ai \
  python scripts/generate_summaries.py --force

# Teste rápido com poucos itens
docker compose -f infra/docker-compose.yml exec ai \
  python scripts/generate_summaries.py --limit 5
```

| Flag | Descrição |
|------|-----------|
| `--engine extractive` | **Padrão.** Limpa a descrição (links, hashtags, timestamps, propaganda) e extrai as frases-chave. Rápido e fiel |
| `--engine vodchat` | Usa o TinyLlama-LoRA. **Não recomendado**: lento na CPU e baixa qualidade para resumo |
| `--force` | Regenera mesmo quem já tem resumo |
| `--limit N` | Processa no máximo N vídeos |

> Não há endpoint admin para isso (é tarefa de manutenção/batch). Caso queira
> expor um botão "Regenerar resumos" no painel no futuro, dá para envolver esse
> script atrás de um endpoint admin — avise que adicionamos.

---

## Resumo dos endpoints novos

| Método | Rota | Perfil | Descrição |
|--------|------|--------|-----------|
| GET | `/admin/reports/insights` | Admin | Resumo executivo (texto) + métricas agregadas |
| GET | `/admin/reports/user-engagement` | Admin | Tempo/retenção por usuário |
