"""
Unit tests for AI Service.
"""
import pytest
import json
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.ai_service import AIService
from models import DocumentCategory, ExtractedData, LineItem


@pytest.mark.unit
class TestAIServiceInit:
    """Test AI service initialization."""

    @patch('services.ai_service.Anthropic')
    def test_initialization_success(self, mock_anthropic):
        """Test successful AI service initialization."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        service = AIService()

        assert service.client is not None
        assert service.model is not None

    @patch('services.ai_service.Anthropic')
    def test_initialization_with_api_key(self, mock_anthropic):
        """Test that API key is passed to Anthropic client."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        with patch('services.ai_service.settings') as mock_settings:
            mock_settings.anthropic_api_key = "test-key-123"
            mock_settings.claude_model = "claude-haiku-4.5"

            service = AIService()

            mock_anthropic.assert_called_once()


@pytest.mark.unit
class TestAIServiceCategoryMatching:
    """Test category matching logic."""

    @patch('services.ai_service.Anthropic')
    def test_match_category_exact_match(self, mock_anthropic):
        """Test exact category matching."""
        service = AIService()

        assert service._match_category("Invoice") == DocumentCategory.INVOICE
        assert service._match_category("Contract") == DocumentCategory.CONTRACT
        assert service._match_category("Receipt") == DocumentCategory.RECEIPT

    @patch('services.ai_service.Anthropic')
    def test_match_category_case_insensitive(self, mock_anthropic):
        """Test case-insensitive matching."""
        service = AIService()

        assert service._match_category("INVOICE") == DocumentCategory.INVOICE
        assert service._match_category("invoice") == DocumentCategory.INVOICE
        assert service._match_category("InVoIcE") == DocumentCategory.INVOICE

    @patch('services.ai_service.Anthropic')
    def test_match_category_partial_match(self, mock_anthropic):
        """Test partial/fuzzy category matching."""
        service = AIService()

        assert service._match_category("Purchase Invoice") == DocumentCategory.INVOICE
        assert service._match_category("Service Contract") == DocumentCategory.CONTRACT
        assert service._match_category("Payment Receipt") == DocumentCategory.RECEIPT

    @patch('services.ai_service.Anthropic')
    def test_match_category_default_to_other(self, mock_anthropic):
        """Test default to OTHER for unrecognized categories."""
        service = AIService()

        assert service._match_category("Unknown Category") == DocumentCategory.OTHER
        assert service._match_category("") == DocumentCategory.OTHER
        assert service._match_category("Random Text") == DocumentCategory.OTHER


@pytest.mark.unit
class TestAIServicePromptBuilding:
    """Test prompt construction."""

    @patch('services.ai_service.Anthropic')
    def test_build_categorization_prompt_basic(self, mock_anthropic):
        """Test basic categorization prompt building."""
        service = AIService()

        prompt = service._build_categorization_prompt(
            text="This is a test invoice",
            filename="invoice.pdf"
        )

        assert "invoice.pdf" in prompt
        assert "test invoice" in prompt
        assert "category" in prompt.lower()
        assert "confidence" in prompt.lower()

    @patch('services.ai_service.Anthropic')
    def test_build_categorization_prompt_truncates_long_text(self, mock_anthropic):
        """Test that long text is truncated."""
        service = AIService()

        long_text = "A" * 10000  # Very long text
        prompt = service._build_categorization_prompt(
            text=long_text,
            filename="test.pdf"
        )

        # Prompt should be shorter than original text
        assert len(prompt) < len(long_text) + 2000  # Allow for prompt template
        assert "[truncated]" in prompt

    @patch('services.ai_service.Anthropic')
    def test_build_dynamic_extraction_prompt_with_fields(self, mock_anthropic):
        """Test dynamic extraction prompt with specific fields."""
        service = AIService()

        selected_fields = ["VENDOR_NAME", "INVOICE_DATE", "AMOUNT"]

        prompt = service._build_dynamic_extraction_prompt(
            text="Test invoice text",
            filename="invoice.pdf",
            selected_fields=selected_fields,
            selected_table_columns=None
        )

        assert "VENDOR_NAME" in prompt
        assert "INVOICE_DATE" in prompt
        assert "AMOUNT" in prompt
        assert "EXACT field names" in prompt

    @patch('services.ai_service.Anthropic')
    def test_build_dynamic_extraction_prompt_with_table_columns(self, mock_anthropic):
        """Test dynamic extraction prompt with table columns."""
        service = AIService()

        selected_fields = ["VENDOR_NAME"]
        table_columns = {
            "LINE_ITEMS": [
                {"label": "Description", "name": "DESCRIPTION"},
                {"label": "Quantity", "name": "QTY"}
            ]
        }

        prompt = service._build_dynamic_extraction_prompt(
            text="Test invoice text",
            filename="invoice.pdf",
            selected_fields=selected_fields,
            selected_table_columns=table_columns
        )

        assert "line items" in prompt.lower()
        assert "Description" in prompt
        assert "Quantity" in prompt


@pytest.mark.unit
class TestAIServiceResponseParsing:
    """Test AI response parsing."""

    @patch('services.ai_service.Anthropic')
    def test_parse_categorization_response_valid_json(self, mock_anthropic):
        """Test parsing valid JSON response."""
        service = AIService()

        response = json.dumps({
            "category": "Invoice",
            "confidence": 0.95,
            "extracted_data": {
                "vendor": "Test Vendor",
                "amount": "$1,234.56",
                "date": "2024-01-15"
            }
        })

        category, confidence, extracted_data = service._parse_categorization_response(response)

        assert category == DocumentCategory.INVOICE
        assert confidence == 0.95
        assert extracted_data is not None
        assert extracted_data.vendor == "Test Vendor"

    @patch('services.ai_service.Anthropic')
    def test_parse_categorization_response_with_markdown(self, mock_anthropic):
        """Test parsing response wrapped in markdown code blocks."""
        service = AIService()

        response = """```json
{
    "category": "Invoice",
    "confidence": 0.90
}
```"""

        category, confidence, extracted_data = service._parse_categorization_response(response)

        assert category == DocumentCategory.INVOICE
        assert confidence == 0.90

    @patch('services.ai_service.Anthropic')
    def test_parse_categorization_response_clamps_confidence(self, mock_anthropic):
        """Test that confidence is clamped between 0 and 1."""
        service = AIService()

        # Test upper bound
        response_high = json.dumps({"category": "Invoice", "confidence": 1.5})
        _, confidence, _ = service._parse_categorization_response(response_high)
        assert confidence == 1.0

        # Test lower bound
        response_low = json.dumps({"category": "Invoice", "confidence": -0.5})
        _, confidence, _ = service._parse_categorization_response(response_low)
        assert confidence == 0.0

    @patch('services.ai_service.Anthropic')
    def test_parse_categorization_response_invalid_json(self, mock_anthropic):
        """Test parsing invalid JSON returns fallback."""
        service = AIService()

        response = "This is not valid JSON"

        category, confidence, extracted_data = service._parse_categorization_response(response)

        assert category == DocumentCategory.OTHER
        assert confidence == 0.3
        assert extracted_data is None

    @patch('services.ai_service.Anthropic')
    def test_parse_categorization_response_with_line_items(self, mock_anthropic):
        """Test parsing response with line items."""
        service = AIService()

        response = json.dumps({
            "category": "Invoice",
            "confidence": 0.95,
            "extracted_data": {
                "vendor": "Test Vendor",
                "line_items": [
                    {
                        "description": "Product A",
                        "quantity": "10",
                        "unit_price": "50.00",
                        "amount": "500.00"
                    }
                ]
            }
        })

        category, confidence, extracted_data = service._parse_categorization_response(response)

        assert extracted_data is not None
        assert extracted_data.line_items is not None
        assert len(extracted_data.line_items) == 1
        assert extracted_data.line_items[0].description == "Product A"


@pytest.mark.unit
class TestAIServiceDynamicExtractionParsing:
    """Test dynamic extraction response parsing."""

    @patch('services.ai_service.Anthropic')
    def test_parse_dynamic_extraction_basic(self, mock_anthropic):
        """Test parsing basic dynamic extraction response."""
        service = AIService()

        response = json.dumps({
            "category": "Invoice",
            "confidence": 0.95,
            "extracted_fields": {
                "VENDOR_NAME": "Acme Corp",
                "INVOICE_DATE": "2024-01-15",
                "AMOUNT": "$1,234.56"
            }
        })

        selected_fields = ["VENDOR_NAME", "INVOICE_DATE", "AMOUNT"]

        category, confidence, extracted_data = service._parse_dynamic_extraction_response(
            response, selected_fields
        )

        assert category == DocumentCategory.INVOICE
        assert confidence == 0.95
        assert extracted_data is not None
        assert extracted_data.other_data is not None
        assert extracted_data.other_data["VENDOR_NAME"] == "Acme Corp"

    @patch('services.ai_service.Anthropic')
    def test_parse_dynamic_extraction_with_line_items(self, mock_anthropic):
        """Test parsing dynamic extraction with line items."""
        service = AIService()

        response = json.dumps({
            "category": "Invoice",
            "confidence": 0.95,
            "extracted_fields": {
                "VENDOR_NAME": "Acme Corp"
            },
            "line_items": [
                {
                    "description": "Product A",
                    "quantity": "5",
                    "unit_price": "100.00",
                    "amount": "500.00",
                    "sku": "SKU-A-001"
                },
                {
                    "description": "Product B",
                    "quantity": "3",
                    "unit_price": "75.00",
                    "amount": "225.00",
                    "sku": "SKU-B-002"
                }
            ]
        })

        selected_fields = ["VENDOR_NAME"]

        category, confidence, extracted_data = service._parse_dynamic_extraction_response(
            response, selected_fields
        )

        assert extracted_data is not None
        assert extracted_data.line_items is not None
        assert len(extracted_data.line_items) == 2
        assert extracted_data.line_items[0].sku == "SKU-A-001"

    @patch('services.ai_service.Anthropic')
    def test_parse_dynamic_extraction_field_mapping(self, mock_anthropic):
        """Test that DocuWare fields are mapped to ExtractedData fields."""
        service = AIService()

        response = json.dumps({
            "category": "Invoice",
            "confidence": 0.95,
            "extracted_fields": {
                "VENDOR_NAME": "Test Vendor",
                "CUSTOMER_NAME": "Test Customer",
                "INVOICE_AMOUNT": "1000.00",
                "INVOICE_NO": "INV-001",
                "PO_NUMBER": "PO-12345",
                "ORDER_DATE": "2024-01-15"
            }
        })

        selected_fields = list(response)

        category, confidence, extracted_data = service._parse_dynamic_extraction_response(
            response, selected_fields
        )

        # Check that fields are mapped correctly
        assert extracted_data.vendor == "Test Vendor"
        assert extracted_data.client == "Test Customer"
        assert extracted_data.amount == "1000.00"
        assert extracted_data.document_number == "INV-001"
        assert extracted_data.reference_number == "PO-12345"
        assert extracted_data.date == "2024-01-15"

    @patch('services.ai_service.Anthropic')
    def test_parse_dynamic_extraction_preserves_exact_field_names(self, mock_anthropic):
        """Test that exact DocuWare field names are preserved in other_data."""
        service = AIService()

        # Test with field names that have typos/unusual formatting
        response = json.dumps({
            "category": "Invoice",
            "confidence": 0.95,
            "extracted_fields": {
                "INVOCE_NO_": "INV-001",  # Typo + trailing underscore
                "ZIP_": "12345",  # Trailing underscore
                "CUSTOMER_P_O__DELIVERY_ADDRES": "123 Main St"  # Double underscore + missing 'S'
            }
        })

        selected_fields = ["INVOCE_NO_", "ZIP_", "CUSTOMER_P_O__DELIVERY_ADDRES"]

        category, confidence, extracted_data = service._parse_dynamic_extraction_response(
            response, selected_fields
        )

        # Check that exact field names are in other_data
        assert "INVOCE_NO_" in extracted_data.other_data
        assert "ZIP_" in extracted_data.other_data
        assert "CUSTOMER_P_O__DELIVERY_ADDRES" in extracted_data.other_data


@pytest.mark.unit
@pytest.mark.asyncio
class TestAIServiceCategorization:
    """Test end-to-end document categorization."""

    @patch('services.ai_service.Anthropic')
    async def test_categorize_document_success(self, mock_anthropic):
        """Test successful document categorization."""
        # Setup mock response
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock()]
        mock_message.content[0].text = json.dumps({
            "category": "Invoice",
            "confidence": 0.95,
            "extracted_data": {
                "vendor": "Test Vendor",
                "amount": "$1,234.56"
            }
        })

        mock_client.messages.create.return_value = mock_message
        mock_anthropic.return_value = mock_client

        service = AIService()

        category, confidence, extracted_data = await service.categorize_document(
            text="Test invoice text",
            filename="invoice.pdf"
        )

        assert category == DocumentCategory.INVOICE
        assert confidence == 0.95
        assert extracted_data.vendor == "Test Vendor"

    @patch('services.ai_service.Anthropic')
    async def test_categorize_document_with_dynamic_fields(self, mock_anthropic):
        """Test document categorization with dynamic field extraction."""
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock()]
        mock_message.content[0].text = json.dumps({
            "category": "Invoice",
            "confidence": 0.95,
            "extracted_fields": {
                "VENDOR_NAME": "Acme Corp",
                "AMOUNT": "1000.00"
            },
            "line_items": []
        })

        mock_client.messages.create.return_value = mock_message
        mock_anthropic.return_value = mock_client

        service = AIService()

        selected_fields = ["VENDOR_NAME", "AMOUNT"]

        category, confidence, extracted_data = await service.categorize_document(
            text="Test invoice text",
            filename="invoice.pdf",
            selected_fields=selected_fields
        )

        assert category == DocumentCategory.INVOICE
        assert extracted_data.other_data["VENDOR_NAME"] == "Acme Corp"

    @patch('services.ai_service.Anthropic')
    async def test_categorize_document_api_error(self, mock_anthropic):
        """Test categorization when API call fails."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API Error")
        mock_anthropic.return_value = mock_client

        service = AIService()

        category, confidence, extracted_data = await service.categorize_document(
            text="Test text",
            filename="test.pdf"
        )

        # Should return fallback values
        assert category == DocumentCategory.OTHER
        assert confidence == 0.3
        assert extracted_data is None

    @patch('services.ai_service.Anthropic')
    async def test_categorize_document_with_table_columns(self, mock_anthropic):
        """Test categorization with table column extraction."""
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock()]
        mock_message.content[0].text = json.dumps({
            "category": "Invoice",
            "confidence": 0.95,
            "extracted_fields": {
                "VENDOR_NAME": "Acme Corp"
            },
            "line_items": [
                {
                    "description": "Widget",
                    "quantity": "10",
                    "unit_price": "50.00",
                    "amount": "500.00"
                }
            ]
        })

        mock_client.messages.create.return_value = mock_message
        mock_anthropic.return_value = mock_client

        service = AIService()

        selected_fields = ["VENDOR_NAME"]
        table_columns = {
            "LINE_ITEMS": [
                {"label": "Description", "name": "DESCRIPTION"},
                {"label": "Quantity", "name": "QTY"}
            ]
        }

        category, confidence, extracted_data = await service.categorize_document(
            text="Test invoice with line items",
            filename="invoice.pdf",
            selected_fields=selected_fields,
            selected_table_columns=table_columns
        )

        assert category == DocumentCategory.INVOICE
        assert extracted_data.line_items is not None
        assert len(extracted_data.line_items) == 1


@pytest.mark.unit
class TestAIServiceEdgeCases:
    """Test edge cases and error handling."""

    @patch('services.ai_service.Anthropic')
    def test_parse_response_missing_extracted_data(self, mock_anthropic):
        """Test parsing response without extracted_data field."""
        service = AIService()

        response = json.dumps({
            "category": "Invoice",
            "confidence": 0.80
            # No extracted_data field
        })

        category, confidence, extracted_data = service._parse_categorization_response(response)

        assert category == DocumentCategory.INVOICE
        assert confidence == 0.80
        assert extracted_data is None

    @patch('services.ai_service.Anthropic')
    def test_parse_response_malformed_extracted_data(self, mock_anthropic):
        """Test parsing response with malformed extracted_data."""
        service = AIService()

        response = json.dumps({
            "category": "Invoice",
            "confidence": 0.90,
            "extracted_data": "this should be an object not a string"
        })

        category, confidence, extracted_data = service._parse_categorization_response(response)

        # Should handle gracefully
        assert category == DocumentCategory.INVOICE
        assert confidence == 0.90

    @patch('services.ai_service.Anthropic')
    def test_parse_dynamic_response_empty_line_items(self, mock_anthropic):
        """Test parsing dynamic response with empty line items."""
        service = AIService()

        response = json.dumps({
            "category": "Invoice",
            "confidence": 0.95,
            "extracted_fields": {},
            "line_items": []
        })

        category, confidence, extracted_data = service._parse_dynamic_extraction_response(
            response, []
        )

        assert extracted_data is not None
        assert extracted_data.line_items == [] or extracted_data.line_items is None
