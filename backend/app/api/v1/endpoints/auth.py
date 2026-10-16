"""
Authentication endpoints: register, login, refresh, logout, profile, API key.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
    verify_token,
)
from app.core.security import oauth2_scheme
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


async def _get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def _get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def _get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the JWT bearer token to an active User ORM instance."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token_data = verify_token(token, expected_type="access")
    except AuthenticationError:
        raise credentials_exception

    result = await db.execute(
        select(User).where(User.id == uuid.UUID(token_data.sub))
    )
    user: User | None = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )
    return user


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> User:
    # Check uniqueness
    if await _get_user_by_email(db, payload.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )
    if await _get_user_by_username(db, payload.username):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This username is already taken.",
        )

    user = User(
        email=payload.email,
        username=payload.username,
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name,
        is_active=True,
        is_superuser=False,
        api_key=secrets.token_urlsafe(48),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and obtain JWT access + refresh tokens",
)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    user = await _get_user_by_email(db, payload.email)

    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated.",
        )

    # Update last login
    user.last_login_at = _utc_now()
    await db.commit()

    token_payload = {"sub": str(user.id), "email": user.email}
    access_token = create_access_token(token_payload)
    refresh_token = create_refresh_token(token_payload)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Exchange a refresh token for a new token pair",
)
async def refresh_tokens(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    try:
        token_data = verify_token(payload.refresh_token, expected_type="refresh")
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    result = await db.execute(
        select(User).where(User.id == uuid.UUID(token_data.sub))
    )
    user: User | None = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_payload = {"sub": str(user.id), "email": user.email}
    access_token = create_access_token(token_payload)
    refresh_token = create_refresh_token(token_payload)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout (client-side token invalidation)",
)
async def logout(
    current_user: User = Depends(_get_current_user),
) -> None:
    """
    Stateless logout — no server-side token store is maintained.
    The client is responsible for discarding its tokens.  A 204 response
    signals that the logout was acknowledged.
    """
    return None


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the current authenticated user",
)
async def get_me(
    current_user: User = Depends(_get_current_user),
) -> User:
    return current_user


# ---------------------------------------------------------------------------
# PUT /auth/me
# ---------------------------------------------------------------------------


@router.put(
    "/me",
    response_model=UserResponse,
    summary="Update the current user's profile",
)
async def update_me(
    payload: UserUpdate,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(current_user, field, value)

    await db.commit()
    await db.refresh(current_user)
    return current_user


# ---------------------------------------------------------------------------
# POST /auth/change-password
# ---------------------------------------------------------------------------


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change the current user's password",
)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    current_user.hashed_password = get_password_hash(payload.new_password)
    await db.commit()
    return None


# ---------------------------------------------------------------------------
# GET /auth/api-key
# ---------------------------------------------------------------------------


@router.get(
    "/api-key",
    summary="Regenerate and return a new API key for the current user",
)
async def get_api_key(
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Generates a fresh API key, persists it, and returns it once.
    The previous key is immediately invalidated.
    """
    new_key = secrets.token_urlsafe(48)
    current_user.api_key = new_key
    await db.commit()
    return {"api_key": new_key}
