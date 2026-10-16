"""
Tests for authentication endpoints:
  POST /api/v1/auth/register
  POST /api/v1/auth/login
  GET  /api/v1/auth/me
  POST /api/v1/auth/refresh
  POST /api/v1/auth/logout
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_refresh_token, get_password_hash
from app.models.user import User

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REGISTER_URL = "/api/v1/auth/register"
_LOGIN_URL = "/api/v1/auth/login"
_ME_URL = "/api/v1/auth/me"
_REFRESH_URL = "/api/v1/auth/refresh"
_LOGOUT_URL = "/api/v1/auth/logout"

_VALID_PAYLOAD = {
    "email": "newuser@example.com",
    "username": "newuser",
    "password": "SecurePass99!",
    "full_name": "New User",
}


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------


async def test_register_success(test_client: AsyncClient) -> None:
    """A new user can register and the response contains the user data."""
    response = await test_client.post(_REGISTER_URL, json=_VALID_PAYLOAD)

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["email"] == _VALID_PAYLOAD["email"]
    assert data["username"] == _VALID_PAYLOAD["username"]
    assert data["full_name"] == _VALID_PAYLOAD["full_name"]
    assert "id" in data
    assert "hashed_password" not in data


async def test_register_duplicate_email(
    test_client: AsyncClient, async_session: AsyncSession
) -> None:
    """Registering with an already-used email returns 409 Conflict."""
    # Pre-create a user with the same email
    user = User(
        email=_VALID_PAYLOAD["email"],
        username="existing_user",
        hashed_password=get_password_hash("SomePass1!"),
        is_active=True,
    )
    async_session.add(user)
    await async_session.commit()

    response = await test_client.post(_REGISTER_URL, json=_VALID_PAYLOAD)
    assert response.status_code == 409
    assert "email" in response.text.lower() or "already" in response.text.lower()


async def test_register_duplicate_username(
    test_client: AsyncClient, async_session: AsyncSession
) -> None:
    """Registering with an already-taken username returns 409 Conflict."""
    user = User(
        email="other@example.com",
        username=_VALID_PAYLOAD["username"],
        hashed_password=get_password_hash("SomePass1!"),
        is_active=True,
    )
    async_session.add(user)
    await async_session.commit()

    response = await test_client.post(_REGISTER_URL, json=_VALID_PAYLOAD)
    assert response.status_code == 409


async def test_register_short_password(test_client: AsyncClient) -> None:
    """A password shorter than 8 characters is rejected with 422."""
    payload = {**_VALID_PAYLOAD, "password": "abc"}
    response = await test_client.post(_REGISTER_URL, json=payload)
    assert response.status_code == 422


async def test_register_invalid_email(test_client: AsyncClient) -> None:
    """An invalid email is rejected with 422."""
    payload = {**_VALID_PAYLOAD, "email": "not-an-email"}
    response = await test_client.post(_REGISTER_URL, json=payload)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


async def test_login_success(
    test_client: AsyncClient, sample_user: User
) -> None:
    """Valid credentials return access and refresh tokens."""
    response = await test_client.post(
        _LOGIN_URL,
        json={"email": sample_user.email, "password": "Password123!"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert isinstance(data["expires_in"], int)
    assert data["expires_in"] > 0


async def test_login_wrong_password(
    test_client: AsyncClient, sample_user: User
) -> None:
    """Wrong password returns 401."""
    response = await test_client.post(
        _LOGIN_URL,
        json={"email": sample_user.email, "password": "WrongPass!"},
    )
    assert response.status_code == 401


async def test_login_unknown_email(test_client: AsyncClient) -> None:
    """Logging in with an unknown email returns 401."""
    response = await test_client.post(
        _LOGIN_URL,
        json={"email": "nobody@nowhere.com", "password": "Password123!"},
    )
    assert response.status_code == 401


async def test_login_inactive_user(
    test_client: AsyncClient,
    sample_user: User,
    async_session: AsyncSession,
) -> None:
    """A deactivated account returns 403 on login."""
    sample_user.is_active = False
    async_session.add(sample_user)
    await async_session.commit()

    response = await test_client.post(
        _LOGIN_URL,
        json={"email": sample_user.email, "password": "Password123!"},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Get /me
# ---------------------------------------------------------------------------


async def test_get_me_authenticated(authenticated_client: AsyncClient, sample_user: User) -> None:
    """An authenticated user can fetch their own profile."""
    response = await authenticated_client.get(_ME_URL)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["email"] == sample_user.email
    assert data["username"] == sample_user.username


async def test_get_me_unauthenticated(test_client: AsyncClient) -> None:
    """Accessing /me without a token returns 401."""
    response = await test_client.get(_ME_URL)
    assert response.status_code == 401


async def test_get_me_invalid_token(test_client: AsyncClient) -> None:
    """A malformed token returns 401."""
    test_client.headers.update({"Authorization": "Bearer not.a.valid.jwt"})
    response = await test_client.get(_ME_URL)
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Refresh token
# ---------------------------------------------------------------------------


async def test_refresh_token(
    test_client: AsyncClient, sample_user: User
) -> None:
    """A valid refresh token returns a new access + refresh token pair."""
    refresh_token = create_refresh_token(
        {"sub": str(sample_user.id), "email": sample_user.email}
    )
    response = await test_client.post(
        _REFRESH_URL, json={"refresh_token": refresh_token}
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


async def test_refresh_token_invalid(test_client: AsyncClient) -> None:
    """A bogus refresh token returns 401."""
    response = await test_client.post(
        _REFRESH_URL, json={"refresh_token": "bogus.token.here"}
    )
    assert response.status_code == 401


async def test_refresh_token_using_access_token(
    test_client: AsyncClient, sample_user: User
) -> None:
    """Passing an access token where a refresh token is expected returns 401."""
    from app.core.security import create_access_token

    access_token = create_access_token(
        {"sub": str(sample_user.id), "email": sample_user.email}
    )
    response = await test_client.post(
        _REFRESH_URL, json={"refresh_token": access_token}
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


async def test_logout(authenticated_client: AsyncClient) -> None:
    """Authenticated logout returns 204 No Content."""
    response = await authenticated_client.post(_LOGOUT_URL)
    assert response.status_code == 204


async def test_logout_unauthenticated(test_client: AsyncClient) -> None:
    """Logout without a token returns 401."""
    response = await test_client.post(_LOGOUT_URL)
    assert response.status_code == 401
