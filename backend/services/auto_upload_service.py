"""
Service to determine if document should be auto-uploaded based on settings.
Handles smart review logic and auto-approval workflow.
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from database import get_db_connection
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def get_organization_settings(organization_id):
    """
    Get review settings for an organization.

    Args:
        organization_id: Organization ID

    Returns:
        Dict with review_mode, confidence_threshold, auto_upload_enabled
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            SELECT review_mode, confidence_threshold, auto_upload_enabled
            FROM organizations
            WHERE id = ?
        ''', (organization_id,))

        result = cursor.fetchone()

        if not result:
            # Default settings
            return {
                'review_mode': 'review_all',
                'confidence_threshold': 0.90,
                'auto_upload_enabled': False
            }

        return {
            'review_mode': result['review_mode'] or 'review_all',
            'confidence_threshold': result['confidence_threshold'] or 0.90,
            'auto_upload_enabled': result['auto_upload_enabled'] or False
        }

    finally:
        conn.close()


def should_auto_upload(org_settings, confidence_score):
    """
    Determine if document should be auto-uploaded.

    Args:
        org_settings: Dict with review_mode, confidence_threshold
        confidence_score: Overall confidence score (0.0 - 1.0)

    Returns:
        Boolean: True if should auto-upload, False if needs review
    """
    review_mode = org_settings.get('review_mode', 'review_all')

    # Review all documents mode
    if review_mode == 'review_all':
        logger.debug(f"Review mode: review_all - Requires manual review")
        return False

    # Auto-upload all mode (no review)
    if review_mode == 'auto_upload':
        logger.debug(f"Review mode: auto_upload - Auto-uploading all documents")
        return True

    # Smart mode - check confidence threshold
    if review_mode == 'smart':
        threshold = org_settings.get('confidence_threshold', 0.90)
        auto_upload = confidence_score >= threshold

        logger.debug(
            f"Review mode: smart - Confidence: {confidence_score:.2f}, "
            f"Threshold: {threshold:.2f}, Auto-upload: {auto_upload}"
        )

        return auto_upload

    # Default: require review
    logger.warning(f"Unknown review mode: {review_mode} - Defaulting to manual review")
    return False


async def approve_and_upload_document(doc_id, organization_id):
    """
    Auto-approve and upload document to connector.
    Called when should_auto_upload returns True.

    Args:
        doc_id: Document ID
        organization_id: Organization ID

    Returns:
        Dict with success status and result
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Update status to approved
        cursor.execute('''
            UPDATE document_metadata
            SET status = 'approved',
                approved_at = ?
            WHERE id = ? AND organization_id = ?
        ''', (datetime.utcnow(), doc_id, organization_id))

        conn.commit()

        logger.info(f"Document {doc_id} auto-approved for organization {organization_id}")

        # Upload to connector
        try:
            from services.connector_service import upload_document_to_connector

            result = await upload_document_to_connector(doc_id, organization_id)

            # Update status to completed
            cursor.execute('''
                UPDATE document_metadata
                SET status = 'completed',
                    uploaded_to_connector = 1
                WHERE id = ?
            ''', (doc_id,))

            conn.commit()

            logger.info(f"Document {doc_id} uploaded to connector successfully")

            return {
                'success': True,
                'auto_uploaded': True,
                'message': result.get('message', 'Document auto-approved and uploaded'),
                'upload_result': result
            }

        except Exception as e:
            logger.error(f"Failed to upload document {doc_id}: {e}")

            # Update status to failed
            cursor.execute('''
                UPDATE document_metadata
                SET status = 'failed',
                    error_message = ?
                WHERE id = ?
            ''', (str(e), doc_id))

            conn.commit()

            raise e

    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to auto-approve document {doc_id}: {e}")
        raise

    finally:
        conn.close()


async def process_document_for_review(doc_id, organization_id, confidence_score):
    """
    Process a document through the review workflow.
    Decides whether to auto-upload or require manual review.

    Args:
        doc_id: Document ID
        organization_id: Organization ID
        confidence_score: Overall confidence score

    Returns:
        Dict with status and action taken
    """
    # Get organization settings
    org_settings = get_organization_settings(organization_id)

    # Determine if should auto-upload
    if should_auto_upload(org_settings, confidence_score):
        # Auto-upload
        try:
            result = await approve_and_upload_document(doc_id, organization_id)
            return {
                'status': 'auto_uploaded',
                'requires_review': False,
                'result': result
            }
        except Exception as e:
            logger.error(f"Auto-upload failed for document {doc_id}: {e}")
            return {
                'status': 'failed',
                'requires_review': True,
                'error': str(e)
            }
    else:
        # Requires manual review
        return {
            'status': 'pending_review',
            'requires_review': True,
            'message': f'Document requires manual review (confidence: {confidence_score:.0%})'
        }


def get_review_stats(organization_id):
    """
    Get review statistics for an organization.

    Args:
        organization_id: Organization ID

    Returns:
        Dict with review statistics
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Get counts by status
        cursor.execute('''
            SELECT
                status,
                COUNT(*) as count,
                AVG(confidence_score) as avg_confidence
            FROM document_metadata
            WHERE organization_id = ?
            GROUP BY status
        ''', (organization_id,))

        status_counts = {}
        for row in cursor.fetchall():
            status_counts[row['status']] = {
                'count': row['count'],
                'avg_confidence': round(row['avg_confidence'] or 0, 2)
            }

        # Get total auto-uploaded vs manual reviewed
        cursor.execute('''
            SELECT
                COUNT(CASE WHEN status IN ('completed', 'approved')
                           AND approved_at IS NOT NULL THEN 1 END) as total_approved,
                COUNT(CASE WHEN status = 'pending_review' THEN 1 END) as pending_review
            FROM document_metadata
            WHERE organization_id = ?
        ''', (organization_id,))

        totals = cursor.fetchone()

        return {
            'by_status': status_counts,
            'total_approved': totals['total_approved'],
            'pending_review': totals['pending_review'],
            'organization_id': organization_id
        }

    finally:
        conn.close()
