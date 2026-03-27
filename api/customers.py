"""Customer management API endpoints."""
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from pydantic import BaseModel, Field

from database import get_db, Customer
from auth.middleware import get_current_user
from auth.rbac import require_permission, Permission, check_customer_access
from services.git_manager import get_git_manager
from services.encryption import get_encryption_service
from config import get_settings
from models import User

router = APIRouter(prefix="/customers", tags=["Customer Management"])
settings = get_settings()


# Pydantic models
class CustomerCreate(BaseModel):
    """Request model for creating a new customer."""
    name: str = Field(..., description="Customer name")
    description: Optional[str] = Field(None, description="Customer description")


class CustomerUpdate(BaseModel):
    """Request model for updating a customer."""
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class CustomerResponse(BaseModel):
    """Response model for customer."""
    id: int
    name: str
    description: Optional[str]
    git_branch: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    customer_data: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new customer."""
    # Check permission
    require_permission(Permission.CUSTOMER_CREATE)(lambda: None)

    # Create Git branch for customer
    git_manager = get_git_manager()

    # We need to generate customer ID first, so we'll use a temporary placeholder
    # and update after database insert
    temp_customer_id = 0  # Will be updated
    git_branch = settings.get_customer_branch(temp_customer_id)

    # Generate encryption key for customer
    encryption = get_encryption_service()
    customer_key = encryption.generate_customer_key(temp_customer_id)
    encryption_key_hash = encryption.hash_key(customer_key)

    # Create customer record
    customer = Customer(
        name=customer_data.name,
        description=customer_data.description,
        git_branch=git_branch,
        encryption_key_hash=encryption_key_hash,
    )

    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    # Update git branch with actual customer ID
    customer.git_branch = settings.get_customer_branch(customer.id)

    # Generate proper encryption key with actual ID
    customer_key = encryption.generate_customer_key(customer.id)
    customer.encryption_key_hash = encryption.hash_key(customer_key)

    await db.commit()

    # Create Git branch
    git_manager.create_customer_branch(customer.id, customer.name)

    return customer


@router.get("", response_model=List[CustomerResponse])
async def list_customers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List customers (filtered by role)."""
    # Build query
    query = select(Customer)

    # Filter by customer access
    if current_user.role.value != "admin":
        if current_user.customer_id:
            # Customer admins can only see their own customer
            query = query.where(Customer.id == current_user.customer_id)

    result = await db.execute(query)
    customers = result.scalars().all()

    return customers


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get customer details."""
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

    return customer


@router.put("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: int,
    customer_data: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update customer."""
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

    # Update fields
    update_data = customer_data.model_dump(exclude_unset=True)
    if update_data:
        await db.execute(
            update(Customer)
            .where(Customer.id == customer_id)
            .values(**update_data)
        )
        await db.commit()
        await db.refresh(customer)

    return customer


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete customer."""
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

    # Delete customer (cascade will delete related records)
    await db.execute(delete(Customer).where(Customer.id == customer_id))
    await db.commit()

    return None
