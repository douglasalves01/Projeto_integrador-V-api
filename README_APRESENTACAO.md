# README de Apresentacao — Plataforma VOD com IA

Este documento foi escrito para apresentar o projeto de forma completa: contexto, problema resolvido, arquitetura, execucao local, onde cada parte esta no codigo, onde a inteligencia artificial foi aplicada e quais tecnicas foram usadas.

Projeto: **Plataforma de Video on Demand (VOD) com recomendacao inteligente, busca semantica e chatbot contextual**.

---

## 1. Resumo para apresentar em 1 minuto

O projeto e uma plataforma de streaming sob demanda, parecida com uma versao academica de Netflix/YouTube, mas voltada para demonstrar backend, dados e inteligencia artificial em um sistema real.

O usuario consegue se cadastrar, fazer login, navegar pelo catalogo, assistir videos, favoritar conteudos, registrar historico de visualizacao e receber recomendacoes personalizadas. Alem disso, existe busca semantica por significado e um chatbot contextual que conversa sobre o catalogo.

A solucao foi implementada como um monorepo com tres aplicacoes:

- `apps/api`: API principal em FastAPI, responsavel por usuarios, autenticacao, catalogo, streaming, favoritos, historico, recomendacoes, chat e administracao.
- `apps/ai`: microservico de IA em FastAPI + PyTorch, responsavel por recomendacao neural, embeddings, busca semantica e VodChat.
- `apps/analytics`: jobs offline para gerar relatorios de produto, engajamento e efetividade das recomendacoes.

A IA aparece em tres pontos principais:

- **VodRec-Transformer**: modelo neural sequencial que recomenda o proximo video com base no historico do usuario.
- **Busca semantica**: sentence embeddings de 384 dimensoes + pgvector para buscar videos por significado.
- **VodChat**: chatbot baseado em TinyLlama 1.1B com adaptacao LoRA para responder sobre o catalogo e o historico do usuario.

---

## 2. Problema que o projeto resolve

Em plataformas de streaming, o usuario normalmente enfrenta tres problemas:

1. **Excesso de conteudo**: ele nao sabe o que assistir.
2. **Busca limitada por palavras exatas**: se ele digita "video de natureza com animais", uma busca simples por titulo pode nao encontrar bons resultados.
3. **Falta de explicacao**: o sistema recomenda algo, mas o usuario nao entende o motivo.

Este projeto resolve esses pontos com:

- recomendacoes personalizadas por historico;
- fallback por popularidade e scoring classico quando a IA nao esta disponivel;
- busca semantica com embeddings;
- chatbot que responde perguntas em linguagem natural;
- relatorios para administradores acompanharem uso, engajamento e recomendacoes.

---

## 3. Visao geral da arquitetura

```text
Cliente web/mobile
        |
        v
API principal - apps/api - porta 8001
        |
        |-- PostgreSQL com pgvector
        |-- Redis
        |
        v
Servico de IA - apps/ai - porta 8002
        |
        |-- VodRec-Transformer
        |-- VodChat
        |-- Sentence Transformers
        |
        v
Analytics - apps/analytics - jobs offline
```

Na pratica:

- O cliente sempre conversa primeiro com `apps/api`.
- A API valida JWT, aplica regras de negocio e consulta o banco.
- Quando precisa de IA, a API chama `apps/ai` via HTTP usando `AIClient`.
- O banco PostgreSQL e compartilhado entre API, IA e Analytics.
- O Redis e usado para cache de recomendacoes e suporte de performance.

Arquivos principais:

- `infra/docker-compose.yml`: sobe Postgres, Redis, API, IA e Analytics.
- `Makefile`: comandos padronizados para setup, execucao, teste e migrations.
- `.env.example`: variaveis de ambiente.
- `apps/api/app/main.py`: registra os routers da API principal.
- `apps/ai/app/main.py`: inicializa modelos classicos, LLMs e rotas do servico de IA.

---

## 4. Como rodar o projeto

### 4.1. Requisitos

- Docker e Docker Compose.
- Python 3.11, caso rode localmente sem Docker.
- Memoria suficiente para os containers.
- Mais RAM/GPU se quiser ativar o VodChat real com TinyLlama.

### 4.2. Setup completo com Docker

Na raiz do repositorio:

```bash
cp .env.example .env
make setup
```

Esse comando:

1. sobe os containers;
2. aguarda Postgres e Redis;
3. sobe a API;
4. roda migrations automaticamente;
5. sobe o servico de IA;
6. popula dados de demonstracao;
7. indexa embeddings para busca semantica.

URLs locais:

- Swagger da API principal: `http://localhost:8001/docs`
- Info dos modelos de IA: `http://localhost:8002/api/v1/llm/info`
- Postgres: `localhost:5432`
- Redis: `localhost:6379`

Credenciais de demonstracao:

- Admin: `admin@streaming.com` / `admin123`
- Usuario: `demo@streaming.com` / `demo1234`

### 4.3. Comandos uteis

```bash
make help
make compose.up
make compose.logs
make compose.down
make api.run
make ai.run
make db.migrate
make test
make lint
make format
```

### 4.4. Ativar VodChat real

No `.env`, altere:

```env
VODCHAT_ENABLED=true
```

Por padrao, o `.env.example` deixa `VODCHAT_ENABLED=false` porque o modelo de chat e pesado. A API continua funcionando sem ele, usando fallback.

---

## 5. Estrutura do monorepo

```text
.
├── apps/
│   ├── api/
│   │   └── app/
│   │       ├── routers/
│   │       ├── services/
│   │       ├── repositories/
│   │       ├── models/
│   │       ├── schemas/
│   │       ├── auth/
│   │       ├── core/
│   │       └── integrations/
│   ├── ai/
│   │   └── app/
│   │       ├── api/routes/
│   │       ├── models/
│   │       ├── services/
│   │       └── core/
│   └── analytics/
│       └── analytics/
├── packages/
│   └── shared/
├── infra/
├── docs/
├── scripts/
├── Makefile
└── .env.example
```

Responsabilidades:

- `routers`: entrada HTTP, validacao de dependencia e resposta.
- `services`: regra de negocio.
- `repositories`: acesso ao banco.
- `models`: entidades SQLAlchemy ou modelos de IA.
- `schemas`: contratos Pydantic de request/response.
- `integrations`: clientes externos, como `AIClient`.
- `core`: configuracoes, cache, middlewares, seguranca e observabilidade.

---

## 6. API principal: `apps/api`

A API principal e o backend que o frontend consome.

Arquivo de inicializacao:

- `apps/api/app/main.py`

Routers registrados:

- `apps/api/app/routers/auth_router.py`
- `apps/api/app/routers/user_router.py`
- `apps/api/app/routers/video_router.py`
- `apps/api/app/routers/genre_router.py`
- `apps/api/app/routers/category_router.py`
- `apps/api/app/routers/plan_router.py`
- `apps/api/app/routers/favorite_router.py`
- `apps/api/app/routers/watch_session_router.py`
- `apps/api/app/routers/interaction_router.py`
- `apps/api/app/routers/recommendation_router.py`
- `apps/api/app/routers/report_router.py`
- `apps/api/app/routers/admin_router.py`
- `apps/api/app/routers/chat_router.py`

### 6.1. Autenticacao e autorizacao

O sistema usa JWT com algoritmo HS256.

Onde esta:

- `apps/api/app/auth/jwt.py`: criacao e validacao de tokens.
- `apps/api/app/auth/dependencies.py`: dependencias `get_current_user` e validacoes de usuario logado.
- `apps/api/app/auth/hashing.py`: hash de senha.
- `apps/api/app/services/auth_service.py`: regra de login, refresh e autenticacao.
- `apps/api/app/models/user.py`: modelo de usuario.
- `apps/api/app/models/refresh_token.py`: refresh tokens persistidos com hash.

Como apresentar:

> O usuario faz login, recebe um access token JWT e usa esse token no header `Authorization: Bearer`. As rotas protegidas validam o token antes de acessar os dados.

### 6.2. Usuarios e planos

O projeto possui usuarios com papeis `USER` e `ADMIN`, alem de planos de assinatura.

Onde esta:

- `apps/api/app/routers/user_router.py`
- `apps/api/app/routers/plan_router.py`
- `apps/api/app/services/user_service.py`
- `apps/api/app/services/plan_service.py`
- `apps/api/app/models/user.py`
- `apps/api/app/models/plan.py`

### 6.3. Catalogo de videos

O catalogo possui videos com:

- titulo;
- descricao;
- URL;
- duracao;
- data de lancamento;
- classificacao indicativa;
- generos;
- categorias;
- embedding semantico.

Onde esta:

- `apps/api/app/routers/video_router.py`
- `apps/api/app/services/video_service.py`
- `apps/api/app/repositories/video_repository.py`
- `apps/api/app/models/video.py`
- `apps/api/app/models/genre.py`
- `apps/api/app/models/category.py`
- `apps/api/app/models/video_genre.py`
- `apps/api/app/models/video_category.py`

### 6.4. Streaming dos videos

O projeto serve arquivos MP4 locais e suporta HTTP Range, permitindo que o player avance no video sem baixar tudo de uma vez.

Onde esta:

- `apps/api/app/services/video_storage.py`
- `apps/api/app/routers/video_router.py`
- `infra/docker-compose.yml`: volume de videos montado no container.

Como apresentar:

> A API nao apenas lista videos. Ela tambem entrega o arquivo de video com suporte a streaming parcial, usando o comportamento esperado por players web/mobile.

### 6.5. Favoritos

Permite favoritar e desfavoritar videos.

Onde esta:

- `apps/api/app/routers/favorite_router.py`
- `apps/api/app/services/favorite_service.py`
- `apps/api/app/repositories/favorite_repository.py`
- `apps/api/app/models/favorite.py`

### 6.6. Historico de visualizacao

As `watch_sessions` registram o consumo real do usuario:

- video assistido;
- tempo assistido;
- percentual assistido;
- se completou ou nao;
- timestamps.

Onde esta:

- `apps/api/app/routers/watch_session_router.py`
- `apps/api/app/services/watch_session_service.py`
- `apps/api/app/repositories/watch_session_repository.py`
- `apps/api/app/models/watch_session.py`

Esse historico e fundamental para:

- recomendacao personalizada;
- deteccao de abandono;
- relatorios;
- contexto do chatbot.

### 6.7. Logs de interacao

O sistema tambem registra eventos como:

- clique;
- busca;
- watch;
- favorite;
- unfavorite.

Onde esta:

- `apps/api/app/routers/interaction_router.py`
- `apps/api/app/services/interaction_service.py`
- `apps/api/app/repositories/interaction_log_repository.py`
- `apps/api/app/models/interaction_log.py`

### 6.8. Recomendacoes na API principal

Endpoint principal:

```text
GET /recommendations
```

Fluxo:

```text
Usuario chama /recommendations
        |
        v
RecommendationService
        |
        |-- Redis tem recomendacao fresca?
        |       |-- sim: retorna do banco
        |
        |-- IA esta disponivel e existe JWT?
        |       |-- sim: chama apps/ai em /llm/recommendations/{user_id}
        |
        |-- falhou ou nao tem IA?
                |-- fallback classico
```

Onde esta:

- `apps/api/app/routers/recommendation_router.py`
- `apps/api/app/services/recommendation_service.py`
- `apps/api/app/repositories/recommendation_repository.py`
- `apps/api/app/integrations/ai_client.py`
- `apps/api/app/core/cache.py`

### 6.9. Chatbot na API principal

Endpoint:

```text
POST /chat
```

Body:

```json
{
  "message": "Quais videos de natureza voce recomenda?"
}
```

Resposta:

```json
{
  "reply": "Separei estes videos sobre natureza...",
  "fallback": false,
  "videos": [],
  "search_query": "natureza",
  "catalog_empty": false
}
```

Onde esta:

- `apps/api/app/routers/chat_router.py`
- `apps/api/app/services/chat_service.py`
- `apps/api/app/services/chat_intent.py`
- `apps/api/app/schemas/chat.py`
- `apps/api/app/integrations/ai_client.py`

Como funciona:

1. O usuario chama `POST /chat` com JWT.
2. A API extrai o `user_id` do token.
3. `ChatService` tenta chamar o VodChat no servico de IA.
4. Em paralelo, se a mensagem parece pedir recomendacao, a API busca videos relevantes no catalogo.
5. Se a IA falhar, a API retorna fallback controlado.
6. Se encontrar videos confiaveis no catalogo, pode preferir resposta baseada no catalogo para evitar alucinacao.

Ponto importante:

> O chatbot e stateless: o historico de conversa nao e salvo entre chamadas. O contexto vem do historico de visualizacao do usuario, nao de uma memoria longa de conversa.

### 6.10. Administracao e relatorios

O projeto tem rotas administrativas para:

- CRUD de catalogo;
- indexacao de embeddings;
- relatorios;
- interacoes;
- modelos.

Onde esta:

- `apps/api/app/routers/admin_router.py`
- `apps/api/app/routers/report_router.py`
- `apps/api/app/services/report_service.py`

---

## 7. Servico de IA: `apps/ai`

O `apps/ai` e um microservico separado para concentrar modelos, inferencia e funcoes de IA.

Arquivo de inicializacao:

- `apps/ai/app/main.py`

Rotas:

- `apps/ai/app/api/router.py`
- `apps/ai/app/api/routes/llm.py`
- `apps/ai/app/api/routes/embeddings.py`
- `apps/ai/app/api/routes/admin.py`
- `apps/ai/app/api/routes/recommendations.py`
- `apps/ai/app/api/routes/profile.py`
- `apps/ai/app/api/routes/training.py`
- `apps/ai/app/api/routes/health.py`
- `apps/ai/app/api/routes/metrics.py`

Endpoints principais:

- `GET /api/v1/llm/info`
- `GET /api/v1/llm/recommendations/{user_id}`
- `POST /api/v1/llm/chat/{user_id}`
- `GET /api/v1/embeddings/encode?q=...`
- `POST /api/v1/admin/index-embeddings`
- `POST /api/v1/admin/reload-models`

---

## 8. Onde a IA esta aplicada

### 8.1. Recomendacao personalizada com VodRec-Transformer

Problema:

> Dado o historico de videos assistidos por um usuario, prever quais videos ele tem maior chance de assistir depois.

Tecnica:

- Transformer decoder-only;
- self-attention causal;
- embeddings de item;
- positional embeddings;
- tied embeddings;
- next-item prediction;
- loss Cross-Entropy;
- otimizador AdamW;
- avaliacao com HitRate@K, NDCG, MAP e MRR.

Onde esta:

- `apps/ai/app/models/vodrec_transformer.py`
- `apps/ai/app/models/orchestrator.py`
- `apps/ai/app/services/llm_recommendation_service.py`
- `apps/ai/scripts/train_vodrec.py`
- `apps/ai/scripts/validate_requirements.py`
- `apps/ai/docs/MODEL_CARD.md`
- `apps/ai/docs/ARQUITETURA_LLM.md`

Como explicar:

> Tratamos o historico do usuario como uma sequencia, do mesmo jeito que um modelo de linguagem trata palavras. Cada video vira um token. O modelo aprende a prever o proximo token da sequencia, que no nosso caso e o proximo video recomendado.

Fluxo conceitual:

```text
Historico do usuario:
[video_10, video_33, video_91, video_12]
        |
        v
Embedding de item + embedding posicional
        |
        v
Blocos Transformer com self-attention causal
        |
        v
Distribuicao de probabilidade sobre o catalogo
        |
        v
Top-K videos recomendados
```

Por que Transformer?

- Ele captura ordem temporal.
- Ele aprende padroes de transicao entre conteudos.
- Ele considera varios itens anteriores, nao apenas o ultimo.
- Ele e mais adequado para recomendacao sequencial do que uma regra simples de genero.

### 8.2. Cold start e fallback por popularidade

Problema:

> Quando um usuario novo tem pouco historico, o modelo neural nao possui contexto suficiente.

Tecnica:

- limiar minimo de interacoes;
- fallback por popularidade;
- degradacao graciosa.

Onde esta:

- `apps/ai/app/models/orchestrator.py`
- `apps/api/app/services/recommendation_service.py`

Regra usada:

- 0 views: retorna vazio ou deixa a API usar fallback.
- 1 a 4 views: usa `PopularityFallback`.
- 5 ou mais views: usa `VodRec-Transformer`.

Como apresentar:

> Isso evita que a IA force uma recomendacao ruim quando nao ha dados suficientes. O sistema escolhe a estrategia conforme a maturidade do perfil do usuario.

### 8.3. Recomendacao classica multi-sinal

Mesmo com IA, o backend tem um recomendador classico que sempre funciona.

Tecnica:

- feature engineering;
- afinidade por genero;
- afinidade por categoria;
- taxa de conclusao;
- popularidade;
- relevancia de busca;
- recencia;
- penalidade por abandono.

Onde esta:

- `apps/api/app/services/recommendation_service.py`

Formula conceitual:

```text
score =
  0.30 * afinidade_genero
+ 0.20 * afinidade_categoria
+ 0.15 * taxa_conclusao
+ 0.15 * popularidade
+ 0.10 * relevancia_busca
+ 0.10 * recencia
- penalidade_abandono
```

Como apresentar:

> Esse fallback e importante porque sistemas de IA em producao precisam continuar funcionando mesmo quando o modelo esta indisponivel, frio ou sem dados.

### 8.4. Busca semantica com embeddings

Problema:

> Busca por texto exato nao entende sinonimos, contexto ou intencao.

Exemplo:

- Usuario digita: "animais do pantanal"
- O titulo talvez nao contenha exatamente essa frase.
- A busca semantica encontra videos parecidos pelo significado.

Tecnica:

- `sentence-transformers`;
- modelo `paraphrase-multilingual-MiniLM-L12-v2`;
- embeddings normalizados de 384 dimensoes;
- PostgreSQL com extensao `pgvector`;
- distancia por cosseno;
- indice `ivfflat`.

Onde esta:

- `apps/ai/app/services/embedding_service.py`
- `apps/ai/app/api/routes/embeddings.py`
- `apps/api/app/services/video_service.py`
- `apps/api/app/repositories/video_repository.py`
- `apps/api/alembic/versions/e3f7a1b2c4d5_add_pgvector_embedding_to_videos.py`

Fluxo:

```text
GET /videos/search?q=animais do pantanal&semantic=true
        |
        v
API chama AIClient.encode(q)
        |
        v
apps/ai gera embedding 384-dim
        |
        v
Postgres ordena por description_embedding <=> query_embedding
        |
        v
Retorna videos semanticamente mais proximos
```

Como apresentar:

> Em vez de comparar palavras, comparamos vetores. Textos com significados parecidos ficam proximos no espaco vetorial.

### 8.5. Chatbot contextual com VodChat

Problema:

> O usuario quer conversar com o sistema em linguagem natural: pedir sugestoes, perguntar o que assistir e receber uma resposta explicada.

Tecnica:

- LLM open-source TinyLlama 1.1B;
- transfer learning;
- LoRA;
- supervised fine-tuning;
- prompt com contexto do historico recente;
- filtro contra respostas ruins;
- fallback quando indisponivel.

Onde esta:

- `apps/ai/app/models/vodchat.py`
- `apps/ai/app/models/vodchat_constraints.py`
- `apps/ai/app/models/orchestrator.py`
- `apps/ai/app/services/llm_recommendation_service.py`
- `apps/ai/app/api/routes/llm.py`
- `apps/api/app/services/chat_service.py`

Como funciona:

```text
POST /chat
        |
        v
apps/api valida JWT e extrai user_id
        |
        v
apps/api chama apps/ai /llm/chat/{user_id}
        |
        v
apps/ai carrega historico do usuario
        |
        v
VodChat recebe pergunta + contexto
        |
        v
Resposta textual em portugues
```

O que e LoRA:

> LoRA significa Low-Rank Adaptation. Em vez de treinar todos os pesos do LLM, o projeto treina pequenas matrizes adicionais de baixo rank. O modelo base fica congelado e apenas esses adapters aprendem o comportamento especifico do dominio.

Formula conceitual:

```text
W' = W + BA
```

Onde:

- `W` e o peso original congelado do modelo base;
- `B` e `A` sao matrizes menores treinaveis;
- o custo de treino cai muito em comparacao com fine-tuning completo.

Por que isso e importante:

- reduz custo de treino;
- cabe em GPU menor;
- gera adapter pequeno;
- permite adaptar o modelo para o dominio do catalogo VOD.

### 8.6. Anti-alucinacao no chatbot

LLMs podem inventar titulos. Para reduzir esse risco, o projeto possui protecoes.

Onde esta:

- `apps/ai/app/models/vodchat_constraints.py`
- `apps/api/app/services/chat_service.py`

Estrategias:

- penalizar titulos fora do catalogo;
- filtrar mencoes desconhecidas;
- detectar respostas em ingles, com URLs ou placeholders;
- preferir resposta baseada em catalogo quando videos reais foram encontrados.

Como apresentar:

> A preocupacao nao foi apenas "usar um chatbot", mas colocar guardrails para que ele nao recomende conteudo inexistente.

---

## 9. Como o backend conversa com a IA

O ponto central e o `AIClient`.

Onde esta:

- `apps/api/app/integrations/ai_client.py`

Ele faz:

- normalizacao da URL base da IA;
- envio do JWT do usuario;
- envio opcional de API key;
- timeout;
- circuit breaker;
- retorno `None` quando a IA falha, para a API usar fallback.

Fluxos:

```text
Recomendacao:
apps/api /recommendations
  -> AIClient.get_recommendations()
  -> apps/ai /api/v1/llm/recommendations/{user_id}

Chat:
apps/api /chat
  -> AIClient.chat()
  -> apps/ai /api/v1/llm/chat/{user_id}

Busca semantica:
apps/api /videos/search?semantic=true
  -> AIClient.encode()
  -> apps/ai /api/v1/embeddings/encode
```

---

## 10. Modelo de dados

Principais tabelas:

- `users`: usuarios, papel, plano e status.
- `refresh_tokens`: tokens de refresh com hash.
- `plans`: planos de assinatura.
- `videos`: catalogo de videos.
- `genres`: generos.
- `categories`: categorias.
- `video_genres`: relacao N:N entre videos e generos.
- `video_categories`: relacao N:N entre videos e categorias.
- `watch_sessions`: historico de visualizacao.
- `favorites`: favoritos do usuario.
- `interaction_logs`: eventos comportamentais.
- `recommendations`: recomendacoes materializadas.

Onde esta:

- `apps/api/app/models/`
- `apps/api/alembic/versions/0001_initial_schema.py`
- `apps/api/alembic/versions/e3f7a1b2c4d5_add_pgvector_embedding_to_videos.py`

Ponto importante:

> A tabela `videos` possui a coluna `description_embedding vector(384)`, usada pela busca semantica com pgvector.

---

## 11. Dataset e seeds

O projeto possui um catalogo real de videos em:

- `apps/ai/data/raw/`

Esses dados sao usados para popular o catalogo e alinhar os IDs com o vocabulario do recomendador.

Seeds:

- `apps/api/app/seeds/seed_data.py`
- `apps/api/app/seeds/seed_real_catalog.py`
- `apps/api/app/seeds/seed_demo_user.py`
- `apps/api/app/seeds/update_video_urls_to_stream.py`

Comandos manuais:

```bash
docker compose -f infra/docker-compose.yml exec api python -m app.seeds.seed_real_catalog
docker compose -f infra/docker-compose.yml exec api python -m app.seeds.seed_demo_user
docker compose -f infra/docker-compose.yml exec api python -m app.seeds.update_video_urls_to_stream
```

---

## 12. Analytics

O modulo `apps/analytics` gera relatorios offline a partir do mesmo banco.

Onde esta:

- `apps/analytics/analytics/cli.py`
- `apps/analytics/analytics/jobs/top_videos.py`
- `apps/analytics/analytics/jobs/retention.py`
- `apps/analytics/analytics/jobs/rec_effectiveness.py`
- `apps/analytics/README.md`

Jobs disponiveis:

```bash
python -m analytics top_videos --days 30
python -m analytics retention --cohort-days 7
python -m analytics rec_effectiveness
python -m analytics export_all
```

Via Docker:

```bash
make compose.analytics
```

Como apresentar:

> Alem de servir a aplicacao, o projeto tambem gera dados para tomada de decisao: videos mais vistos, retencao e efetividade das recomendacoes.

---

## 13. Infraestrutura

### 13.1. Docker Compose

Arquivo:

- `infra/docker-compose.yml`

Servicos:

- `db`: PostgreSQL 16 com pgvector.
- `redis`: cache.
- `api`: backend principal.
- `ai`: servico de IA.
- `analytics`: jobs offline sob profile.

### 13.2. Migrations automaticas

Arquivo:

- `infra/entrypoint-api.sh`

Ao subir o container da API, o projeto executa:

```bash
alembic upgrade head
```

Depois inicia o Uvicorn.

Como apresentar:

> Isso evita subir a aplicacao com schema desatualizado. Se a migration falhar, o container para e o erro fica visivel nos logs.

### 13.3. Variaveis de ambiente importantes

Arquivo:

- `.env.example`

Principais:

- `DATABASE_URL`: conexao com Postgres.
- `SECRET_KEY`: segredo JWT da API.
- `JWT_SECRET`: mesmo segredo no servico de IA.
- `REDIS_URL`: conexao Redis.
- `AI_SERVICE_URL`: URL do servico de IA para a API.
- `AI_SERVICE_API_KEY`: chave usada pela API ao chamar a IA.
- `AI_API_KEY`: protege rotas administrativas da IA.
- `AI_ENABLED`: habilita chamadas da API para IA.
- `SEMANTIC_SEARCH_ENABLED`: habilita busca semantica.
- `LLM_ENABLED`: carrega VodRec no boot da IA.
- `VODCHAT_ENABLED`: carrega VodChat no boot da IA.
- `VODREC_MODEL_PATH`: caminho do checkpoint do recomendador.
- `VODCHAT_ADAPTER_PATH`: caminho do adapter LoRA.

---

## 14. Testes e qualidade

Comandos:

```bash
make test
make test.api
make test.ai
make lint
make format
```

Onde estao os testes:

- `apps/api/tests/`
- `apps/ai/tests/`

Exemplos de cobertura importante:

- rotas de LLM;
- comportamento do chatbot;
- fallback do VodChat;
- constraints anti-alucinacao;
- configuracao de tokens do VodChat;
- cliente HTTP da IA.

---

## 15. Roteiro sugerido para apresentacao

### 15.1. Abertura

> Nosso projeto e uma plataforma VOD com backend completo, recomendacao inteligente, busca semantica e chatbot contextual. A ideia foi simular um produto real de streaming, com autenticacao, catalogo, historico, favoritos, IA e analytics.

### 15.2. Demonstrar a arquitetura

Mostre:

- `apps/api` como API principal;
- `apps/ai` como microservico de IA;
- PostgreSQL + pgvector;
- Redis;
- Docker Compose.

### 15.3. Demonstrar login

No Swagger:

1. Abra `http://localhost:8001/docs`.
2. Chame `POST /auth/login`.
3. Use `demo@streaming.com` / `demo1234`.
4. Copie o token.
5. Clique em `Authorize`.

### 15.4. Demonstrar catalogo e streaming

Mostre:

- listagem de videos;
- filtro por busca;
- endpoint de streaming;
- relacao com generos e categorias.

### 15.5. Demonstrar recomendacoes

Chame:

```text
GET /recommendations
```

Explique:

- primeiro tenta cache;
- depois tenta IA;
- se IA falhar, usa fallback classico;
- recomendacoes sao materializadas no banco.

### 15.6. Demonstrar busca semantica

Chame:

```text
GET /videos/search?q=natureza animais&semantic=true
```

Explique:

- a query vira vetor;
- o banco compara com embeddings dos videos;
- usa distancia cosseno via pgvector.

### 15.7. Demonstrar chatbot

Chame:

```text
POST /chat
```

Com:

```json
{
  "message": "Me recomende videos de natureza"
}
```

Explique:

- a API valida o usuario;
- o chat usa o historico do usuario;
- o VodChat pode responder em linguagem natural;
- se a IA nao estiver ativa, existe fallback.

### 15.8. Fechar com IA

Fale dos tres blocos:

- VodRec-Transformer para recomendacao;
- embeddings + pgvector para busca semantica;
- TinyLlama + LoRA para chatbot.

---

## 16. Perguntas provaveis da banca e respostas

### Onde exatamente voces usaram IA?

Usamos IA em tres pontos:

1. recomendacao neural sequencial com `VodRec-Transformer`;
2. busca semantica com embeddings de texto;
3. chatbot contextual com TinyLlama adaptado por LoRA.

Arquivos:

- `apps/ai/app/models/vodrec_transformer.py`
- `apps/ai/app/services/embedding_service.py`
- `apps/ai/app/models/vodchat.py`

### O recomendador foi feito por voces?

Sim. O `VodRec-Transformer` foi implementado em PyTorch, com blocos de self-attention, FFN, residual, LayerNorm, causal mask e tied embeddings.

Arquivo:

- `apps/ai/app/models/vodrec_transformer.py`

### O chatbot foi treinado do zero?

Nao. O chatbot usa um modelo base open-source, TinyLlama 1.1B, e aplica fine-tuning eficiente com LoRA para adaptar ao dominio do catalogo VOD.

Essa e uma abordagem correta de transfer learning: aproveita conhecimento linguistico geral do modelo base e treina apenas adapters menores para a tarefa especifica.

Arquivo:

- `apps/ai/app/models/vodchat.py`

### Por que usar LoRA?

Porque fine-tuning completo de um LLM e caro. Com LoRA, treinamos apenas matrizes pequenas de adaptacao, mantendo o modelo base congelado. Isso reduz memoria, tempo e custo.

### Como a busca semantica funciona?

Cada video recebe um vetor de 384 dimensoes baseado em titulo e descricao. Quando o usuario busca algo, a query tambem vira vetor. O Postgres com pgvector ordena os videos pela distancia cosseno.

Arquivos:

- `apps/ai/app/services/embedding_service.py`
- `apps/api/app/repositories/video_repository.py`

### O que acontece se a IA falhar?

O sistema continua funcionando. A API usa fallbacks:

- recomendacao classica;
- busca textual;
- resposta de chatbot com `fallback=true`;
- cache Redis quando disponivel.

Arquivos:

- `apps/api/app/services/recommendation_service.py`
- `apps/api/app/services/chat_service.py`
- `apps/api/app/services/video_service.py`
- `apps/api/app/integrations/ai_client.py`

### Como voces evitam que o chatbot invente titulos?

O sistema tem filtros e constraints:

- detecta respostas ruins;
- filtra titulos desconhecidos;
- prefere resposta baseada no catalogo quando ha sugestoes reais;
- usa guardrails no VodChat.

Arquivos:

- `apps/ai/app/models/vodchat_constraints.py`
- `apps/api/app/services/chat_service.py`

### Por que separar API e IA?

Porque sao responsabilidades diferentes:

- API principal precisa ser rapida, estavel e lidar com regras de negocio.
- Servico de IA pode carregar modelos pesados, ter dependencias proprias e escalar separadamente.

Isso tambem permite desligar ou reiniciar a IA sem derrubar a API principal.

---

## 17. Mapa rapido: feature -> onde esta no codigo

| Feature | Arquivos principais |
|---|---|
| Inicializacao da API | `apps/api/app/main.py` |
| Inicializacao da IA | `apps/ai/app/main.py` |
| Docker | `infra/docker-compose.yml` |
| Comandos | `Makefile` |
| Variaveis | `.env.example` |
| Auth JWT | `apps/api/app/auth/jwt.py`, `apps/api/app/auth/dependencies.py` |
| Login/refresh | `apps/api/app/services/auth_service.py`, `apps/api/app/routers/auth_router.py` |
| Usuarios | `apps/api/app/models/user.py`, `apps/api/app/services/user_service.py` |
| Planos | `apps/api/app/models/plan.py`, `apps/api/app/services/plan_service.py` |
| Videos | `apps/api/app/models/video.py`, `apps/api/app/services/video_service.py` |
| Streaming | `apps/api/app/services/video_storage.py` |
| Generos/categorias | `apps/api/app/models/genre.py`, `apps/api/app/models/category.py` |
| Favoritos | `apps/api/app/services/favorite_service.py` |
| Watch sessions | `apps/api/app/services/watch_session_service.py` |
| Logs de interacao | `apps/api/app/services/interaction_service.py` |
| Recomendacao API | `apps/api/app/services/recommendation_service.py` |
| Cliente da IA | `apps/api/app/integrations/ai_client.py` |
| Chat API | `apps/api/app/services/chat_service.py`, `apps/api/app/routers/chat_router.py` |
| Intencao do chat | `apps/api/app/services/chat_intent.py` |
| VodRec | `apps/ai/app/models/vodrec_transformer.py` |
| Orquestrador IA | `apps/ai/app/models/orchestrator.py` |
| LLM routes | `apps/ai/app/api/routes/llm.py` |
| VodChat | `apps/ai/app/models/vodchat.py` |
| Anti-alucinacao | `apps/ai/app/models/vodchat_constraints.py` |
| Embeddings | `apps/ai/app/services/embedding_service.py` |
| Busca pgvector | `apps/api/app/repositories/video_repository.py` |
| Migration pgvector | `apps/api/alembic/versions/e3f7a1b2c4d5_add_pgvector_embedding_to_videos.py` |
| Analytics | `apps/analytics/analytics/jobs/` |
| Model card | `apps/ai/docs/MODEL_CARD.md` |
| Arquitetura LLM | `apps/ai/docs/ARQUITETURA_LLM.md` |
| Guia de usuario | `docs/INTEGRACAO_USUARIO.md` |
| Guia admin | `docs/INTEGRACAO_ADMIN.md` |

---

## 18. Pontos fortes do projeto

- Arquitetura separada por servicos.
- Backend completo com autenticacao, catalogo e historico.
- IA aplicada em recomendacao, busca e chat.
- Recomendador neural proprio em PyTorch.
- Uso de embeddings e pgvector para recuperacao semantica.
- Chatbot com transfer learning e LoRA.
- Fallbacks para manter o sistema funcionando sem IA.
- Cache Redis para performance.
- Migrations automaticas no boot.
- Analytics offline para medir comportamento.
- Documentacao e testes para API e IA.

---

## 19. Limitacoes e melhorias futuras

Limitacoes atuais:

- VodChat pode ser pesado em CPU.
- Chat e stateless, sem memoria de conversa entre chamadas.
- Qualidade do recomendador depende da quantidade e qualidade de interacoes.
- Catalogo local e pequeno para fins de demonstracao.
- O uso real em producao exigiria monitoramento continuo de drift e qualidade.

Melhorias futuras:

- streaming de resposta do chatbot;
- memoria conversacional persistida;
- re-treino periodico automatizado;
- A/B test de recomendacoes;
- dashboard web para analytics;
- quantizacao GGUF do VodChat para CPU;
- observabilidade mais completa com tracing e metricas de negocio.

---

## 20. Frase final para a apresentacao

> O principal diferencial do projeto e que ele nao usa IA como uma funcionalidade isolada. A IA esta integrada ao fluxo real da aplicacao: melhora a descoberta de conteudo com recomendacao neural, melhora a busca com embeddings semanticos e melhora a experiencia do usuario com um chatbot contextual. Ao mesmo tempo, o sistema foi pensado com fallback, cache e separacao de servicos para continuar funcionando mesmo quando os modelos nao estiverem disponiveis.
