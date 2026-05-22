# Prompts Cursor — Migração para LLM próprio

Sequência de prompts para colar no Cursor que **integram os dois modelos LLM próprios** (VodRec-Transformer + VodChat) no projeto VOD-IA existente.

> Contexto que o Cursor precisa: o projeto VOD-IA está em `/Users/henriquemartelini/Desktop/VOD-IA`. A arquitetura clássica (TF-IDF + ALS) já existe em `app/models/content_based.py`, `app/models/collaborative.py`, `app/models/hybrid.py`. Agora estamos adicionando dois modelos **construídos por nós**: VodRec-Transformer (PyTorch from scratch) e VodChat (TinyLlama + LoRA). Veja `docs/ARQUITETURA_LLM.md`.

---

## PROMPT L0 — Anexar contexto

Antes de tudo, no Cursor:

```
@docs/ARQUITETURA_LLM.md
@app/models/vodrec_transformer.py
@app/models/vodchat.py
@app/models/orchestrator.py
@app/services/llm_recommendation_service.py
@app/api/routes/llm.py
```

Esses arquivos já existem (foram criados nesta entrega). Os prompts a seguir os **integram** ao resto do projeto.

---

## PROMPT L1 — Adicionar dependências e configurar settings

```
Atualize a configuração do projeto VOD-IA para suportar os novos modelos LLM.

1. Adicione ao `requirements.txt` as dependências de runtime (NÃO as de fine-tuning):
   ```
   torch>=2.2.0,<2.5.0
   transformers==4.44.2
   peft==0.12.0
   accelerate==0.33.0
   safetensors>=0.4.0
   sentencepiece>=0.2.0
   ```
   (As deps de fine-tuning — bitsandbytes, trl, datasets — ficam em `requirements-llm.txt` separado, que já existe.)

2. Em `app/core/config.py`, adicione ao `Settings`:
   ```python
   VODREC_MODEL_PATH: str = "models/vodrec/model.pt"
   VODREC_VOCAB_PATH: str = "models/vodrec/vocab.json"
   VODCHAT_ADAPTER_PATH: str = "models/vodchat/vodchat-lora-final"
   VODCHAT_BASE_MODEL: str = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
   VODCHAT_GGUF_PATH: str | None = None
   LLM_ENABLED: bool = True
   VODCHAT_ENABLED: bool = True
   ```

3. Atualize `.env.example` adicionando as mesmas chaves comentadas.

4. Em `app/main.py`, adicione um handler de startup que chama
   `app.services.llm_recommendation_service.load_llm_models()`
   se `settings.LLM_ENABLED` for True. Em caso de erro de carregamento,
   logar warning e seguir (o serviço continua respondendo com fallback clássico).
```

---

## PROMPT L2 — Registrar o router /llm no FastAPI

```
Em `app/api/router.py`, importe e registre o novo router de LLM:

```python
from app.api.routes import llm as llm_routes

router.include_router(llm_routes.router)
```

Verifique que ele expõe:
- GET  /llm/recommendations/{user_id}
- POST /llm/chat/{user_id}
- GET  /llm/info

Em `app/api/routes/llm.py` o `_load_user_history(db, user_id)` usa
`app.models.schemas_db.ViewHistory`. Confirme que esse modelo existe
no projeto; se o nome do campo for diferente (ex: `viewed_at`, `created_at`)
ajuste a referência.

Adicione testes em `tests/api/test_llm_routes.py`:
1. GET /llm/info retorna 200 mesmo sem modelo carregado (loaded: false)
2. GET /llm/recommendations/{user_id} com user_id sem histórico retorna lista vazia
3. POST /llm/chat/{user_id} retorna 503 se VodChat não estiver carregado
```

---

## PROMPT L3 — Catalog Loader

```
Crie `app/services/catalog_loader.py` com a função:

```python
def load_catalog_from_db(db) -> dict[int, dict]:
    """Retorna { content_id: {"title": str, "genres": [str, ...], "duration_sec": int} }"""
```

Implementação:
- Faz query joining `Content`, `ContentGenre`, `Genre`
- Agrega gêneros em lista por conteúdo
- Retorna dict

No startup do FastAPI (em `app/main.py`), depois de carregar os modelos,
chame:

```python
from app.services import catalog_loader, llm_recommendation_service as llmsvc
with SessionLocal() as db:
    catalog = catalog_loader.load_catalog_from_db(db)
llmsvc.update_catalog(catalog)
```

O catalog precisa ser recarregado quando novos conteúdos forem inseridos.
Crie também um endpoint `POST /admin/reload-catalog` que recarrega e
retorna o número de itens.
```

---

## PROMPT L4 — Endpoint admin para hot-swap dos modelos

```
Crie `app/api/routes/admin.py` com endpoints protegidos por API key
(header `X-AI-API-Key` igual a `settings.ADMIN_API_KEY`):

1. `POST /admin/reload-models`
   Recarrega VodRec e VodChat dos paths atuais. Útil após upload de
   novo checkpoint sem reiniciar o container.

2. `POST /admin/reload-catalog`
   Recarrega o catálogo do MySQL.

3. `GET /admin/model-version`
   Retorna conteúdo de `models/vodrec/VERSION.txt` e
   `models/vodchat/VERSION.txt`.

Em todos, retornar 401 se a API key estiver errada.

Registrar o router em `app/api/router.py`.
```

---

## PROMPT L5 — Adaptar o backend Node.js

```
No backend Node.js (assumindo que existe em outro repositório), o cliente
HTTP precisa apenas trocar a URL dos endpoints:

- DE: `GET ${AI_URL}/recommendations/${userId}`
- PARA: `GET ${AI_URL}/llm/recommendations/${userId}`

Adicione um parâmetro opcional `with_explanation=true` quando o usuário
acessar a tela "Por que estou vendo isso?".

Adicione também:
- `POST ${AI_URL}/llm/chat/${userId}` para a feature de chat conversacional
  com o catálogo.

Mantenha o fallback existente (Popularity vinda do MySQL) para o caso do
AI Service estar fora.

Latência alvo: <2s para o endpoint /llm/recommendations (sem explanation).
Quando `with_explanation=true`, latência pode chegar a 3-5s — fazer essa
chamada em background na UI.
```

---

## PROMPT L6 — Dockerfile multi-stage atualizado

```
Atualize o `Dockerfile` para incluir PyTorch sem inchar a imagem.

Use multi-stage build:

```dockerfile
# Stage 1: build
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: runtime
FROM python:3.12-slim
WORKDIR /app

# Copia deps já instaladas
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Pre-download do modelo base do VodChat (opcional, comente para acelerar build)
ARG PREDOWNLOAD_BASE_MODEL=true
RUN if [ "$PREDOWNLOAD_BASE_MODEL" = "true" ]; then \
        python -c "from transformers import AutoModelForCausalLM, AutoTokenizer; \
                   AutoModelForCausalLM.from_pretrained('TinyLlama/TinyLlama-1.1B-Chat-v1.0'); \
                   AutoTokenizer.from_pretrained('TinyLlama/TinyLlama-1.1B-Chat-v1.0')"; \
    fi

COPY app/ app/
COPY scripts/ scripts/
COPY pyproject.toml ./

# Modelos vêm via volume mount (não copiamos para a imagem)
VOLUME ["/app/models"]

EXPOSE 8000
CMD ["gunicorn", "app.main:app", \
     "-w", "2", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120"]
```

Em `docker-compose.yml`, adicione volume:

```yaml
services:
  ai-service:
    build: .
    volumes:
      - ./models:/app/models:ro
      - hf_cache:/root/.cache/huggingface
    environment:
      VODREC_MODEL_PATH: /app/models/vodrec/model.pt
      VODREC_VOCAB_PATH: /app/models/vodrec/vocab.json
      VODCHAT_ADAPTER_PATH: /app/models/vodchat/vodchat-lora-final
      LLM_ENABLED: "true"
volumes:
  hf_cache:
```
```

---

## PROMPT L7 — Treinar e fazer deploy

```
Implemente o pipeline de re-treino e deploy.

1. Crie `scripts/deploy_models.sh`:
   ```bash
   #!/usr/bin/env bash
   set -euo pipefail
   # Empacota e envia os modelos para o servidor
   TAG=${1:-vodrec-v1.0.0}
   tar -czf "${TAG}.tar.gz" -C models .
   scp "${TAG}.tar.gz" "${VOD_AI_HOST}:/opt/vod-ai/incoming/"
   ssh "${VOD_AI_HOST}" "
       cd /opt/vod-ai &&
       tar -xzf incoming/${TAG}.tar.gz -C models/ &&
       curl -X POST http://localhost:8000/admin/reload-models \
            -H 'X-AI-API-Key: ${VOD_ADMIN_KEY}'
   "
   echo 'Deploy completo.'
   ```

2. Crie `.github/workflows/train-vodrec.yml`:
   - Trigger: workflow_dispatch (manual) ou cron diário
   - Job: dump do MySQL → roda `scripts/train_vodrec.py` → testa métricas
     mínimas (HR@10 >= 0.65) → faz upload do artifact para release
   - Notifica Slack/Discord em caso de regressão

3. Documente no `README.md` o fluxo:
   - Local: notebook 06 e 07 para iterar
   - CI: `scripts/train_vodrec.py` para batch reproduzível
   - Deploy: `deploy_models.sh` + hot-reload via /admin
```

---

## PROMPT L8 — Atualizar testes

```
Atualize a suíte de testes para os novos modelos.

1. `tests/models/test_vodrec_transformer.py`:
   - Testa que `VodRecTransformer` produz logits no shape correto
   - Testa save/load do checkpoint preserva pesos (compara um forward pass antes/depois)
   - Testa que `VodRecRecommender.recommend()` exclui itens vistos
   - Testa que recommend retorna no máximo k itens
   - Testa que com história vazia retorna []

2. `tests/models/test_orchestrator.py`:
   - Mock do VodRec e VodChat
   - Testa que sem vodchat o `with_explanation=True` apenas não preenche reason
   - Testa que catálogo é usado para preencher title/genres

3. `tests/api/test_llm_routes.py`:
   - Usa TestClient do FastAPI
   - Mocks `get_orchestrator()` para retornar um stub
   - Testa GET /llm/recommendations, POST /llm/chat, GET /llm/info

Rode `pytest tests/ -v --cov=app/models/vodrec_transformer --cov=app/models/vodchat --cov=app/models/orchestrator`
e busque >85% de cobertura nos módulos LLM.
```

---

## PROMPT L9 — Documentação para apresentação

```
Atualize `docs/MODEL_CARD.md` com:

- Seção "VodRec-Transformer"
  * Arquitetura: decoder-only, X parâmetros, X camadas
  * Dados: catálogo VOD, sequências de visualização
  * Métricas: HR@10, NDCG@10, MRR
  * Latência: P50, P95 em CPU e GPU
  * Limitações: cold start, bias de popularidade

- Seção "VodChat"
  * Modelo base: TinyLlama-1.1B-Chat-v1.0
  * Adapter: LoRA r=16, alpha=32
  * Dataset: 3000 exemplos sintéticos cobrindo 5 templates
  * Métricas qualitativas: amostras antes/depois do fine-tune
  * Limitações: alucinação de títulos (mitigada via constrained decoding futuro)

Atualize `docs/API.md` com os novos endpoints /llm/*.

Crie `docs/RUNBOOK.md` com:
- Como treinar (notebook + script CLI)
- Como fazer deploy (deploy_models.sh)
- Como reverter para uma versão anterior
- Como monitorar (latência, HR@10 em produção via amostragem)
- Troubleshooting: o que fazer se modelo não carregar
```

---

## Ordem de execução

1. L0 — Anexar arquivos ao contexto do Cursor
2. L1 — Dependências + config
3. L2 — Registrar router /llm
4. L3 — Catalog loader
5. L4 — Admin endpoints
6. L5 — Adaptar backend Node.js
7. L6 — Dockerfile + docker-compose
8. L7 — CI/CD e deploy
9. L8 — Testes
10. L9 — Documentação

Após cada prompt: `pytest tests/` e `docker-compose up --build` para validar.

---

## Notas finais

- Os notebooks 06 e 07 são para **treino** (rode no Colab com GPU).
- Os módulos em `app/models/` e `app/services/` são para **inferência em produção** (rodam no FastAPI).
- Os modelos `.pt` (VodRec) e `vodchat-lora-final/` (VodChat) **não vão no Git** — sobem via S3/release no GitHub e são montados via Docker volume.
- A arquitetura clássica (TF-IDF + ALS) **continua existindo** como fallback de emergência se os LLMs falharem (define isso via flag em `settings.py`).
