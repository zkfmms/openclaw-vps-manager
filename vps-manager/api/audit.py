"""Audit logging API endpoints."""
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field

from database import get_db, AuditLog, User, VPSServer
from auth.middleware import get_current_user
from auth.rbac import require_permission, Permission, check_customer_access
from models import User as UserModel

router = APIRouter(prefix="/audit", tags=["Audit Logging"])


# Pydantic models
class AuditLogResponse(BaseModel):
    """Response model for audit log."""
    id: int
    user_id: Optional[int]
    vps_id: Optional[int]
    customer_id: Optional[int]
    action: str
    resource_type: str
    resource_id: Optional[int]
    details: Optional[dict]
    ip_address: Optional[str]
    timestamp: datetime

    class Config:
        from_attributes = True


@router.get("/logs", response_model=List[AuditLogResponse])
async def list_audit_logs(
    customer_id: Optional[int] = None,
    vps_id: Optional[int] = None,
    action: Optional[str] = None,
    limit: int = Field(default=100, ge=1, le=1000),
    offset: int = Field(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """List audit logs (filtered by role)."""
    # Check permission
    require_permission(Permission.AUDIT_READ)(lambda: None)

    # Build query
    query = select(AuditLog)

    # Filter by access
    if current_user.role.value != "admin":
        if current_user.customer_id:
            # Customer admins can only see their own logs
            query = query.where(AuditLog.customer_id == current_user.customer_id)
        elif customer_id:
            # Other non-admin users can filter by customer
            query = query.where(AuditLog.customer_id == customer_id)

    # Additional filters
    if customer_id:
        query = query.where(AuditLog.customer_id == customer_id)
    if vps_id:
        # Check VPS access
        vps_result = await db.execute(select(VPSServer).where(VPSServer.id == vps_id))
        vps = vps_result.scalar_one_or_none()
        if vps and not check_customer_access(current_user.customer_id, vps.customer_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot access this VPS's logs",
            )
        query = query.where(AuditLog.vps_id == vps_id)
    if action:
        query = query.where(AuditLog.action == action)

    # Order by timestamp descending
    query = query.order_by(AuditLog.timestamp.desc())

    # Apply pagination
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    logs = result.scalars().all()

    return logs


@router.get("/vps/{vps_id}", response_model=List[AuditLogResponse])
async def get_vps_audit_trail(
    vps_id: int,
    limit: int = Field(default=100, ge=1, le=1000),
    offset: int = Field(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """Get audit trail for a specific VPS."""
    # Check permission
    require_permission(Permission.AUDIT_READ)(lambda: None)

    # Verify VPS exists and check access
    vps_result = await db.execute(select(VPSServer).where(VPSServer.id == vps_id))
    vps = vps_result.scalar_one_or_none()

    if not vps:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPS not found",
        )

    # Check customer access
    if not check_customer_access(current_user.customer_id, vps.customer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access this VPS's logs",
        )

    # Build query
    query = select(AuditLog).where(AuditLog.vps_id == vps_id)

    # Order by timestamp descending
    query = query.order_by(AuditLog.timestamp.desc())

    # Apply pagination
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    logs = result.scalars().all()

    return logs


@router.get("/stats")
async def get_audit_stats(
    customer_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """Get audit log statistics."""
    # Check permission
    require_permission(Permission.AUDIT_READ)(lambda: None)

    # Build base query
    query = select(AuditLog)

    # Filter by access
    if current_user.role.value != "admin":
        if current_user.customer_id:
            query = query.where(AuditLog.customer_id == current_user.customer_id)
        elif customer_id:
            query = query.where(AuditLog.customer_id == customer_id)

    # Count by resource type
    resource_type_counts = {}
    for resource_type in ["customer", "vps", "deployment", "config", "user"]:
        count_query = query.where(AuditLog.resource_type == resource_type)
        result = await db.execute(count_query)
        count = len(result.scalars().all())
        resource_type_counts[resource_type] = count

    # Count by action
    action_counts = {}
    for action in ["create", "update", "delete", "deploy", "restart"]:
        count_query = query.where(AuditLog.action == action)
        result = await db.execute(count_query)
        count = len(result.scalars().all())
        action_counts[action] = count

    return {
        "by_resource_type": resource_type_counts,
        "by_action": action_counts,
    }
