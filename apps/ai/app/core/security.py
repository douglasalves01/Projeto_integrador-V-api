"""JWT validation and FastAPI auth dependencies."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()
bearer_scheme = HTTPBearer(auto_error=True)


def verify_jwt(token: str) -> dict[str, Any]:
    """Validate a JWT issued by the platform backend (external repository)."""
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def extract_user_id(payload: dict[str, Any]) -> str:
    for key in ("sub", "user_id", "userId", "id"):
        value = payload.get(key)
        if value is not None:
            return str(value)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token missing user identifier",
    )


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict[str, Any]:
    """FastAPI dependency that returns the authenticated JWT payload."""
    payload = verify_jwt(credentials.credentials)
    user_id = extract_user_id(payload)
    payload["_user_id"] = user_id
    request.state.user_id = user_id
    if isinstance(request.scope.get("state"), dict):
        request.scope["state"]["user_id"] = user_id
    return payload


def ensure_user_access(current_user: dict[str, Any], user_id: int | UUID | str) -> None:
    if str(current_user["_user_id"]) != str(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to access this user's resources",
        )
