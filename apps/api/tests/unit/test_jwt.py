"""Unit tests for JWT token creation and validation."""
import uuid
from datetime import datetime, timedelta

import pytest
from jose import jwt

from app.auth.jwt import create_access_token, create_refresh_token, decode_token
from app.core.config import settings


class TestAccessToken:
    def test_create_access_token_contains_claims(self):
        user_id = str(uuid.uuid4())
        role = "USER"
        token = create_access_token(user_id, role)

        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == user_id
        assert payload["role"] == role
        assert payload["type"] == "access"
        assert "exp" in payload

    def test_access_token_for_admin(self):
        user_id = str(uuid.uuid4())
        token = create_access_token(user_id, "ADMIN")

        payload = decode_token(token)
        assert payload["role"] == "ADMIN"

    def test_access_token_expires_in_30_minutes(self):
        user_id = str(uuid.uuid4())
        token = create_access_token(user_id, "USER")

        payload = decode_token(token)
        exp = datetime.utcfromtimestamp(payload["exp"])
        now = datetime.utcnow()
        # Should expire roughly 30 minutes from now
        diff = (exp - now).total_seconds()
        assert 1700 < diff < 1900  # ~30 minutes with some tolerance


class TestRefreshToken:
    def test_create_refresh_token_contains_claims(self):
        user_id = str(uuid.uuid4())
        token = create_refresh_token(user_id)

        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == user_id
        assert payload["type"] == "refresh"
        assert "exp" in payload

    def test_refresh_token_expires_in_7_days(self):
        user_id = str(uuid.uuid4())
        token = create_refresh_token(user_id)

        payload = decode_token(token)
        exp = datetime.utcfromtimestamp(payload["exp"])
        now = datetime.utcnow()
        diff = (exp - now).total_seconds()
        # Should expire roughly 7 days from now
        expected = 7 * 24 * 3600
        assert (expected - 60) < diff < (expected + 60)

    def test_refresh_token_has_no_role(self):
        user_id = str(uuid.uuid4())
        token = create_refresh_token(user_id)

        payload = decode_token(token)
        assert "role" not in payload


class TestDecodeToken:
    def test_decode_valid_token(self):
        user_id = str(uuid.uuid4())
        token = create_access_token(user_id, "USER")
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == user_id

    def test_decode_invalid_token(self):
        payload = decode_token("invalid.token.here")
        assert payload is None

    def test_decode_expired_token(self):
        expired_payload = {
            "sub": str(uuid.uuid4()),
            "role": "USER",
            "exp": datetime.utcnow() - timedelta(hours=1),
            "type": "access",
        }
        token = jwt.encode(expired_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        payload = decode_token(token)
        assert payload is None

    def test_decode_token_wrong_secret(self):
        payload_data = {
            "sub": str(uuid.uuid4()),
            "role": "USER",
            "exp": datetime.utcnow() + timedelta(hours=1),
            "type": "access",
        }
        token = jwt.encode(payload_data, "wrong-secret-key", algorithm=settings.ALGORITHM)
        payload = decode_token(token)
        assert payload is None

    def test_decode_empty_string(self):
        payload = decode_token("")
        assert payload is None

    def test_decode_malformed_jwt(self):
        payload = decode_token("not.a.valid.jwt.token.at.all")
        assert payload is None
