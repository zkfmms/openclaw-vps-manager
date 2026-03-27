"""Tests for custom exceptions module."""
from datetime import datetime

import pytest

from services.exceptions import (
    VPSManagerError,
    AuthenticationError,
    AuthorizationError,
    InvalidTokenError,
    PermissionDeniedError,
    VPSNotFoundError,
    VPSStatusError,
    VPSDeploymentError,
    SSHConnectionError,
    SSHKeyError,
    SSHCommandError,
    GitOperationError,
    GitBranchNotFoundError,
    GitConflictError,
    EncryptionError,
    KeyNotFoundError,
    CustomerNotFoundError,
    CustomerAccessError,
    ConfigurationError,
    InvalidConfigurationError,
    ConfigurationValidationError,
    DatabaseError,
    DuplicateResourceError,
    DeploymentNotFoundError,
    RollbackError,
    ValidationError,
    PasswordStrengthError,
    RateLimitError,
    handle_exception,
)


class TestVPSManagerError:
    """Test cases for VPSManagerError base class."""

    def test_error_creation(self):
        """Test creating a VPSManagerError."""
        error = VPSManagerError(
            message="Test error",
            code="TEST_ERROR",
            status_code=400,
            details={"key": "value"},
        )

        assert error.message == "Test error"
        assert error.code == "TEST_ERROR"
        assert error.status_code == 400
        assert error.details == {"key": "value"}

    def test_error_to_dict(self):
        """Test converting error to dictionary."""
        error = VPSManagerError(
            message="Test error",
            code="TEST_ERROR",
            status_code=400,
            details={"key": "value"},
        )

        result = error.to_dict()

        assert result["error"] == "TEST_ERROR"
        assert result["message"] == "Test error"
        assert result["status_code"] == 400
        assert result["key"] == "value"

    def test_error_to_dict_no_details(self):
        """Test converting error to dictionary without details."""
        error = VPSManagerError(
            message="Test error",
            code="TEST_ERROR",
            status_code=400,
        )

        result = error.to_dict()

        assert result["error"] == "TEST_ERROR"
        assert result["message"] == "Test error"
        assert result["status_code"] == 400


class TestAuthenticationErrors:
    """Test cases for authentication-related errors."""

    def test_authentication_error(self):
        """Test AuthenticationError creation."""
        error = AuthenticationError("Invalid credentials")

        assert error.message == "Invalid credentials"
        assert error.code == "AUTHENTICATION_ERROR"
        assert error.status_code == 401
        assert isinstance(error, VPSManagerError)

    def test_invalid_token_error(self):
        """Test InvalidTokenError creation."""
        error = InvalidTokenError("Token expired")

        assert error.message == "Token expired"
        assert error.code == "INVALID_TOKEN"
        assert error.status_code == 401


class TestAuthorizationErrors:
    """Test cases for authorization-related errors."""

    def test_authorization_error(self):
        """Test AuthorizationError creation."""
        error = AuthorizationError("Access denied")

        assert error.message == "Access denied"
        assert error.code == "AUTHORIZATION_ERROR"
        assert error.status_code == 403

    def test_permission_denied_error(self):
        """Test PermissionDeniedError creation."""
        error = PermissionDeniedError("vps:read", "server-1")

        assert error.code == "PERMISSION_DENIED"
        assert error.status_code == 403
        assert error.details["permission"] == "vps:read"
        assert error.details["resource"] == "server-1"


class TestVPSErrors:
    """Test cases for VPS-related errors."""

    def test_vps_not_found_error(self):
        """Test VPSNotFoundError creation."""
        error = VPSNotFoundError(999)

        assert error.code == "VPS_NOT_FOUND"
        assert error.status_code == 404
        assert error.details["vps_id"] == 999

    def test_vps_status_error(self):
        """Test VPSStatusError creation."""
        error = VPSStatusError(1, "pending", "active")

        assert error.code == "VPS_STATUS_ERROR"
        assert error.status_code == 409
        assert error.details["current_status"] == "pending"
        assert error.details["required_status"] == "active"

    def test_vps_deployment_error(self):
        """Test VPSDeploymentError creation."""
        error = VPSDeploymentError(1, "Connection timeout")

        assert error.code == "VPS_DEPLOYMENT_ERROR"
        assert error.status_code == 500
        assert error.details["vps_id"] == 1
        assert error.details["reason"] == "Connection timeout"


class TestSSHErrors:
    """Test cases for SSH-related errors."""

    def test_ssh_connection_error(self):
        """Test SSHConnectionError creation."""
        error = SSHConnectionError("vps.example.com", "Connection refused")

        assert error.code == "SSH_CONNECTION_ERROR"
        assert error.status_code == 503
        assert error.details["hostname"] == "vps.example.com"
        assert error.details["reason"] == "Connection refused"

    def test_ssh_connection_error_with_port(self):
        """Test SSHConnectionError with custom port."""
        error = SSHConnectionError("vps.example.com", "Connection refused", port=2222)

        assert error.details["port"] == 2222

    def test_ssh_key_error(self):
        """Test SSHKeyError creation."""
        error = SSHKeyError("File not found")

        assert error.code == "SSH_KEY_ERROR"
        assert error.status_code == 500
        assert error.details["reason"] == "File not found"

    def test_ssh_key_error_with_path(self):
        """Test SSHKeyError with key path."""
        error = SSHKeyError("Invalid format", key_path="/tmp/key.pem")

        assert error.details["key_path"] == "/tmp/key.pem"

    def test_ssh_command_error(self):
        """Test SSHCommandError creation."""
        error = SSHCommandError("vps.example.com", "ls /nonexistent", 2, "No such file")

        assert error.code == "SSH_COMMAND_ERROR"
        assert error.status_code == 500
        assert error.details["hostname"] == "vps.example.com"
        assert error.details["command"] == "ls /nonexistent"
        assert error.details["exit_code"] == 2
        assert error.details["stderr"] == "No such file"


class TestGitErrors:
    """Test cases for Git-related errors."""

    def test_git_operation_error(self):
        """Test GitOperationError creation."""
        error = GitOperationError("push", "Remote rejected")

        assert error.code == "GIT_OPERATION_ERROR"
        assert error.status_code == 500
        assert error.details["operation"] == "push"
        assert error.details["reason"] == "Remote rejected"

    def test_git_operation_error_with_repo_path(self):
        """Test GitOperationError with repo path."""
        error = GitOperationError("clone", "Repository not found", repo_path="/tmp/repo")

        assert error.details["repo_path"] == "/tmp/repo"

    def test_git_branch_not_found_error(self):
        """Test GitBranchNotFoundError creation."""
        error = GitBranchNotFoundError("feature-branch")

        assert error.code == "GIT_OPERATION_ERROR"
        assert error.details["branch_name"] == "feature-branch"

    def test_git_conflict_error(self):
        """Test GitConflictError creation."""
        error = GitConflictError(["file1.txt", "file2.txt"])

        assert error.code == "GIT_OPERATION_ERROR"
        assert error.details["operation"] == "merge"
        assert len(error.details["conflicting_files"]) == 2


class TestEncryptionErrors:
    """Test cases for encryption-related errors."""

    def test_encryption_error(self):
        """Test EncryptionError creation."""
        error = EncryptionError("encrypt", "Invalid key")

        assert error.code == "ENCRYPTION_ERROR"
        assert error.status_code == 500
        assert error.details["operation"] == "encrypt"
        assert error.details["reason"] == "Invalid key"

    def test_key_not_found_error(self):
        """Test KeyNotFoundError creation."""
        error = KeyNotFoundError("/tmp/key.pem")

        assert error.code == "KEY_NOT_FOUND"
        assert error.status_code == 500
        assert error.details["key_path"] == "/tmp/key.pem"


class TestCustomerErrors:
    """Test cases for customer-related errors."""

    def test_customer_not_found_error(self):
        """Test CustomerNotFoundError creation."""
        error = CustomerNotFoundError(999)

        assert error.code == "CUSTOMER_NOT_FOUND"
        assert error.status_code == 404
        assert error.details["customer_id"] == 999

    def test_customer_access_error(self):
        """Test CustomerAccessError creation."""
        error = CustomerAccessError(1, 2)

        assert error.code == "CUSTOMER_ACCESS_ERROR"
        assert error.status_code == 403
        assert error.details["user_customer_id"] == 1
        assert error.details["resource_customer_id"] == 2


class TestConfigurationErrors:
    """Test cases for configuration-related errors."""

    def test_configuration_error(self):
        """Test ConfigurationError creation."""
        error = ConfigurationError("Invalid JSON format")

        assert error.code == "CONFIGURATION_ERROR"
        assert error.status_code == 400

    def test_configuration_error_with_details(self):
        """Test ConfigurationError with details."""
        error = ConfigurationError("Invalid value", {"field": "port", "value": "abc"})

        assert error.details["field"] == "port"
        assert error.details["value"] == "abc"

    def test_invalid_configuration_error(self):
        """Test InvalidConfigurationError creation."""
        error = InvalidConfigurationError("port", "Must be a number")

        assert error.code == "CONFIGURATION_VALIDATION_ERROR"
        assert error.details["field"] == "port"
        assert error.details["reason"] == "Must be a number"

    def test_configuration_validation_error(self):
        """Test ConfigurationValidationError creation."""
        errors = {
            "port": "Must be numeric",
            "hostname": "Invalid characters",
        }
        error = ConfigurationValidationError(errors)

        assert error.code == "CONFIGURATION_VALIDATION_ERROR"
        assert error.details["validation_errors"] == errors


class TestDatabaseErrors:
    """Test cases for database-related errors."""

    def test_database_error(self):
        """Test DatabaseError creation."""
        error = DatabaseError("select", "Connection timeout")

        assert error.code == "DATABASE_ERROR"
        assert error.status_code == 500
        assert error.details["operation"] == "select"
        assert error.details["reason"] == "Connection timeout"

    def test_duplicate_resource_error(self):
        """Test DuplicateResourceError creation."""
        error = DuplicateResourceError("vps", "vps1.example.com")

        assert error.code == "DUPLICATE_RESOURCE"
        assert error.status_code == 409
        assert error.details["resource_type"] == "vps"
        assert error.details["identifier"] == "vps1.example.com"


class TestDeploymentErrors:
    """Test cases for deployment-related errors."""

    def test_deployment_not_found_error(self):
        """Test DeploymentNotFoundError creation."""
        error = DeploymentNotFoundError(999)

        assert error.code == "DEPLOYMENT_NOT_FOUND"
        assert error.status_code == 404
        assert error.details["deployment_id"] == 999

    def test_rollback_error(self):
        """Test RollbackError creation."""
        error = RollbackError(123, "Commit not found")

        assert error.code == "ROLLBACK_ERROR"
        assert error.status_code == 500
        assert error.details["deployment_id"] == 123
        assert error.details["reason"] == "Commit not found"


class TestValidationErrors:
    """Test cases for validation-related errors."""

    def test_validation_error(self):
        """Test ValidationError creation."""
        error = ValidationError("email", "Invalid format")

        assert error.code == "VALIDATION_ERROR"
        assert error.status_code == 400
        assert error.details["field"] == "email"
        assert error.details["reason"] == "Invalid format"

    def test_validation_error_with_value(self):
        """Test ValidationError with value."""
        error = ValidationError("age", "Must be positive", "-5")

        assert error.details["value"] == "-5"

    def test_password_strength_error(self):
        """Test PasswordStrengthError creation."""
        error = PasswordStrengthError("Too short")

        assert error.code == "PASSWORD_STRENGTH_ERROR"
        assert error.code == "VALIDATION_ERROR"
        assert error.details["field"] == "password"
        assert error.details["reason"] == "Too short"


class TestRateLimitErrors:
    """Test cases for rate limiting errors."""

    def test_rate_limit_error(self):
        """Test RateLimitError creation."""
        error = RateLimitError(100, 60)

        assert error.code == "RATE_LIMIT_EXCEEDED"
        assert error.status_code == 429
        assert error.details["limit"] == 100
        assert error.details["window"] == 60


class TestHandleException:
    """Test cases for handle_exception utility function."""

    def test_handle_vps_manager_exception(self):
        """Test handling VPSManagerError."""
        error = VPSNotFoundError(123)
        result = handle_exception(error)

        assert result["error"] == "VPS_NOT_FOUND"
        assert result["status_code"] == 404
        assert result["vps_id"] == 123

    def test_handle_generic_exception(self):
        """Test handling generic exception."""
        error = ValueError("Something went wrong")
        result = handle_exception(error)

        assert result["error"] == "INTERNAL_ERROR"
        assert result["message"] == "An unexpected error occurred"
        assert result["status_code"] == 500

    def test_handle_none_exception(self):
        """Test handling None as exception."""
        result = handle_exception(None)

        assert result["error"] == "INTERNAL_ERROR"
        assert result["message"] == "An unexpected error occurred"

    def test_handle_subclass_exception(self):
        """Test handling subclass of VPSManagerError."""
        error = SSHConnectionError("host", "Failed")
        result = handle_exception(error)

        assert result["error"] == "SSH_CONNECTION_ERROR"
        assert result["status_code"] == 503
