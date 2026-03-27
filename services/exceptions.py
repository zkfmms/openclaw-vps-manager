"""Custom exceptions for VPS Manager with consistent error handling."""
from typing import Any, Dict, Optional


class VPSManagerError(Exception):
    """Base exception for all VPS Manager errors."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize VPS Manager error.

        Args:
            message: Human-readable error message.
            code: Machine-readable error code.
            status_code: HTTP status code to return.
            details: Additional error context.
        """
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for API responses."""
        return {
            "error": self.code,
            "message": self.message,
            "status_code": self.status_code,
            **self.details,
        }


# Authentication and Authorization Errors
class AuthenticationError(VPSManagerError):
    """Authentication failed."""

    def __init__(self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="AUTHENTICATION_ERROR",
            status_code=401,
            details=details,
        )


class AuthorizationError(VPSManagerError):
    """Authorization failed - insufficient permissions."""

    def __init__(self, message: str = "Access denied", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="AUTHORIZATION_ERROR",
            status_code=403,
            details=details,
        )


class InvalidTokenError(AuthenticationError):
    """Invalid or expired token."""

    def __init__(self, message: str = "Invalid or expired token"):
        super().__init__(message=message, code="INVALID_TOKEN")


class PermissionDeniedError(AuthorizationError):
    """Permission denied for specific resource."""

    def __init__(self, permission: str, resource: str):
        super().__init__(
            message=f"Permission denied: {permission} required for {resource}",
            code="PERMISSION_DENIED",
            details={"permission": permission, "resource": resource},
        )


# VPS Management Errors
class VPSNotFoundError(VPSManagerError):
    """VPS server not found."""

    def __init__(self, vps_id: int):
        super().__init__(
            message=f"VPS server with ID {vps_id} not found",
            code="VPS_NOT_FOUND",
            status_code=404,
            details={"vps_id": vps_id},
        )


class VPSStatusError(VPSManagerError):
    """VPS is in an invalid state for requested operation."""

    def __init__(self, vps_id: int, current_status: str, required_status: str):
        super().__init__(
            message=f"VPS {vps_id} is {current_status}, but requires {required_status}",
            code="VPS_STATUS_ERROR",
            status_code=409,
            details={"vps_id": vps_id, "current_status": current_status, "required_status": required_status},
        )


class VPSDeploymentError(VPSManagerError):
    """Failed to deploy configuration to VPS."""

    def __init__(self, vps_id: int, reason: str):
        super().__init__(
            message=f"Deployment to VPS {vps_id} failed: {reason}",
            code="VPS_DEPLOYMENT_ERROR",
            status_code=500,
            details={"vps_id": vps_id, "reason": reason},
        )


# SSH Connection Errors
class SSHConnectionError(VPSManagerError):
    """Failed to establish SSH connection."""

    def __init__(self, hostname: str, reason: str, port: int = 22):
        super().__init__(
            message=f"SSH connection to {hostname}:{port} failed: {reason}",
            code="SSH_CONNECTION_ERROR",
            status_code=503,
            details={"hostname": hostname, "port": port, "reason": reason},
        )


class SSHKeyError(VPSManagerError):
    """Error with SSH key handling."""

    def __init__(self, reason: str, key_path: Optional[str] = None):
        details = {"reason": reason}
        if key_path:
            details["key_path"] = key_path
        super().__init__(
            message=f"SSH key error: {reason}",
            code="SSH_KEY_ERROR",
            status_code=500,
            details=details,
        )


class SSHCommandError(VPSManagerError):
    """SSH command execution failed."""

    def __init__(self, hostname: str, command: str, exit_code: int, stderr: str):
        super().__init__(
            message=f"Command failed on {hostname}: {command[:100]}",
            code="SSH_COMMAND_ERROR",
            status_code=500,
            details={
                "hostname": hostname,
                "command": command,
                "exit_code": exit_code,
                "stderr": stderr,
            },
        )


# Git Operation Errors
class GitOperationError(VPSManagerError):
    """Git operation failed."""

    def __init__(self, operation: str, reason: str, repo_path: Optional[str] = None):
        details = {"operation": operation, "reason": reason}
        if repo_path:
            details["repo_path"] = repo_path
        super().__init__(
            message=f"Git operation '{operation}' failed: {reason}",
            code="GIT_OPERATION_ERROR",
            status_code=500,
            details=details,
        )


class GitBranchNotFoundError(GitOperationError):
    """Git branch not found."""

    def __init__(self, branch_name: str):
        super().__init__(
            operation="checkout",
            reason=f"Branch '{branch_name}' not found",
            details={"branch_name": branch_name},
        )


class GitConflictError(GitOperationError):
    """Git merge conflict occurred."""

    def __init__(self, files: list):
        super().__init__(
            operation="merge",
            reason=f"Merge conflict in {len(files)} files",
            details={"conflicting_files": files},
        )


# Encryption Errors
class EncryptionError(VPSManagerError):
    """Encryption or decryption failed."""

    def __init__(self, operation: str, reason: str):
        super().__init__(
            message=f"Encryption {operation} failed: {reason}",
            code="ENCRYPTION_ERROR",
            status_code=500,
            details={"operation": operation, "reason": reason},
        )


class KeyNotFoundError(VPSManagerError):
    """Encryption key not found."""

    def __init__(self, key_path: str):
        super().__init__(
            message=f"Encryption key not found at {key_path}",
            code="KEY_NOT_FOUND",
            status_code=500,
            details={"key_path": key_path},
        )


# Customer Errors
class CustomerNotFoundError(VPSManagerError):
    """Customer not found."""

    def __init__(self, customer_id: int):
        super().__init__(
            message=f"Customer with ID {customer_id} not found",
            code="CUSTOMER_NOT_FOUND",
            status_code=404,
            details={"customer_id": customer_id},
        )


class CustomerAccessError(AuthorizationError):
    """User cannot access customer resources."""

    def __init__(self, user_customer_id: Optional[int], resource_customer_id: int):
        super().__init__(
            message=f"Cannot access customer {resource_customer_id} resources",
            code="CUSTOMER_ACCESS_ERROR",
            details={
                "user_customer_id": user_customer_id,
                "resource_customer_id": resource_customer_id,
            },
        )


# Configuration Errors
class ConfigurationError(VPSManagerError):
    """Configuration error."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="CONFIGURATION_ERROR",
            status_code=400,
            details=details,
        )


class InvalidConfigurationError(ConfigurationError):
    """Invalid configuration format or values."""

    def __init__(self, field: str, reason: str):
        super().__init__(
            message=f"Invalid configuration: {field} - {reason}",
            details={"field": field, "reason": reason},
        )


class ConfigurationValidationError(ConfigurationError):
    """Configuration validation failed."""

    def __init__(self, errors: Dict[str, str]):
        super().__init__(
            message=f"Configuration validation failed with {len(errors)} error(s)",
            code="CONFIGURATION_VALIDATION_ERROR",
            details={"validation_errors": errors},
        )


# Database Errors
class DatabaseError(VPSManagerError):
    """Database operation failed."""

    def __init__(self, operation: str, reason: str):
        super().__init__(
            message=f"Database {operation} failed: {reason}",
            code="DATABASE_ERROR",
            status_code=500,
            details={"operation": operation, "reason": reason},
        )


class DuplicateResourceError(VPSManagerError):
    """Resource already exists."""

    def __init__(self, resource_type: str, identifier: str):
        super().__init__(
            message=f"{resource_type} with identifier '{identifier}' already exists",
            code="DUPLICATE_RESOURCE",
            status_code=409,
            details={"resource_type": resource_type, "identifier": identifier},
        )


# Deployment Errors
class DeploymentNotFoundError(VPSManagerError):
    """Deployment not found."""

    def __init__(self, deployment_id: int):
        super().__init__(
            message=f"Deployment with ID {deployment_id} not found",
            code="DEPLOYMENT_NOT_FOUND",
            status_code=404,
            details={"deployment_id": deployment_id},
        )


class RollbackError(VPSManagerError):
    """Deployment rollback failed."""

    def __init__(self, deployment_id: int, reason: str):
        super().__init__(
            message=f"Rollback of deployment {deployment_id} failed: {reason}",
            code="ROLLBACK_ERROR",
            status_code=500,
            details={"deployment_id": deployment_id, "reason": reason},
        )


# Validation Errors
class ValidationError(VPSManagerError):
    """Input validation failed."""

    def __init__(self, field: str, reason: str, value: Any = None):
        details: Dict[str, Any] = {"field": field, "reason": reason}
        if value is not None:
            details["value"] = str(value)
        super().__init__(
            message=f"Validation error: {field} - {reason}",
            code="VALIDATION_ERROR",
            status_code=400,
            details=details,
        )


class PasswordStrengthError(ValidationError):
    """Password does not meet strength requirements."""

    def __init__(self, reason: str):
        super().__init__(
            field="password",
            reason=reason,
            code="PASSWORD_STRENGTH_ERROR",
        )


# Rate Limiting Errors
class RateLimitError(VPSManagerError):
    """Request rate limit exceeded."""

    def __init__(self, limit: int, window: int):
        super().__init__(
            message=f"Rate limit exceeded: {limit} requests per {window} seconds",
            code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details={"limit": limit, "window": window},
        )


# Utility function for handling exceptions in endpoints
def handle_exception(exc: Exception) -> Dict[str, Any]:
    """
    Convert an exception to a consistent error response.

    Args:
        exc: Exception to handle.

    Returns:
        Dictionary with error information.
    """
    if isinstance(exc, VPSManagerError):
        return exc.to_dict()
    else:
        # Unexpected exception
        return {
            "error": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "status_code": 500,
        }
