"""
JWT-based authentication utilities and FastAPI dependency helpers.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
import bcrypt as _bcrypt
from pydantic import BaseModel

from app.core.config import settings
from app.core.exceptions import AuthenticationError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def get_password_hash(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


# ---------------------------------------------------------------------------
# Token models
# ---------------------------------------------------------------------------


class TokenData(BaseModel):
    """Payload extracted from a validated JWT."""

    sub: str  # user id (str representation of UUID / int PK)
    email: Optional[str] = None
    scopes: list[str] = []
    token_type: str = "access"


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Encode *data* into a signed JWT access token.

    Parameters
    ----------
    data:
        Arbitrary claims to embed.  A ``sub`` key is expected.
    expires_delta:
        Custom expiry; defaults to ``JWT_ACCESS_TOKEN_EXPIRE_MINUTES``.
    """
    to_encode = data.copy()
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = _utc_now() + expires_delta
    to_encode.update(
        {
            "exp": expire,
            "iat": _utc_now(),
            "type": "access",
        }
    )
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """
    Encode *data* into a signed JWT refresh token.

    The refresh token has a longer expiry and carries ``type=refresh`` so it
    cannot be used as an access token.
    """
    to_encode = data.copy()
    expire = _utc_now() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update(
        {
            "exp": expire,
            "iat": _utc_now(),
            "type": "refresh",
        }
    )
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


# ---------------------------------------------------------------------------
# Token verification
# ---------------------------------------------------------------------------


def verify_token(token: str, expected_type: str = "access") -> TokenData:
    """
    Decode and validate *token*.

    Raises
    ------
    AuthenticationError
        When the token is expired, malformed, or has the wrong type.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise AuthenticationError(f"Token validation failed: {exc}") from exc

    token_type: str = payload.get("type", "access")
    if token_type != expected_type:
        raise AuthenticationError(
            f"Invalid token type: expected '{expected_type}', got '{token_type}'"
        )

    sub: Optional[str] = payload.get("sub")
    if sub is None:
        raise AuthenticationError("Token is missing 'sub' claim")

    return TokenData(
        sub=sub,
        email=payload.get("email"),
        scopes=payload.get("scopes", []),
        token_type=token_type,
    )


# ---------------------------------------------------------------------------
# OAuth2 scheme
# ---------------------------------------------------------------------------

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# An optional variant that does not raise when the token is absent.
oauth2_scheme_optional = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login", auto_error=False
)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: "AsyncSession" = None,  # injected by callers that have a DB session dep
):
    """
    FastAPI dependency that resolves the JWT token to the current user.

    Usage::

        @router.get("/me")
        async def me(user=Depends(get_current_user)):
            ...

    This function intentionally avoids importing the ORM ``User`` model at
    module level to prevent circular imports.  Import it inside the body so
    each service can wire its own DB session dependency on top of this one.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        token_data = verify_token(token, expected_type="access")
    except AuthenticationError:
        raise credentials_exception

    if db is None:
        # When no DB session is passed we return only the token payload.
        # Callers that need the full ORM object must inject their own DB dep.
        return token_data

    # Lazy import to avoid circular dependency with models package.
    try:
        from app.models.user import User  # noqa: PLC0415
        from sqlalchemy import select  # noqa: PLC0415

        result = await db.execute(select(User).where(User.id == token_data.sub))
        user = result.scalar_one_or_none()
    except Exception as exc:  # pragma: no cover
        raise credentials_exception from exc

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )

    return user


async def get_current_active_user(
    current_user=Depends(get_current_user),
):
    """Alias dependency that explicitly names the 'active user' requirement."""
    return current_user
