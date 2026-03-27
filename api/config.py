"""Configuration management API endpoints."""
from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field

from database import get_db, Customer
from auth.middleware import get_current_user
from auth.rbac import require_permission, Permission, check_customer_access
from services.git_manager import get_git_manager
from models import User

router = APIRouter(prefix="/config", tags=["Configuration Management"])


# Pydantic models
class SkillConfig(BaseModel):
    """Skill configuration model."""
    skill_name: str = Field(..., description="Skill name")
    enabled: bool = Field(default=True, description="Whether skill is enabled")
    config: Dict[str, Any] = Field(default_factory=dict, description="Skill-specific config")


class ConfigHistoryItem(BaseModel):
    """Configuration history item."""
    hash: str
    message: str
    author: str
    timestamp: str


@router.get("/{customer_id}")
async def get_customer_config(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get customer's OpenClaw configuration."""
    # Check permission
    require_permission(Permission.CONFIG_READ)(lambda: None)

    # Verify customer exists and access
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    # Check customer access
    if not check_customer_access(current_user.customer_id, customer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access this customer's resources",
        )

    # Get configuration from Git
    git_manager = get_git_manager()
    config = git_manager.get_customer_config(customer_id)

    return config


@router.put("/{customer_id}")
async def update_customer_config(
    customer_id: int,
    config: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, str]:
    """Update customer's OpenClaw configuration."""
    # Check permission
    require_permission(Permission.CONFIG_UPDATE)(lambda: None)

    # Verify customer exists and access
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    # Check customer access
    if not check_customer_access(current_user.customer_id, customer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access this customer's resources",
        )

    # Update configuration in Git
    git_manager = get_git_manager()
    commit_hash = git_manager.update_customer_config(
        customer_id=customer_id,
        config=config,
        user_id=current_user.id,
    )

    return {
        "message": "Configuration updated successfully",
        "commit_hash": commit_hash,
    }


@router.post("/{customer_id}/skills")
async def manage_skill(
    customer_id: int,
    skill_config: SkillConfig,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, str]:
    """Enable or disable a skill for a customer."""
    # Check permission
    require_permission(Permission.CONFIG_UPDATE)(lambda: None)

    # Verify customer exists and access
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    # Check customer access
    if not check_customer_access(current_user.customer_id, customer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access this customer's resources",
        )

    # Get current configuration
    git_manager = get_git_manager()
    current_config = git_manager.get_customer_config(customer_id)

    # Update skill in configuration
    if "skills" not in current_config:
        current_config["skills"] = {"entries": {}}

    if skill_config.enabled:
        current_config["skills"]["entries"][skill_config.skill_name] = skill_config.config
    else:
        current_config["skills"]["entries"].pop(skill_config.skill_name, None)

    # Save updated configuration
    git_manager.update_customer_config(
        customer_id=customer_id,
        config=current_config,
        user_id=current_user.id,
    )

    # Also save as separate skill file
    skill_config_data = {
        "enabled": skill_config.enabled,
        "config": skill_config.config,
    }

    git_manager.update_skill_config(
        customer_id=customer_id,
        skill_name=skill_config.skill_name,
        skill_config=skill_config_data,
        user_id=current_user.id,
    )

    return {
        "message": f"Skill '{skill_config.skill_name}' {'enabled' if skill_config.enabled else 'disabled'} successfully",
        "skill_name": skill_config.skill_name,
        "enabled": skill_config.enabled,
    }


@router.get("/{customer_id}/skills")
async def list_skills(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[str]:
    """List enabled skills for a customer."""
    # Check permission
    require_permission(Permission.CONFIG_READ)(lambda: None)

    # Verify customer exists and access
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    # Check customer access
    if not check_customer_access(current_user.customer_id, customer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access this customer's resources",
        )

    # Get configuration
    git_manager = get_git_manager()
    config = git_manager.get_customer_config(customer_id)

    # Extract enabled skills
    skills = list(config.get("skills", {}).get("entries", {}).keys())

    return skills


@router.get("/{customer_id}/history", response_model=List[ConfigHistoryItem])
async def get_config_history(
    customer_id: int,
    limit: int = Field(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get configuration change history for a customer."""
    # Check permission
    require_permission(Permission.CONFIG_HISTORY)(lambda: None)

    # Verify customer exists and access
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    # Check customer access
    if not check_customer_access(current_user.customer_id, customer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access this customer's resources",
        )

    # Get history from Git
    git_manager = get_git_manager()
    history = git_manager.get_config_history(customer_id, limit)

    return [
        ConfigHistoryItem(
            hash=item["hash"],
            message=item["message"],
            author=item["author"],
            timestamp=item["timestamp"],
        )
        for item in history
    ]
