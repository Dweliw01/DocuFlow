"""
Pytest configuration and shared fixtures for DocuFlow tests.
"""
import pytest
import asyncio
import os
from pathlib import Path
from unittest.mock import Mock, MagicMock, AsyncMock
from typing import Dict, Any, List
import sys

# Set up test environment variables BEFORE importing any modules
os.environ['ANTHROPIC_API_KEY'] = 'test-api-key-for-testing'
os.environ['USE_GOOGLE_VISION'] = 'false'
os.environ['UPLOAD_DIR'] = './test_storage/uploads'
os.environ['PROCESSED_DIR'] = './test_storage/processed'
os.environ['LOG_DIR'] = './test_storage/logs'

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import (
    ExtractedData, LineItem, FileCabinet, StorageDialog,
    IndexField, TableColumn, DocuWareConfig
)


# ==================== Test Data Fixtures ====================

@pytest.fixture
def sample_extracted_data() -> ExtractedData:
    """Sample extracted data from a processed invoice."""
    return ExtractedData(
        document_type="Invoice",
        vendor="Acme Corporation",
        client="Test Client Inc",
        date="2024-01-15",
        due_date="2024-02-15",
        amount=1500.00,
        currency="USD",
        document_number="INV-2024-001",
        reference_number="PO-12345",
        email="billing@acmecorp.com",
        phone="+1-555-0123",
        address="123 Main St, New York, NY 10001",
        line_items=[
            LineItem(
                description="Premium Widget",
                quantity="10",
                unit_price="100.00",
                amount="1000.00",
                sku="WIDGET-001"
            ),
            LineItem(
                description="Standard Service",
                quantity="5",
                unit_price="100.00",
                amount="500.00",
                sku="SERVICE-001"
            )
        ],
        other_data={
            "custom_field_1": "Custom Value",
            "notes": "Test invoice for automation"
        }
    )


@pytest.fixture
def sample_line_items() -> List[LineItem]:
    """Sample line items for invoice testing."""
    return [
        LineItem(
            description="Product A",
            quantity="2",
            unit_price="50.00",
            amount="100.00",
            sku="SKU-A-001"
        ),
        LineItem(
            description="Product B",
            quantity="3",
            unit_price="75.00",
            amount="225.00",
            sku="SKU-B-002"
        )
    ]


@pytest.fixture
def sample_file_cabinets() -> List[FileCabinet]:
    """Sample DocuWare file cabinets."""
    return [
        FileCabinet(
            id="cab-001",
            name="Invoices",
            description="Invoice storage cabinet"
        ),
        FileCabinet(
            id="cab-002",
            name="Contracts",
            description="Contract storage cabinet"
        )
    ]


@pytest.fixture
def sample_storage_dialogs() -> List[StorageDialog]:
    """Sample DocuWare storage dialogs."""
    return [
        StorageDialog(
            id="dialog-001",
            name="Store Invoice",
            description="Default invoice storage dialog"
        ),
        StorageDialog(
            id="dialog-002",
            name="Store with Approval",
            description="Storage requiring approval"
        )
    ]


@pytest.fixture
def sample_index_fields() -> List[IndexField]:
    """Sample DocuWare index fields."""
    return [
        IndexField(
            name="DOCUMENT_TYPE",
            type="String",
            required=True,
            max_length=50,
            is_system_field=False
        ),
        IndexField(
            name="VENDOR_NAME",
            type="String",
            required=True,
            max_length=100,
            is_system_field=False
        ),
        IndexField(
            name="INVOICE_DATE",
            type="Date",
            required=True,
            is_system_field=False
        ),
        IndexField(
            name="INVOICE_AMOUNT",
            type="Decimal",
            required=True,
            is_system_field=False
        ),
        IndexField(
            name="INVOICE_NUMBER",
            type="String",
            required=False,
            max_length=50,
            is_system_field=False
        ),
        IndexField(
            name="LINE_ITEMS",
            type="Table",
            required=False,
            is_system_field=False,
            is_table_field=True,
            table_columns=[
                TableColumn(name="DESCRIPTION", label="Description", type="String", required=True),
                TableColumn(name="QTY", label="Quantity", type="Decimal", required=True),
                TableColumn(name="UNIT_PRICE", label="Unit Price", type="Decimal", required=True),
                TableColumn(name="AMOUNT", label="Amount", type="Decimal", required=True),
                TableColumn(name="SKU", label="SKU", type="String", required=False)
            ]
        )
    ]


@pytest.fixture
def sample_table_columns() -> List[TableColumn]:
    """Sample table columns for line items."""
    return [
        TableColumn(name="DESCRIPTION", label="Description", type="String", required=True),
        TableColumn(name="QTY", label="Quantity", type="Decimal", required=True),
        TableColumn(name="UNIT_PRICE", label="Unit Price", type="Decimal", required=True),
        TableColumn(name="AMOUNT", label="Amount", type="Decimal", required=True),
        TableColumn(name="SKU", label="SKU", type="String", required=False)
    ]


@pytest.fixture
def sample_docuware_config() -> DocuWareConfig:
    """Sample DocuWare configuration."""
    return DocuWareConfig(
        server_url="https://test.docuware.cloud",
        username="test_user",
        password="test_password",
        cabinet_id="cab-001",
        dialog_id="dialog-001",
        selected_fields={
            "document_type": "DOCUMENT_TYPE",
            "vendor": "VENDOR_NAME",
            "date": "INVOICE_DATE",
            "amount": "INVOICE_AMOUNT",
            "document_number": "INVOICE_NUMBER"
        },
        selected_table_columns={
            "LINE_ITEMS": {
                "description": "DESCRIPTION",
                "quantity": "QTY",
                "unit_price": "UNIT_PRICE",
                "amount": "AMOUNT",
                "sku": "SKU"
            }
        }
    )


@pytest.fixture
def sample_credentials() -> Dict[str, str]:
    """Sample credentials for testing."""
    return {
        "server_url": "https://test.docuware.cloud",
        "username": "test_user",
        "password": "test_password"
    }


# ==================== Mock Fixtures ====================

@pytest.fixture
def mock_docuware_client():
    """Mock DocuWare client for testing."""
    client = MagicMock()

    # Mock organizations and file cabinets
    org = MagicMock()
    cabinet1 = MagicMock()
    cabinet1.id = "cab-001"
    cabinet1.name = "Invoices"
    cabinet1.description = "Invoice storage"

    cabinet2 = MagicMock()
    cabinet2.id = "cab-002"
    cabinet2.name = "Contracts"
    cabinet2.description = "Contract storage"

    org.file_cabinets = [cabinet1, cabinet2]
    client.organizations = [org]

    # Mock login
    session = MagicMock()
    client.login.return_value = session

    return client


@pytest.fixture
def mock_docuware_session():
    """Mock DocuWare session for testing."""
    session = MagicMock()
    return session


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client for AI service testing."""
    client = MagicMock()

    # Mock message response
    message = MagicMock()
    message.content = [MagicMock()]
    message.content[0].text = """{
        "document_type": "Invoice",
        "vendor": "Test Vendor",
        "amount": 1500.00,
        "date": "2024-01-15"
    }"""

    client.messages.create.return_value = message

    return client


@pytest.fixture
def mock_file_service():
    """Mock file service for testing."""
    service = MagicMock()
    service.save_upload.return_value = Path("/tmp/test.pdf")
    service.organize_files.return_value = Path("/tmp/organized")
    return service


# ==================== Async Fixtures ====================

@pytest.fixture
async def mock_async_docuware_connector():
    """Mock DocuWare connector with async methods."""
    connector = MagicMock()

    # Make async methods return awaitable values
    connector.authenticate = AsyncMock(return_value=MagicMock())
    connector.test_connection = AsyncMock(return_value=(True, "Connected"))
    connector.get_file_cabinets = AsyncMock(return_value=[
        FileCabinet(id="cab-001", name="Invoices", description="Invoice cabinet")
    ])
    connector.get_storage_dialogs = AsyncMock(return_value=[
        StorageDialog(id="dialog-001", name="Store", description="Default storage")
    ])
    connector.get_index_fields = AsyncMock(return_value=[
        IndexField(name="VENDOR", type="String", required=True, is_system_field=False)
    ])
    connector.upload_document = AsyncMock(return_value="doc-12345")

    return connector


# ==================== Utility Fixtures ====================

@pytest.fixture
def temp_test_files(tmp_path):
    """Create temporary test files."""
    # Create a test PDF file (empty for testing)
    pdf_file = tmp_path / "test_invoice.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 test content")

    # Create a test text file
    txt_file = tmp_path / "test.txt"
    txt_file.write_text("Test extracted text from OCR")

    return {
        "pdf": pdf_file,
        "txt": txt_file,
        "dir": tmp_path
    }


@pytest.fixture
def reset_singletons():
    """Reset singleton instances between tests."""
    # Import singletons that need resetting
    from services.field_mapping_service import FieldMappingService

    # Clear singleton instance
    FieldMappingService._instance = None

    yield

    # Clean up after test
    FieldMappingService._instance = None


# ==================== Event Loop Fixture ====================

@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
