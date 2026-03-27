"""Tests for authentication and RBAC."""
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status

from auth.middleware import (
    verify_password,
    get_password_hash,
    create_access_token,
    verify_jwt_token,
    verify_api_key,
    verify_mtls,
    get_password_hash,
    require_role,
    get_current_user,
)
from auth.rbac import (
    Permission,
    get_user_permissions,
    check_permission,
    require_permission,
    check_customer_access,
)
from database import UserRole


class TestPasswordHashing:
    """Test cases for password hashing."""

    def test_get_password_hash(self):
        """Test password hashing."""
        password = "test_password_123"
        hashed = get_password_hash(password)

        # Hash should be different from original
        assert hashed != password

        # Hash should be a bcrypt hash (starts with $2b$)
        assert hashed.startswith("$2b$")

    def test_verify_password_correct(self):
        """Test verifying correct password."""
        password = "test_password_123"
        hashed = get_password_hash(password)

        result = verify_password(password, hashed)
        assert result is True

    def test_verify_password_incorrect(self):
        """Test verifying incorrect password."""
        password = "test_password_123"
        wrong_password = "wrong_password"
        hashed = get_password_hash(password)

        result = verify_password(wrong_password, hashed)
        assert result is False

    def test_verify_password_empty(self):
        """Test verifying empty password."""
        password = ""
        hashed = get_password_hash(password)

        result = verify_password("", hashed)
        assert result is True

        result = verify_password("wrong", hashed)
        assert result is False


class TestJWT:
    """Test cases for JWT token handling."""

    @patch("auth.middleware.settings")
    def test_create_access_token(self, mock_settings):
        """Test creating JWT access token."""
        mock_settings.jwt_secret = "test_secret"
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.jwt_expiration_hours = 24

        data = {"sub": 123, "role": "admin"}
        token = create_access_token(data)

        assert token is not None
        assert isinstance(token, str)

        # Verify token can be decoded
        from jose import jwt
        decoded = jwt.decode(token, "test_secret", algorithms=["HS256"])
        assert decoded["sub"] == 123
        assert decoded["role"] == "admin"

    @patch("auth.middleware.settings")
    def test_create_access_token_custom_expiration(self, mock_settings):
        """Test creating token with custom expiration."""
        mock_settings.jwt_secret = "test_secret"
        mock_settings.jwt_algorithm = "HS256"

        data = {"sub": 123}
        token = create_access_token(data, expires_delta=timedelta(hours=2))

        # Verify token expiration
        from jose import jwt
        decoded = jwt.decode(token, "test_secret", algorithms=["HS256"])
        exp = datetime.fromtimestamp(decoded["exp"])
        now = datetime.utcnow()
        assert (exp - now).total_seconds() < 7200  # 2 hours

    @pytest.mark.asyncio
    @patch("auth.middleware.settings")
    async def test_verify_jwt_token_success(self, mock_settings):
        """Test successful JWT token verification."""
        mock_settings.jwt_secret = "test_secret"
        mock_settings.jwt_algorithm = "HS256"

        from database import User
        mock_user = User(
            id=123,
            email="test@example.com",
            username="testuser",
            hashed_password="hash",
            role=UserRole.ADMIN,
            is_active=True,
        )

        mock_db = AsyncMock()
        mock_db.execute = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result

        data = {"sub": 123}
        token = create_access_token(data)

        # Mock credentials
        mock_credentials = MagicMock()
        mock_credentials.credentials = token

        user = await verify_jwt_token(mock_credentials, mock_db)

        assert user.id == 123
        assert user.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_verify_jwt_token_no_credentials(self):
        """Test JWT verification with no credentials."""
        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await verify_jwt_token(None, mock_db)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("auth.middleware.settings")
    async def test_verify_jwt_token_invalid_token(self, mock_settings):
        """Test JWT verification with invalid token."""
        mock_settings.jwt_secret = "test_secret"
        mock_settings.jwt_algorithm = "HS256"

        mock_db = AsyncMock()
        mock_credentials = MagicMock()
        mock_credentials.credentials = "invalid_token"

        with pytest.raises(HTTPException) as exc_info:
            await verify_jwt_token(mock_credentials, mock_db)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("auth.middleware.settings")
    async def test_verify_jwt_token_user_not_found(self, mock_settings):
        """Test JWT verification when user not found."""
        mock_settings.jwt_secret = "test_secret"
        mock_settings.jwt_algorithm = "HS256"

        mock_db = AsyncMock()
        mock_db.execute = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        data = {"sub": 999}
        token = create_access_token(data)

        mock_credentials = MagicMock()
        mock_credentials.credentials = token

        with pytest.raises(HTTPException) as exc_info:
            await verify_jwt_token(mock_credentials, mock_db)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("auth.middleware.settings")
    async def test_verify_jwt_token_inactive_user(self, mock_settings):
        """Test JWT verification with inactive user."""
        mock_settings.jwt_secret = "test_secret"
        mock_settings.jwt_algorithm = "HS256"

        from database import User
        mock_user = User(
            id=123,
            email="test@example.com",
            username="testuser",
            hashed_password="hash",
            role=UserRole.ADMIN,
            is_active=False,  # Inactive user
        )

        mock_db = AsyncMock()
        mock_db.execute = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result

        data = {"sub": 123}
        token = create_access_token(data)

        mock_credentials = MagicMock()
        mock_credentials.credentials = token

        with pytest.raises(HTTPException) as exc_info:
            await verify_jwt_token(mock_credentials, mock_db)

        assert exc_info.value.status_code == 403


class TestRBAC:
    """Test cases for role-based access control."""

    def test_get_user_permissions_admin(self):
        """Test getting permissions for admin role."""
        permissions = get_user_permissions(UserRole.ADMIN)

        assert Permission.CUSTOMER_CREATE in permissions
        assert Permission.VPS_CREATE in permissions
        assert Permission.CONFIG_UPDATE in permissions
        assert Permission.AUDIT_READ in permissions

    def test_get_user_permissions_operator(self):
        """Test getting permissions for operator role."""
        permissions = get_user_permissions(UserRole.OPERATOR)

        # Operators can manage VPSes but not customers
        assert Permission.VPS_DEPLOY in permissions
        assert Permission.VPS_RESTART in permissions
        assert Permission.CONFIG_UPDATE in permissions
        assert Permission.CUSTOMER_CREATE not in permissions

    def test_get_user_permissions_auditor(self):
        """Test getting permissions for auditor role."""
        permissions = get_user_permissions(UserRole.AUDITOR)

        # Auditors can only read audit logs
        assert Permission.AUDIT_READ in permissions
        assert Permission.VPS_READ not in permissions
        assert Permission.CONFIG_READ not in permissions

    def test_check_permission_admin(self):
        """Test permission check for admin."""
        assert check_permission(UserRole.ADMIN, Permission.CUSTOMER_DELETE)
        assert check_permission(UserRole.ADMIN, Permission.CONFIG_UPDATE)
        assert check_permission(UserRole.ADMIN, Permission.VPS_DEPLOY)

    def test_check_permission_operator(self):
        """Test permission check for operator."""
        assert check_permission(UserRole.OPERATOR, Permission.VPS_DEPLOY)
        assert check_permission(UserRole.OPERATOR, Permission.CONFIG_UPDATE)
        assert not check_permission(UserRole.OPERATOR, Permission.CUSTOMER_CREATE)
        assert not check_permission(UserRole.OPERATOR, Permission.USER_DELETE)

    def test_check_permission_customer_admin(self):
        """Test permission check for customer admin."""
        assert check_permission(UserRole.CUSTOMER_ADMIN, Permission.VPS_DEPLOY)
        assert check_permission(UserRole.CUSTOMER_ADMIN, Permission.CONFIG_UPDATE)
        assert not check_permission(UserRole.CUSTOMER_ADMIN, Permission.CUSTOMER_CREATE)

    def test_check_customer_access_admin(self):
        """Test customer access for admin (None customer_id)."""
        # Admins can access any customer
        assert check_customer_access(None, 1)
        assert check_customer_access(None, 999)

    def test_check_customer_access_same_customer(self):
        """Test customer access for same customer."""
        # Customer admins can access their own customer
        assert check_customer_access(1, 1)
        assert check_customer_access(42, 42)

    def test_check_customer_access_different_customer(self):
        """Test customer access for different customer."""
        # Customer admins cannot access other customers
        assert not check_customer_access(1, 2)
        assert not check_customer_access(42, 1)

    @pytest.mark.asyncio
    @patch("auth.middleware.settings")
    async def test_require_permission_decorator_success(self, mock_settings):
        """Test require_permission decorator with sufficient permission."""
        mock_settings.jwt_secret = "test_secret"
        mock_settings.jwt_algorithm = "HS256"

        from database import User
        mock_user = User(
            id=1,
            email="admin@example.com",
            username="admin",
            hashed_password="hash",
            role=UserRole.ADMIN,
            is_active=True,
        )

        async def test_func(current_user):
            return "success"

        decorated_func = require_permission(Permission.CUSTOMER_CREATE)(test_func)
        result = await decorated_func(current_user=mock_user)

        assert result == "success"

    @pytest.mark.asyncio
    @patch("auth.middleware.settings")
    async def test_require_permission_decorator_denied(self, mock_settings):
        """Test require_permission decorator with insufficient permission."""
        mock_settings.jwt_secret = "test_secret"
        mock_settings.jwt_algorithm = "HS256"

        from database import User
        mock_user = User(
            id=2,
            email="auditor@example.com",
            username="auditor",
            hashed_password="hash",
            role=UserRole.AUDITOR,
            is_active=True,
        )

        async def test_func(current_user):
            return "success"

        decorated_func = require_permission(Permission.CUSTOMER_CREATE)(test_func)

        with pytest.raises(HTTPException) as exc_info:
            await decorated_func(current_user=mock_user)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @patch("auth.middleware.settings")
    async def test_require_permission_decorator_no_user(self, mock_settings):
        """Test require_permission decorator without user."""
        mock_settings.jwt_secret = "test_secret"
        mock_settings.jwt_algorithm = "HS256"

        async def test_func():
            return "success"

        decorated_func = require_permission(Permission.CUSTOMER_CREATE)(test_func)

        with pytest.raises(HTTPException) as exc_info:
            await decorated_func()

        assert exc_info.value.status_code == 401


class TestAPIKey:
    """Test cases for API key authentication."""

    @pytest.mark.asyncio
    @patch("auth.middleware.settings")
    async def test_verify_api_key_disabled(self, mock_settings):
        """Test API key verification when disabled."""
        mock_settings.api_key_enabled = False

        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key("test_key", mock_db)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("auth.middleware.settings")
    async def test_verify_api_key_no_key(self, mock_settings):
        """Test API key verification with no key."""
        mock_settings.api_key_enabled = True

        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(None, mock_db)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("auth.middleware.settings")
    async def test_verify_api_key_not_implemented(self, mock_settings):
        """Test API key verification (not implemented)."""
        mock_settings.api_key_enabled = True

        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key("test_key", mock_db)

        assert exc_info.value.status_code == 501


class TestMTLS:
    """Test cases for mTLS verification."""

    @patch("auth.middleware.settings")
    def test_verify_mtls_disabled(self, mock_settings):
        """Test mTLS verification when disabled."""
        mock_settings.tls_verify_client = False

        mock_request = MagicMock()

        result = verify_mtls(mock_request)
        assert result is True

    @patch("auth.middleware.settings")
    def test_verify_mtls_no_certificate(self, mock_settings):
        """Test mTLS verification without certificate."""
        mock_settings.tls_verify_client = True

        mock_request = MagicMock()
        mock_request.client.ssl_object = None

        with pytest.raises(HTTPException) as exc_info:
            verify_mtls(mock_request)

        assert exc_info.value.status_code == 403

    @patch("auth.middleware.settings")
    def test_verify_mtls_with_certificate(self, mock_settings):
        """Test mTLS verification with certificate."""
        mock_settings.tls_verify_client = True

        mock_request = MagicMock()
        mock_request.client.ssl_object = MagicMock()

        result = verify_mtls(mock_request)
        assert result is True


class TestRequireRole:
    """Test cases for require_role decorator."""

    @pytest.mark.asyncio
    async def test_require_role_success(self):
        """Test require_role with allowed role."""
        from database import User
        mock_user = User(
            id=1,
            email="admin@example.com",
            username="admin",
            hashed_password="hash",
            role=UserRole.ADMIN,
            is_active=True,
        )

        async def test_func(current_user):
            return "success"

        decorated_func = require_role(UserRole.ADMIN, UserRole.OPERATOR)(test_func)
        result = await decorated_func(current_user=mock_user)

        assert result == "success"

    @pytest.mark.asyncio
    async def test_require_role_denied(self):
        """Test require_role with disallowed role."""
        from database import User
        mock_user = User(
            id=2,
            email="auditor@example.com",
            username="auditor",
            hashed_password="hash",
            role=UserRole.AUDITOR,
            is_active=True,
        )

        async def test_func(current_user):
            return "success"

        decorated_func = require_role(UserRole.ADMIN)(test_func)

        with pytest.raises(HTTPException) as exc_info:
            await decorated_func(current_user=mock_user)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_require_role_no_user(self):
        """Test require_role without user."""
        async def test_func():
            return "success"

        decorated_func = require_role(UserRole.ADMIN)(test_func)

        with pytest.raises(HTTPException) as exc_info:
            await decorated_func()

        assert exc_info.value.status_code == 401
