"""Unit tests for AI client URL normalization and breaker behavior."""

from app.integrations.ai_client import AIClient, normalize_ai_base_url


def test_normalize_ai_base_url_adds_prefix_when_missing():
    assert normalize_ai_base_url("http://localhost:8002") == "http://localhost:8002/api/v1"


def test_normalize_ai_base_url_keeps_existing_prefix():
    assert normalize_ai_base_url("http://ai:8000/api/v1") == "http://ai:8000/api/v1"


def test_normalize_ai_base_url_handles_trailing_slash():
    assert normalize_ai_base_url("http://ai:8000/") == "http://ai:8000/api/v1"


def test_ai_client_circuit_opens_after_fail_threshold():
    client = AIClient("http://localhost:8002")

    for _ in range(5):
        client._breaker.record_failure()

    assert client.available is False
