# Integração dos fronts Flutter com o monorepo

Este guia descreve como rodar **4 componentes** juntos:

| # | Componente | Repo | Porta padrão local |
|---|---|---|---|
| 1 | API REST (FastAPI + Postgres) | `Projeto_integrador-V-api/apps/api` | **8001** |
| 2 | Serviço de IA (FastAPI + PyTorch) | `Projeto_integrador-V-api/apps/ai` | **8002** |
| 3 | Dashboard admin (Flutter) | `Projeto-Integrador-V-Dashboard-Front` | — |
| 4 | App consumidor (Flutter) | `Projeto-Integrador-V-App-Front` | — |

## Topologia

```
┌──────────────────┐         ┌──────────────────┐
│  App (Flutter)   │ ──────► │     API REST     │  (auth, videos, recs)
│  porta nativa    │ ◄────── │      :8001       │
└──────────────────┘         └──────┬───────────┘
        │                           │
        │ /llm/chat                 │ /llm/recommendations (interno)
        ▼                           ▼
┌──────────────────────────────────────────────┐
│      Serviço de IA (VodRec + VodChat)        │
│                 :8002                        │
└──────────────────────────────────────────────┘
        ▲
        │ /llm/info  (status dos modelos)
        │
┌──────────────────┐
│   Dashboard      │
└──────────────────┘
```

**Regras:**
- App fala com a **API** para tudo (auth, vídeos, favoritos, histórico, recomendações).
- App fala com a **IA** *apenas* para o chat (`/llm/chat/{user_id}`).
- API fala com a IA internamente (cliente HTTP com circuit breaker) para enriquecer recomendações.
- Dashboard fala com a API (admin) e com a IA *só para status* (`/llm/info`).

## 1. Subir o monorepo

```bash
cd Projeto_integrador-V-api
cp .env.example .env
make install
make db.migrate
make compose.up      # sobe Postgres + Redis + API (8001) + IA (8002)
```

Verifique:
```bash
curl http://localhost:8001/docs       # API OpenAPI
curl http://localhost:8002/llm/info   # IA status
```

## 2. Rodar o Dashboard (admin)

```bash
cd Projeto-Integrador-V-Dashboard-Front
flutter pub get

# Endpoints padrao: API=8001 e IA=8002.
# Override quando estiver num device remoto:
flutter run -d chrome \
  --dart-define=API_BASE_URL=http://192.168.0.10:8001 \
  --dart-define=AI_BASE_URL=http://192.168.0.10:8002
```

Configurações em `lib/core/constants/app_constants.dart`:
```dart
apiBaseUrl  defaultValue: 'http://localhost:8001'   (API)
aiBaseUrl   defaultValue: 'http://localhost:8002'   (IA — apenas status)
```

Serviço `AiStatusService` (já registrado em `AppServices.aiStatus`) chama
`GET /llm/info` e retorna `AiModelInfo` com:
- `loaded`, `vodrecParams`, `vodrecVocab`, `vodrecLayers`, `vodrecHeads`
- `vodchatLoaded`, `vodchatBackend`

## 3. Rodar o App (consumidor)

```bash
cd Projeto-Integrador-V-App-Front
flutter pub get

# iOS / macOS:
flutter run -d macos

# Android emulador (mapeia 10.0.2.2 → host automaticamente):
flutter run

# Device fisico / IP custom:
flutter run \
  --dart-define=API_BASE_URL=http://192.168.0.10:8001 \
  --dart-define=AI_BASE_URL=http://192.168.0.10:8002
```

`lib/core/config/api_config.dart` resolve as URLs por plataforma:
- Web → `localhost:{porta}`
- Android emulador → `10.0.2.2:{porta}`
- macOS → `127.0.0.1:{porta}`

### AiChatScreen

A tela `lib/presentation/screens/ai_chat_screen/` usa `AiRepository` para
chamar `/llm/chat/{user_id}` no boot:
1. `bootstrap()` carrega `user_id` (via `/users/me`) e checa `/llm/info`.
2. Se a IA está OK, cada mensagem do usuário vai para o VodChat real.
3. Se IA falha (timeout, 503, erro), cai num **mock heurístico local**
   sem quebrar a UX.

## 4. Variáveis de ambiente — visão geral

| Local | Variável | Onde usar |
|---|---|---|
| Monorepo | `DATABASE_URL` | Postgres compartilhado |
| Monorepo | `SECRET_KEY` / `JWT_SECRET` | **devem ser iguais** entre API e IA |
| Monorepo | `AI_SERVICE_URL` | API encontra a IA (default `http://ai:8000` no compose) |
| Monorepo | `LLM_ENABLED` / `VODCHAT_ENABLED` | liga/desliga IA |
| Dashboard | `API_BASE_URL` / `AI_BASE_URL` | URLs do monorepo |
| App | `API_BASE_URL` / `AI_BASE_URL` | idem |

## 5. Fluxos completos (end-to-end)

### Login

```
App  →  POST  /auth/login           (API)
App  ←       { access_token, refresh_token }
App  →  GET   /users/me             (API com JWT)
App  ←       { id, name, email, plan, ... }
```

### Recomendações na home

```
App  →  GET   /recommendations              (API com JWT)
       ├── API tenta IA (com circuit breaker)
       │       GET /llm/recommendations/{user_id}   (IA com mesmo JWT)
       │       IA carrega historico (Postgres watch_sessions)
       │       IA decide estrategia: empty / cold_start / vodrec
       │       IA retorna top-K
       └── Se IA fora: API usa scoring classico (popularity-based + afinidade)
App  ←  list[RecommendationResponse]
```

### Chat conversacional

```
App  →  POST /llm/chat/{user_id}    (IA direto, com JWT)
            body: { "message": "..." }
IA   →  carrega historico do usuario do Postgres
IA   →  VodChat (LLM TinyLlama+LoRA) gera resposta
App  ←  { reply: "..." }

(se IA falhar → App usa mock local heuristico)
```

### Dashboard observando o modelo

```
Dashboard  →  GET /llm/info  (IA)
Dashboard  ←  { loaded, vodrec: {...}, vodchat: {loaded, backend} }
```

## 6. Troubleshooting

| Sintoma | Causa provavel | Solucao |
|---|---|---|
| App em Android nao conecta | Usando `localhost` | Android emulador precisa de `10.0.2.2` (ja default) |
| `403 forbidden` no `/llm/*` | JWT da API tem `SECRET_KEY` diferente do `JWT_SECRET` da IA | Garantir que sao iguais no `.env` |
| Chat lento | VodChat em CPU sem quantizacao | Setar `VODCHAT_ENABLED=false` ou quantizar com GGUF |
| `circuit breaker OPEN` na API | IA caiu por mais de 5 reqs | Subir IA novamente; circuito reabre apos 30s |
| Recomendacoes "Populares" no cold start | Usuario tem <5 historicos | Comportamento correto (RFIA03) |
