"""VodChat: wrapper de inferencia para o LLM textual fine-tunado com LoRA.

Carrega o modelo base (TinyLlama/Phi-3/...) + adapter LoRA treinado no
notebook 07_vodchat_lora_finetune.ipynb e fornece dois metodos principais:

- `explain(history_titles, recommended_title)` -> str
  Gera explicacao textual de uma recomendacao.

- `chat(history_titles, user_message)` -> str
  Resposta conversacional ao usuario.

Suporta duas backends:
1. transformers + peft (GPU recomendada, ou CPU com paciencia)
2. llama-cpp-python carregando um .gguf quantizado (CPU rapido)

O backend e escolhido pelo parametro `backend` ou pela presenca dos arquivos.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Literal, Sequence

from loguru import logger

DEFAULT_SYSTEM_PROMPT = (
    "Voce e o VodChat, assistente da plataforma de streaming VOD. "
    "Responda sempre em portugues do Brasil, de forma clara e amigavel. "
    "Quando o usuario pedir sugestoes, cite titulos reais do catalogo que voce conhece "
    "(entre aspas), em lista numerada se forem varios. "
    "Nao invente filmes que nao existem no catalogo. "
    "Nao responda em ingles nem faca meta-comentarios sobre o modelo ou o treinamento."
)


class VodChat:
    """Cliente de inferencia para o LLM VodChat (LoRA fine-tuned)."""

    def __init__(
        self,
        adapter_path: str | Path | None = None,
        base_model_id: str = "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        gguf_path: str | Path | None = None,
        backend: Literal["transformers", "llamacpp", "auto"] = "auto",
        max_new_tokens: int = 160,
        max_time_seconds: float | None = 20.0,
        temperature: float = 0.7,
        device: str | None = None,
        known_titles: list[str] | None = None,
        use_title_constraints: bool = True,
    ) -> None:
        self.adapter_path = Path(adapter_path) if adapter_path else None
        self.base_model_id = base_model_id
        self.gguf_path = Path(gguf_path) if gguf_path else None
        self.max_new_tokens = max_new_tokens
        self.max_time_seconds = max_time_seconds
        self.temperature = temperature
        self.device = device
        self.known_titles = known_titles or []
        self.use_title_constraints = use_title_constraints

        if backend == "auto":
            if self.gguf_path and self.gguf_path.exists():
                backend = "llamacpp"
            else:
                backend = "transformers"
        self.backend = backend

        self._tokenizer = None
        self._model = None
        self._llama = None
        self._loaded = False
        self._logits_processors = None  # construido apos carregar tokenizer

    def update_known_titles(self, titles: list[str]) -> None:
        """Atualiza o conjunto de titulos validos (catalogo) para constrained decoding."""
        self.known_titles = list(titles)
        self._logits_processors = None  # forca reconstrucao

    # ------------------------------------------------------------------
    # Lazy loading
    # ------------------------------------------------------------------

    def load(self) -> None:
        if self._loaded:
            return
        if self.backend == "transformers":
            self._load_transformers()
        elif self.backend == "llamacpp":
            self._load_llamacpp()
        else:
            raise ValueError(f"Backend desconhecido: {self.backend}")
        self._loaded = True

    def _load_transformers(self) -> None:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        device = self.device or ("cuda" if torch.cuda.is_available() else "cpu")
        dtype = torch.bfloat16 if device == "cuda" else torch.float16

        tokenizer = AutoTokenizer.from_pretrained(self.base_model_id)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        base = AutoModelForCausalLM.from_pretrained(
            self.base_model_id,
            torch_dtype=dtype,
            device_map=device if device == "cuda" else None,
        )

        if self.adapter_path and self.adapter_path.exists():
            model = PeftModel.from_pretrained(base, str(self.adapter_path))
        else:
            model = base
        if device == "cpu":
            model = model.to(device)
        model.eval()

        self._tokenizer = tokenizer
        self._model = model
        self._device = device

    def _load_llamacpp(self) -> None:
        try:
            from llama_cpp import Llama
        except ImportError as e:
            raise RuntimeError(
                "llama-cpp-python nao instalado. "
                "`pip install llama-cpp-python`"
            ) from e
        if not self.gguf_path or not self.gguf_path.exists():
            raise FileNotFoundError(f"GGUF nao encontrado: {self.gguf_path}")
        n_threads = max(1, (os.cpu_count() or 4) - 1)
        self._llama = Llama(
            model_path=str(self.gguf_path),
            n_ctx=2048,
            n_threads=n_threads,
            verbose=False,
        )

    # ------------------------------------------------------------------
    # High-level API
    # ------------------------------------------------------------------

    def explain(
        self,
        history_titles: Sequence[str],
        recommended_title: str,
        recommended_genres: Sequence[str] | None = None,
    ) -> str:
        """Gera explicacao textual de uma recomendacao."""
        self.load()
        history_str = ", ".join(f'"{t}"' for t in history_titles) or "(historico vazio)"
        genres_str = (
            f" ({', '.join(recommended_genres)})" if recommended_genres else ""
        )
        prompt = (
            f"O usuario assistiu recentemente: {history_str}. "
            f"Explique de forma natural por que recomendariamos "
            f'"{recommended_title}"{genres_str} para ele.'
        )
        return self._generate(prompt)

    def chat(
        self,
        user_message: str,
        history_titles: Sequence[str] | None = None,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> str:
        """Resposta conversacional. Historico vai no system prompt (nao na mensagem do usuario)."""
        self.load()
        effective_system = system_prompt
        if history_titles:
            titles_line = "; ".join(history_titles)
            effective_system += (
                f"\n\nContexto: o usuario ja assistiu recentemente a: {titles_line}. "
                "Use isso apenas para personalizar a resposta a pergunta atual."
            )
        return self._generate(user_message.strip(), system_prompt=effective_system)

    def summarize(
        self,
        title: str,
        description: str | None,
        max_chars: int = 1500,
    ) -> str:
        """Gera um resumo curto (2-3 frases) a partir do titulo + descricao.

        Reaproveita o mesmo LLM do chat. Pensado para rodar OFFLINE (batch),
        ja que TinyLlama em CPU e lento. A descricao e truncada para caber no
        contexto do modelo.
        """
        self.load()
        source = (description or "").strip()
        if not source:
            return ""
        source = source[:max_chars]
        system_prompt = (
            "Voce resume videos de uma plataforma de streaming educativa, em "
            "portugues do Brasil. Escreva um resumo objetivo de 2 a 3 frases sobre "
            "o conteudo do video. Nao use hashtags, links, emojis, marcas de tempo "
            "(timestamps) nem listas. Responda apenas com o resumo."
        )
        prompt = (
            f"Titulo: {title}\n\n"
            f"Descricao original:\n{source}\n\n"
            "Resumo:"
        )
        return self._generate(prompt, system_prompt=system_prompt)

    # ------------------------------------------------------------------
    # Backend-specific generation
    # ------------------------------------------------------------------

    def _generate(self, user_message: str, system_prompt: str = DEFAULT_SYSTEM_PROMPT) -> str:
        if self.backend == "transformers":
            return self._gen_transformers(user_message, system_prompt)
        return self._gen_llamacpp(user_message, system_prompt)

    def _build_logits_processors(self):
        """Constroi a LogitsProcessorList se constrained decoding estiver ativo."""
        if not self.use_title_constraints or not self.known_titles:
            return None
        try:
            from transformers import LogitsProcessorList
            from app.models.vodchat_constraints import TitleAnchoredLogitsProcessor
        except ImportError:
            return None
        return LogitsProcessorList([
            TitleAnchoredLogitsProcessor(self._tokenizer, self.known_titles, penalty=2.0)
        ])

    def _gen_transformers(self, user_message: str, system_prompt: str) -> str:
        import torch

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        prompt = self._tokenizer.apply_chat_template(  # type: ignore[union-attr]
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self._tokenizer(prompt, return_tensors="pt").to(  # type: ignore[union-attr]
            self._model.device  # type: ignore[union-attr]
        )
        if self._logits_processors is None:
            self._logits_processors = self._build_logits_processors()

        started = time.perf_counter()
        logger.info(
            "VodChat generation started",
            backend=self.backend,
            device=str(self._model.device),  # type: ignore[union-attr]
            prompt_chars=len(prompt),
            max_new_tokens=self.max_new_tokens,
            max_time_seconds=self.max_time_seconds,
        )
        with torch.no_grad():
            gen_kwargs = dict(
                max_new_tokens=self.max_new_tokens,
                temperature=self.temperature,
                do_sample=True,
                top_p=0.9,
                repetition_penalty=1.1,
                pad_token_id=self._tokenizer.eos_token_id,  # type: ignore[union-attr]
            )
            if self.max_time_seconds and self.max_time_seconds > 0:
                gen_kwargs["max_time"] = self.max_time_seconds
            if self._logits_processors is not None:
                gen_kwargs["logits_processor"] = self._logits_processors
            out = self._model.generate(**inputs, **gen_kwargs)  # type: ignore[union-attr]

        completion = self._tokenizer.decode(  # type: ignore[union-attr]
            out[0, inputs.input_ids.shape[1]:], skip_special_tokens=True
        )
        # Post-hoc filter: titulos entre aspas que nao existem viram texto neutro.
        if self.use_title_constraints and self.known_titles:
            from app.models.vodchat_constraints import filter_unknown_titles
            completion = filter_unknown_titles(completion, set(self.known_titles))
        logger.info(
            "VodChat generation completed",
            backend=self.backend,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            completion_chars=len(completion),
        )
        return completion.strip()

    def _gen_llamacpp(self, user_message: str, system_prompt: str) -> str:
        started = time.perf_counter()
        logger.info(
            "VodChat generation started",
            backend=self.backend,
            max_new_tokens=self.max_new_tokens,
            max_time_seconds=None,
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        resp = self._llama.create_chat_completion(  # type: ignore[union-attr]
            messages=messages,
            max_tokens=self.max_new_tokens,
            temperature=self.temperature,
            top_p=0.9,
            repeat_penalty=1.1,
        )
        completion = resp["choices"][0]["message"]["content"].strip()
        if self.use_title_constraints and self.known_titles:
            from app.models.vodchat_constraints import filter_unknown_titles

            completion = filter_unknown_titles(completion, set(self.known_titles))
        logger.info(
            "VodChat generation completed",
            backend=self.backend,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            completion_chars=len(completion),
        )
        return completion
