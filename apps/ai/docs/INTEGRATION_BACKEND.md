# Integração com o backend (repositório externo)

Este repositório contém **apenas o microserviço de IA** (Python/FastAPI). O backend Node.js/Express é desenvolvido em **outro repositório** e consumirá esta API quando estiver no ar.

## Escopo deste repo

| Incluído | Não incluído |
|----------|----------------|
| API de recomendações e perfil | Código do backend Node |
| Treino offline e modelos `.pkl` | Autenticação de usuários final |
| MySQL/Redis do pipeline de IA | Rotas de catálogo/streaming |

## Contrato HTTP (para implementar no backend)

**Base URL:** `http://<ai-service-host>:8000/api/v1` (ou variável `AI_SERVICE_URL` no backend)

### Autenticação

- **Recomendações e perfil:** `Authorization: Bearer <JWT>`
  - Mesmo `JWT_SECRET` e algoritmo `HS256` que o backend usa para login.
  - Payload deve incluir `sub` ou `user_id` (inteiro).
  - O `user_id` na URL deve ser o mesmo do token.

### Endpoints que o backend deve chamar

#### 1. Recomendações LLM (preferencial quando modelos montados)

```
GET /api/v1/llm/recommendations/{user_id}?k=20&with_explanation=false
Authorization: Bearer <jwt>
```

- **Latência alvo:** P95 &lt; 2s sem `with_explanation`.
- **`with_explanation=true`:** 3–5s — chamar em background na tela "Por que estou vendo isso?".

#### 1b. Recomendações clássicas (fallback de emergência)

```
GET /api/v1/recommendations/{user_id}?k=20
Authorization: Bearer <jwt>
```

Use se `/llm/*` retornar 503 ou timeout. Resposta: `user_id`, `model_version`, `strategy`, `total_views`, `recommendations[]`, `generated_at`.

**Sugestão:** timeout ~2,5s; em falha, fallback local (ex.: popularidade no MySQL do backend).

#### 1c. Chat conversacional (VodChat)

```
POST /api/v1/llm/chat/{user_id}
Authorization: Bearer <jwt>
Content-Type: application/json

{"message": "Quero uma série de suspense curta"}
```

#### 2. Atualização de perfil (assíncrono / fire-and-forget)

Chamar após cada progresso de visualização relevante (RFIA04):

```
POST /api/v1/profile/{user_id}/update
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "content_id": 318,
  "watched_sec": 4200,
  "total_sec": 5400,
  "ended_at": "2026-05-22T14:25:00Z"
}
```

Não bloqueia a resposta ao cliente mobile — erros devem ser apenas logados.

#### 3. Retreino (ops / cron — opcional)

```
POST /api/v1/train
X-AI-API-Key: <AI_API_KEY>

GET /api/v1/train/status/{job_id}
X-AI-API-Key: <AI_API_KEY>
```

A chave `AI_API_KEY` é **interna** deste serviço (não é API do Gemini nem de LLM).

## Variáveis no backend (referência)

Configurar no repositório do backend, não neste repo:

| Variável | Exemplo | Uso |
|----------|---------|-----|
| `AI_SERVICE_URL` | `http://vod-ai:8000/api/v1` | Base URL |
| `JWT_SECRET` | (igual ao deste serviço) | Assinar/validar JWT |
| `AI_SERVICE_TIMEOUT_MS` | `2500` | Timeout HTTP |
| `AI_SERVICE_API_KEY` | (opcional) | Só se o backend disparar `/train` |

## Checklist para integração futura

Quando o backend estiver disponível, validar:

- [ ] `JWT_SECRET` idêntico nos dois serviços
- [ ] MySQL compartilhado: `view_history`, `user_profiles_ai`, catálogo
- [ ] `GET /recommendations/:userId` com JWT do usuário logado
- [ ] `POST /profile/:userId/update` em fire-and-forget após view
- [ ] Health: `GET http://ai-service:8000/health`
- [ ] Docker/rede: backend alcança `ai-service` na porta 8000

## Documentação relacionada

- [API.md](./API.md) — exemplos `curl` e OpenAPI
- [ARQUITETURA_IA.md](./ARQUITETURA_IA.md) — pipeline ML e requisitos RFIA
