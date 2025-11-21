"""
Tests for organization management.
Tests CRUD operations, subscriptions, settings, and usage tracking.
"""
import pytest
from datetime import datetime

from backend.database import (
    create_organization,
    get_organization,
    update_organization,
    get_organization_by_user,
    get_organization_users,
    save_organization_setting,
    get_organization_setting,
    create_subscription,
    get_subscription,
    log_usage,
    get_usage_stats
)


class TestOrganizationCRUD:
    """Test organization CRUD operations."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_organization(self, test_db, sample_organization_data):
        """Test creating a new organization."""
        org_id = await create_organization(
            name=sample_organization_data["name"],
            billing_email=sample_organization_data["billing_email"],
            subscription_plan=sample_organization_data["subscription_plan"],
            status=sample_organization_data["status"],
            metadata=sample_organization_data["metadata"]
        )

        assert org_id is not None
        assert isinstance(org_id, int)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_organization(self, test_db, created_organization):
        """Test retrieving organization by ID."""
        org = created_organization

        assert org is not None
        assert org["name"] == "Test Organization"
        assert org["billing_email"] == "billing@testorg.com"
        assert org["subscription_plan"] == "trial"
        assert org["status"] == "active"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_update_organization(self, test_db, created_organization):
        """Test updating organization details."""
        org_id = created_organization["id"]

        # Update organization
        await update_organization(
            org_id=org_id,
            name="Updated Organization Name",
            billing_email="new-billing@testorg.com"
        )

        # Fetch updated organization
        org = await get_organization(org_id)

        assert org["name"] == "Updated Organization Name"
        assert org["billing_email"] == "new-billing@testorg.com"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_organization_by_user(self, test_db, user_with_organization):
        """Test getting organization through user relationship."""
        user = user_with_organization["user"]
        expected_org = user_with_organization["organization"]

        org = await get_organization_by_user(user["id"])

        assert org is not None
        assert org["id"] == expected_org["id"]
        assert org["name"] == expected_org["name"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_organization_users(self, test_db, organization_with_multiple_users):
        """Test getting all users in an organization."""
        org = organization_with_multiple_users["organization"]

        users = await get_organization_users(org["id"])

        assert len(users) == 5

        # Verify user data
        for user in users:
            assert user["organization_id"] == org["id"]
            assert "email" in user
            assert "role" in user


class TestOrganizationSettings:
    """Test organization settings and connector configurations."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_save_organization_setting(self, test_db, user_with_organization, sample_connector_config):
        """Test saving organization connector settings."""
        org = user_with_organization["organization"]
        user = user_with_organization["user"]

        setting_id = await save_organization_setting(
            org_id=org["id"],
            connector_type=sample_connector_config["connector_type"],
            config_encrypted="encrypted_config_data",
            user_id=user["id"]
        )

        assert setting_id is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_organization_setting(self, test_db, user_with_organization, sample_connector_config):
        """Test retrieving organization connector settings."""
        org = user_with_organization["organization"]
        user = user_with_organization["user"]

        # Save setting first
        await save_organization_setting(
            org_id=org["id"],
            connector_type=sample_connector_config["connector_type"],
            config_encrypted="encrypted_config_data",
            user_id=user["id"]
        )

        # Retrieve setting
        setting = await get_organization_setting(
            org_id=org["id"],
            connector_type=sample_connector_config["connector_type"]
        )

        assert setting is not None
        assert setting["connector_type"] == sample_connector_config["connector_type"]
        assert setting["config_encrypted"] == "encrypted_config_data"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_update_organization_setting(self, test_db, user_with_organization, sample_connector_config):
        """Test updating existing organization setting."""
        org = user_with_organization["organization"]
        user = user_with_organization["user"]

        # Save initial setting
        await save_organization_setting(
            org_id=org["id"],
            connector_type=sample_connector_config["connector_type"],
            config_encrypted="initial_config",
            user_id=user["id"]
        )

        # Update setting
        await save_organization_setting(
            org_id=org["id"],
            connector_type=sample_connector_config["connector_type"],
            config_encrypted="updated_config",
            user_id=user["id"]
        )

        # Retrieve setting
        setting = await get_organization_setting(
            org_id=org["id"],
            connector_type=sample_connector_config["connector_type"]
        )

        assert setting["config_encrypted"] == "updated_config"


class TestSubscriptions:
    """Test subscription management."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_subscription(self, test_db, created_organization):
        """Test creating a subscription for an organization."""
        org_id = created_organization["id"]

        sub_id = await create_subscription(
            org_id=org_id,
            plan_type="pay_per_document",
            price_per_document=0.10,
            monthly_document_limit=None
        )

        assert sub_id is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_subscription(self, test_db, created_organization):
        """Test retrieving subscription."""
        org_id = created_organization["id"]

        # Create subscription
        await create_subscription(
            org_id=org_id,
            plan_type="trial",
            price_per_document=0.0,
            monthly_document_limit=50
        )

        # Get subscription
        subscription = await get_subscription(org_id)

        assert subscription is not None
        assert subscription["plan_type"] == "trial"
        assert subscription["monthly_document_limit"] == 50

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_subscription_plans(self, test_db, created_organization):
        """Test different subscription plan types."""
        org_id = created_organization["id"]

        # Test trial plan
        await create_subscription(
            org_id=org_id,
            plan_type="trial",
            price_per_document=0.0,
            monthly_document_limit=50
        )

        sub = await get_subscription(org_id)
        assert sub["plan_type"] == "trial"
        assert sub["status"] == "active"


class TestUsageTracking:
    """Test usage logging and statistics."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_log_usage(self, test_db, user_with_organization, sample_usage_log):
        """Test logging document usage."""
        org = user_with_organization["organization"]
        user = user_with_organization["user"]

        log_id = await log_usage(
            org_id=org["id"],
            action_type=sample_usage_log["action_type"],
            document_count=sample_usage_log["document_count"],
            user_id=user["id"],
            metadata=sample_usage_log["metadata"]
        )

        assert log_id is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_usage_stats(self, test_db, user_with_organization, sample_usage_log):
        """Test retrieving usage statistics."""
        org = user_with_organization["organization"]
        user = user_with_organization["user"]

        # Log some usage
        await log_usage(
            org_id=org["id"],
            action_type=sample_usage_log["action_type"],
            document_count=sample_usage_log["document_count"],
            user_id=user["id"],
            metadata=sample_usage_log["metadata"]
        )

        # Get current billing period (simplified)
        billing_period = datetime.utcnow().strftime("%Y-%m")

        # Get stats
        stats = await get_usage_stats(org["id"], billing_period)

        assert stats is not None
        assert stats["total_documents"] >= sample_usage_log["document_count"]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_usage_accumulation(self, test_db, user_with_organization):
        """Test that usage accumulates over multiple operations."""
        org = user_with_organization["organization"]
        user = user_with_organization["user"]

        # Log multiple usage events
        await log_usage(org["id"], "document_processed", 5, user["id"], {})
        await log_usage(org["id"], "document_processed", 3, user["id"], {})
        await log_usage(org["id"], "document_processed", 2, user["id"], {})

        # Get stats
        billing_period = datetime.utcnow().strftime("%Y-%m")
        stats = await get_usage_stats(org["id"], billing_period)

        assert stats["total_documents"] == 10


class TestOrganizationLifecycle:
    """Test complete organization lifecycle scenarios."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_new_organization_setup(self, test_db, sample_user_data, sample_organization_data):
        """Test complete new organization setup flow."""
        from backend.database import create_user
        import aiosqlite

        # 1. Create user
        user_id = await create_user(
            auth0_user_id=sample_user_data["auth0_user_id"],
            email=sample_user_data["email"],
            name=sample_user_data["name"]
        )

        # 2. Create organization
        org_id = await create_organization(
            name=sample_organization_data["name"],
            billing_email=sample_organization_data["billing_email"],
            subscription_plan="trial",
            status="active",
            metadata={}
        )

        # 3. Associate user with organization as owner
        async with aiosqlite.connect(test_db) as db:
            await db.execute(
                "UPDATE users SET organization_id = ?, role = ? WHERE id = ?",
                (org_id, "owner", user_id)
            )
            await db.commit()

        # 4. Create default subscription
        await create_subscription(
            org_id=org_id,
            plan_type="trial",
            price_per_document=0.0,
            monthly_document_limit=50
        )

        # Verify setup
        org = await get_organization(org_id)
        users = await get_organization_users(org_id)
        subscription = await get_subscription(org_id)

        assert org is not None
        assert len(users) == 1
        assert users[0]["role"] == "owner"
        assert subscription["plan_type"] == "trial"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_organization_upgrade_flow(self, test_db, user_with_organization):
        """Test upgrading organization from trial to paid plan."""
        org = user_with_organization["organization"]

        # Create trial subscription
        await create_subscription(
            org_id=org["id"],
            plan_type="trial",
            price_per_document=0.0,
            monthly_document_limit=50
        )

        # Simulate upgrade by updating organization
        await update_organization(
            org_id=org["id"],
            subscription_plan="pay_per_document"
        )

        # Verify upgrade
        updated_org = await get_organization(org["id"])
        assert updated_org["subscription_plan"] == "pay_per_document"
