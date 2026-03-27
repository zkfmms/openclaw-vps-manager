"""VPS management API endpoints."""
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from pydantic import BaseModel, Field

from database import get_db, VPSServer, VPSStatus, Deployment, DeploymentStatus
from services.git_manager import GitManager
from auth.middleware import get_current_user
from auth.rbac import require_permission, Permission, check_customer_access
from services.ssh_manager import get_ssh_pool, SSHKeyManager
from services.openclaw_manager import get_openclaw_manager
from config import get_settings
from models import User

router = APIRouter(prefix="/vps", tags=["VPS Management"])
settings = get_settings()


# Pydantic models
class VPSCreate(BaseModel):
    """Request model for creating a new VPS."""
    customer_id: int = Field(..., description="Customer ID")
    hostname: str = Field(..., description="VPS hostname or IP")
    ssh_user: str = Field(default="openclaw", description="SSH username")
    openclaw_version: str = Field(default="latest", description="OpenClaw version")


class VPSUpdate(BaseModel):
    """Request model for updating a VPS."""
    openclaw_version: Optional[str] = None
    status: Optional[VPSStatus] = None


class VPSResponse(BaseModel):
    """Response model for VPS."""
    id: int
    customer_id: int
    hostname: str
    ssh_user: str
    openclaw_version: str
    status: VPSStatus
    last_health_check: Optional[datetime]
    last_deployment_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class HealthCheckResponse(BaseModel):
    """Response model for health check."""
    vps_id: int
    service_active: bool
    process_running: bool
    version: str
    config_exists: bool
    timestamp: str


class DeploymentResponse(BaseModel):
    """Response model for deployment."""
    id: int
    vps_id: int
    customer_id: int
    git_commit_hash: str
    deployed_at: datetime
    status: DeploymentStatus
    rollback_commit: Optional[str]
    error_message: Optional[str]

    class Config:
        from_attributes = True


@router.post("", response_model=VPSResponse, status_code=status.HTTP_201_CREATED)
async def create_vps(
    vps_data: VPSCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new VPS server."""
    # Check permission
    require_permission(Permission.VPS_CREATE)(lambda: None)

    # Check customer access
    if not check_customer_access(current_user.customer_id, vps_data.customer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access this customer's resources",
        )

    # Generate SSH key pair for this VPS
    ssh_key_manager = SSHKeyManager()
    private_key_path, public_key_path = ssh_key_manager.generate_keypair(
        key_type=settings.ssh_key_type,
        passphrase=settings.ssh_key_passphrase,
    )

    # Create VPS record
    vps = VPSServer(
        customer_id=vps_data.customer_id,
        hostname=vps_data.hostname,
        ssh_user=vps_data.ssh_user,
        ssh_key_path=str(private_key_path),
        openclaw_version=vps_data.openclaw_version,
        status=VPSStatus.PENDING,
    )

    db.add(vps)
    await db.commit()
    await db.refresh(vps)

    # Rename key files to use VPS ID
    new_private_key_path = settings.get_ssh_key_path(vps.id)
    new_public_key_path = Path(str(new_private_key_path) + ".pub")

    private_key_path.rename(new_private_key_path)
    public_key_path.rename(new_public_key_path)

    # Update database with new paths
    vps.ssh_key_path = str(new_private_key_path)
    await db.commit()

    return vps


@router.get("", response_model=List[VPSResponse])
async def list_vps(
    customer_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List VPS servers (filtered by customer and role)."""
    # Build query
    query = select(VPSServer)

    # Filter by customer access
    if current_user.role.value != "admin":
        if current_user.customer_id:
            query = query.where(VPSServer.customer_id == current_user.customer_id)
        elif customer_id:
            # Customer admins can only see their own VPSes
            query = query.where(VPSServer.customer_id == customer_id)
    else:
        # Admins can filter by customer
        if customer_id:
            query = query.where(VPSServer.customer_id == customer_id)

    result = await db.execute(query)
    vps_list = result.scalars().all()

    return vps_list


@router.get("/{vps_id}", response_model=VPSResponse)
async def get_vps(
    vps_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get VPS details."""
    result = await db.execute(select(VPSServer).where(VPSServer.id == vps_id))
    vps = result.scalar_one_or_none()

    if not vps:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPS not found",
        )

    # Check customer access
    if not check_customer_access(current_user.customer_id, vps.customer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access this customer's resources",
        )

    return vps


@router.put("/{vps_id}", response_model=VPSResponse)
async def update_vps(
    vps_id: int,
    vps_data: VPSUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update VPS configuration."""
    result = await db.execute(select(VPSServer).where(VPSServer.id == vps_id))
    vps = result.scalar_one_or_none()

    if not vps:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPS not found",
        )

    # Check customer access
    if not check_customer_access(current_user.customer_id, vps.customer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access this customer's resources",
        )

    # Update fields
    update_data = vps_data.model_dump(exclude_unset=True)
    if update_data:
        await db.execute(
            update(VPSServer)
            .where(VPSServer.id == vps_id)
            .values(**update_data)
        )
        await db.commit()
        await db.refresh(vps)

    return vps


@router.delete("/{vps_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vps(
    vps_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete VPS server."""
    result = await db.execute(select(VPSServer).where(VPSServer.id == vps_id))
    vps = result.scalar_one_or_none()

    if not vps:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPS not found",
        )

    # Check customer access
    if not check_customer_access(current_user.customer_id, vps.customer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access this customer's resources",
        )

    # Delete VPS (cascade will delete related records)
    await db.execute(delete(VPSServer).where(VPSServer.id == vps_id))
    await db.commit()

    return None


@router.post("/{vps_id}/deploy", response_model=DeploymentResponse)
async def deploy_vps(
    vps_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Deploy configuration to VPS."""
    result = await db.execute(select(VPSServer).where(VPSServer.id == vps_id))
    vps = result.scalar_one_or_none()

    if not vps:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPS not found",
        )

    # Check customer access
    if not check_customer_access(current_user.customer_id, vps.customer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access this customer's resources",
        )

    # Create deployment record
    deployment = Deployment(
        vps_id=vps.id,
        customer_id=vps.customer_id,
        git_commit_hash="",  # Will be updated after sync
        deployed_by=current_user.id,
        status=DeploymentStatus.IN_PROGRESS,
    )

    db.add(deployment)
    await db.commit()
    await db.refresh(deployment)

    # Sync configuration
    openclaw_manager = get_openclaw_manager()
    try:
        result = await openclaw_manager.sync_config(
            hostname=vps.hostname,
            username=vps.ssh_user,
            key_path=Path(vps.ssh_key_path),
            customer_id=vps.customer_id,
            port=22,
        )

        if result.exit_code != 0:
            raise Exception(f"Deployment failed: {result.stderr}")

        # Get current commit hash
        from services.git_manager import get_git_manager
        git_manager = get_git_manager()
        commit_hash = git_manager.repo.head.commit.hexsha

        # Update deployment record
        deployment.git_commit_hash = commit_hash
        deployment.status = DeploymentStatus.SUCCESS

        # Update VPS
        vps.last_deployment_at = datetime.utcnow()
        vps.status = VPSStatus.ACTIVE

        await db.commit()

    except Exception as e:
        # Update deployment record with error
        deployment.status = DeploymentStatus.FAILED
        deployment.error_message = str(e)
        vps.status = VPSStatus.ERROR
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Deployment failed: {str(e)}",
        )

    return deployment


@router.post("/{vps_id}/restart", status_code=status.HTTP_204_NO_CONTENT)
async def restart_vps(
    vps_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Restart OpenClaw service on VPS."""
    result = await db.execute(select(VPSServer).where(VPSServer.id == vps_id))
    vps = result.scalar_one_or_none()

    if not vps:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPS not found",
        )

    # Check customer access
    if not check_customer_access(current_user.customer_id, vps.customer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access this customer's resources",
        )

    # Restart service
    openclaw_manager = get_openclaw_manager()
    result = await openclaw_manager.restart_service(
        hostname=vps.hostname,
        username=vps.ssh_user,
        key_path=Path(vps.ssh_key_path),
        port=22,
    )

    if result.exit_code != 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Restart failed: {result.stderr}",
        )

    return None


@router.get("/{vps_id}/health", response_model=HealthCheckResponse)
async def health_check_vps(
    vps_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Perform health check on VPS."""
    result = await db.execute(select(VPSServer).where(VPSServer.id == vps_id))
    vps = result.scalar_one_or_none()

    if not vps:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPS not found",
        )

    # Check customer access
    if not check_customer_access(current_user.customer_id, vps.customer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access this customer's resources",
        )

    # Perform health check
    openclaw_manager = get_openclaw_manager()
    health = await openclaw_manager.health_check(
        hostname=vps.hostname,
        username=vps.ssh_user,
        key_path=Path(vps.ssh_key_path),
        port=22,
    )

    # Update VPS health check time
    vps.last_health_check = datetime.utcnow()
    await db.commit()

    return HealthCheckResponse(
        vps_id=vps.id,
        **health,
        timestamp=health.get("timestamp", ""),
    )


class ImportConfigResponse(BaseModel):
    """Response model for config import."""
    vps_id: int
    success: bool
    config: Optional[dict] = None
    error: Optional[str] = None
    warnings: List[str] = []
    metadata: Optional[dict] = None


@router.get("/{vps_id}/import-config", response_model=ImportConfigResponse)
async def import_config_vps(
    vps_id: int,
    save_to_git: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Import OpenClaw configuration from existing VPS instance.

    This reads the OpenClaw configuration file from the VPS and optionally
    saves it to the Git repository for central management.

    Args:
        vps_id: VPS server ID.
        save_to_git: If True, save imported config to Git repository.

    Returns:
        Imported configuration and status.
    """
    # Get VPS
    result = await db.execute(select(VPSServer).where(VPSServer.id == vps_id))
    vps = result.scalar_one_or_none()

    if not vps:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPS not found",
        )

    # Check customer access
    if not check_customer_access(current_user.customer_id, vps.customer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access this customer's resources",
        )

    # Import configuration from VPS
    openclaw_manager = get_openclaw_manager()
    import_result = await openclaw_manager.import_config(
        hostname=vps.hostname,
        username=vps.ssh_user,
        key_path=Path(vps.ssh_key_path),
        port=22,
    )

    if not import_result["success"]:
        return ImportConfigResponse(
            vps_id=vps.id,
            success=False,
            error=import_result.get("error"),
            warnings=import_result.get("warnings", []),
        )

    # Optionally save to Git
    if save_to_git:
        try:
            from services.git_manager import get_git_manager
            from services.logging import log_audit_event

            # Get global Git manager instance
            git_manager = get_git_manager()

            # Update VPS config in VPS-specific directory
            commit_hash = git_manager.update_vps_config(
                config=import_result["config"],
                user_id=current_user.id,
                vps_id=vps_id,
                commit_message=f"Import config from VPS {vps.hostname}",
            )

            # Log audit event
            log_audit_event(
                user_id=current_user.id,
                action="import_config",
                resource_type="vps",
                resource_id=vps_id,
                details={
                    "hostname": vps.hostname,
                    "commit_hash": commit_hash,
                    "save_to_git": True,
                },
            )

        except Exception as e:
            # Continue even if Git save fails
            import_result["warnings"].append(f"Failed to save to Git: {str(e)}")

    return ImportConfigResponse(
        vps_id=vps.id,
        success=import_result["success"],
        config=import_result.get("config"),
        error=import_result.get("error"),
        warnings=import_result.get("warnings", []),
        metadata=import_result.get("metadata"),
    )
