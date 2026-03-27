"""Role-based access control (RBAC) for VPS Manager."""
from typing import List, Optional
from enum import Enum

from database import UserRole


class Permission(str, Enum):
    """Permission enumeration."""
    # Customer management
    CUSTOMER_CREATE = "customer:create"
    CUSTOMER_READ = "customer:read"
    CUSTOMER_UPDATE = "customer:update"
    CUSTOMER_DELETE = "customer:delete"

    # VPS management
    VPS_CREATE = "vps:create"
    VPS_READ = "vps:read"
    VPS_UPDATE = "vps:update"
    VPS_DELETE = "vps:delete"
    VPS_DEPLOY = "vps:deploy"
    VPS_RESTART = "vps:restart"

    # Configuration management
    CONFIG_READ = "config:read"
    CONFIG_UPDATE = "config:update"
    CONFIG_HISTORY = "config:history"

    # Deployment management
    DEPLOYMENT_READ = "deployment:read"
    DEPLOYMENT_ROLLBACK = "deployment:rollback"

    # Audit logging
    AUDIT_READ = "audit:read"

    # User management
    USER_CREATE = "user:create"
    USER_READ = "user:read"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"


# Role permissions mapping
ROLE_PERMISSIONS: dict[UserRole, List[Permission]] = {
    UserRole.ADMIN: [
        # Full access to all resources
        Permission.CUSTOMER_CREATE,
        Permission.CUSTOMER_READ,
        Permission.CUSTOMER_UPDATE,
        Permission.CUSTOMER_DELETE,
        Permission.VPS_CREATE,
        Permission.VPS_READ,
        Permission.VPS_UPDATE,
        Permission.VPS_DELETE,
        Permission.VPS_DEPLOY,
        Permission.VPS_RESTART,
        Permission.CONFIG_READ,
        Permission.CONFIG_UPDATE,
        Permission.CONFIG_HISTORY,
        Permission.DEPLOYMENT_READ,
        Permission.DEPLOYMENT_ROLLBACK,
        Permission.AUDIT_READ,
        Permission.USER_CREATE,
        Permission.USER_READ,
        Permission.USER_UPDATE,
        Permission.USER_DELETE,
    ],
    UserRole.OPERATOR: [
        # Can manage VPSes and deploy configurations
        Permission.VPS_READ,
        Permission.VPS_UPDATE,
        Permission.VPS_DEPLOY,
        Permission.VPS_RESTART,
        Permission.CONFIG_READ,
        Permission.CONFIG_UPDATE,
        Permission.CONFIG_HISTORY,
        Permission.DEPLOYMENT_READ,
        Permission.DEPLOYMENT_ROLLBACK,
    ],
    UserRole.AUDITOR: [
        # Read-only access to audit logs
        Permission.AUDIT_READ,
    ],
    UserRole.CUSTOMER_ADMIN: [
        # Can manage their own customer's VPSes
        Permission.CUSTOMER_READ,
        Permission.VPS_READ,
        Permission.VPS_UPDATE,
        Permission.VPS_DEPLOY,
        Permission.VPS_RESTART,
        Permission.CONFIG_READ,
        Permission.CONFIG_UPDATE,
        Permission.CONFIG_HISTORY,
        Permission.DEPLOYMENT_READ,
    ],
}


def get_user_permissions(role: UserRole) -> List[Permission]:
    """
    Get permissions for a given role.

    Args:
        role: User role.

    Returns:
        List of permissions.
    """
    return ROLE_PERMISSIONS.get(role, [])


def check_permission(role: UserRole, permission: Permission) -> bool:
    """
    Check if a role has a specific permission.

    Args:
        role: User role.
        permission: Permission to check.

    Returns:
        True if role has permission, False otherwise.
    """
    return permission in get_user_permissions(role)


def require_permission(permission: Permission):
    """
    Decorator to require a specific permission.

    Args:
        permission: Required permission.

    Returns:
        Decorator function.
    """
    from functools import wraps
    from fastapi import HTTPException, status

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get current user from kwargs (injected by dependency)
            current_user = kwargs.get("current_user")
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated",
                )

            if not check_permission(current_user.role, permission):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission {permission.value} required",
                )

            return await func(*args, **kwargs)
        return wrapper
    return decorator


def check_customer_access(user_customer_id: Optional[int], resource_customer_id: int) -> bool:
    """
    Check if user can access a customer's resources.

    Args:
        user_customer_id: User's customer ID (None for admins).
        resource_customer_id: Resource's customer ID.

    Returns:
        True if user can access, False otherwise.
    """
    # Admins can access any customer
    if user_customer_id is None:
        return True

    # Customer admins can only access their own customer
    return user_customer_id == resource_customer_id
