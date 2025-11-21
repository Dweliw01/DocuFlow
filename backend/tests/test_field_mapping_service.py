"""
Unit tests for Field Mapping Service.
"""
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.field_mapping_service import FieldMappingService, get_field_mapping_service
from models import IndexField, ExtractedData, LineItem


@pytest.mark.unit
class TestFieldMappingServiceInit:
    """Test field mapping service initialization."""

    def test_singleton_pattern(self, reset_singletons):
        """Test that get_field_mapping_service returns singleton."""
        service1 = get_field_mapping_service()
        service2 = get_field_mapping_service()

        assert service1 is service2

    def test_semantic_mappings_defined(self):
        """Test that semantic mappings are properly defined."""
        service = FieldMappingService()

        assert 'vendor' in service.SEMANTIC_MAPPINGS
        assert 'client' in service.SEMANTIC_MAPPINGS
        assert 'amount' in service.SEMANTIC_MAPPINGS
        assert 'date' in service.SEMANTIC_MAPPINGS


@pytest.mark.unit
class TestFieldMappingServicePopulatedFields:
    """Test extraction of populated fields."""

    def test_get_populated_fields_all_fields(self, sample_extracted_data):
        """Test getting all populated fields from extracted data."""
        service = FieldMappingService()

        fields = service._get_populated_fields(sample_extracted_data)

        assert 'vendor' in fields
        assert 'amount' in fields
        assert 'document_number' in fields
        assert fields['vendor'] == "Acme Corporation"
        assert fields['amount'] == 1500.00

    def test_get_populated_fields_excludes_none(self):
        """Test that None values are excluded."""
        service = FieldMappingService()

        data = ExtractedData(
            document_type="Invoice",
            vendor="Test Vendor",
            amount=None,  # This should be excluded
            date=None  # This should be excluded
        )

        fields = service._get_populated_fields(data)

        assert 'vendor' in fields
        assert 'amount' not in fields
        assert 'date' not in fields

    def test_get_populated_fields_excludes_empty_string(self):
        """Test that empty strings are excluded."""
        service = FieldMappingService()

        data = ExtractedData(
            document_type="Invoice",
            vendor="",  # Should be excluded
            amount=100.00
        )

        fields = service._get_populated_fields(data)

        assert 'vendor' not in fields
        assert 'amount' in fields

    def test_get_populated_fields_excludes_empty_list(self):
        """Test that empty lists are excluded."""
        service = FieldMappingService()

        data = ExtractedData(
            document_type="Invoice",
            amount=100.00,
            line_items=[]  # Should be excluded
        )

        fields = service._get_populated_fields(data)

        assert 'amount' in fields
        assert 'line_items' not in fields


@pytest.mark.unit
class TestFieldMappingServiceMatchScore:
    """Test match score calculation."""

    def test_calculate_match_score_exact_match(self):
        """Test exact match returns perfect score."""
        service = FieldMappingService()

        score = service._calculate_match_score(
            "vendor", "vendor",
            "VENDOR", "vendor"
        )

        assert score == 1.0

    def test_calculate_match_score_substring_source_in_target(self):
        """Test source substring in target."""
        service = FieldMappingService()

        score = service._calculate_match_score(
            "vendor", "vendor",
            "VENDOR_NAME", "vendorname"
        )

        assert score == 0.9

    def test_calculate_match_score_substring_target_in_source(self):
        """Test target substring in source."""
        service = FieldMappingService()

        score = service._calculate_match_score(
            "vendor_name", "vendorname",
            "VENDOR", "vendor"
        )

        assert score == 0.85

    def test_calculate_match_score_semantic_match(self):
        """Test semantic matching."""
        service = FieldMappingService()

        # "vendor" and "supplier" are semantically equivalent
        score = service._calculate_match_score(
            "vendor", "vendor",
            "SUPPLIER", "supplier"
        )

        assert score == 0.95

    def test_calculate_match_score_fuzzy_match(self):
        """Test fuzzy string matching."""
        service = FieldMappingService()

        # Similar but not identical
        score = service._calculate_match_score(
            "invoice_num", "invoicenum",
            "INVOICE_NUMBER", "invoicenumber"
        )

        # Should be high but not 100%
        assert 0.7 < score < 1.0


@pytest.mark.unit
class TestFieldMappingServiceSemanticMatch:
    """Test semantic matching functionality."""

    def test_check_semantic_match_vendor_supplier(self):
        """Test vendor-supplier semantic equivalence."""
        service = FieldMappingService()

        score = service._check_semantic_match("vendor", "SUPPLIER_NAME")

        assert score == 0.95

    def test_check_semantic_match_client_customer(self):
        """Test client-customer semantic equivalence."""
        service = FieldMappingService()

        score = service._check_semantic_match("client", "CUSTOMER_NAME")

        assert score == 0.95

    def test_check_semantic_match_amount_total(self):
        """Test amount-total semantic equivalence."""
        service = FieldMappingService()

        score = service._check_semantic_match("amount", "TOTAL_AMOUNT")

        assert score == 0.95

    def test_check_semantic_match_no_match(self):
        """Test no semantic match returns 0."""
        service = FieldMappingService()

        score = service._check_semantic_match("vendor", "UNRELATED_FIELD")

        assert score == 0.0


@pytest.mark.unit
class TestFieldMappingServiceBestMatch:
    """Test finding best field matches."""

    def test_find_best_match_direct_match(self, sample_index_fields):
        """Test finding exact match."""
        service = FieldMappingService()

        best = service._find_best_match("vendor", sample_index_fields)

        assert best is not None
        assert best.name == "VENDOR_NAME"

    def test_find_best_match_semantic_match(self):
        """Test finding semantic match."""
        service = FieldMappingService()

        fields = [
            IndexField(name="SUPPLIER_NAME", type="String", required=True, is_system_field=False),
            IndexField(name="OTHER_FIELD", type="String", required=False, is_system_field=False)
        ]

        best = service._find_best_match("vendor", fields)

        assert best is not None
        assert best.name == "SUPPLIER_NAME"

    def test_find_best_match_below_threshold(self):
        """Test that low-confidence matches are rejected."""
        service = FieldMappingService()

        fields = [
            IndexField(name="COMPLETELY_UNRELATED", type="String", required=False, is_system_field=False)
        ]

        best = service._find_best_match("vendor", fields, confidence_threshold=0.6)

        assert best is None

    def test_find_best_match_custom_threshold(self, sample_index_fields):
        """Test custom confidence threshold."""
        service = FieldMappingService()

        # Use very high threshold
        best = service._find_best_match("vendor", sample_index_fields, confidence_threshold=0.99)

        # Should still find exact/semantic match
        assert best is not None


@pytest.mark.unit
class TestFieldMappingServiceAutoMap:
    """Test automatic field mapping."""

    def test_auto_map_fields_basic(self, sample_extracted_data, sample_index_fields):
        """Test basic auto-mapping of fields."""
        service = FieldMappingService()

        mapping = service.auto_map_fields(sample_extracted_data, sample_index_fields)

        assert 'vendor' in mapping
        assert mapping['vendor'] == 'VENDOR_NAME'
        assert 'date' in mapping
        assert 'amount' in mapping

    def test_auto_map_fields_skips_line_items(self, sample_extracted_data, sample_index_fields):
        """Test that line_items are skipped in auto-mapping."""
        service = FieldMappingService()

        mapping = service.auto_map_fields(sample_extracted_data, sample_index_fields)

        assert 'line_items' not in mapping

    def test_auto_map_fields_skips_other_data(self, sample_extracted_data, sample_index_fields):
        """Test that other_data is skipped in auto-mapping."""
        service = FieldMappingService()

        mapping = service.auto_map_fields(sample_extracted_data, sample_index_fields)

        assert 'other_data' not in mapping

    def test_auto_map_fields_empty_extracted_data(self, sample_index_fields):
        """Test auto-mapping with minimal data."""
        service = FieldMappingService()

        data = ExtractedData(document_type="Invoice")
        mapping = service.auto_map_fields(data, sample_index_fields)

        # Should map document_type
        assert 'document_type' in mapping

    def test_auto_map_fields_no_matches(self):
        """Test auto-mapping when no fields match."""
        service = FieldMappingService()

        data = ExtractedData(document_type="Invoice", vendor="Test")

        # Fields with completely different names
        fields = [
            IndexField(name="ZZZZZ_UNRELATED", type="String", required=False, is_system_field=False)
        ]

        mapping = service.auto_map_fields(data, fields)

        # Should return empty or minimal mapping
        assert isinstance(mapping, dict)


@pytest.mark.unit
class TestFieldMappingServiceValidation:
    """Test field mapping validation."""

    def test_validate_mapping_all_required_fields_present(self, sample_extracted_data):
        """Test validation passes when all required fields are mapped."""
        service = FieldMappingService()

        mapping = {
            "vendor": "VENDOR_NAME",
            "date": "INVOICE_DATE",
            "amount": "INVOICE_AMOUNT"
        }

        fields = [
            IndexField(name="VENDOR_NAME", type="String", required=True, is_system_field=False),
            IndexField(name="INVOICE_DATE", type="Date", required=True, is_system_field=False),
            IndexField(name="INVOICE_AMOUNT", type="Decimal", required=True, is_system_field=False)
        ]

        is_valid, missing = service.validate_mapping(mapping, fields, sample_extracted_data)

        assert is_valid is True
        assert len(missing) == 0

    def test_validate_mapping_missing_required_field(self, sample_extracted_data):
        """Test validation fails when required field is not mapped."""
        service = FieldMappingService()

        mapping = {
            "vendor": "VENDOR_NAME"
            # Missing "amount" mapping
        }

        fields = [
            IndexField(name="VENDOR_NAME", type="String", required=True, is_system_field=False),
            IndexField(name="INVOICE_AMOUNT", type="Decimal", required=True, is_system_field=False)
        ]

        is_valid, missing = service.validate_mapping(mapping, fields, sample_extracted_data)

        assert is_valid is False
        assert "INVOICE_AMOUNT" in missing

    def test_validate_mapping_mapped_but_no_value(self):
        """Test validation fails when field is mapped but has no value."""
        service = FieldMappingService()

        # Data with missing vendor value
        data = ExtractedData(
            document_type="Invoice",
            vendor=None,  # No value
            amount=100.00
        )

        mapping = {
            "vendor": "VENDOR_NAME",
            "amount": "INVOICE_AMOUNT"
        }

        fields = [
            IndexField(name="VENDOR_NAME", type="String", required=True, is_system_field=False),
            IndexField(name="INVOICE_AMOUNT", type="Decimal", required=True, is_system_field=False)
        ]

        is_valid, missing = service.validate_mapping(mapping, fields, data)

        assert is_valid is False
        assert any("VENDOR_NAME" in m for m in missing)

    def test_find_source_for_target(self):
        """Test finding source field for target."""
        service = FieldMappingService()

        mapping = {
            "vendor": "VENDOR_NAME",
            "amount": "TOTAL_AMOUNT"
        }

        source = service._find_source_for_target("VENDOR_NAME", mapping)
        assert source == "vendor"

        source = service._find_source_for_target("TOTAL_AMOUNT", mapping)
        assert source == "amount"

        source = service._find_source_for_target("NOT_MAPPED", mapping)
        assert source is None


@pytest.mark.unit
class TestFieldMappingServiceValueConversion:
    """Test value conversion for different field types."""

    def test_convert_value_string(self):
        """Test string value conversion."""
        service = FieldMappingService()

        field = IndexField(name="TEST", type="String", required=False, is_system_field=False)
        result = service.convert_value_for_field("Test Value", field)

        assert result == "Test Value"

    def test_convert_value_string_truncation(self):
        """Test string truncation when exceeding max_length."""
        service = FieldMappingService()

        field = IndexField(
            name="TEST",
            type="String",
            required=False,
            max_length=10,
            is_system_field=False
        )

        long_value = "This is a very long string that exceeds the limit"
        result = service.convert_value_for_field(long_value, field)

        assert len(result) == 10

    def test_convert_value_decimal(self):
        """Test decimal value conversion."""
        service = FieldMappingService()

        field = IndexField(name="AMOUNT", type="Decimal", required=False, is_system_field=False)

        result = service.convert_value_for_field("123.45", field)
        assert result == 123.45

        result = service.convert_value_for_field(100, field)
        assert result == 100.0

    def test_convert_value_integer(self):
        """Test integer value conversion."""
        service = FieldMappingService()

        field = IndexField(name="QTY", type="Integer", required=False, is_system_field=False)

        result = service.convert_value_for_field("42", field)
        assert result == 42

        result = service.convert_value_for_field("42.7", field)
        assert result == 42  # Should truncate decimals

    def test_convert_value_date(self):
        """Test date value conversion."""
        service = FieldMappingService()

        field = IndexField(name="DATE", type="Date", required=False, is_system_field=False)

        result = service.convert_value_for_field("2024-01-15", field)
        assert result == "2024-01-15"

    def test_convert_value_none(self):
        """Test None value returns None."""
        service = FieldMappingService()

        field = IndexField(name="TEST", type="String", required=False, is_system_field=False)

        result = service.convert_value_for_field(None, field)
        assert result is None

    def test_convert_value_empty_string(self):
        """Test empty string returns None."""
        service = FieldMappingService()

        field = IndexField(name="TEST", type="String", required=False, is_system_field=False)

        result = service.convert_value_for_field("", field)
        assert result is None


@pytest.mark.unit
class TestFieldMappingServiceParseDecimal:
    """Test decimal parsing."""

    def test_parse_decimal_clean_number(self):
        """Test parsing clean decimal number."""
        service = FieldMappingService()

        assert service._parse_decimal("123.45") == 123.45
        assert service._parse_decimal(100.5) == 100.5
        assert service._parse_decimal(42) == 42.0

    def test_parse_decimal_with_currency_symbols(self):
        """Test parsing numbers with currency symbols."""
        service = FieldMappingService()

        assert service._parse_decimal("$1,234.56") == 1234.56
        assert service._parse_decimal("€500.00") == 500.0
        assert service._parse_decimal("£99.99") == 99.99

    def test_parse_decimal_invalid_input(self):
        """Test parsing invalid decimal input."""
        service = FieldMappingService()

        # Invalid input should return 0.0
        assert service._parse_decimal("invalid") == 0.0
        assert service._parse_decimal("abc") == 0.0


@pytest.mark.unit
class TestFieldMappingServiceParseDate:
    """Test date parsing."""

    def test_parse_date_iso_format(self):
        """Test parsing ISO date format."""
        service = FieldMappingService()

        result = service._parse_date("2024-01-15")
        assert result == "2024-01-15"

    def test_parse_date_various_formats(self):
        """Test parsing various date formats."""
        service = FieldMappingService()

        # These should all parse to the same date
        result = service._parse_date("01/15/2024")
        assert "2024" in result and "01" in result and "15" in result

        result = service._parse_date("January 15, 2024")
        assert "2024" in result

    def test_parse_date_invalid_input(self):
        """Test parsing invalid date input."""
        service = FieldMappingService()

        # Should return string as-is if parsing fails
        result = service._parse_date("not a date")
        assert isinstance(result, str)

    def test_parse_date_already_string(self):
        """Test parsing when value is already a valid date string."""
        service = FieldMappingService()

        result = service._parse_date("2024-01-15")
        assert result == "2024-01-15"
