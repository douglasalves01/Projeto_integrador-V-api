# Aplicação de Inteligência Artificial — Plataforma VOD

**Projeto Integrador V — PUC-Campinas**

---

## Contexto do Projeto

Plataforma de streaming sob demanda (VOD) onde os conceitos de IA da disciplina
foram aplicados em problemas reais: recomendar conteúdo, entender linguagem
natural e recuperar informação por significado.

---

## 1. Redes Neurais e Transformer — Recomendação Sequencial

### Conceito aplicado
Redes neurais profundas com mecanismo de atenção (Transformer), aprendizado
supervisionado com gradiente descendente e função de perda Cross-Entropy.

### Problema
Dado o histórico de vídeos assistidos por um usuário, prever qual vídeo ele
vai querer assistir a seguir (**next-item prediction**).

### Como foi aplicado
Foi implementado um **Transformer decoder-only** do zero em PyTorch — sem
bibliotecas prontas de alto nível — seguindo a mesma arquitetura do GPT:

```
Histórico: [Interestelar, Gravity, Arrival]
                    ↓
         Item Embedding + Positional Embedding
                    ↓
       Multi-Head Self-Attention (causal mask)
         "cada vídeo presta atenção nos anteriores,
          nunca nos futuros"
                    ↓
         Feed Forward (GELU) + Residual + LayerNorm
                    ↓  (× 4 blocos)
         Logits → Softmax → Top-K vídeos recomendados
```

**Causal mask:** impede que o modelo "veja o futuro" durante o treinamento.
É uma matriz triangular inferior que zera os scores de atenção para posições
futuras — o mesmo princípio usado em modelos de linguagem.

**Tied embeddings:** a mesma matriz usada para representar os vídeos na entrada
é reutilizada na projeção final (`logits = h @ W_emb^T`). Reduz parâmetros e
garante que o espaço de entrada e saída seja coerente.

**Treinamento:** cross-entropy loss entre o próximo token real e a distribuição
prevista pelo modelo. Tokens de padding são ignorados (`ignore_index=0`).

> Arquivo: `apps/ai/app/models/vodrec_transformer.py`

---

## 2. Problema de Cold Start — Estratégia por Limiar

### Conceito aplicado
Cold start é um problema clássico de Sistemas de Recomendação: o modelo não
tem dados suficientes do usuário para fazer previsões confiáveis.

### Como foi aplicado
Foi definido um limiar baseado no requisito RFIA03 da disciplina:

| Situação | Estratégia |
|---|---|
| 0 vídeos assistidos | Retorna lista vazia — API usa popularidade global |
| 1 a 4 vídeos | **PopularityFallback** — ranking pelos mais assistidos da plataforma |
| 5 ou mais vídeos | **VodRec-Transformer** — predição personalizada |

O limiar de 5 vídeos foi escolhido como mínimo para que a sequência de entrada
tenha contexto suficiente para a atenção funcionar de forma significativa.

> Arquivo: `apps/ai/app/models/orchestrator.py`

---

## 3. Representação de Conhecimento e Similaridade — Busca Semântica

### Conceito aplicado
Word embeddings / sentence embeddings: representar texto como vetores em
espaço de alta dimensão onde significados parecidos ficam próximos.
Similaridade por cosseno como métrica de distância semântica.

### Problema
Busca por substring (`LIKE '%heroi%'`) não encontra "Mad Max" para a query
"herói em estrada". O usuário precisa saber o título exato.

### Como foi aplicado
Cada vídeo é representado por um **vetor de 384 dimensões** gerado pelo
modelo `paraphrase-multilingual-MiniLM-L12-v2` (treinado para português),
armazenado no banco de dados via extensão **pgvector**.

```
Usuário digita: "herói viajando no tempo"
                        ↓
           sentence-transformers.encode()
                        ↓
         vetor 384-dim: [0.023, -0.145, ...]
                        ↓
     PostgreSQL: ORDER BY embedding <=> query_vector
                  (distância coseno — pgvector)
                        ↓
         Vídeos semanticamente similares
         mesmo sem as palavras exatas no título
```

A **similaridade por cosseno** mede o ângulo entre dois vetores no espaço
semântico. Quanto menor o ângulo (cosseno mais próximo de 1), mais similares
os significados — independente do comprimento dos textos.

> Arquivos: `apps/ai/app/services/embedding_service.py`,
> `apps/api/app/repositories/video_repository.py`

---

## 4. Scoring Multi-sinal — Algoritmo de Recomendação Clássico

### Conceito aplicado
Feature engineering, normalização de atributos e combinação ponderada de
múltiplos sinais — base dos algoritmos de recomendação baseados em conteúdo
e filtragem colaborativa simplificada.

### Como foi aplicado
Quando a IA não está disponível (modelo não treinado, usuário novo), um
algoritmo de scoring calcula uma pontuação para cada vídeo candidato:

```
score(v) = 0,30 × afinidade_genero(v)
         + 0,20 × afinidade_categoria(v)
         + 0,15 × taxa_de_conclusao(v)
         + 0,15 × popularidade(v)
         + 0,10 × relevancia_de_busca(v)
         + 0,10 × recencia
         × penalidade_abandono(v)
```

Cada sinal é calculado a partir do comportamento real do usuário:

- **Afinidade de gênero:** proporção do tempo total assistido por gênero
- **Recência:** decaimento linear — `1 - dias_desde_última_interação / 30`
- **Penalidade de abandono:** multiplica o score por 0,5 se o usuário
  abandonou mais de 50% das sessões daquele vídeo (sinal negativo explícito)

> Arquivo: `apps/api/app/services/recommendation_service.py`

---

## 5. Transfer Learning e Fine-tuning — Assistente de Chat (VodChat)

### Conceito aplicado
Transfer learning: partir de um modelo pré-treinado em grande corpus e
adaptá-lo para uma tarefa específica com poucos dados.
LoRA (Low-Rank Adaptation): técnica de fine-tuning eficiente que treina
apenas matrizes de baixa dimensão, sem alterar os pesos originais.

### Como foi aplicado
O assistente **VodChat** usa o **TinyLlama 1.1B** como modelo base — um LLM
treinado em trilhões de tokens — e aplica um adapter **LoRA** treinado
especificamente para:
- Conhecer o catálogo de vídeos da plataforma
- Responder perguntas sobre recomendações em português
- Usar o histórico do usuário como contexto

```
Pergunta: "Quais filmes de ação você recomenda?"
                ↓
  Contexto injetado no prompt:
    - Catálogo completo de vídeos
    - Últimos 8 filmes que o usuário assistiu
                ↓
     TinyLlama 1.1B + LoRA adapter
                ↓
  "Com base no seu histórico, você pode gostar
   de 'Mad Max: Estrada da Fúria'..."
```

O LoRA adiciona matrizes `A` e `B` de baixo rank a cada camada de atenção:
`W' = W + BA`, onde `W` permanece congelado e apenas `B` e `A` são treinados.
Isso reduz drasticamente o número de parâmetros treináveis.

> Arquivos: `apps/ai/app/models/vodchat.py`,
> `apps/ai/app/services/llm_recommendation_service.py`

---

## 6. Sistemas Inteligentes e Robustez — Fallbacks em Cadeia

### Conceito aplicado
Sistemas inteligentes em produção precisam de **degradação graciosa**: quando
um componente de IA falha, o sistema não pode parar — ele precisa cair de
forma controlada para uma alternativa menos sofisticada.

### Como foi aplicado

```
Usuário pede recomendações
        │
        ▼
[1] Cache Redis válido?
    SIM → retorna resultado anterior (resposta em ms)
        │
        ▼ NÃO
[2] IA disponível e usuário tem ≥ 5 vídeos?
    SIM → VodRec-Transformer (predição neural)
        │
        ▼ NÃO
[3] Scoring clássico (sempre funciona, sem modelo)
```

O mesmo padrão se aplica na busca semântica:
- IA online → embeddings + pgvector
- IA offline → busca por substring clássica

E no chat:
- VodChat disponível → resposta do LLM
- Qualquer falha → `{"reply": "...", "fallback": true}` — nunca um erro 500

---

## Resumo

| Conceito da Disciplina | Aplicação no Projeto | Arquivo |
|---|---|---|
| Redes Neurais Profundas | VodRec-Transformer (PyTorch do zero) | `vodrec_transformer.py` |
| Mecanismo de Atenção | Multi-head self-attention com causal mask | `vodrec_transformer.py` |
| Next-item prediction | Recomendação sequencial por histório | `orchestrator.py` |
| Cold Start | Limiar de 5 vídeos, 3 estratégias | `orchestrator.py` |
| Word/Sentence Embeddings | Vetores 384-dim para busca semântica | `embedding_service.py` |
| Similaridade por Cosseno | Busca pgvector `<=>` | `video_repository.py` |
| Transfer Learning + LoRA | VodChat sobre TinyLlama 1.1B | `vodchat.py` |
| Feature Engineering | Scoring multi-sinal ponderado | `recommendation_service.py` |
| Degradação Graciosa | Fallbacks em cadeia (IA → clássico → cache) | `recommendation_service.py` |
