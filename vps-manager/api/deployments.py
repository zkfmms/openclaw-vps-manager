"""Deployment management API endpoints."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field

from database import get_db, Deployment
from auth.middleware import get_current_user
from auth.rbac import require_permission, Permission, check_customer_access
from services.git_manager import get_git_manager
from models import User

router = APIRouter(prefix="/deployments", tags=["Deployment Management"])


# Pydantic models
class DeploymentResponse(BaseModel):
    """Response model for deployment."""
    id: int
    vps_id: int
    customer_id: int
    git_commit_hash: str
    deployed_at: str
    status: str
    rollback_commit: Optional[str]
    error_message: Optional[str]

    class Config:
        from_attributes = True


class RollbackResponse(BaseModel):
    """Response model for rollback operation."""
    message: str
    rollback_commit: str
    previous_commit: str


@router.get("", response_model=List[DeploymentResponse])
async def list_deployments(
    customer_id: Optional[int] = None,
    vps_id: Optional[int] = None,
    status_filter: Optional[str] = None,
    limit: int = Field(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List deployments (filtered by role)."""
    # Check permission
    require_permission(Permission.DEPLOYMENT_READ)(lambda: None)

    # Build query
    query = select(Deployment)

    # Filter by customer access
    if current_user.role.value != "admin":
        if current_user.customer_id:
            query = query.where(Deployment.customer_id == current_user.customer_id)
        elif customer_id:
            # Customer admins can filter by customer
            query = query.where(Deployment.customer_id == customer_id)

    # Additional filters
    if customer_id:
        query = query.where(Deployment.customer_id == customer_id)
    if vps_id:
        query = query.where(Deployment.vps_id == vps_id)
    if status_filter:
        query = query.where(Deployment.status == status_filter)

    # Order by deployed_at descending
    query = query.order_by(Deployment.deployed_at.desc())

    # Apply limit
    query = query.limit(limit)

    result = await db.execute(query)
    deployments = result.scalars().all()

    return deployments


@router.get("/{deployment_id}", response_model=DeploymentResponse)
async def get_deployment(
    deployment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get deployment details."""
    result = await db.execute(select(Deployment).where(Deployment.id == deployment_id))
    deployment = result.scalar_one_or_none()

    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        )

    # Check customer access
    if not check_customer_access(current_user.customer_id, deployment.customer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access this deployment",
        )

    return deployment


@router.post("/{deployment_id}/rollback", response_model=RollbackResponse)
async def rollback_deployment(
    deployment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Rollback to a previous deployment commit."""
    # Check permission
    require_permission(Permission.DEPLOYMENT_ROLLBACK)(lambda: None)

    result = await db.execute(select(Deployment).where(Deployment.id == deployment_id))
    deployment = result.scalar_one_or_none()

    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        )

    # Check customer access
    if not check_customer_access(current_user.customer_id, deployment.customer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot rollback this deployment",
        )

    # Perform rollback in Git
    git_manager = get_git_manager()
    previous_commit = git_manager.repo.head.commit.hexsha

    try:
        rollback_commit = git_manager.rollback_config(
            customer_id=deployment.customer_id,
            commit_hash=deployment.git_commit_hash,
            user_id=current_user.id,
        )

        return RollbackResponse(
            message="Rollback completed successfully",
            rollback_commit=rollback_commit,
            previous_commit=previous_commit,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Rollback failed: {str(e)}",
        )


@router.get("/vps/{vps_id}", response_model=List[DeploymentResponse])
async def get_vps_deployments(
    vps_id: int,
    limit: int = Field(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get deployment history for a specific VPS."""
    # Check permission
    require_permission(Permission.DEPLOYMENT_READ)(lambda: None)

    # Build query
    query = select(Deployment).where(Deployment.vps_id == vps_id)

    # Get VPS to check customer access
    from database import VPSServer
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
            detail="Cannot access this VPS's deployments",
        )

    # Order by deployed_at descending
    query = query.order_by(Deployment.deployed_at.desc())

    # Apply limit
    query = query.limit(limit)

    result = await db.execute(query)
    deployments = result.scalars().all()

    return deployments
