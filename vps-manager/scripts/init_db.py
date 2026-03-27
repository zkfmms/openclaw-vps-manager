#!/usr/bin/env python3
"""Database initialization script."""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import init_db, User, Customer, UserRole
from services.encryption import get_encryption_service
from config import get_settings


async def create_default_admin():
    """Create default admin user."""
    settings = get_settings()

    from database import AsyncSessionLocal
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        # Check if admin already exists
        result = await db.execute(select(User).where(User.email == "admin@openclaw.local"))
        admin = result.scalar_one_or_none()

        if admin:
            print("Admin user already exists")
            return

        # Create admin user
        from auth.middleware import get_password_hash

        admin = User(
            email="admin@openclaw.local",
            username="admin",
            hashed_password=get_password_hash("admin123"),  # Change this!
            role=UserRole.ADMIN,
            is_active=True,
        )

        db.add(admin)
        await db.commit()
        print("Admin user created successfully")
        print("  Email: admin@openclaw.local")
        print("  Password: admin123 (CHANGE THIS IMMEDIATELY!)")


async def main():
    """Main initialization function."""
    print("Initializing OpenClaw VPS Manager database...")

    # Create database tables
    await init_db()
    print("Database tables created")

    # Create default admin user
    await create_default_admin()

    # Initialize encryption key
    encryption = get_encryption_service()
    print("Encryption service initialized")

    print("\nInitialization complete!")
    print("\nNext steps:")
    print("1. Change the default admin password")
    print("2. Create TLS certificates for mTLS (if enabled)")
    print("3. Configure Git repository URL")
    print("4. Start the API server")


if __name__ == "__main__":
    asyncio.run(main())
