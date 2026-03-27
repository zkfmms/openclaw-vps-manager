"""Authentication middleware for VPS Manager."""
import os
from typing import Optional
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status, Request, Security
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import User, get_db
from config import get_settings
from auth.rbac import check_permission

settings = get_settings()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT configuration
security = HTTPBearer()
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.

    Args:
        data: Data to encode in the token.
        expires_delta: Optional custom expiration delta.

    Returns:
        Encoded JWT token.
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=settings.jwt_expiration_hours)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return encoded_jwt


async def verify_jwt_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Verify JWT token and return user.

    Args:
        credentials: HTTP Authorization credentials.
        db: Database session.

    Returns:
        User object if token is valid.

    Raises:
        HTTPException: If token is invalid or user not found.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    # Fetch user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return user


async def verify_api_key(
    api_key: Optional[str] = Security(api_key_header),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Verify API key and return user.

    Args:
        api_key: API key from header.
        db: Database session.

    Returns:
        User object if API key is valid.

    Raises:
        HTTPException: If API key is invalid or user not found.
    """
    # TODO: Implement API key storage and validation
    # For now, we'll skip API key authentication
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="API key authentication not implemented",
    )


# Alias for convenience
get_current_user = verify_jwt_token


async def verify_mtls(request: Request) -> bool:
    """
    Verify mTLS client certificate.

    Args:
        request: FastAPI request object.

    Returns:
        True if certificate is valid.

    Raises:
        HTTPException: If mTLS verification fails.
    """
    if not settings.tls_verify_client:
        # mTLS disabled, allow request
        return True

    # Check for client certificate
    client_cert = request.client.ssl_object
    if not client_cert:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client certificate required",
        )

    # TODO: Implement proper certificate validation
    # This should verify the certificate against the CA
    # and check against a certificate revocation list

    return True


def require_role(*allowed_roles):
    """
    Decorator to require specific user roles.

    Args:
        *allowed_roles: Allowed user roles.

    Returns:
        Decorator function.
    """
    from functools import wraps
    from fastapi import HTTPException, status

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get("current_user")
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated",
                )

            if current_user.role not in allowed_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Role {current_user.role.value} not allowed",
                )

            return await func(*args, **kwargs)
        return wrapper
    return decorator


# Alias for backward compatibility
verify_jwt = verify_jwt_token
