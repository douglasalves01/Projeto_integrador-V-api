"""Tests for metrics, structured logging context, and error handlers."""

from __future__ import annotations

from fastapi import Request
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import get_current_user
from app.main import app

settings = get_settings()


class TestMetrics:
    def test_metrics_endpoint_returns_prometheus_text(self, test_client: TestClient) -> None:
        response = test_client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")
        body = response.text
        assert "vod_ai_http_requests_total" in body
        assert "vod_ai_model_loaded" in body


class TestRequestContext:
    def test_response_includes_request_id_header(self, test_client: TestClient) -> None:
        response = test_client.get("/health")
        assert response.status_code == 200
        assert response.headers.get("X-Request-ID")

    def test_custom_request_id_is_echoed(self, test_client: TestClient) -> None:
        custom_id = "test-req-abc-123"
        response = test_client.get("/health", headers={"X-Request-ID": custom_id})
        assert response.headers.get("X-Request-ID") == custom_id


class TestErrorHandlers:
    def test_user_not_found_returns_404(
        self,
        test_client: TestClient,
    ) -> None:
        async def _user_42(request: Request) -> dict:
            request.state.user_id = 42
            if isinstance(request.scope.get("state"), dict):
                request.scope["state"]["user_id"] = 42
            return {"sub": "42", "_user_id": 42, "user_id": 42}

        app.dependency_overrides[get_current_user] = _user_42
        try:
            response = test_client.get(
                f"{settings.API_PREFIX}/recommendations/42?k=5",
                headers={"Authorization": "Bearer unused"},
            )
            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_internal_error_hides_details_when_not_debug(self, monkeypatch) -> None:
        """Handler must not leak exception message when DEBUG is false."""
        from app.core.error_handlers import register_exception_handlers
        from fastapi import FastAPI

        monkeypatch.setattr("app.core.error_handlers.settings.DEBUG", False)

        probe = FastAPI()

        @probe.get("/probe")
        async def _probe() -> None:
            raise RuntimeError("secret internal detail")

        register_exception_handlers(probe)
        client = TestClient(probe, raise_server_exceptions=False)
        response = client.get("/probe")
        assert response.status_code == 500
        assert response.json()["detail"] == "Internal server error"
