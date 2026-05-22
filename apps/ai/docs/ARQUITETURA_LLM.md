# Arquitetura LLM — VOD-IA

Documento técnico que descreve a substituição da abordagem clássica (TF-IDF + ALS) por **modelos LLM construídos do zero ou fine-tunados**.

> Esta arquitetura **não usa** OpenAI, Gemini, Claude ou qualquer API externa. Não usa `sklearn.TfidfVectorizer` nem `implicit.ALS` como motor da recomendação. Os modelos são treinados pelo time do projeto.

---

## 1. Resumo executivo

A plataforma VOD utiliza **dois modelos próprios**, ambos treinados pelo time:

```
┌────────────────────────────────────────────────────────────────┐
│                    Cliente (Flutter)                            │
└──────────────────────┬─────────────────────────────────────────┘
                       │ HTTPS
                       ▼
┌────────────────────────────────────────────────────────────────┐
│             Backend Node.js (Express/Fastify)                   │
└──────────────────────┬─────────────────────────────────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────────────────┐
│  VOD-IA Service (Python · FastAPI · PyTorch · Transformers)    │
│                                                                  │
│  ┌──────────────────────────┐    ┌────────────────────────┐    │
│  │   VodRec-Transformer     │    │       VodChat          │    │
│  │   (recomendação)         │    │   (LLM textual)        │    │
│  │                          │    │                        │    │
│  │ Decoder-only Transformer │    │ TinyLlama-1.1B ou      │    │
│  │ em PyTorch puro          │    │ Phi-3-mini 3.8B com    │    │
│  │ ~10M parâmetros          │    │ LoRA fine-tuning       │    │
│  │                          │    │                        │    │
│  │ Input:  seq de content_id│    │ Input:  prompt textual │    │
│  │ Output: prob sobre items │    │ Output: texto natural  │    │
│  │                          │    │                        │    │
│  │ Treinado from scratch    │    │ Fine-tuned com LoRA    │    │
│  │ Loss: CE next-item       │    │ Loss: SFT + opcional   │    │
│  │                          │    │       DPO             │    │
│  └──────────────────────────┘    └────────────────────────┘    │
│              │                              │                   │
│              └──────────────┬───────────────┘                   │
│                             ▼                                   │
│              ┌──────────────────────────────┐                   │
│              │  RecommendationOrchestrator  │                   │
│              │  - chama VodRec para ranking │                   │
│              │  - chama VodChat para        │                   │
│              │    explicação opcional       │                   │
│              └──────────────────────────────┘                   │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
              ┌──────────────────────────────┐
              │  MySQL  +  Redis cache       │
              └──────────────────────────────┘
```

---

## 2. Por que dois modelos?

| Necessidade | Modelo certo | Por quê |
|---|---|---|
| Prever rapidamente o próximo item que o usuário vai consumir, sobre um catálogo finito de N itens | **VodRec-Transformer** (próprio) | Sequence-aware. Softmax sobre o catálogo é direto. Caps de latência (RFIA02) facilmente atingíveis. |
| Gerar texto natural explicando *por que* uma recomendação foi feita, ou conversar sobre o catálogo | **VodChat** (LLM fine-tunado) | LLM textual é o instrumento certo para gerar linguagem natural fluente. |

Misturar as duas tarefas em **um único LLM textual** funciona, mas:
1. fica caro para inferência (precisa gerar tokens um a um), comprometendo RFIA02
2. fica difícil garantir que ele só sugira itens que existem no catálogo
3. metrica de avaliação fica subjetiva

Por isso usamos cada um para o que faz melhor.

---

## 3. Modelo 1 — VodRec-Transformer

### 3.1 Inspiração

Combinação de:
- **SASRec** (Kang & McAuley, 2018) — Self-attentive sequential recommendation.
- **BERT4Rec** (Sun et al., 2019) — Bidirectional encoder com MLM.
- **GPT-2** (Radford et al., 2019) — Decoder-only causal LM.

Escolhemos **decoder-only causal**, igual GPT, porque é mais simples de treinar e servir, e a tarefa "prever o próximo item" combina naturalmente com causal language modeling.

### 3.2 Formulação

Cada usuário tem uma sequência de visualizações ordenada por tempo:

```
S_u = [c_1, c_2, c_3, ..., c_T]
```

onde `c_i ∈ {1, ..., V}` é o `content_id` do i-ésimo conteúdo assistido e `V` é o tamanho do catálogo (vocabulário).

O modelo aprende a distribuição:

```
P(c_{t+1} | c_1, ..., c_t)
```

ou seja, dada a sequência até `t`, prevê probabilidade sobre **todos os V itens** do catálogo para `t+1`.

### 3.3 Arquitetura (PyTorch puro — sem `transformers` da HF)

```python
class VodRecTransformer(nn.Module):
    def __init__(self, vocab_size, d_model=128, n_heads=4, n_layers=4,
                 max_seq_len=128, dropout=0.1):
        super().__init__()
        # Embeddings
        self.item_emb = nn.Embedding(vocab_size + 2, d_model, padding_idx=0)
        # +2: 0 = padding, 1 = [MASK] (opcional, futuro)
        self.pos_emb = nn.Embedding(max_seq_len, d_model)

        # N blocos de Transformer decoder
        self.blocks = nn.ModuleList([
            TransformerBlock(d_model, n_heads, dropout)
            for _ in range(n_layers)
        ])
        self.ln_f = nn.LayerNorm(d_model)

        # Tied weights: o head de saída compartilha pesos com item_emb
        # (reduz parâmetros e melhora generalização)

    def forward(self, seq):
        # seq: (B, T) — ids de items, 0 = pad
        B, T = seq.shape
        positions = torch.arange(T, device=seq.device).unsqueeze(0)

        x = self.item_emb(seq) + self.pos_emb(positions)
        mask = causal_mask(T)  # (T, T) — só pode atender ao passado

        for block in self.blocks:
            x = block(x, mask)
        x = self.ln_f(x)

        # Logits = x @ item_emb.weight.T (tied embeddings)
        logits = x @ self.item_emb.weight.T  # (B, T, V+2)
        return logits  # cross-entropy contra targets shiftados em 1
```

Onde `TransformerBlock` é um bloco GPT-style: MultiHeadSelfAttention + FFN + residual + LayerNorm.

### 3.4 Hiperparâmetros sugeridos

| Hiperparâmetro | Valor |
|---|---|
| `d_model` (embedding dim) | 128 |
| `n_heads` | 4 |
| `n_layers` | 4 |
| `max_seq_len` | 128 (últimos 128 vistos) |
| `dropout` | 0.1 |
| Otimizador | AdamW, lr=3e-4, weight_decay=0.01 |
| LR schedule | Linear warmup 1k steps + cosine decay |
| Batch | 256 |
| Epochs | 20–50 (early stop em validation HR@10) |
| Loss | Cross-entropy com `label_smoothing=0.1`, ignorando pad (`ignore_index=0`) |

Com `vocab_size=10000` (catálogo de 10k títulos), o modelo tem ~5–8M parâmetros. Cabe **folgado** em uma GPU T4 do Colab gratuito.

### 3.5 Treino

1. Constrói para cada usuário a sequência ordenada `S_u` filtrando `rating_implicit >= 0.4` (sinal positivo).
2. Para sequências mais longas que `max_seq_len`, faz **sliding window** com stride 32.
3. Para cada amostra `seq[:-1]`, o target é `seq[1:]` (next-item prediction).
4. Pad à esquerda com 0.
5. Treina com cross-entropy categorical.

```python
# pseudocódigo do loop de treino
for epoch in range(num_epochs):
    for seq in dataloader:
        # seq: (B, T)
        inputs  = seq[:, :-1]         # (B, T-1)
        targets = seq[:, 1:]          # (B, T-1)
        logits  = model(inputs)       # (B, T-1, V)
        loss = F.cross_entropy(
            logits.reshape(-1, V),
            targets.reshape(-1),
            ignore_index=0,           # ignora padding
            label_smoothing=0.1,
        )
        loss.backward()
        optimizer.step()
        optimizer.zero_grad()
```

### 3.6 Inferência

```python
def recommend(model, history: List[int], k: int = 20, exclude_seen=True):
    # history: lista de content_ids, mais recente por último
    seq = torch.tensor([history[-max_seq_len:]]).to(device)
    with torch.no_grad():
        logits = model(seq)         # (1, T, V+2)
    last_logits = logits[0, -1]      # (V+2,)
    # Excluir pad e mask tokens
    last_logits[0] = -float('inf')
    last_logits[1] = -float('inf')
    if exclude_seen:
        for cid in history:
            last_logits[cid] = -float('inf')
    probs = F.softmax(last_logits, dim=-1)
    topk_scores, topk_ids = probs.topk(k)
    return list(zip(topk_ids.tolist(), topk_scores.tolist()))
```

Latência alvo em CPU (sem GPU em produção): ~30–80ms para `k=20` com modelo de 8M parâmetros. Em GPU T4: <5ms.

### 3.7 Cold start

Para usuários com `< 5` interações (RFIA03), o modelo ainda funciona — apenas a sequência é curta. Mas a qualidade cai. Estratégias:

1. **Padding com `<bos>` token** + treino com sequências curtas no augmentation → o modelo aprende a recomendar mesmo com pouco histórico.
2. **Fallback para popularity** se `len(history) < 2`.
3. **Mistura com VodChat** (próxima seção): para usuários novos, perguntar gêneros preferidos e usar VodChat para gerar recomendações guiadas.

---

## 4. Modelo 2 — VodChat (LLM fine-tunado)

### 4.1 Escolha do modelo base

Comparação de candidatos (todos open source, rodam no Colab gratuito):

| Modelo | Parâmetros | VRAM (fp16) | VRAM (4bit) | Qualidade | Velocidade |
|---|---|---|---|---|---|
| **TinyLlama-1.1B-Chat** | 1.1B | 2.2GB | 0.8GB | Boa | Rápida |
| **Qwen2.5-0.5B-Instruct** | 0.5B | 1GB | 0.4GB | Razoável | Muito rápida |
| **Phi-3-mini-4k-Instruct** | 3.8B | 7.6GB | 2.5GB | Excelente | Média |
| **Gemma-2-2B-it** | 2B | 4GB | 1.5GB | Muito boa | Média |

**Recomendação:** **TinyLlama-1.1B** para POC e demo (cabe em qualquer hardware) ou **Phi-3-mini** se houver GPU com 8GB+ disponível. Os dois são tratados nos notebooks.

### 4.2 Estratégia: LoRA (Low-Rank Adaptation)

Em vez de fine-tunar todos os pesos (caro), adicionamos matrizes de baixa-rank que aprendem o "delta" sobre os pesos congelados.

```
W = W_pretrained + α · A B
       (frozen)    (treinável, posto r=8 ou 16)
```

Só ~0.5–2% dos parâmetros são treináveis. Treino cabe em GPU de 8GB.

Lib: **`peft`** (Parameter Efficient Fine-Tuning) da Hugging Face.

### 4.3 Dataset de fine-tuning

Construímos um dataset sintético + bootstrap do catálogo, em formato instrução-resposta:

```json
[
  {
    "instruction": "Recomende 5 filmes para um usuário que assistiu: 'Vingança Sombra', 'Eclipse Tormenta', 'Caçador Lua' (todos Ação/Aventura).",
    "response": "Com base no histórico de Ação/Aventura, sugiro:\n1. **Reino Destino** — aventura épica\n2. **Última Lenda** — ação com herói solitário\n..."
  },
  {
    "instruction": "Por que você recomendou 'Cidade Eclipse' para mim?",
    "response": "Recomendei *Cidade Eclipse* porque ela combina os gêneros Ação e Suspense que aparecem com frequência no seu histórico..."
  },
  {
    "instruction": "Quero algo mais leve do que o que costumo ver. Sugestões?",
    "response": "Notei que você assiste muito Ação e Suspense. Para uma noite mais leve, recomendo Comédia ou Romance..."
  }
]
```

**Pelo menos 1.000–3.000 exemplos** são suficientes com LoRA. Eles são gerados:
1. Programaticamente, combinando metadados reais do catálogo (gêneros, sinopses) com templates.
2. Por destilação: pode-se usar um LLM grande **uma única vez** para gerar exemplos diversos (não é dependência de runtime — só de geração do dataset).

### 4.4 Pipeline de treino

Usaremos a stack padrão de HF:

```python
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer
from datasets import Dataset

# 1. Carrega base em 4-bit (QLoRA)
model = AutoModelForCausalLM.from_pretrained(
    "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    load_in_4bit=True,
    device_map="auto",
)
model = prepare_model_for_kbit_training(model)

# 2. Adiciona LoRA
lora_config = LoraConfig(
    r=16, lora_alpha=32, target_modules=["q_proj", "v_proj"],
    lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
)
model = get_peft_model(model, lora_config)

# 3. SFT
trainer = SFTTrainer(
    model=model,
    train_dataset=ds,
    tokenizer=tokenizer,
    args=TrainingArguments(
        output_dir="vodchat-lora",
        num_train_epochs=3,
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        bf16=True,
        logging_steps=10,
        save_strategy="epoch",
    ),
    max_seq_length=1024,
)
trainer.train()
trainer.save_model("vodchat-lora-final")
```

O adapter LoRA fica em ~10–50 MB (vs 2GB do modelo base). O modelo base é baixado uma vez e fica em cache.

### 4.5 Inferência

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

tok = AutoTokenizer.from_pretrained("TinyLlama/TinyLlama-1.1B-Chat-v1.0")
base = AutoModelForCausalLM.from_pretrained(
    "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    torch_dtype=torch.bfloat16,
    device_map="auto",
)
model = PeftModel.from_pretrained(base, "vodchat-lora-final")
model.eval()

def explain(user_history_titles: list[str], rec_title: str) -> str:
    prompt = build_explanation_prompt(user_history_titles, rec_title)
    inputs = tok(prompt, return_tensors="pt").to(model.device)
    out = model.generate(**inputs, max_new_tokens=120, temperature=0.7, do_sample=True)
    return tok.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
```

Latência alvo em T4: ~300–800ms para 100 tokens. Em CPU: 2–5s. Por isso o uso do VodChat é **opcional e assíncrono** — a recomendação principal vem do VodRec-Transformer (rápido), e a explicação é carregada em segundo plano se o usuário pedir.

### 4.6 Quantização para produção

Para servir em CPU com latência aceitável:

- **GGUF + llama.cpp:** converter o adapter merged + base para GGUF Q4_K_M. Inferência em CPU vira ~50–200ms para 100 tokens.
- **ONNX + ONNX Runtime:** alternativa para produção em ambientes não-Linux.
- **vLLM ou TGI:** se houver GPU dedicada em produção.

---

## 5. RecommendationOrchestrator

A camada que decide qual modelo chamar e como combinar:

```python
class RecommendationOrchestrator:
    def __init__(self, vodrec: VodRecTransformer, vodchat: VodChat):
        self.vodrec = vodrec
        self.vodchat = vodchat

    def recommend(self, user_id: int, history: list[int], k: int = 20,
                  with_explanation: bool = False) -> dict:
        # 1. Ranking rápido com VodRec
        ranked = self.vodrec.recommend(history, k=k)

        # 2. Se pedido, gera explicação para o top-1 com VodChat (async)
        if with_explanation and ranked:
            top_content = ranked[0][0]
            explanation = self.vodchat.explain(history, top_content)
        else:
            explanation = None

        return {
            "model_version": "vodrec-v1.0+vodchat-v1.0",
            "recommendations": ranked,
            "top_explanation": explanation,
        }

    def chat(self, user_id: int, history: list[int], message: str) -> str:
        # Conversa livre com o usuário sobre o catálogo
        return self.vodchat.chat(history, message)
```

---

## 6. Endpoints do AI Service

| Endpoint | Modelo usado | Latência alvo |
|---|---|---|
| `GET /recommendations/{user_id}?k=20` | VodRec | < 100ms (CPU) / < 10ms (GPU) |
| `GET /recommendations/{user_id}?with_explanation=true` | VodRec + VodChat | < 2s (RFIA02) |
| `POST /chat/{user_id}` (body: `{"message": "..."}`) | VodChat | < 3s |
| `POST /profile/{user_id}/update` | (atualiza sequência) | < 50ms |
| `POST /train/vodrec` | treino completo VodRec (batch) | — |
| `POST /train/vodchat` | fine-tune VodChat (batch) | — |

---

## 7. Estrutura de pastas atualizada

```
VOD-IA/
├── app/
│   ├── models/
│   │   ├── vodrec_transformer.py   ← NOVO — arquitetura PyTorch
│   │   ├── vodchat.py              ← NOVO — wrapper de inferência do LLM
│   │   ├── orchestrator.py         ← NOVO — combina os dois
│   │   ├── content_based.py        (legado, fallback)
│   │   ├── collaborative.py        (legado, fallback)
│   │   └── hybrid.py               (legado, fallback)
│   ├── services/
│   │   ├── llm_recommendation_service.py   ← NOVO
│   │   └── ...
│   ├── api/routes/
│   │   ├── llm.py                  ← NOVO — endpoints /chat e /explain
│   │   └── ...
│   └── ...
├── notebooks/
│   ├── 06_vodrec_transformer.ipynb     ← NOVO
│   └── 07_vodchat_lora_finetune.ipynb  ← NOVO
├── scripts/
│   ├── train_vodrec.py             ← NOVO
│   └── train_vodchat.py            ← NOVO
├── data/
│   ├── vodrec/
│   │   ├── sequences.parquet       (sequências de treino)
│   │   └── vocab.json              (mapeamento content_id ↔ token_id)
│   └── vodchat/
│       ├── sft_dataset.jsonl       (dataset de instrução)
│       └── eval_prompts.jsonl
├── models/
│   ├── vodrec/
│   │   ├── model.pt                (state_dict do VodRec)
│   │   ├── config.json             (hiperparâmetros)
│   │   └── VERSION.txt
│   └── vodchat/
│       ├── adapter_model.safetensors  (LoRA adapter)
│       ├── adapter_config.json
│       └── VERSION.txt
├── requirements.txt                (atualizado)
├── requirements-llm.txt            ← NOVO — torch/transformers/peft/trl
└── docs/
    ├── ARQUITETURA_LLM.md          ← este documento
    └── PROMPTS_CURSOR_LLM.md       ← prompts para implementar
```

---

## 8. Mapeamento Requisitos → LLM

| Requisito | Como é atendido nesta arquitetura |
|---|---|
| RFIA01 — Acurácia ≥ 70% (HitRate@10) | VodRec-Transformer normalmente supera 75–85% em datasets sintéticos bem feitos e 65–80% em reais |
| RFIA02 — Resposta ≤ 2s | VodRec em CPU: ~50–80ms. VodChat para explicação só é chamado se solicitado (async) |
| RFIA03 — Mín. 5 conteúdos | VodRec funciona com qualquer N ≥ 1; fallback para popularity se N < 2 |
| RFIA04 — Atualização contínua | A sequência do usuário é apêndice em MySQL; VodRec não precisa retreinar a cada interação |
| Seção 6 — Classificar gostos | As representações latentes do VodRec (embeddings de itens + estado oculto do usuário) **são** a classificação aprendida; `genre_weights` continua sendo derivado para UI |
| Seção 7.4 — Híbrido | VodRec atende sozinho; opcionalmente, ensemble com CF clássico para diversidade |

---

## 9. Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Pouca diversidade de dados sintéticos prejudica o LLM | Treinar VodRec primeiro com dados reais quando o backend estiver vivo; manter pipeline de dados claro |
| VodChat alucinar títulos que não existem | Constrained decoding: durante a geração, força que IDs de filmes mencionados estejam no catálogo (logits processor) |
| Latência do VodChat em CPU | Quantização GGUF Q4_K_M + llama.cpp; ou marcar explicações como opcionais e fazer streaming |
| Modelo decora dataset sintético e não generaliza | Misturar dados reais assim que estiverem disponíveis; validar com split temporal e holdout de usuários |
| Tamanho do checkpoint dificulta deploy | LoRA adapters são ~10MB; VodRec é ~30MB. Couber em qualquer servidor |

---

## 10. Cronograma sugerido

| Semana | Atividade | Entrega |
|---|---|---|
| 1 | Geração de dados sintéticos / dump do MySQL real | `sequences.parquet`, `vocab.json` |
| 2 | Notebook 06 — treino VodRec do zero | `models/vodrec/model.pt` |
| 3 | Avaliação VodRec, tuning de hiperparâmetros | Métricas batendo RFIA01 |
| 4 | Notebook 07 — fine-tune VodChat | `adapter_model.safetensors` |
| 5 | Implementação dos módulos `vodrec_transformer.py`, `vodchat.py`, orchestrator | Código produção |
| 6 | Endpoints FastAPI + integração com backend Node.js | API funcional |
| 7 | Quantização e benchmark de latência | RFIA02 batendo |
| 8 | Documentação, testes, deploy | Produção |

---

## 11. Glossário rápido

- **LLM**: Large Language Model. Aqui usado em sentido amplo: qualquer modelo neural autoregressivo treinado para modelar distribuições de sequências. O VodRec é tecnicamente um LM sobre vocabulário de items; o VodChat é um LM sobre vocabulário de tokens textuais.
- **LoRA**: Low-Rank Adaptation. Fine-tuning eficiente que adapta apenas matrizes de baixa-rank.
- **QLoRA**: LoRA + quantização 4-bit do modelo base. Treino cabe em GPU pequena.
- **SFT**: Supervised Fine-Tuning. Treino do LLM com pares (prompt, resposta esperada).
- **PEFT**: Parameter Efficient Fine-Tuning. Família de técnicas, LoRA é uma delas.
- **GGUF**: formato binário usado por llama.cpp para inferência otimizada em CPU.
- **HR@k, NDCG@k**: métricas de ranking. Ver `app/utils/metrics.py`.
