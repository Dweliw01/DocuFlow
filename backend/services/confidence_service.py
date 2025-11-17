"""
Confidence score calculation for extracted data.
Initially uses heuristic-based scoring, can be upgraded to ML-based later.
"""

import re
from typing import Dict, Any


def calculate_field_confidence(field_name: str, value: Any) -> float:
    """
    Calculate confidence score for a single field.

    Args:
        field_name: Name of the field (e.g., 'amount', 'date', 'vendor')
        value: Extracted value for the field

    Returns:
        Float between 0.0 and 1.0 representing confidence
    """
    if not value or str(value).strip() == '':
        return 0.3  # Low confidence for empty fields

    value_str = str(value).strip()

    # Amount field validation
    if field_name in ['amount', 'total', 'subtotal']:
        if re.match(r'^\$?[\d,]+\.\d{2}$', value_str):
            return 0.95  # High confidence - proper currency format
        elif re.match(r'^\$?[\d,]+', value_str):
            return 0.75  # Medium - has numbers
        else:
            return 0.50  # Low - doesn't look like amount

    # Date field validation
    if field_name in ['date', 'due_date', 'invoice_date']:
        try:
            # Try parsing as date
            from dateutil import parser
            parser.parse(value_str)
            return 0.93  # High confidence - valid date
        except:
            # Check for common date patterns
            if re.match(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', value_str):
                return 0.85  # Looks like a date
            return 0.55  # Low - not a valid date

    # Email validation
    if field_name == 'email':
        if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', value_str):
            return 0.96  # High confidence - valid email format
        else:
            return 0.50

    # Phone validation
    if field_name == 'phone':
        if re.match(r'^[\d\s\-\(\)\.]{10,}$', value_str):
            return 0.88  # High confidence - looks like phone
        else:
            return 0.60

    # Vendor/Company names
    if field_name in ['vendor', 'client', 'company']:
        if len(value_str) >= 3 and len(value_str) <= 100:
            return 0.80  # Medium-high confidence
        else:
            return 0.60

    # Document numbers
    if field_name in ['document_number', 'invoice_number', 'po_number', 'reference_number']:
        if len(value_str) >= 3:
            return 0.85
        else:
            return 0.55

    # Default: if we have a value, medium confidence
    if len(value_str) > 0:
        return 0.75

    return 0.50


def calculate_overall_confidence(extracted_data: Dict[str, Any]) -> float:
    """
    Calculate overall confidence score for entire document.
    Returns weighted average of field confidences.

    Args:
        extracted_data: Dictionary of extracted fields and values

    Returns:
        Float between 0.0 and 1.0 representing overall confidence
    """
    if not extracted_data:
        return 0.0

    # Weight important fields higher
    field_weights = {
        'amount': 2.0,
        'date': 1.5,
        'vendor': 1.5,
        'document_number': 1.2,
        'invoice_number': 1.2,
    }

    total_score = 0.0
    total_weight = 0.0

    for field_name, value in extracted_data.items():
        # Skip line items and metadata
        if field_name in ['line_items', 'id', 'user_id', 'created_at', 'other_data']:
            continue

        # Handle nested value objects (if already scored)
        if isinstance(value, dict) and 'value' in value:
            value = value['value']

        confidence = calculate_field_confidence(field_name, value)
        weight = field_weights.get(field_name, 1.0)

        total_score += confidence * weight
        total_weight += weight

    if total_weight == 0:
        return 0.0

    overall = total_score / total_weight
    return round(overall, 2)


def add_confidence_to_extracted_data(extracted_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform extracted data to include confidence scores for each field.

    Input:  {'vendor': 'Acme Corp', 'amount': '$1,234'}
    Output: {
        'vendor': {'value': 'Acme Corp', 'confidence': 0.80},
        'amount': {'value': '$1,234', 'confidence': 0.95}
    }

    Args:
        extracted_data: Dictionary of extracted fields

    Returns:
        Dictionary with confidence scores added to each field
    """
    scored_data = {}

    for field_name, value in extracted_data.items():
        # Skip special fields - keep as is
        if field_name in ['line_items', 'other_data']:
            scored_data[field_name] = value
            continue

        # Already scored? Skip
        if isinstance(value, dict) and 'confidence' in value:
            scored_data[field_name] = value
            continue

        confidence = calculate_field_confidence(field_name, value)
        scored_data[field_name] = {
            'value': value,
            'confidence': confidence
        }

    return scored_data


def get_confidence_badge_info(confidence: float) -> Dict[str, str]:
    """
    Get badge display information for a confidence score.

    Args:
        confidence: Confidence score (0.0 - 1.0)

    Returns:
        Dictionary with 'class', 'label', and 'icon' for UI display
    """
    if confidence >= 0.9:
        return {
            'class': 'confidence-high',
            'label': f'✓ {int(confidence * 100)}%',
            'icon': 'check',
            'level': 'high'
        }
    elif confidence >= 0.7:
        return {
            'class': 'confidence-medium',
            'label': f'⚠ {int(confidence * 100)}%',
            'icon': 'warning',
            'level': 'medium'
        }
    else:
        return {
            'class': 'confidence-low',
            'label': f'❌ {int(confidence * 100)}%',
            'icon': 'times',
            'level': 'low'
        }
