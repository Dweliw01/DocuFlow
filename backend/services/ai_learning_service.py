"""
AI Learning Service - Learns from user corrections to improve extraction accuracy.

Features:
1. Query past corrections for similar documents/fields
2. Adjust confidence scores based on correction patterns
3. Suggest field values based on historical corrections
4. Track error-prone fields for review flagging
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from database import get_db_connection
from typing import Dict, Any, List, Optional, Tuple
import logging
from collections import Counter
import json

logger = logging.getLogger(__name__)


class AILearningService:
    """
    Service for learning from user corrections and improving AI extraction.
    """

    def __init__(self):
        """Initialize the AI learning service."""
        self.min_corrections_for_learning = 3  # Minimum corrections needed to apply learning
        logger.info("AI Learning Service initialized")

    def get_correction_patterns(self, organization_id: int, field_name: str, limit: int = 50) -> Dict[str, Any]:
        """
        Analyze correction patterns for a specific field across all documents.

        Args:
            organization_id: Organization ID
            field_name: Field name to analyze
            limit: Maximum number of corrections to analyze

        Returns:
            Dictionary with correction patterns:
            {
                'total_corrections': int,
                'most_common_value': str,
                'value_frequency': dict,
                'average_original_confidence': float,
                'correction_rate': float,
                'suggested_value': str or None
            }
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # Get recent corrections for this field
            cursor.execute('''
                SELECT corrected_value, original_value, original_confidence
                FROM field_corrections
                WHERE organization_id = ? AND field_name = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (organization_id, field_name, limit))

            corrections = cursor.fetchall()

            if not corrections:
                return {
                    'total_corrections': 0,
                    'most_common_value': None,
                    'value_frequency': {},
                    'average_original_confidence': None,
                    'correction_rate': 0.0,
                    'suggested_value': None
                }

            # Analyze patterns
            corrected_values = [c['corrected_value'] for c in corrections if c['corrected_value']]
            value_counts = Counter(corrected_values)
            most_common = value_counts.most_common(1)[0] if value_counts else (None, 0)

            # Calculate average original confidence
            confidences = [c['original_confidence'] for c in corrections if c['original_confidence'] is not None]
            avg_confidence = sum(confidences) / len(confidences) if confidences else None

            # Determine if we should suggest a value
            suggested_value = None
            if most_common[0] and most_common[1] >= self.min_corrections_for_learning:
                # If same value appears in 60%+ of corrections, suggest it
                if most_common[1] / len(corrections) >= 0.6:
                    suggested_value = most_common[0]
                    logger.debug(f"[AI LEARNING] Suggesting '{suggested_value}' for {field_name} "
                               f"(appears in {most_common[1]}/{len(corrections)} corrections)")

            return {
                'total_corrections': len(corrections),
                'most_common_value': most_common[0],
                'value_frequency': dict(value_counts),
                'average_original_confidence': avg_confidence,
                'correction_rate': len(corrections) / limit if limit > 0 else 0,
                'suggested_value': suggested_value
            }

        finally:
            conn.close()

    def get_error_prone_fields(self, organization_id: int, min_corrections: int = 5) -> List[Dict[str, Any]]:
        """
        Identify fields that are frequently corrected (error-prone).

        Args:
            organization_id: Organization ID
            min_corrections: Minimum corrections to consider field error-prone

        Returns:
            List of error-prone fields with statistics
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT
                    field_name,
                    COUNT(*) as correction_count,
                    AVG(original_confidence) as avg_confidence
                FROM field_corrections
                WHERE organization_id = ?
                GROUP BY field_name
                HAVING correction_count >= ?
                ORDER BY correction_count DESC
            ''', (organization_id, min_corrections))

            fields = cursor.fetchall()

            logger.info(f"[AI LEARNING] Found {len(fields)} error-prone fields with {min_corrections}+ corrections")

            return [dict(field) for field in fields]

        finally:
            conn.close()

    def adjust_confidence_with_learning(
        self,
        extracted_data: Dict[str, Any],
        organization_id: int,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Adjust confidence scores based on correction history.
        Lower confidence for fields that are frequently corrected.

        Args:
            extracted_data: Original extracted data with confidence scores
            organization_id: Organization ID
            category: Document category (optional, for category-specific learning)

        Returns:
            Extracted data with adjusted confidence scores
        """
        # Get error-prone fields
        error_prone_fields = self.get_error_prone_fields(organization_id)
        error_prone_map = {field['field_name']: field for field in error_prone_fields}

        adjusted_data = extracted_data.copy()
        adjustments_made = 0

        for field_name, field_data in extracted_data.items():
            # Skip non-field data
            if field_name in ['line_items', 'other_data', 'raw_text']:
                continue

            # Check if this field has confidence data
            if isinstance(field_data, dict) and 'confidence' in field_data:
                original_confidence = field_data['confidence']

                # Check if field is error-prone
                if field_name in error_prone_map:
                    correction_count = error_prone_map[field_name]['correction_count']
                    avg_original_confidence = error_prone_map[field_name]['avg_confidence']

                    # Reduce confidence based on correction frequency
                    # More corrections = lower confidence adjustment
                    penalty = min(0.3, correction_count * 0.02)  # Max 30% penalty
                    new_confidence = max(0.0, original_confidence - penalty)

                    adjusted_data[field_name]['confidence'] = new_confidence
                    adjustments_made += 1

                    logger.debug(f"[AI LEARNING] Adjusted confidence for {field_name}: "
                               f"{original_confidence:.2f} -> {new_confidence:.2f} "
                               f"(corrected {correction_count} times)")

        if adjustments_made > 0:
            logger.info(f"[AI LEARNING] Adjusted confidence for {adjustments_made} fields based on correction history")

        return adjusted_data

    def get_field_suggestions(
        self,
        extracted_data: Dict[str, Any],
        organization_id: int,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get field value suggestions based on correction history.

        Args:
            extracted_data: Extracted data from current document
            organization_id: Organization ID
            category: Document category (optional)

        Returns:
            Dictionary of field_name -> suggested_value
        """
        suggestions = {}

        # Check each field in extracted data
        for field_name, field_data in extracted_data.items():
            # Skip non-field data
            if field_name in ['line_items', 'raw_text']:
                continue

            # Get correction patterns for this field
            patterns = self.get_correction_patterns(organization_id, field_name)

            # If we have a suggested value and current extraction is low confidence or empty
            if patterns['suggested_value']:
                current_value = field_data.get('value') if isinstance(field_data, dict) else field_data
                current_confidence = field_data.get('confidence', 0) if isinstance(field_data, dict) else 0

                # Suggest if:
                # 1. Current value is empty/None, OR
                # 2. Current confidence is low (<0.7) AND we have strong pattern (60%+ frequency)
                if not current_value or (current_confidence < 0.7 and patterns['total_corrections'] >= 5):
                    suggestions[field_name] = {
                        'suggested_value': patterns['suggested_value'],
                        'reason': f"Based on {patterns['total_corrections']} past corrections",
                        'frequency': patterns['value_frequency'].get(patterns['suggested_value'], 0),
                        'confidence_boost': 0.15  # Boost confidence if suggestion is used
                    }

        if suggestions:
            logger.info(f"[AI LEARNING] Generated {len(suggestions)} field suggestions based on history")

        return suggestions

    def apply_learned_suggestions(
        self,
        extracted_data: Dict[str, Any],
        organization_id: int,
        category: Optional[str] = None
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Apply learned suggestions to extracted data.

        Args:
            extracted_data: Original extracted data
            organization_id: Organization ID
            category: Document category

        Returns:
            Tuple of (enhanced_data, list_of_applied_suggestions)
        """
        # Get suggestions
        suggestions = self.get_field_suggestions(extracted_data, organization_id, category)

        if not suggestions:
            return extracted_data, []

        enhanced_data = extracted_data.copy()
        applied = []

        for field_name, suggestion in suggestions.items():
            # Apply suggestion
            if isinstance(enhanced_data.get(field_name), dict):
                # Update value and boost confidence
                enhanced_data[field_name]['value'] = suggestion['suggested_value']
                enhanced_data[field_name]['confidence'] = min(1.0,
                    enhanced_data[field_name].get('confidence', 0.5) + suggestion['confidence_boost'])
            else:
                # Create new field with suggestion
                enhanced_data[field_name] = {
                    'value': suggestion['suggested_value'],
                    'confidence': 0.75  # Good confidence for learned value
                }

            applied.append(field_name)
            logger.info(f"[AI LEARNING] Applied suggestion for {field_name}: '{suggestion['suggested_value']}' "
                       f"({suggestion['reason']})")

        return enhanced_data, applied

    def get_learning_statistics(self, organization_id: int) -> Dict[str, Any]:
        """
        Get statistics about AI learning for an organization.

        Args:
            organization_id: Organization ID

        Returns:
            Dictionary with learning statistics
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # Total corrections
            cursor.execute('''
                SELECT COUNT(*) as total
                FROM field_corrections
                WHERE organization_id = ?
            ''', (organization_id,))
            total_corrections = cursor.fetchone()['total']

            # Unique fields corrected
            cursor.execute('''
                SELECT COUNT(DISTINCT field_name) as unique_fields
                FROM field_corrections
                WHERE organization_id = ?
            ''', (organization_id,))
            unique_fields = cursor.fetchone()['unique_fields']

            # Corrections by method
            cursor.execute('''
                SELECT correction_method, COUNT(*) as count
                FROM field_corrections
                WHERE organization_id = ?
                GROUP BY correction_method
            ''', (organization_id,))
            by_method = {row['correction_method']: row['count'] for row in cursor.fetchall()}

            # Error-prone fields
            error_prone = self.get_error_prone_fields(organization_id, min_corrections=3)

            return {
                'total_corrections': total_corrections,
                'unique_fields_corrected': unique_fields,
                'corrections_by_method': by_method,
                'error_prone_fields_count': len(error_prone),
                'top_error_prone_fields': error_prone[:5],
                'learning_enabled': total_corrections >= self.min_corrections_for_learning
            }

        finally:
            conn.close()

    def get_few_shot_examples(
        self,
        organization_id: int,
        selected_fields: Optional[List[str]] = None,
        category: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get few-shot examples from correction history to inject into AI prompts.

        Args:
            organization_id: Organization ID
            selected_fields: Optional list of fields to focus on
            category: Optional document category to filter by
            limit: Maximum number of examples to return

        Returns:
            List of example dictionaries with filename, category, and corrections
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # Query to get recent reviewed documents with corrections
            query = '''
                SELECT DISTINCT
                    d.id,
                    d.filename,
                    d.category,
                    d.extracted_text_preview
                FROM documents d
                INNER JOIN field_corrections fc ON fc.document_id = d.id
                WHERE d.organization_id = ?
                    AND fc.organization_id = ?
            '''
            params = [organization_id, organization_id]

            # Filter by category if provided
            if category:
                query += ' AND d.category = ?'
                params.append(category)

            query += ' ORDER BY fc.created_at DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            documents = cursor.fetchall()

            examples = []
            for doc in documents:
                # Get all corrections for this document
                cursor.execute('''
                    SELECT
                        field_name,
                        original_value,
                        corrected_value
                    FROM field_corrections
                    WHERE document_id = ? AND organization_id = ?
                ''', (doc['id'], organization_id))

                corrections = cursor.fetchall()

                # Filter corrections by selected_fields if provided
                if selected_fields:
                    corrections = [c for c in corrections if c['field_name'] in selected_fields]

                if corrections:
                    examples.append({
                        'filename': doc['filename'],
                        'category': doc['category'],
                        'text_preview': doc['extracted_text_preview'][:200] if doc['extracted_text_preview'] else '',
                        'corrections': [
                            {
                                'field': c['field_name'],
                                'corrected_value': c['corrected_value']
                            }
                            for c in corrections
                        ]
                    })

            logger.info(f"[FEW-SHOT] Retrieved {len(examples)} examples for organization {organization_id}")
            return examples

        finally:
            conn.close()

    def format_few_shot_examples(self, examples: List[Dict[str, Any]]) -> str:
        """
        Format few-shot examples into a text block for AI prompt injection.

        Args:
            examples: List of example dictionaries from get_few_shot_examples()

        Returns:
            Formatted string to inject into AI prompt
        """
        if not examples:
            return ""

        formatted = "\n\nHere are some examples from your previous work to help guide your extraction:\n\n"

        for i, example in enumerate(examples, 1):
            formatted += f"Example {i}:\n"
            formatted += f"Filename: {example['filename']}\n"
            formatted += f"Category: {example['category']}\n"

            if example.get('text_preview'):
                formatted += f"Text Preview: {example['text_preview']}...\n"

            formatted += "Corrected Values:\n"
            for correction in example['corrections']:
                formatted += f"  - {correction['field']}: {correction['corrected_value']}\n"

            formatted += "\n"

        formatted += "Use these examples as reference for similar documents, but always extract data from the current document.\n"

        logger.debug(f"[FEW-SHOT] Formatted {len(examples)} examples ({len(formatted)} chars)")
        return formatted


# Singleton instance
_ai_learning_service = None


def get_ai_learning_service() -> AILearningService:
    """
    Get singleton instance of AI learning service.

    Returns:
        AILearningService instance
    """
    global _ai_learning_service
    if _ai_learning_service is None:
        _ai_learning_service = AILearningService()
    return _ai_learning_service
