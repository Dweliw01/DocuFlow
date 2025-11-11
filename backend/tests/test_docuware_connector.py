"""
Unit tests for DocuWare connector.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from connectors.docuware_connector import DocuWareConnector
from models import FileCabinet, StorageDialog, IndexField, TableColumn


@pytest.mark.unit
@pytest.mark.docuware
class TestDocuWareConnectorInit:
    """Test DocuWare connector initialization."""

    def test_connector_initialization(self):
        """Test that connector initializes with correct defaults."""
        connector = DocuWareConnector()

        assert connector.client is None
        assert connector.session is None
        assert connector.cabinet_cache == {}
        assert connector.field_definitions_cache == {}
        assert connector.current_credentials_key is None
        assert connector.auth_failure_count == 0

    def test_has_valid_session_false_initially(self):
        """Test that has_valid_session returns False initially."""
        connector = DocuWareConnector()
        assert connector._has_valid_session() is False

    def test_has_valid_session_true_with_session(self):
        """Test that has_valid_session returns True when session exists."""
        connector = DocuWareConnector()
        connector.session = MagicMock()
        connector.client = MagicMock()

        assert connector._has_valid_session() is True


@pytest.mark.unit
@pytest.mark.docuware
class TestDocuWareConnectorCache:
    """Test DocuWare connector caching functionality."""

    def test_clear_cache_resets_all_data(self):
        """Test that clear_cache resets all cached data."""
        connector = DocuWareConnector()

        # Set some data
        connector.cabinet_cache = {"test": "data"}
        connector.field_definitions_cache = {"test": "fields"}
        connector.current_credentials_key = "test_key"
        connector.client = MagicMock()
        connector.session = MagicMock()
        connector.auth_failure_count = 3

        # Clear cache
        connector.clear_cache()

        # Verify all cleared
        assert connector.cabinet_cache == {}
        assert connector.field_definitions_cache == {}
        assert connector.current_credentials_key is None
        assert connector.client is None
        assert connector.session is None
        assert connector.auth_failure_count == 0


@pytest.mark.unit
@pytest.mark.docuware
class TestDocuWareConnectorFieldValidation:
    """Test field validation and sanitization."""

    def test_is_system_field_dwsys_prefix(self):
        """Test system field detection for DWSYS prefix."""
        connector = DocuWareConnector()
        assert connector._is_system_field("DWSYS_FIELD") is True
        assert connector._is_system_field("REGULAR_FIELD") is False

    def test_is_system_field_common_system_fields(self):
        """Test system field detection for common system fields."""
        connector = DocuWareConnector()

        system_fields = ["DWDOCID", "DWSTOREDATETIME", "DWMODIFYDATETIME"]
        for field in system_fields:
            assert connector._is_system_field(field) is True

    def test_sanitize_field_value_string(self):
        """Test string field value sanitization."""
        connector = DocuWareConnector()

        # Test string truncation
        long_string = "a" * 300
        result = connector._sanitize_field_value(long_string, "String", max_length=100)
        assert len(result) == 100

        # Test string without max_length
        result = connector._sanitize_field_value("test", "String")
        assert result == "test"

    def test_sanitize_field_value_decimal(self):
        """Test decimal field value sanitization."""
        connector = DocuWareConnector()

        # Test valid decimal
        assert connector._sanitize_field_value("123.45", "Decimal") == "123.45"

        # Test integer conversion
        assert connector._sanitize_field_value("100", "Decimal") == "100.00"

        # Test invalid decimal
        assert connector._sanitize_field_value("invalid", "Decimal") is None

        # Test with currency symbols
        assert connector._sanitize_field_value("$1,234.56", "Decimal") == "1234.56"

    def test_sanitize_field_value_date(self):
        """Test date field value sanitization."""
        connector = DocuWareConnector()

        # Test valid date
        assert connector._sanitize_field_value("2024-01-15", "Date") == "2024-01-15"

        # Test invalid date format
        assert connector._sanitize_field_value("01/15/2024", "Date") is None

        # Test datetime conversion
        assert connector._sanitize_field_value("2024-01-15T10:30:00", "Date") == "2024-01-15"

    def test_sanitize_field_value_int(self):
        """Test integer field value sanitization."""
        connector = DocuWareConnector()

        # Test valid integer
        assert connector._sanitize_field_value("42", "Int") == 42

        # Test float conversion
        assert connector._sanitize_field_value("42.7", "Int") == 42

        # Test invalid integer
        assert connector._sanitize_field_value("invalid", "Int") is None


@pytest.mark.unit
@pytest.mark.docuware
@pytest.mark.asyncio
class TestDocuWareConnectorAuthentication:
    """Test DocuWare authentication."""

    async def test_authenticate_success(self, sample_credentials):
        """Test successful authentication."""
        connector = DocuWareConnector()

        with patch.object(connector, '_authenticate_sync', return_value=MagicMock()) as mock_auth:
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_executor = AsyncMock(return_value=MagicMock())
                mock_loop.return_value.run_in_executor = mock_executor

                session = await connector.authenticate(sample_credentials)

                assert session is not None
                mock_auth.assert_called_once()

    async def test_test_connection_success(self, sample_credentials):
        """Test successful connection test."""
        connector = DocuWareConnector()

        with patch.object(connector, '_test_connection_sync', return_value=(True, "Connected")) as mock_test:
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_executor = AsyncMock(return_value=(True, "Connected"))
                mock_loop.return_value.run_in_executor = mock_executor

                success, message = await connector.test_connection(sample_credentials)

                assert success is True
                assert message == "Connected"

    async def test_test_connection_invalid_credentials(self, sample_credentials):
        """Test connection test with invalid credentials."""
        connector = DocuWareConnector()

        with patch.object(connector, '_test_connection_sync', return_value=(False, "Invalid credentials")) as mock_test:
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_executor = AsyncMock(return_value=(False, "Invalid credentials"))
                mock_loop.return_value.run_in_executor = mock_executor

                success, message = await connector.test_connection(sample_credentials)

                assert success is False
                assert "Invalid credentials" in message


@pytest.mark.unit
@pytest.mark.docuware
@pytest.mark.asyncio
class TestDocuWareConnectorCabinets:
    """Test DocuWare file cabinet operations."""

    async def test_get_file_cabinets_success(self, sample_credentials, sample_file_cabinets):
        """Test successful retrieval of file cabinets."""
        connector = DocuWareConnector()
        connector.session = MagicMock()
        connector.client = MagicMock()

        with patch.object(connector, '_get_cabinets_sync', return_value=sample_file_cabinets):
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_executor = AsyncMock(return_value=sample_file_cabinets)
                mock_loop.return_value.run_in_executor = mock_executor

                cabinets = await connector.get_file_cabinets(sample_credentials)

                assert len(cabinets) == 2
                assert cabinets[0].name == "Invoices"
                assert cabinets[1].name == "Contracts"

    async def test_get_file_cabinets_no_session(self, sample_credentials):
        """Test get_file_cabinets authenticates when no session."""
        connector = DocuWareConnector()

        with patch.object(connector, 'authenticate', new=AsyncMock(return_value=None)):
            cabinets = await connector.get_file_cabinets(sample_credentials)
            assert cabinets == []


@pytest.mark.unit
@pytest.mark.docuware
@pytest.mark.asyncio
class TestDocuWareConnectorDialogs:
    """Test DocuWare storage dialog operations."""

    async def test_get_storage_dialogs_success(self, sample_credentials, sample_storage_dialogs):
        """Test successful retrieval of storage dialogs."""
        connector = DocuWareConnector()
        connector.session = MagicMock()
        connector.client = MagicMock()

        with patch.object(connector, '_get_dialogs_sync', return_value=sample_storage_dialogs):
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_executor = AsyncMock(return_value=sample_storage_dialogs)
                mock_loop.return_value.run_in_executor = mock_executor

                dialogs = await connector.get_storage_dialogs("cab-001", sample_credentials)

                assert len(dialogs) == 2
                assert dialogs[0].name == "Store Invoice"

    async def test_get_storage_dialogs_no_session(self, sample_credentials):
        """Test get_storage_dialogs authenticates when no session."""
        connector = DocuWareConnector()

        with patch.object(connector, 'authenticate', new=AsyncMock(return_value=None)):
            dialogs = await connector.get_storage_dialogs("cab-001", sample_credentials)
            assert dialogs == []


@pytest.mark.unit
@pytest.mark.docuware
@pytest.mark.asyncio
class TestDocuWareConnectorFields:
    """Test DocuWare index field operations."""

    async def test_get_index_fields_success(self, sample_credentials, sample_index_fields):
        """Test successful retrieval of index fields."""
        connector = DocuWareConnector()
        connector.session = MagicMock()
        connector.client = MagicMock()

        with patch.object(connector, '_get_fields_sync', return_value=sample_index_fields):
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_executor = AsyncMock(return_value=sample_index_fields)
                mock_loop.return_value.run_in_executor = mock_executor

                fields = await connector.get_index_fields("cab-001", "dialog-001", sample_credentials)

                assert len(fields) == 6
                assert any(f.name == "VENDOR_NAME" for f in fields)
                assert any(f.is_table_field for f in fields)

    def test_parse_table_columns_success(self):
        """Test parsing table columns from field data."""
        connector = DocuWareConnector()

        field_data = {
            "Item": {
                "$type": "DocumentIndexFieldTable",
                "Row": [
                    {
                        "ColumnValue": [
                            {
                                "FieldName": "DESCRIPTION",
                                "FieldLabel": "Description",
                                "ItemElementName": "String",
                                "IsNull": False
                            },
                            {
                                "FieldName": "QTY",
                                "FieldLabel": "Quantity",
                                "ItemElementName": "Decimal",
                                "IsNull": False
                            }
                        ]
                    }
                ]
            }
        }

        columns = connector._parse_table_columns(field_data)

        assert len(columns) == 2
        assert columns[0].name == "DESCRIPTION"
        assert columns[0].type == "String"
        assert columns[1].name == "QTY"
        assert columns[1].type == "Decimal"

    def test_parse_table_columns_empty(self):
        """Test parsing table columns with no data."""
        connector = DocuWareConnector()

        field_data = {"Item": {}}
        columns = connector._parse_table_columns(field_data)

        assert columns == []


@pytest.mark.unit
@pytest.mark.docuware
class TestDocuWareConnectorLineItems:
    """Test line items and table field handling."""

    def test_build_table_field_data_success(self, sample_table_columns, sample_line_items):
        """Test building table field data from line items."""
        connector = DocuWareConnector()

        # Convert columns to dict format expected by the method
        columns = [
            {"name": "DESCRIPTION", "label": "Description", "type": "String"},
            {"name": "QTY", "label": "Quantity", "type": "Decimal"},
            {"name": "UNIT_PRICE", "label": "Unit Price", "type": "Decimal"},
            {"name": "AMOUNT", "label": "Amount", "type": "Decimal"},
            {"name": "SKU", "label": "SKU", "type": "String"}
        ]

        # Convert line items to dict format
        line_items = [item.dict() for item in sample_line_items]

        result = connector._build_table_field_data("LINE_ITEMS", columns, line_items)

        assert "FieldName" in result
        assert result["FieldName"] == "LINE_ITEMS"
        assert "Item" in result
        assert "$type" in result["Item"]
        assert result["Item"]["$type"] == "DocumentIndexFieldTable"

    def test_find_line_item_value_direct_match(self):
        """Test finding line item value with direct match."""
        connector = DocuWareConnector()

        line_item = {"quantity": 5, "unit_price": 100.00}
        field_mapping = {"quantity": ["QTY", "QUANTITY"]}

        value = connector._find_line_item_value(line_item, "QTY", field_mapping)
        assert value == 5

    def test_find_line_item_value_no_match(self):
        """Test finding line item value with no match."""
        connector = DocuWareConnector()

        line_item = {"description": "Product"}
        field_mapping = {"quantity": ["QTY"]}

        value = connector._find_line_item_value(line_item, "QTY", field_mapping)
        assert value is None


@pytest.mark.unit
@pytest.mark.docuware
@pytest.mark.asyncio
class TestDocuWareConnectorUpload:
    """Test document upload functionality."""

    async def test_upload_document_success(self, sample_extracted_data, sample_docuware_config, sample_credentials):
        """Test successful document upload."""
        connector = DocuWareConnector()
        connector.session = MagicMock()
        connector.client = MagicMock()

        test_pdf_path = Path("/tmp/test.pdf")

        with patch.object(connector, '_upload_document_sync', return_value="doc-12345"):
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_executor = AsyncMock(return_value="doc-12345")
                mock_loop.return_value.run_in_executor = mock_executor

                doc_id = await connector.upload_document(
                    pdf_path=test_pdf_path,
                    extracted_data=sample_extracted_data,
                    storage_config=sample_docuware_config.dict(),
                    credentials=sample_credentials
                )

                assert doc_id == "doc-12345"

    async def test_upload_document_no_session(self, sample_extracted_data, sample_docuware_config, sample_credentials):
        """Test upload authenticates when no session."""
        connector = DocuWareConnector()

        test_pdf_path = Path("/tmp/test.pdf")

        with patch.object(connector, 'authenticate', new=AsyncMock(return_value=None)):
            doc_id = await connector.upload_document(
                pdf_path=test_pdf_path,
                extracted_data=sample_extracted_data,
                storage_config=sample_docuware_config.dict(),
                credentials=sample_credentials
            )

            assert doc_id is None


@pytest.mark.unit
@pytest.mark.docuware
class TestDocuWareConnectorHelpers:
    """Test helper methods."""

    def test_document_has_table_data_true(self):
        """Test detecting documents with table data."""
        connector = DocuWareConnector()

        doc_data = {
            "Fields": [
                {
                    "ItemElementName": "Table",
                    "Item": {
                        "$type": "DocumentIndexFieldTable",
                        "Row": [{"ColumnValue": []}]
                    }
                }
            ]
        }

        result = connector._document_has_table_data(doc_data)
        assert result is True

    def test_document_has_table_data_false(self):
        """Test detecting documents without table data."""
        connector = DocuWareConnector()

        doc_data = {
            "Fields": [
                {"ItemElementName": "String", "Item": "Test"}
            ]
        }

        result = connector._document_has_table_data(doc_data)
        assert result is False

    def test_document_has_table_data_empty(self):
        """Test detecting documents with empty table."""
        connector = DocuWareConnector()

        doc_data = {
            "Fields": [
                {
                    "ItemElementName": "Table",
                    "Item": {
                        "$type": "DocumentIndexFieldTable",
                        "Row": []
                    }
                }
            ]
        }

        result = connector._document_has_table_data(doc_data)
        assert result is False
