"""
Tests for authentication and user management.
Tests token validation, user creation, and authorization.
"""
import pytest
from datetime import datetime, timedelta
from jose import jwt

from backend.auth import verify_token, AuthError
from backend.database import (
    create_user,
    get_user_by_auth0_id,
    get_user_by_email,
    update_last_login
)


class TestUserManagement:
    """Test user CRUD operations."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_user(self, test_db, sample_user_data):
        """Test creating a new user."""
        user_id = await create_user(
            auth0_user_id=sample_user_data["auth0_user_id"],
            email=sample_user_data["email"],
            name=sample_user_data["name"]
        )

        assert user_id is not None
        assert isinstance(user_id, int)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_user_by_auth0_id(self, test_db, created_user):
        """Test retrieving user by Auth0 ID."""
        user = created_user

        assert user is not None
        assert user["auth0_user_id"] == "auth0|test_user_123"
        assert user["email"] == "test@example.com"
        assert user["name"] == "Test User"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_user_by_email(self, test_db, created_user):
        """Test retrieving user by email."""
        user = await get_user_by_email("test@example.com")

        assert user is not None
        assert user["email"] == "test@example.com"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_nonexistent_user(self, test_db):
        """Test that getting nonexistent user returns None."""
        user = await get_user_by_auth0_id("auth0|nonexistent")

        assert user is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_duplicate_email(self, test_db, sample_user_data):
        """Test that creating user with duplicate email fails."""
        # Create first user
        await create_user(
            auth0_user_id=sample_user_data["auth0_user_id"],
            email=sample_user_data["email"],
            name=sample_user_data["name"]
        )

        # Try to create second user with same email
        with pytest.raises(Exception):  # Should raise unique constraint error
            await create_user(
                auth0_user_id="auth0|different_user",
                email=sample_user_data["email"],  # Same email
                name="Different User"
            )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_update_last_login(self, test_db, created_user):
        """Test updating user's last login timestamp."""
        user_id = created_user["id"]
        original_last_login = created_user["last_login"]

        # Update last login
        await update_last_login(user_id)

        # Fetch user again
        user = await get_user_by_auth0_id(created_user["auth0_user_id"])

        # last_login should be updated
        assert user["last_login"] != original_last_login


class TestUserOrganizationRelationship:
    """Test user-organization relationships."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_user_without_organization(self, test_db, created_user):
        """Test that new user has no organization."""
        assert created_user["organization_id"] is None
        assert created_user["role"] == "member"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_user_with_organization(self, test_db, user_with_organization):
        """Test user associated with organization."""
        user = user_with_organization["user"]
        org = user_with_organization["organization"]

        assert user["organization_id"] == org["id"]
        assert user["role"] == "owner"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_multiple_users_same_organization(self, test_db, organization_with_multiple_users):
        """Test multiple users in same organization with different roles."""
        org = organization_with_multiple_users["organization"]
        users = organization_with_multiple_users["users"]

        assert len(users) == 5

        # Check roles
        assert users[0]["role"] == "owner"
        assert users[1]["role"] == "admin"
        assert users[2]["role"] == "member"

        # Check all belong to same org
        for user in users:
            assert user["organization_id"] == org["id"]


class TestTokenValidation:
    """Test JWT token validation (Note: These tests require proper Auth0 setup)."""

    @pytest.mark.unit
    def test_mock_token_structure(self, mock_auth0_token):
        """Test that mock token has correct structure."""
        # Decode without verification (for testing structure)
        payload = jwt.decode(mock_auth0_token, options={"verify_signature": False})

        assert "sub" in payload
        assert "email" in payload
        assert "iss" in payload
        assert "aud" in payload

    @pytest.mark.unit
    def test_invalid_token_raises_error(self):
        """Test that invalid token raises AuthError."""
        with pytest.raises(Exception):  # Will raise JWTError
            verify_token("invalid.token.here")


class TestAuthenticationFlow:
    """Test complete authentication flows."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_first_time_login_creates_user(self, test_db):
        """Test that first-time login creates a new user."""
        auth0_user_id = "auth0|new_user_123"

        # Verify user doesn't exist
        user = await get_user_by_auth0_id(auth0_user_id)
        assert user is None

        # Simulate first login (create user)
        user_id = await create_user(
            auth0_user_id=auth0_user_id,
            email="newuser@example.com",
            name="New User"
        )

        # Verify user was created
        user = await get_user_by_auth0_id(auth0_user_id)
        assert user is not None
        assert user["email"] == "newuser@example.com"
        assert user["organization_id"] is None  # No org yet

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_returning_user_login(self, test_db, created_user):
        """Test that returning user login updates last_login."""
        original_last_login = created_user["last_login"]

        # Simulate login (update last_login)
        await update_last_login(created_user["id"])

        # Fetch user again
        user = await get_user_by_auth0_id(created_user["auth0_user_id"])

        # last_login should be updated
        assert user["last_login"] != original_last_login

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_user_needs_onboarding(self, test_db, created_user):
        """Test identifying user that needs onboarding."""
        # User without organization needs onboarding
        needs_onboarding = created_user["organization_id"] is None

        assert needs_onboarding is True

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_user_completed_onboarding(self, test_db, user_with_organization):
        """Test identifying user that completed onboarding."""
        user = user_with_organization["user"]

        # User with organization doesn't need onboarding
        needs_onboarding = user["organization_id"] is None

        assert needs_onboarding is False
