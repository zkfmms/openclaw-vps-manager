"""API tests for VPS Manager."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from main import app
from database import get_db
from auth.middleware import get_password_hash


client = TestClient(app)


class MockAuth:
    """Mock authentication for testing."""

    @staticmethod
    def get_auth_headers():
        """Get mock authentication headers."""
        # In production, this would use JWT tokens
        return {
            "Authorization": "Bearer mock-token-for-testing",
        }


@pytest.fixture
async def db_session():
    """Fixture for database session."""
    from database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def test_user(db_session: AsyncSession):
    """Fixture for test user."""
    from database import User, UserRole

    user = User(
        email="test@example.com",
        username="testuser",
        hashed_password=get_password_hash("testpass"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_customer(db_session: AsyncSession):
    """Fixture for test customer."""
    from database import Customer
    from services.encryption import get_encryption_service

    encryption = get_encryption_service()
    customer_key = encryption.generate_customer_key(999)
    encryption_key_hash = encryption.hash_key(customer_key)

    customer = Customer(
        name="Test Customer",
        description="A test customer",
        git_branch="customer-999",
        encryption_key_hash=encryption_key_hash,
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    return customer


def test_health_check():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "service" in data


def test_api_info():
    """Test API info endpoint."""
    response = client.get("/api/v1")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "endpoints" in data


# Note: These tests would require proper auth middleware mocking
# and database setup to work fully

# async def test_create_customer(db_session: AsyncSession, test_user):
#     """Test creating a customer."""
#     # This test requires auth setup and database initialization
#     pass


# async def test_list_vps(db_session: AsyncSession, test_user, test_customer):
#     """Test listing VPS servers."""
#     # This test requires auth setup and database initialization
#     pass


if __name__ == "__main__":
    # Run basic tests
    test_health_check()
    test_api_info()
    print("Basic tests passed!")
