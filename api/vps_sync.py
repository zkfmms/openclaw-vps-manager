"""VPS synchronization API endpoints."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field

from database import get_db, VPSGitSync, VPSServer
from auth.middleware import get_current_user
from auth.rbac import check_permission, Permission, check_customer_access
from services.vps_sync_manager import get_vps_sync_manager
from models import User

router = APIRouter(prefix="/sync", tags=["VPS Synchronization"])


# Pydantic models
class SyncRequest(BaseModel):
    """Request model for VPS synchronization."""
    direction: str = Field(default="both", description="Sync direction: push, pull, or both")
    force: bool = Field(default=False, description="Force sync without conflict detection")


class SyncStatusResponse(BaseModel):
    """Response model for sync status."""
    sync_id: int
    status: str
    message: str
    local_commit: Optional[str]
    remote_commit: Optional[str]
    conflicts: Optional[dict]
    created_at: str


class ConflictResolutionRequest(BaseModel):
    """Request model for conflict resolution."""
    resolution: str = Field(..., description="Resolution: local, remote, merge, or manual")
    manual_content: Optional[str] = Field(None, description="Manual merge content if resolution=manual")


@router.post("/vps/{vps_id}/sync")
async def sync_vps(
    vps_id: int,
    request: SyncRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Synchronize with VPS (bidirectional Git sync).

    This performs a two-way sync between the central Git repository and the VPS's local Git repository.
    Conflicts are detected and must be resolved before the sync can complete.
    """
    # Check permission
    require_permission(Permission.VPS_DEPLOY)(lambda: None)

    # Get VPS
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
            detail="Cannot access this VPS",
        )

    # Perform sync
    sync_manager = get_vps_sync_manager()
    result = await sync_manager.sync_vps(
        vps_id=vps_id,
        db=db,
        direction=request.direction,
        force=request.force,
        user_id=current_user.id,
    )

    return result


@router.get("/vps/{vps_id}/status")
async def get_sync_status(
    vps_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get current synchronization status for a VPS.

    Returns information about the most recent sync operation including:
    - Status (pending, in_progress, success, failed, conflict)
    - Last sync timestamp
    - Local and remote commit hashes
    - Any conflict details
    """
    # Get VPS
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
            detail="Cannot access this VPS",
        )

    # Get sync status
    sync_manager = get_vps_sync_manager()
    status = await sync_manager.get_sync_status(vps_id, db)

    if status is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No sync records found for this VPS",
        )

    return status


@router.post("/vps/{vps_id}/resolve-conflict")
async def resolve_sync_conflict(
    vps_id: int,
    request: ConflictResolutionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Resolve a merge conflict during synchronization.

    Resolution strategies:
    - local: Keep local (central) changes, reject VPS changes
    - remote: Keep VPS changes, reject local (central) changes
    - merge: Attempt automated merge (may require manual intervention)
    - manual: Provide manual merge content
    """
    # Get VPS
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
            detail="Cannot access this VPS",
        )

    # Get latest sync record
    sync_result = await db.execute(
        select(VPSGitSync)
        .where(VPSGitSync.vps_id == vps_id)
        .order_by(VPSGitSync.created_at.desc())
    )
    sync_record = sync_result.scalar_one_or_none()

    if not sync_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending conflict found for this VPS",
        )

    if sync_record.sync_status != "conflict":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No conflict to resolve",
        )

    # Resolve conflict
    sync_manager = get_vps_sync_manager()
    resolved = await sync_manager.resolve_conflict(sync_record.id, request.resolution, db)

    if not resolved:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resolve conflict",
        )

    return {
        "message": "Conflict resolved successfully",
        "resolution": request.resolution,
        "sync_id": sync_record.id,
    }


@router.get("/vps/{vps_id}/history")
async def get_sync_history(
    vps_id: int,
    limit: int = Field(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[dict]:
    """
    Get synchronization history for a VPS.

    Returns a list of past sync operations including:
    - Sync status
    - Direction (auto/manual)
    - Commit hashes
    - Timestamps
    - Any conflicts
    """
    # Get VPS
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
            detail="Cannot access this VPS",
        )

    # Get sync history
    sync_manager = get_vps_sync_manager()
    history = await sync_manager.get_sync_history(vps_id, db, limit)

    return history


@router.post("/vps/{vps_id}/force")
async def force_sync_vps(
    vps_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Force synchronization with VPS, skipping conflict detection.

    This will overwrite VPS changes with central repository changes.
    Use with caution as it may result in data loss.
    """
    # Check permission
    require_permission(Permission.VPS_DEPLOY)(lambda: None)

    # Get VPS
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
            detail="Cannot access this VPS",
        )

    # Perform forced sync
    sync_manager = get_vps_sync_manager()
    result = await sync_manager.sync_vps(
        vps_id=vps_id,
        db=db,
        direction="both",
        force=True,
        user_id=current_user.id,
    )

    return result


@router.get("/vps/{vps_id}/compare")
async def compare_repos(
    vps_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Compare local (central) and VPS Git repositories.

    Returns differences between the two repositories to help identify
    what changes would be merged.
    """
    # Get VPS
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
            detail="Cannot access this VPS",
        )

    # Get current commits
    sync_manager = get_vps_sync_manager()
    sync_status = await sync_manager.get_sync_status(vps_id, db)

    if sync_status:
        return {
            "vps_id": vps_id,
            "local_commit": sync_status.get("local_commit"),
            "remote_commit": sync_status.get("remote_commit"),
            "are_different": sync_status.get("local_commit") != sync_status.get("remote_commit"),
            "last_sync": sync_status.get("last_sync_at"),
        }
    else:
        return {
            "vps_id": vps_id,
            "message": "No sync history found",
        }
