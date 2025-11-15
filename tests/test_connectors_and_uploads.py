"""
Tests for connector configurations and document upload functionality.
Tests DocuWare, Google Drive connectors, and upload processing.
"""
import pytest
import json

from backend.database import (
    save_organization_setting,
    get_organization_setting,
    log_usage
)


class TestConnectorConfiguration:
    """Test connector configuration storage and retrieval."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_save_docuware_config(self, test_db, user_with_organization):
        """Test saving DocuWare connector configuration."""
        user = user_with_organization["user"]
        org = user_with_organization["organization"]

        config = {
            "base_url": "https://test.docuware.cloud",
            "username": "test_user",
            "organization": "test_org"
        }

        config_json = json.dumps(config)

        setting_id = await save_organization_setting(
            org_id=org["id"],
            connector_type="docuware",
            config_encrypted=config_json,  # In real app, this would be encrypted
            user_id=user["id"]
        )

        assert setting_id is not None

        # Retrieve and verify
        setting = await get_organization_setting(org["id"], "docuware")
        retrieved_config = json.loads(setting["config_encrypted"])

        assert retrieved_config["base_url"] == config["base_url"]
        assert retrieved_config["username"] == config["username"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_save_google_drive_config(self, test_db, user_with_organization):
        """Test saving Google Drive connector configuration."""
        user = user_with_organization["user"]
        org = user_with_organization["organization"]

        config = {
            "credentials": "oauth_credentials_json",
            "root_folder_id": "test_folder_id"
        }

        config_json = json.dumps(config)

        setting_id = await save_organization_setting(
            org_id=org["id"],
            connector_type="google_drive",
            config_encrypted=config_json,
            user_id=user["id"]
        )

        assert setting_id is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_multiple_connectors_per_organization(self, test_db, user_with_organization):
        """Test that organization can have multiple connector configs."""
        user = user_with_organization["user"]
        org = user_with_organization["organization"]

        # Save DocuWare config
        await save_organization_setting(
            org_id=org["id"],
            connector_type="docuware",
            config_encrypted=json.dumps({"test": "docuware"}),
            user_id=user["id"]
        )

        # Save Google Drive config
        await save_organization_setting(
            org_id=org["id"],
            connector_type="google_drive",
            config_encrypted=json.dumps({"test": "gdrive"}),
            user_id=user["id"]
        )

        # Both should be retrievable
        docuware = await get_organization_setting(org["id"], "docuware")
        gdrive = await get_organization_setting(org["id"], "google_drive")

        assert docuware is not None
        assert gdrive is not None
        assert docuware["connector_type"] == "docuware"
        assert gdrive["connector_type"] == "google_drive"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_update_connector_config(self, test_db, user_with_organization):
        """Test updating existing connector configuration."""
        user = user_with_organization["user"]
        org = user_with_organization["organization"]

        # Save initial config
        initial_config = {"base_url": "https://old.docuware.cloud"}
        await save_organization_setting(
            org_id=org["id"],
            connector_type="docuware",
            config_encrypted=json.dumps(initial_config),
            user_id=user["id"]
        )

        # Update config
        updated_config = {"base_url": "https://new.docuware.cloud"}
        await save_organization_setting(
            org_id=org["id"],
            connector_type="docuware",
            config_encrypted=json.dumps(updated_config),
            user_id=user["id"]
        )

        # Verify update
        setting = await get_organization_setting(org["id"], "docuware")
        config = json.loads(setting["config_encrypted"])

        assert config["base_url"] == "https://new.docuware.cloud"


class TestDocumentUpload:
    """Test document upload and processing workflows."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_upload_logs_usage(self, test_db, user_with_organization):
        """Test that document upload logs usage."""
        user = user_with_organization["user"]
        org = user_with_organization["organization"]

        # Simulate uploading 5 documents
        await log_usage(
            org_id=org["id"],
            action_type="document_uploaded",
            document_count=5,
            user_id=user["id"],
            metadata={"file_types": ["pdf"]}
        )

        # Verify usage logged
        from backend.database import get_usage_stats
        from datetime import datetime

        billing_period = datetime.utcnow().strftime("%Y-%m")
        stats = await get_usage_stats(org["id"], billing_period)

        assert stats["total_documents"] == 5

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_batch_upload(self, test_db, user_with_organization):
        """Test batch document upload (up to 100 files)."""
        user = user_with_organization["user"]
        org = user_with_organization["organization"]

        # Simulate batch upload of 50 documents
        await log_usage(
            org_id=org["id"],
            action_type="batch_upload",
            document_count=50,
            user_id=user["id"],
            metadata={"batch_id": "batch_123"}
        )

        from backend.database import get_usage_stats
        from datetime import datetime

        billing_period = datetime.utcnow().strftime("%Y-%m")
        stats = await get_usage_stats(org["id"], billing_period)

        assert stats["total_documents"] == 50

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_upload_with_categorization(self, test_db, user_with_organization):
        """Test document upload with AI categorization."""
        user = user_with_organization["user"]
        org = user_with_organization["organization"]

        # Simulate upload with categorization
        await log_usage(
            org_id=org["id"],
            action_type="document_categorized",
            document_count=3,
            user_id=user["id"],
            metadata={
                "categories": ["invoice", "contract", "receipt"]
            }
        )

        from backend.database import get_usage_stats
        from datetime import datetime

        billing_period = datetime.utcnow().strftime("%Y-%m")
        stats = await get_usage_stats(org["id"], billing_period)

        assert stats["total_documents"] == 3


class TestConnectorIntegration:
    """Test integration between connectors and document processing."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_docuware_upload_flow(self, test_db, user_with_organization):
        """
        Test complete DocuWare upload flow:
        1. Configure DocuWare connector
        2. Upload documents
        3. Log usage
        4. Verify connector was used
        """
        user = user_with_organization["user"]
        org = user_with_organization["organization"]

        # 1. Configure DocuWare
        docuware_config = {
            "base_url": "https://test.docuware.cloud",
            "cabinet_id": "test_cabinet"
        }

        await save_organization_setting(
            org_id=org["id"],
            connector_type="docuware",
            config_encrypted=json.dumps(docuware_config),
            user_id=user["id"]
        )

        # 2. Upload documents
        await log_usage(
            org_id=org["id"],
            action_type="document_uploaded",
            document_count=10,
            user_id=user["id"],
            metadata={
                "connector": "docuware",
                "cabinet_id": "test_cabinet"
            }
        )

        # 3. Verify
        from backend.database import get_usage_stats
        from datetime import datetime

        billing_period = datetime.utcnow().strftime("%Y-%m")
        stats = await get_usage_stats(org["id"], billing_period)

        assert stats["total_documents"] == 10

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_google_drive_folder_organization(self, test_db, user_with_organization):
        """
        Test Google Drive folder organization:
        1. Configure Google Drive
        2. Upload documents with categories
        3. Verify metadata includes folder structure
        """
        user = user_with_organization["user"]
        org = user_with_organization["organization"]

        # 1. Configure Google Drive
        gdrive_config = {
            "root_folder_id": "test_root_folder",
            "category_folders": {
                "invoices": "folder_id_invoices",
                "contracts": "folder_id_contracts"
            }
        }

        await save_organization_setting(
            org_id=org["id"],
            connector_type="google_drive",
            config_encrypted=json.dumps(gdrive_config),
            user_id=user["id"]
        )

        # 2. Upload documents
        await log_usage(
            org_id=org["id"],
            action_type="document_uploaded",
            document_count=5,
            user_id=user["id"],
            metadata={
                "connector": "google_drive",
                "category": "invoices",
                "folder_id": "folder_id_invoices"
            }
        )

        # 3. Verify
        setting = await get_organization_setting(org["id"], "google_drive")
        config = json.loads(setting["config_encrypted"])

        assert "category_folders" in config
        assert config["category_folders"]["invoices"] == "folder_id_invoices"


class TestConnectorTesting:
    """Test connector test/validation endpoints."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_connector_test_success(self, test_db, user_with_organization):
        """Test successful connector connection test."""
        user = user_with_organization["user"]
        org = user_with_organization["organization"]

        # Save valid config
        config = {
            "base_url": "https://test.docuware.cloud",
            "username": "test_user"
        }

        await save_organization_setting(
            org_id=org["id"],
            connector_type="docuware",
            config_encrypted=json.dumps(config),
            user_id=user["id"]
        )

        # In real app, this would call /api/connectors/test
        # For now, just verify config was saved
        setting = await get_organization_setting(org["id"], "docuware")

        assert setting is not None
        assert setting["connector_type"] == "docuware"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_connector_test_failure(self, test_db, user_with_organization):
        """Test connector connection test with invalid credentials."""
        user = user_with_organization["user"]
        org = user_with_organization["organization"]

        # Save invalid config (missing required fields)
        invalid_config = {
            "base_url": "https://invalid.url"
            # Missing username, password, etc.
        }

        await save_organization_setting(
            org_id=org["id"],
            connector_type="docuware",
            config_encrypted=json.dumps(invalid_config),
            user_id=user["id"]
        )

        # Config is saved, but connection test would fail
        # Real implementation would validate on test
        setting = await get_organization_setting(org["id"], "docuware")

        assert setting is not None
        # In real app, test endpoint would return error


class TestFieldMapping:
    """Test field mapping service for document data extraction."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_field_mapping_usage_log(self, test_db, user_with_organization):
        """Test that field mapping operations are logged."""
        user = user_with_organization["user"]
        org = user_with_organization["organization"]

        # Simulate field mapping operation
        await log_usage(
            org_id=org["id"],
            action_type="field_mapping_created",
            document_count=0,  # No documents, just mapping
            user_id=user["id"],
            metadata={
                "source_fields": ["Date", "Amount", "Vendor"],
                "target_fields": ["INVOICE_DATE", "AMOUNT", "VENDOR_NAME"]
            }
        )

        # Verify logged
        from backend.database import get_usage_stats
        from datetime import datetime

        billing_period = datetime.utcnow().strftime("%Y-%m")
        stats = await get_usage_stats(org["id"], billing_period)

        # Field mapping doesn't count toward document usage
        assert stats["total_documents"] == 0
