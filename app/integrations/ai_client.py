"""Lightweight HTTP client for the external AI recommendation service."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)

_API_PREFIX = "/api/v1"


def normalize_ai_base_url(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith(_API_PREFIX):
        return root
    return f"{root}{_API_PREFIX}"


class _CircuitBreaker:
    def __init__(self, fail_threshold: int = 5, reset_after_sec: float = 30.0) -> None:
        self.fail_threshold = fail_threshold
        self.reset_after_sec = reset_after_sec
        self._fails = 0
        self._opened_at: Optional[float] = None

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at > self.reset_after_sec:
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
    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout_sec: float = 2.5,
    ) -> None:
        self.base_url = normalize_ai_base_url(base_url)
        self.api_key = api_key
        self.timeout = httpx.Timeout(timeout_sec, connect=1.0)
        self._breaker = _CircuitBreaker()

    @property
    def available(self) -> bool:
        return not self._breaker.is_open

    def _headers(self, jwt: Optional[str] = None) -> Dict[str, str]:
        headers: Dict[str, str] = {"Accept": "application/json"}
        if jwt:
            headers["Authorization"] = f"Bearer {jwt}"
        if self.api_key:
            headers["X-AI-API-Key"] = self.api_key
        return headers

    async def get_recommendations(
        self,
        user_id: UUID,
        jwt: str,
        k: int = 10,
    ) -> Optional[Dict[str, Any]]:
        if self._breaker.is_open:
            return None

        url = f"{self.base_url}/llm/recommendations/{user_id}"
        params = {"k": k, "with_explanation": "false"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params, headers=self._headers(jwt))
            response.raise_for_status()
            self._breaker.record_success()
            return response.json()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            self._breaker.record_failure()
            logger.warning("AI request failed: %s", exc)
            return None


_ai_client: Optional[AIClient] = None


def init_ai_client(base_url: str, api_key: Optional[str] = None) -> AIClient:
    global _ai_client
    _ai_client = AIClient(base_url=base_url, api_key=api_key)
    return _ai_client


def get_ai_client() -> Optional[AIClient]:
    return _ai_client
