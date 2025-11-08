"""
Field Mapping Service for intelligent mapping between DocuFlow and DMS fields.
Uses fuzzy matching to auto-map extracted data fields to target system fields.
"""
from typing import Dict, List, Optional, Tuple, Any
from difflib import SequenceMatcher
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from models import IndexField, ExtractedData


class FieldMappingService:
    """
    Service for intelligently mapping DocuFlow extracted fields to DMS index fields.
    Uses fuzzy matching and semantic understanding to create optimal mappings.
    """

    # Known semantic equivalents for better matching
    SEMANTIC_MAPPINGS = {
        'vendor': ['vendor', 'supplier', 'seller', 'provider', 'vendor_name'],
        'client': ['client', 'customer', 'buyer', 'purchaser', 'client_name'],
        'company': ['company', 'organization', 'business', 'firm', 'company_name'],
        'person_name': ['person', 'name', 'employee', 'contact', 'individual'],
        'document_number': ['invoice', 'receipt', 'document', 'number', 'doc_no', 'inv_no'],
        'reference_number': ['reference', 'po', 'order', 'ref', 'po_number'],
        'date': ['date', 'invoice_date', 'doc_date', 'issue_date'],
        'due_date': ['due', 'due_date', 'payment_date', 'deadline'],
        'amount': ['amount', 'total', 'sum', 'value', 'price'],
        'currency': ['currency', 'curr', 'cur'],
        'address': ['address', 'location', 'addr'],
        'email': ['email', 'e_mail', 'mail'],
        'phone': ['phone', 'telephone', 'tel', 'mobile', 'contact_number'],
        'document_type': ['type', 'doc_type', 'category', 'document_type']
    }

    def auto_map_fields(
        self,
        extracted_data: ExtractedData,
        target_fields: List[IndexField]
    ) -> Dict[str, str]:
        """
        Intelligently map DocuFlow extracted fields to target system index fields.

        Args:
            extracted_data: Extracted data from document
            target_fields: List of available fields in target system

        Returns:
            Dictionary mapping DocuFlow field names to target field names
            Example: {
                "vendor": "VENDOR_NAME",
                "document_number": "INVOICE_NUMBER",
                "amount": "TOTAL_AMOUNT"
            }
        """
        mapping = {}

        # Get all non-null fields from extracted data
        source_fields = self._get_populated_fields(extracted_data)

        for source_field, source_value in source_fields.items():
            # Skip line_items and other_data (handled separately)
            if source_field in ['line_items', 'other_data']:
                continue

            # Find best matching target field
            best_match = self._find_best_match(source_field, target_fields)

            if best_match:
                mapping[source_field] = best_match.name

        return mapping

    def _get_populated_fields(self, extracted_data: ExtractedData) -> Dict[str, Any]:
        """
        Get dictionary of populated (non-null) fields from extracted data.

        Args:
            extracted_data: Extracted data object

        Returns:
            Dictionary of field_name: value for populated fields
        """
        fields = {}

        # Convert Pydantic model to dict
        data_dict = extracted_data.dict(exclude_none=True)

        for field_name, value in data_dict.items():
            if value is not None and value != "" and value != []:
                fields[field_name] = value

        return fields

    def _find_best_match(
        self,
        source_field: str,
        target_fields: List[IndexField],
        confidence_threshold: float = 0.6
    ) -> Optional[IndexField]:
        """
        Find the best matching target field for a source field.
        Uses fuzzy matching and semantic understanding.

        Args:
            source_field: DocuFlow field name (e.g., "vendor")
            target_fields: List of target system fields
            confidence_threshold: Minimum confidence score (0.0 to 1.0)

        Returns:
            Best matching IndexField or None if no good match found
        """
        best_score = 0.0
        best_field = None

        source_normalized = source_field.lower().replace('_', '').replace('-', '')

        for target_field in target_fields:
            target_normalized = target_field.name.lower().replace('_', '').replace('-', '')

            # Calculate match score
            score = self._calculate_match_score(
                source_field,
                source_normalized,
                target_field.name,
                target_normalized
            )

            if score > best_score:
                best_score = score
                best_field = target_field

        # Return match only if confidence is above threshold
        if best_score >= confidence_threshold:
            return best_field

        return None

    def _calculate_match_score(
        self,
        source_field: str,
        source_normalized: str,
        target_field: str,
        target_normalized: str
    ) -> float:
        """
        Calculate match score between source and target field names.
        Uses multiple strategies for robust matching.

        Args:
            source_field: Original source field name
            source_normalized: Normalized source field name
            target_field: Original target field name
            target_normalized: Normalized target field name

        Returns:
            Match score between 0.0 and 1.0
        """
        # Strategy 1: Exact match (100%)
        if source_normalized == target_normalized:
            return 1.0

        # Strategy 2: Source is substring of target (90%)
        if source_normalized in target_normalized:
            return 0.9

        # Strategy 3: Target is substring of source (85%)
        if target_normalized in source_normalized:
            return 0.85

        # Strategy 4: Semantic mapping (95%)
        semantic_score = self._check_semantic_match(source_field, target_field)
        if semantic_score > 0:
            return semantic_score

        # Strategy 5: Fuzzy string matching
        fuzzy_score = SequenceMatcher(None, source_normalized, target_normalized).ratio()

        return fuzzy_score

    def _check_semantic_match(self, source_field: str, target_field: str) -> float:
        """
        Check if fields are semantically equivalent based on known mappings.

        Args:
            source_field: Source field name
            target_field: Target field name

        Returns:
            Match score (0.95 if semantic match found, 0.0 otherwise)
        """
        source_lower = source_field.lower()
        target_lower = target_field.lower()

        # Check if source field has semantic equivalents
        if source_lower in self.SEMANTIC_MAPPINGS:
            equivalents = self.SEMANTIC_MAPPINGS[source_lower]

            # Check if any equivalent appears in target field
            for equiv in equivalents:
                if equiv in target_lower or target_lower in equiv:
                    return 0.95

        return 0.0

    def validate_mapping(
        self,
        mapping: Dict[str, str],
        target_fields: List[IndexField],
        extracted_data: ExtractedData
    ) -> Tuple[bool, List[str]]:
        """
        Validate that all required target fields have mapped sources with values.

        Args:
            mapping: Proposed field mapping
            target_fields: List of target fields with requirements
            extracted_data: Extracted data to check for values

        Returns:
            Tuple of (is_valid: bool, missing_fields: List[str])
            Example: (False, ["INVOICE_NUMBER", "VENDOR_NAME"])
        """
        missing_fields = []
        mapped_targets = set(mapping.values())

        # Check each required field
        for target_field in target_fields:
            if target_field.required:
                # Check if field is mapped
                if target_field.name not in mapped_targets:
                    missing_fields.append(target_field.name)
                else:
                    # Check if source has a value
                    source_field = self._find_source_for_target(target_field.name, mapping)
                    if source_field:
                        value = getattr(extracted_data, source_field, None)
                        if value is None or value == "":
                            missing_fields.append(f"{target_field.name} (no value in {source_field})")

        is_valid = len(missing_fields) == 0
        return is_valid, missing_fields

    def _find_source_for_target(self, target_name: str, mapping: Dict[str, str]) -> Optional[str]:
        """
        Find source field name for a given target field name.

        Args:
            target_name: Target field name
            mapping: Field mapping dictionary

        Returns:
            Source field name or None
        """
        for source, target in mapping.items():
            if target == target_name:
                return source
        return None

    def convert_value_for_field(
        self,
        value: Any,
        field: IndexField
    ) -> Any:
        """
        Convert extracted value to match target field type requirements.

        Args:
            value: Extracted value
            field: Target field specification

        Returns:
            Converted value appropriate for target field type
        """
        if value is None or value == "":
            return None

        field_type = field.type.lower()

        try:
            if field_type == "date":
                # Date conversion
                return self._parse_date(value)

            elif field_type in ["decimal", "float", "money"]:
                # Decimal/currency conversion
                return self._parse_decimal(value)

            elif field_type in ["integer", "int"]:
                # Integer conversion
                return int(float(str(value).replace(',', '')))

            elif field_type in ["text", "string"]:
                # Text conversion with max length check
                text = str(value)
                if field.max_length and len(text) > field.max_length:
                    # Truncate with warning
                    print(f"WARNING: Truncating field {field.name} from {len(text)} to {field.max_length} chars")
                    text = text[:field.max_length]
                return text

            else:
                # Default: return as string
                return str(value)

        except Exception as e:
            print(f"Failed to convert value '{value}' for field '{field.name}' (type: {field_type}): {e}")
            return str(value)

    def _parse_date(self, value: Any) -> str:
        """
        Parse date value into ISO format (YYYY-MM-DD).

        Args:
            value: Date string in various formats

        Returns:
            ISO formatted date string
        """
        from dateutil import parser

        try:
            # Try to parse date string
            if isinstance(value, str):
                dt = parser.parse(value, fuzzy=True)
                return dt.strftime("%Y-%m-%d")
            return str(value)
        except Exception:
            # Return as-is if parsing fails
            return str(value)

    def _parse_decimal(self, value: Any) -> float:
        """
        Parse decimal/currency value.

        Args:
            value: Currency string like "$1,234.56" or "€500.00"

        Returns:
            Float value
        """
        if isinstance(value, (int, float)):
            return float(value)

        # Remove currency symbols and commas
        value_str = str(value)
        cleaned = ''.join(c for c in value_str if c.isdigit() or c in '.-')

        try:
            return float(cleaned)
        except ValueError:
            return 0.0


# Singleton instance
_field_mapping_service = None


def get_field_mapping_service() -> FieldMappingService:
    """
    Get singleton instance of FieldMappingService.

    Returns:
        FieldMappingService instance
    """
    global _field_mapping_service
    if _field_mapping_service is None:
        _field_mapping_service = FieldMappingService()
    return _field_mapping_service
