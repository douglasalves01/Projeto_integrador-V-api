import hashlib
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.hashing import verify_password
from app.auth.jwt import create_access_token, create_refresh_token, decode_token
from app.core.constants import REFRESH_TOKEN_EXPIRE_DAYS
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenResponse


class AuthService:
    def __init__(self):
        self.user_repo = UserRepository()

    async def authenticate(self, db: AsyncSession, email: str, password: str) -> TokenResponse:
        user = await self.user_repo.get_by_email(db, email)

        if not user or not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        access_token = create_access_token(str(user.id), user.role.value)
        refresh_token = create_refresh_token(str(user.id))

        # Store refresh token hash
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        expires_at = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

        db_token = RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            revoked=False,
            expires_at=expires_at,
        )
        db.add(db_token)
        await db.flush()

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        )

    async def refresh_tokens(self, db: AsyncSession, refresh_token: str) -> TokenResponse:
        payload = decode_token(refresh_token)

        if not payload or payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

        # Find the token hash in DB
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        result = await db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked == False,
            )
        )
        db_token = result.scalar_one_or_none()

        if not db_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or revoked refresh token",
            )

        if db_token.expires_at < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token expired",
            )

        # Revoke old token (single-use rotation)
        db_token.revoked = True
        await db.flush()

        # Get user for role
        user = await self.user_repo.get_by_id(db, UUID(user_id))
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )

        # Issue new tokens
        new_access_token = create_access_token(str(user.id), user.role.value)
        new_refresh_token = create_refresh_token(str(user.id))

        # Store new refresh token
        new_token_hash = hashlib.sha256(new_refresh_token.encode()).hexdigest()
        new_expires_at = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

        new_db_token = RefreshToken(
            user_id=user.id,
            token_hash=new_token_hash,
            revoked=False,
            expires_at=new_expires_at,
        )
        db.add(new_db_token)
        await db.flush()

        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
        )
