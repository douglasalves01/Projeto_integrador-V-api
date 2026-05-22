"""Cliente HTTP para o servico de IA do monorepo (apps/ai).

Caracteristicas:
- Timeout curto (RFIA02 exige <2s; aqui 2.5s com margem)
- Circuit breaker simples (abre apos 5 falhas, half-open apos 30s)
- Falha em silencio (caller decide fallback)
"""
from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)

_API_PREFIX = "/api/v1"


def normalize_ai_base_url(base_url: str) -> str:
    """Ensure base URL includes the FastAPI API_PREFIX (/api/v1)."""
    root = base_url.rstrip("/")
    if root.endswith(_API_PREFIX):
        return root
    return f"{root}{_API_PREFIX}"


class _CircuitBreaker:
    """Circuit breaker basico: open / half_open / closed."""
    def __init__(self, fail_threshold: int = 5, reset_after_sec: float = 30.0) -> None:
        self.fail_threshold = fail_threshold
        self.reset_after_sec = reset_after_sec
        self._fails = 0
        self._opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at > self.reset_after_sec:
            # half-open: zera para tentar de novo
            self._opened_at = None
            self._fails = 0
            return False
        return True

    def record_success(self) -> None:
        self._fails = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._fails += 1
        if self._fails >= self.fail_threshold and self._opened_at is None:
            self._opened_at = time.monotonic()
            logger.warning("AI circuit breaker OPEN (fails=%d)", self._fails)


class AIClient:
    """Cliente HTTP assincrono para o servico de IA."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout_sec: float = 2.5,
    ) -> None:
        self.base_url = normalize_ai_base_url(base_url)
        self.api_key = api_key
        self.timeout = httpx.Timeout(timeout_sec, connect=1.0)
        self._breaker = _CircuitBreaker()

    def _headers(self, jwt: str | None = None) -> dict[str, str]:
        h: dict[str, str] = {"Accept": "application/json"}
        if jwt:
            h["Authorization"] = f"Bearer {jwt}"
        if self.api_key:
            h["X-AI-API-Key"] = self.api_key
        return h

    @property
    def available(self) -> bool:
        return not self._breaker.is_open

    async def get_recommendations(
        self,
        user_id: UUID,
        jwt: str,
        k: int = 20,
        with_explanation: bool = False,
    ) -> dict[str, Any] | None:
        """Retorna o payload de recomendacoes ou None em caso de falha."""
        if self._breaker.is_open:
            logger.debug("AI circuit OPEN, skipping call")
            return None
        url = f"{self.base_url}/llm/recommendations/{user_id}"
        params = {"k": k, "with_explanation": str(with_explanation).lower()}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params, headers=self._headers(jwt))
            resp.raise_for_status()
            self._breaker.record_success()
            return resp.json()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            self._breaker.record_failure()
            logger.warning("AI request failed: %s", exc)
            return None

    async def chat(self, user_id: UUID, jwt: str, message: str) -> str | None:
        if self._breaker.is_open:
            return None
        url = f"{self.base_url}/llm/chat/{user_id}"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=1.0)) as client:
                resp = await client.post(
                    url, json={"message": message}, headers=self._headers(jwt)
                )
            resp.raise_for_status()
            self._breaker.record_success()
            return resp.json().get("reply")
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            self._breaker.record_failure()
            logger.warning("AI chat failed: %s", exc)
            return None

    async def info(self) -> dict[str, Any] | None:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(2.0)) as client:
                resp = await client.get(f"{self.base_url}/llm/info")
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, httpx.TimeoutException):
            return None


# Singleton — instanciado no main.py
_ai_client: AIClient | None = None


def init_ai_client(base_url: str, api_key: str | None = None) -> AIClient:
    global _ai_client
    _ai_client = AIClient(base_url=base_url, api_key=api_key)
    return _ai_client


def get_ai_client() -> AIClient | None:
    return _ai_client
