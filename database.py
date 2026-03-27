"""Database models and connection management."""
from datetime import datetime
from typing import Optional
from enum import Enum

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

from config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


class UserRole(str, Enum):
    """User role enumeration."""
    ADMIN = "admin"
    OPERATOR = "operator"
    AUDITOR = "auditor"
    CUSTOMER_ADMIN = "customer_admin"


class VPSStatus(str, Enum):
    """VPS server status."""
    PENDING = "pending"
    ACTIVE = "active"
    MAINTENANCE = "maintenance"
    ERROR = "error"


class VPSGitSyncStatus(str, Enum):
    """VPS Git synchronization status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    CONFLICT = "conflict"
    SYNCED = "synced"
    DECOMMISSIONED = "decommissioned"


class DeploymentStatus(str, Enum):
    """Deployment status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class User(Base):
    """User model for authentication and authorization."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(String(20), default=UserRole.CUSTOMER_ADMIN)
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = relationship("Customer", back_populates="users")


class Customer(Base):
    """Customer model representing a customer organization."""
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    git_branch: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    encryption_key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    users = relationship("User", back_populates="customer", cascade="all, delete-orphan")
    vps_servers = relationship("VPSServer", back_populates="customer", cascade="all, delete-orphan")
    deployments = relationship("Deployment", back_populates="customer", cascade="all, delete-orphan")


class VPSServer(Base):
    """VPS server model representing a managed server."""
    __tablename__ = "vps_servers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ssh_user: Mapped[str] = mapped_column(String(100), default="openclaw")
    ssh_key_path: Mapped[str] = mapped_column(String(500), nullable=False)
    openclaw_version: Mapped[str] = mapped_column(String(50), default="latest")
    status: Mapped[VPSStatus] = mapped_column(String(20), default=VPSStatus.PENDING)
    last_health_check: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_deployment_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = relationship("Customer", back_populates="vps_servers")
    deployments = relationship("Deployment", back_populates="vps", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="vps", cascade="all, delete-orphan")
    sync_records = relationship("VPSGitSync", back_populates="vps", cascade="all, delete-orphan")


class Deployment(Base):
    """Deployment model tracking configuration deployments."""
    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    vps_id: Mapped[int] = mapped_column(ForeignKey("vps_servers.id"), nullable=False, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    git_commit_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    deployed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    status: Mapped[DeploymentStatus] = mapped_column(String(20), default=DeploymentStatus.PENDING)
    rollback_commit: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deployed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    vps = relationship("VPSServer", back_populates="deployments")
    customer = relationship("Customer", back_populates="deployments")
    deployer = relationship("User")


class AuditLog(Base):
    """Audit log model for tracking all administrative actions."""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    vps_id: Mapped[Optional[int]] = mapped_column(ForeignKey("vps_servers.id"), nullable=True, index=True)
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(Text, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    user = relationship("User")
    vps = relationship("VPSServer", back_populates="audit_logs")


# Database engine and session
async_engine = create_async_engine(
    settings.database_url.replace("postgresql://", "postgresql+asyncpg://"),
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """Dependency to get database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Initialize database tables."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


class VPSGitSync(Base):
    """VPS Git synchronization tracking model."""
    __tablename__ = "vps_git_sync"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    vps_id: Mapped[int] = mapped_column(ForeignKey("vps_servers.id"), nullable=False, index=True)
    last_sync_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    sync_status: Mapped[VPSGitSyncStatus] = mapped_column(String(20), default=VPSGitSyncStatus.PENDING, nullable=False, index=True)
    local_commit: Mapped[str] = mapped_column(String(64), nullable=True)
    remote_commit: Mapped[str] = mapped_column(String(64), nullable=True)
    conflict_details: Mapped[Optional[dict]] = mapped_column(Text, nullable=True)
    sync_type: Mapped[str] = mapped_column(String(20), default="auto", nullable=False)  # auto, manual, force
    initiated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    vps = relationship("VPSServer", back_populates="sync_records")
    initiator = relationship("User")


# Add sync_records relationship to VPSServer
# This needs to be added after VPSServer class definition
