"""Authentication middleware for VPS Manager."""
import os
import re
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
    # Validate password strength before hashing
    is_valid, error_msg = _validate_password(password)
    if not is_valid:
        from services.exceptions import PasswordStrengthError
        raise PasswordStrengthError(error_msg)
    return pwd_context.hash(password)


def _validate_password(password: str) -> tuple[bool, Optional[str]]:
    """
    Validate password strength.

    Args:
        password: Password to validate.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if len(password) < settings.password_min_length:
        return False, f"Password must be at least {settings.password_min_length} characters long"

    if settings.password_require_uppercase and not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"

    if settings.password_require_lowercase and not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"

    if settings.password_require_digits and not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit"

    if settings.password_require_special and not any(c in settings.password_special_chars for c in password):
        return False, f"Password must contain at least one special character from: {settings.password_special_chars}"

    return True, None


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
    request: Request = None,
) -> User:
    """
    Verify JWT token and return user.

    Args:
        credentials: HTTP Authorization credentials.
        db: Database session.
        request: FastAPI request object.

    Returns:
        User object if token is valid.

    Raises:
        HTTPException: If token is invalid or user not found.
    """
    from services.exceptions import InvalidTokenError
    from services.logging import get_logger

    logger = get_logger("auth")

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
    except JWTError as e:
        logger.warning(f"Invalid JWT token", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    # Fetch user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        logger.warning(f"User not found for token", user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        logger.warning(f"Inactive user attempted login", user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    # Store user in request state for logging
    if request:
        request.state.user = user

    return user


async def verify_api_key(
    api_key: Optional[str] = Security(api_key_header),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
) -> User:
    """
    Verify API key and return user.

    Args:
        api_key: API key from header.
        db: Database session.
        request: FastAPI request object.

    Returns:
        User object if API key is valid.

    Raises:
        HTTPException: If API key is invalid or user not found.
    """
    from services.logging import get_logger

    logger = get_logger("auth")

    if not settings.api_key_enabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key authentication is disabled",
        )

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
        )

    # TODO: Implement API key storage and validation
    # This would check the database for the API key and return the associated user
    logger.warning(f"API key authentication attempted but not implemented", api_key_prefix=api_key[:8] if api_key else None)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="API key authentication not yet implemented",
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
