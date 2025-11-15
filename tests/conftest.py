"""
Pytest fixtures and configuration for DocuFlow tests.
Provides common test data, database setup, and mock objects.
"""
import pytest
import asyncio
import aiosqlite
import os
import sys
from pathlib import Path
from typing import Dict, Any
from datetime import datetime, timedelta
from jose import jwt

# Add root directory and backend directory to path
root_dir = Path(__file__).parent.parent
backend_dir = root_dir / "backend"
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(backend_dir))

from backend.config import settings
from backend.database import DB_PATH, init_database


# Test database path
TEST_DB_PATH = "test_docuflow.db"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def test_db():
    """
    Create a fresh test database for each test.
    Automatically cleaned up after test.
    """
    # Remove existing test database
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

    # Temporarily override DB_PATH
    import backend.database as db_module
    original_db_path = db_module.DB_PATH
    db_module.DB_PATH = TEST_DB_PATH

    # Initialize test database
    await init_database()

    yield TEST_DB_PATH

    # Cleanup
    db_module.DB_PATH = original_db_path
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


@pytest.fixture
def mock_auth0_token():
    """Generate a mock Auth0 JWT token for testing."""
    payload = {
        "sub": "auth0|test_user_123",
        "email": "test@example.com",
        "name": "Test User",
        "iss": f"https://{settings.auth0_domain}/",
        "aud": settings.auth0_audience,
        "iat": datetime.utcnow().timestamp(),
        "exp": (datetime.utcnow() + timedelta(hours=24)).timestamp()
    }

    # Note: This won't pass real validation, but good for testing token parsing
    token = jwt.encode(payload, "test-secret", algorithm="HS256")
    return token


@pytest.fixture
def sample_user_data():
    """Sample user data for testing."""
    return {
        "auth0_user_id": "auth0|test_user_123",
        "email": "test@example.com",
        "name": "Test User"
    }


@pytest.fixture
def sample_organization_data():
    """Sample organization data for testing."""
    return {
        "name": "Test Organization",
        "billing_email": "billing@testorg.com",
        "subscription_plan": "trial",
        "status": "active",
        "metadata": {"industry": "technology"}
    }


@pytest.fixture
async def created_user(test_db, sample_user_data):
    """Create a test user in the database."""
    from backend.database import create_user, get_user_by_auth0_id

    user_id = await create_user(
        auth0_user_id=sample_user_data["auth0_user_id"],
        email=sample_user_data["email"],
        name=sample_user_data["name"]
    )

    user = await get_user_by_auth0_id(sample_user_data["auth0_user_id"])
    return user


@pytest.fixture
async def created_organization(test_db, sample_organization_data):
    """Create a test organization in the database."""
    from backend.database import create_organization, get_organization

    org_id = await create_organization(
        name=sample_organization_data["name"],
        billing_email=sample_organization_data["billing_email"],
        subscription_plan=sample_organization_data["subscription_plan"],
        status=sample_organization_data["status"],
        metadata=sample_organization_data["metadata"]
    )

    org = await get_organization(org_id)
    return org


@pytest.fixture
async def user_with_organization(test_db, created_user, created_organization):
    """Create a user associated with an organization."""
    from backend.database import update_user_organization

    # Associate user with organization
    async with aiosqlite.connect(test_db) as db:
        await db.execute(
            "UPDATE users SET organization_id = ?, role = ? WHERE id = ?",
            (created_organization["id"], "owner", created_user["id"])
        )
        await db.commit()

    # Fetch updated user
    from backend.database import get_user_by_auth0_id
    user = await get_user_by_auth0_id(created_user["auth0_user_id"])

    return {
        "user": user,
        "organization": created_organization
    }


@pytest.fixture
def auth_headers(mock_auth0_token):
    """Create authorization headers for API requests."""
    return {
        "Authorization": f"Bearer {mock_auth0_token}"
    }


@pytest.fixture
def mock_auth0_user_info():
    """Mock Auth0 user info response."""
    return {
        "sub": "auth0|test_user_123",
        "email": "test@example.com",
        "email_verified": True,
        "name": "Test User",
        "picture": "https://example.com/avatar.jpg",
        "updated_at": "2024-01-15T10:00:00.000Z"
    }


@pytest.fixture
def multiple_users_data():
    """Generate multiple user data sets for testing."""
    return [
        {
            "auth0_user_id": f"auth0|user_{i}",
            "email": f"user{i}@example.com",
            "name": f"Test User {i}"
        }
        for i in range(1, 6)
    ]


@pytest.fixture
async def organization_with_multiple_users(test_db, created_organization, multiple_users_data):
    """Create an organization with multiple users."""
    from backend.database import create_user

    users = []
    for i, user_data in enumerate(multiple_users_data):
        user_id = await create_user(
            auth0_user_id=user_data["auth0_user_id"],
            email=user_data["email"],
            name=user_data["name"]
        )

        # Set role: first user is owner, second is admin, rest are members
        role = "owner" if i == 0 else ("admin" if i == 1 else "member")

        async with aiosqlite.connect(test_db) as db:
            await db.execute(
                "UPDATE users SET organization_id = ?, role = ? WHERE id = ?",
                (created_organization["id"], role, user_id)
            )
            await db.commit()

        from backend.database import get_user_by_auth0_id
        user = await get_user_by_auth0_id(user_data["auth0_user_id"])
        users.append(user)

    return {
        "organization": created_organization,
        "users": users
    }


@pytest.fixture
def sample_connector_config():
    """Sample connector configuration for testing."""
    return {
        "connector_type": "docuware",
        "config": {
            "base_url": "https://test.docuware.cloud",
            "username": "test_user",
            "password": "encrypted_password",
            "organization": "test_org"
        }
    }


@pytest.fixture
def sample_usage_log():
    """Sample usage log data for testing."""
    return {
        "action_type": "document_processed",
        "document_count": 5,
        "metadata": {
            "connector": "docuware",
            "category": "invoices"
        }
    }
