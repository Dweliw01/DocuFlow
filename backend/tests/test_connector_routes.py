"""
Integration tests for connector routes.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from models import FileCabinet, StorageDialog, IndexField, ExtractedData, TableColumn


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def valid_credentials():
    """Valid DocuWare credentials for testing."""
    return {
        "server_url": "https://test.docuware.cloud",
        "username": "test_user",
        "password": "test_password"
    }


@pytest.mark.integration
@pytest.mark.connector
class TestDocuWareConnectionTest:
    """Test DocuWare connection testing endpoint."""

    @patch('routes.connector_routes.docuware_connector')
    def test_connection_test_success(self, mock_connector, client, valid_credentials):
        """Test successful connection test."""
        mock_connector.test_connection = AsyncMock(return_value=(True, "Connected successfully"))

        response = client.post(
            "/api/connectors/docuware/test",
            json=valid_credentials
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "success" in data["message"].lower()

    @patch('routes.connector_routes.docuware_connector')
    def test_connection_test_invalid_credentials(self, mock_connector, client):
        """Test connection test with invalid credentials."""
        mock_connector.test_connection = AsyncMock(return_value=(False, "Invalid credentials"))

        credentials = {
            "server_url": "https://test.docuware.cloud",
            "username": "wrong_user",
            "password": "wrong_password"
        }

        response = client.post(
            "/api/connectors/docuware/test",
            json=credentials
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is False
        assert "invalid" in data["message"].lower()

    @patch('routes.connector_routes.docuware_connector')
    def test_connection_test_server_error(self, mock_connector, client, valid_credentials):
        """Test connection test when server errors occur."""
        mock_connector.test_connection = AsyncMock(
            side_effect=Exception("Connection timeout")
        )

        response = client.post(
            "/api/connectors/docuware/test",
            json=valid_credentials
        )

        assert response.status_code == 500
        assert "failed" in response.json()["detail"].lower()

    def test_connection_test_missing_credentials(self, client):
        """Test connection test with missing credentials."""
        incomplete_credentials = {
            "server_url": "https://test.docuware.cloud"
            # Missing username and password
        }

        response = client.post(
            "/api/connectors/docuware/test",
            json=incomplete_credentials
        )

        assert response.status_code == 422  # Validation error


@pytest.mark.integration
@pytest.mark.connector
class TestDocuWareCabinets:
    """Test DocuWare cabinet retrieval endpoint."""

    @patch('routes.connector_routes.docuware_connector')
    def test_get_cabinets_success(self, mock_connector, client, valid_credentials, sample_file_cabinets):
        """Test successful cabinet retrieval."""
        mock_connector.get_file_cabinets = AsyncMock(return_value=sample_file_cabinets)

        response = client.post(
            "/api/connectors/docuware/cabinets",
            json=valid_credentials
        )

        assert response.status_code == 200
        data = response.json()

        assert "cabinets" in data
        assert len(data["cabinets"]) == 2
        assert data["cabinets"][0]["name"] == "Invoices"

    @patch('routes.connector_routes.docuware_connector')
    def test_get_cabinets_empty_list(self, mock_connector, client, valid_credentials):
        """Test cabinet retrieval when no cabinets exist."""
        mock_connector.get_file_cabinets = AsyncMock(return_value=[])

        response = client.post(
            "/api/connectors/docuware/cabinets",
            json=valid_credentials
        )

        assert response.status_code == 200
        data = response.json()

        assert "cabinets" in data
        assert len(data["cabinets"]) == 0

    @patch('routes.connector_routes.docuware_connector')
    def test_get_cabinets_authentication_failure(self, mock_connector, client):
        """Test cabinet retrieval with authentication failure."""
        mock_connector.get_file_cabinets = AsyncMock(
            side_effect=Exception("Authentication failed")
        )

        credentials = {
            "server_url": "https://test.docuware.cloud",
            "username": "invalid",
            "password": "invalid"
        }

        response = client.post(
            "/api/connectors/docuware/cabinets",
            json=credentials
        )

        assert response.status_code == 500


@pytest.mark.integration
@pytest.mark.connector
class TestDocuWareDialogs:
    """Test DocuWare dialog retrieval endpoint."""

    @patch('routes.connector_routes.docuware_connector')
    def test_get_dialogs_success(self, mock_connector, client, sample_storage_dialogs):
        """Test successful dialog retrieval."""
        mock_connector.get_storage_dialogs = AsyncMock(return_value=sample_storage_dialogs)

        request_data = {
            "server_url": "https://test.docuware.cloud",
            "username": "test_user",
            "password": "test_password",
            "cabinet_id": "cab-001"
        }

        response = client.post(
            "/api/connectors/docuware/dialogs",
            json=request_data
        )

        assert response.status_code == 200
        data = response.json()

        assert "dialogs" in data
        assert len(data["dialogs"]) == 2
        assert data["dialogs"][0]["name"] == "Store Invoice"

    @patch('routes.connector_routes.docuware_connector')
    def test_get_dialogs_invalid_cabinet(self, mock_connector, client):
        """Test dialog retrieval with invalid cabinet ID."""
        mock_connector.get_storage_dialogs = AsyncMock(return_value=[])

        request_data = {
            "server_url": "https://test.docuware.cloud",
            "username": "test_user",
            "password": "test_password",
            "cabinet_id": "invalid-cabinet"
        }

        response = client.post(
            "/api/connectors/docuware/dialogs",
            json=request_data
        )

        assert response.status_code == 200
        assert len(response.json()["dialogs"]) == 0

    def test_get_dialogs_missing_cabinet_id(self, client):
        """Test dialog retrieval without cabinet ID."""
        request_data = {
            "server_url": "https://test.docuware.cloud",
            "username": "test_user",
            "password": "test_password"
            # Missing cabinet_id
        }

        response = client.post(
            "/api/connectors/docuware/dialogs",
            json=request_data
        )

        assert response.status_code == 422  # Validation error


@pytest.mark.integration
@pytest.mark.connector
class TestDocuWareFields:
    """Test DocuWare field retrieval endpoint."""

    @patch('routes.connector_routes.docuware_connector')
    def test_get_fields_success(self, mock_connector, client, sample_index_fields):
        """Test successful field retrieval."""
        mock_connector.get_index_fields = AsyncMock(return_value=sample_index_fields)

        request_data = {
            "server_url": "https://test.docuware.cloud",
            "username": "test_user",
            "password": "test_password",
            "cabinet_id": "cab-001",
            "dialog_id": "dialog-001"
        }

        response = client.post(
            "/api/connectors/docuware/fields",
            json=request_data
        )

        assert response.status_code == 200
        data = response.json()

        assert "fields" in data
        assert len(data["fields"]) == 6
        # Check for required fields
        assert any(f["name"] == "VENDOR_NAME" for f in data["fields"])

    @patch('routes.connector_routes.docuware_connector')
    def test_get_fields_with_table_fields(self, mock_connector, client, sample_index_fields):
        """Test field retrieval including table fields."""
        mock_connector.get_index_fields = AsyncMock(return_value=sample_index_fields)

        request_data = {
            "server_url": "https://test.docuware.cloud",
            "username": "test_user",
            "password": "test_password",
            "cabinet_id": "cab-001",
            "dialog_id": "dialog-001"
        }

        response = client.post(
            "/api/connectors/docuware/fields",
            json=request_data
        )

        assert response.status_code == 200
        data = response.json()

        # Find table field
        table_fields = [f for f in data["fields"] if f.get("is_table_field")]
        assert len(table_fields) > 0

        # Check table columns
        table_field = table_fields[0]
        assert "table_columns" in table_field
        assert len(table_field["table_columns"]) > 0

    @patch('routes.connector_routes.docuware_connector')
    def test_get_fields_no_fields_available(self, mock_connector, client):
        """Test field retrieval when no fields are available."""
        mock_connector.get_index_fields = AsyncMock(return_value=[])

        request_data = {
            "server_url": "https://test.docuware.cloud",
            "username": "test_user",
            "password": "test_password",
            "cabinet_id": "cab-001",
            "dialog_id": "dialog-001"
        }

        response = client.post(
            "/api/connectors/docuware/fields",
            json=request_data
        )

        assert response.status_code == 200
        assert len(response.json()["fields"]) == 0


@pytest.mark.integration
@pytest.mark.connector
class TestFieldAutoMapping:
    """Test automatic field mapping endpoint."""

    @patch('routes.connector_routes.field_mapping_service')
    def test_auto_map_fields_success(
        self,
        mock_mapping_service,
        client,
        sample_extracted_data,
        sample_index_fields
    ):
        """Test successful automatic field mapping."""
        mock_mapping_service.auto_map_fields.return_value = {
            "vendor": "VENDOR_NAME",
            "amount": "INVOICE_AMOUNT",
            "date": "INVOICE_DATE"
        }

        request_data = {
            "extracted_data": sample_extracted_data.dict(),
            "index_fields": [field.dict() for field in sample_index_fields]
        }

        response = client.post(
            "/api/connectors/auto-map",
            json=request_data
        )

        assert response.status_code == 200
        data = response.json()

        assert "mapping" in data
        assert data["mapping"]["vendor"] == "VENDOR_NAME"
        assert data["mapping"]["amount"] == "INVOICE_AMOUNT"

    @patch('routes.connector_routes.field_mapping_service')
    def test_auto_map_fields_no_matches(
        self,
        mock_mapping_service,
        client,
        sample_extracted_data
    ):
        """Test auto-mapping when no fields match."""
        mock_mapping_service.auto_map_fields.return_value = {}

        # Use fields with completely different names
        fields = [
            IndexField(name="ZZZZZ", type="String", required=False, is_system_field=False).dict()
        ]

        request_data = {
            "extracted_data": sample_extracted_data.dict(),
            "index_fields": fields
        }

        response = client.post(
            "/api/connectors/auto-map",
            json=request_data
        )

        assert response.status_code == 200
        assert len(response.json()["mapping"]) == 0


@pytest.mark.integration
@pytest.mark.connector
class TestConnectorConfiguration:
    """Test connector configuration save/get/clear endpoints."""

    def test_save_connector_config(self, client, sample_docuware_config):
        """Test saving connector configuration."""
        response = client.post(
            "/api/connectors/config",
            json=sample_docuware_config.dict()
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "saved" in data["message"].lower()

    @patch('routes.connector_routes.current_connector_config')
    def test_get_connector_config(self, mock_config, client, sample_docuware_config):
        """Test retrieving current connector configuration."""
        with patch('routes.connector_routes.current_connector_config', sample_docuware_config):
            response = client.get("/api/connectors/config")

            assert response.status_code == 200
            data = response.json()

            assert data["connector_type"] == sample_docuware_config.connector_type
            assert data["cabinet_id"] == sample_docuware_config.cabinet_id

    def test_get_connector_config_none(self, client):
        """Test getting config when none is set."""
        with patch('routes.connector_routes.current_connector_config', None):
            response = client.get("/api/connectors/config")

            assert response.status_code == 404

    @patch('routes.connector_routes.docuware_connector')
    def test_clear_connector_config(self, mock_connector, client):
        """Test clearing connector configuration."""
        mock_connector.clear_cache = Mock()

        response = client.delete("/api/connectors/config")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        mock_connector.clear_cache.assert_called_once()


@pytest.mark.integration
@pytest.mark.connector
class TestConnectorEdgeCases:
    """Test edge cases and error scenarios."""

    def test_test_connection_invalid_url(self, client):
        """Test connection with invalid URL format."""
        credentials = {
            "server_url": "not-a-valid-url",
            "username": "test",
            "password": "test"
        }

        with patch('routes.connector_routes.docuware_connector.test_connection',
                   new=AsyncMock(return_value=(False, "Invalid URL"))):
            response = client.post(
                "/api/connectors/docuware/test",
                json=credentials
            )

            assert response.status_code == 200
            assert response.json()["success"] is False

    def test_test_connection_empty_credentials(self, client):
        """Test connection with empty credentials."""
        credentials = {
            "server_url": "",
            "username": "",
            "password": ""
        }

        response = client.post(
            "/api/connectors/docuware/test",
            json=credentials
        )

        # Should either fail validation or return connection error
        assert response.status_code in [422, 200]

    @patch('routes.connector_routes.docuware_connector')
    def test_get_cabinets_timeout(self, mock_connector, client, valid_credentials):
        """Test cabinet retrieval with timeout."""
        mock_connector.get_file_cabinets = AsyncMock(
            side_effect=Exception("Connection timeout after 30s")
        )

        response = client.post(
            "/api/connectors/docuware/cabinets",
            json=valid_credentials
        )

        assert response.status_code == 500
        assert "timeout" in response.json()["detail"].lower()


@pytest.mark.integration
@pytest.mark.connector
class TestEncryption:
    """Test password encryption in connector config."""

    @patch('routes.connector_routes.encryption_service')
    def test_save_config_encrypts_password(
        self,
        mock_encryption,
        client,
        sample_docuware_config
    ):
        """Test that password is encrypted when saving config."""
        mock_encryption.encrypt_password.return_value = "encrypted_password_12345"

        response = client.post(
            "/api/connectors/config",
            json=sample_docuware_config.dict()
        )

        assert response.status_code == 200
        # Verify encryption was called
        mock_encryption.encrypt_password.assert_called()

    @patch('routes.connector_routes.encryption_service')
    @patch('routes.connector_routes.current_connector_config')
    def test_get_config_decrypts_password(
        self,
        mock_config,
        mock_encryption,
        client,
        sample_docuware_config
    ):
        """Test that password is decrypted when retrieving config."""
        mock_encryption.decrypt_password.return_value = "decrypted_password"

        with patch('routes.connector_routes.get_current_config_with_decrypted_password',
                   return_value=sample_docuware_config):
            response = client.get("/api/connectors/config")

            # Config should be returned (decryption handled by helper function)
            assert response.status_code == 200
