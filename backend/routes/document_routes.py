"""
Document routes for review workflow.
Handles document viewing, field corrections, and approval.
"""

from fastapi import APIRouter, HTTPException, Depends, Response
from fastapi.responses import FileResponse
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
import json
from datetime import datetime
import os
import logging

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from auth import get_current_user
from database import get_db_connection
from services.ai_learning_service import get_ai_learning_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

# Initialize AI learning service
ai_learning_service = get_ai_learning_service()


# Request/Response Models
class FieldCorrection(BaseModel):
    field_name: str
    original_value: Optional[str] = None
    corrected_value: str
    original_confidence: Optional[float] = 0.0
    method: str = "manual"  # "manual" or "highlighted"


class ApproveDocumentRequest(BaseModel):
    corrections: List[FieldCorrection] = []


class DocumentResponse(BaseModel):
    id: int
    filename: str
    file_path: str
    category: Optional[str]
    status: str
    confidence_score: float
    extracted_data: Dict[str, Any]
    corrections: Dict[str, Any]
    created_at: str
    connector_type: Optional[str]


class PendingDocumentsResponse(BaseModel):
    documents: List[Dict[str, Any]]
    count: int


# ============================================================================
# IMPORTANT: Specific routes (like /pending) MUST come before parameterized
# routes (like /{doc_id}) in FastAPI, otherwise the path parameter will
# match everything and specific routes will never be reached!
# ============================================================================


@router.get("/pending")
async def get_pending_documents(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get all documents pending review for current organization.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            SELECT id, filename, category, confidence_score, created_at
            FROM document_metadata
            WHERE organization_id = ? AND status = 'pending_review'
            ORDER BY created_at DESC
        ''', (current_user['organization_id'],))

        docs = cursor.fetchall()

        documents = []
        for doc in docs:
            documents.append({
                'id': doc['id'],
                'filename': doc['filename'],
                'category': doc['category'],
                'confidence_score': doc['confidence_score'],
                'created_at': doc['created_at']
            })

        return {
            'documents': documents,
            'count': len(documents)
        }

    finally:
        conn.close()


@router.get("/")
async def get_all_documents(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get all documents for current organization with optional filtering.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Build query
        query = '''
            SELECT id, filename, category, status, confidence_score,
                   created_at, approved_at, connector_type
            FROM document_metadata
            WHERE organization_id = ?
        '''
        params = [current_user['organization_id']]

        if status:
            query += ' AND status = ?'
            params.append(status)

        query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])

        cursor.execute(query, params)
        docs = cursor.fetchall()

        # Get total count
        count_query = '''
            SELECT COUNT(*) as count
            FROM document_metadata
            WHERE organization_id = ?
        '''
        count_params = [current_user['organization_id']]

        if status:
            count_query += ' AND status = ?'
            count_params.append(status)

        cursor.execute(count_query, count_params)
        total = cursor.fetchone()['count']

        documents = []
        for doc in docs:
            documents.append({
                'id': doc['id'],
                'filename': doc['filename'],
                'category': doc['category'],
                'status': doc['status'],
                'confidence_score': doc['confidence_score'],
                'created_at': doc['created_at'],
                'approved_at': doc['approved_at'],
                'connector_type': doc['connector_type']
            })

        return {
            'documents': documents,
            'total': total,
            'limit': limit,
            'offset': offset
        }

    finally:
        conn.close()


@router.get("/{doc_id}")
async def get_document(
    doc_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get document details with extracted data and confidence scores.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Get document
        cursor.execute('''
            SELECT * FROM document_metadata
            WHERE id = ? AND organization_id = ?
        ''', (doc_id, current_user['organization_id']))

        doc = cursor.fetchone()
        if not doc:
            raise HTTPException(status_code=404, detail='Document not found')

        # Get corrections for this document
        cursor.execute('''
            SELECT * FROM field_corrections
            WHERE document_id = ?
            ORDER BY created_at DESC
        ''', (doc_id,))

        corrections = cursor.fetchall()

        # Parse extracted data
        extracted_data = json.loads(doc['extracted_data']) if doc['extracted_data'] else {}

        # Build corrections dict
        corrections_dict = {}
        for corr in corrections:
            corrections_dict[corr['field_name']] = {
                'original_value': corr['original_value'],
                'corrected_value': corr['corrected_value'],
                'original_confidence': corr['original_confidence'],
                'method': corr['correction_method'],
                'created_at': corr['created_at']
            }

        # Get connector configuration from document's snapshot
        # Use the config that was active when this document was processed,
        # not the current active config (to preserve historical field display)
        connector_config = None
        logger.info(f"[CONNECTOR-CONFIG] Loading config snapshot for document {doc_id}")

        # If document was processed without a connector, don't load any connector config
        if not doc['connector_type'] or doc['connector_type'] == 'null':
            logger.info(f"[CONNECTOR-CONFIG] Document processed without connector, no config to load")
        elif doc['connector_config_snapshot']:
            try:
                connector_config = json.loads(doc['connector_config_snapshot'])
                logger.info(f"[CONNECTOR-CONFIG] Using document's config snapshot, connector type: {doc['connector_type']}")

                # Only log DocuWare-specific fields if this is a DocuWare document
                if doc['connector_type'] == 'docuware':
                    if connector_config and 'docuware' in connector_config:
                        docuware_config = connector_config.get('docuware')
                        if docuware_config and isinstance(docuware_config, dict) and 'selected_table_columns' in docuware_config:
                            logger.info(f"[CONNECTOR-CONFIG] Table columns: {list(docuware_config['selected_table_columns'].keys())}")
            except Exception as e:
                logger.error(f"[CONNECTOR-CONFIG] Failed to parse config snapshot: {e}")
                logger.info(f"[CONNECTOR-CONFIG] Will attempt to load matching connector config")
                # Only fallback if we can find a config that matches this document's connector type
                cursor.execute('''
                    SELECT config_encrypted, connector_type FROM organization_settings
                    WHERE organization_id = ? AND connector_type = ?
                    ORDER BY updated_at DESC
                    LIMIT 1
                ''', (current_user['organization_id'], doc['connector_type']))

                config_row = cursor.fetchone()
                if config_row:
                    try:
                        connector_config = json.loads(config_row['config_encrypted'])
                        logger.info(f"[CONNECTOR-CONFIG] Loaded matching {doc['connector_type']} config")
                    except:
                        logger.warning(f"[CONNECTOR-CONFIG] Failed to parse fallback config")
                        pass
                else:
                    logger.warning(f"[CONNECTOR-CONFIG] No matching {doc['connector_type']} config found, fields may not display correctly")
        else:
            logger.info(f"[CONNECTOR-CONFIG] No snapshot found, loading config matching connector type: {doc['connector_type']}")
            # Document has no snapshot (processed before this feature)
            # Load a config that matches this document's connector type
            cursor.execute('''
                SELECT config_encrypted, connector_type FROM organization_settings
                WHERE organization_id = ? AND connector_type = ?
                ORDER BY updated_at DESC
                LIMIT 1
            ''', (current_user['organization_id'], doc['connector_type']))

            config_row = cursor.fetchone()
            if config_row:
                try:
                    connector_config = json.loads(config_row['config_encrypted'])
                    logger.info(f"[CONNECTOR-CONFIG] Loaded matching {doc['connector_type']} config")
                except:
                    logger.warning(f"[CONNECTOR-CONFIG] Failed to parse config")
                    pass
            else:
                logger.warning(f"[CONNECTOR-CONFIG] No {doc['connector_type']} config found for document")

        # Log final connector_config state before returning
        if connector_config:
            logger.info(f"[CONNECTOR-CONFIG] Returning config for document {doc_id}: connector_type={doc['connector_type']}, has_config=True")
        else:
            logger.warning(f"[CONNECTOR-CONFIG] Returning NULL config for document {doc_id}: connector_type={doc['connector_type']}")

        return {
            'id': doc['id'],
            'filename': doc['filename'],
            'file_path': doc['file_path'],
            'category': doc['category'],
            'status': doc['status'],
            'confidence_score': doc['confidence_score'],
            'extracted_data': extracted_data,
            'corrections': corrections_dict,
            'created_at': doc['created_at'],
            'connector_type': doc['connector_type'],
            'connector_config': connector_config  # Include connector config for line items
        }

    finally:
        conn.close()


@router.get("/{doc_id}/view")
async def view_document(
    doc_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Serve document file (PDF or image) for viewing in browser.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            SELECT file_path FROM document_metadata
            WHERE id = ? AND organization_id = ?
        ''', (doc_id, current_user['organization_id']))

        doc = cursor.fetchone()

        if not doc:
            raise HTTPException(status_code=404, detail='Document not found')

        file_path = doc['file_path']

        # Check if file exists
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail='File not found on disk')

        # Determine media type based on file extension
        file_extension = os.path.splitext(file_path)[1].lower()
        media_type_map = {
            '.pdf': 'application/pdf',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.tiff': 'image/tiff',
            '.tif': 'image/tiff',
            '.bmp': 'image/bmp',
            '.gif': 'image/gif'
        }

        media_type = media_type_map.get(file_extension, 'application/octet-stream')

        return FileResponse(
            file_path,
            media_type=media_type,
            filename=os.path.basename(file_path)
        )

    finally:
        conn.close()


@router.get("/{doc_id}/ocr-data")
async def get_ocr_data(
    doc_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get OCR coordinate data for a document (if available).
    Returns bounding box coordinates for words extracted via OCR.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Get document file path
        cursor.execute('''
            SELECT file_path FROM document_metadata
            WHERE id = ? AND organization_id = ?
        ''', (doc_id, current_user['organization_id']))

        doc = cursor.fetchone()

        if not doc:
            raise HTTPException(status_code=404, detail='Document not found')

        file_path = doc['file_path']

        # Calculate OCR coordinates file path
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        coords_filename = f"{base_name}_ocr_coordinates.json"
        coords_path = os.path.join(os.path.dirname(file_path), coords_filename)

        # Check if OCR coordinates file exists
        if not os.path.exists(coords_path):
            raise HTTPException(
                status_code=404,
                detail='OCR coordinate data not available for this document'
            )

        # Read and return the JSON data
        with open(coords_path, 'r', encoding='utf-8') as f:
            ocr_data = json.load(f)

        logger.info(f"Serving OCR data for document {doc_id}: {len(ocr_data.get('words', []))} words")

        return ocr_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading OCR data for document {doc_id}: {e}")
        raise HTTPException(status_code=500, detail=f'Error loading OCR data: {str(e)}')
    finally:
        conn.close()


@router.post("/{doc_id}/correct-field")
async def correct_field(
    doc_id: int,
    correction: FieldCorrection,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Save a field correction.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Verify document belongs to user's organization
        cursor.execute('''
            SELECT id FROM document_metadata
            WHERE id = ? AND organization_id = ?
        ''', (doc_id, current_user['organization_id']))

        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail='Document not found')

        # Save correction
        cursor.execute('''
            INSERT INTO field_corrections
            (organization_id, document_id, field_name, original_value,
             corrected_value, original_confidence, correction_method, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            current_user['organization_id'],
            doc_id,
            correction.field_name,
            correction.original_value,
            correction.corrected_value,
            correction.original_confidence,
            correction.method,
            current_user['email']
        ))

        conn.commit()
        correction_id = cursor.lastrowid

        # Log the correction for AI learning visibility
        logger.info(f"[AI LEARNING] Saved correction #{correction_id} for doc {doc_id}: "
                   f"{correction.field_name} = '{correction.corrected_value}' "
                   f"(was: '{correction.original_value or 'null'}')")

        return {
            'success': True,
            'correction_id': correction_id
        }

    finally:
        conn.close()


@router.post("/{doc_id}/approve")
async def approve_document(
    doc_id: int,
    request: ApproveDocumentRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Approve document and send to connector.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Get document
        cursor.execute('''
            SELECT * FROM document_metadata
            WHERE id = ? AND organization_id = ?
        ''', (doc_id, current_user['organization_id']))

        doc = cursor.fetchone()
        if not doc:
            raise HTTPException(status_code=404, detail='Document not found')

        # Save any pending corrections
        for correction in request.corrections:
            cursor.execute('''
                INSERT INTO field_corrections
                (organization_id, document_id, field_name, original_value,
                 corrected_value, original_confidence, correction_method, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                current_user['organization_id'],
                doc_id,
                correction.field_name,
                correction.original_value,
                correction.corrected_value,
                correction.original_confidence,
                correction.method,
                current_user['email']
            ))

        # Apply corrections to extracted_data and save
        extracted_data_dict = json.loads(doc['extracted_data']) if doc['extracted_data'] else {}

        # Apply all corrections to the extracted data
        for correction in request.corrections:
            if correction.field_name == '_line_items':
                # Special handling for line items
                try:
                    extracted_data_dict['line_items'] = json.loads(correction.corrected_value)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse line_items correction")
            elif 'other_data' in extracted_data_dict and correction.field_name in extracted_data_dict.get('other_data', {}):
                extracted_data_dict['other_data'][correction.field_name] = correction.corrected_value
            else:
                extracted_data_dict[correction.field_name] = correction.corrected_value

        # Update document with corrected data and approved status
        cursor.execute('''
            UPDATE document_metadata
            SET status = 'approved',
                approved_at = ?,
                extracted_data = ?
            WHERE id = ?
        ''', (datetime.utcnow(), json.dumps(extracted_data_dict), doc_id))

        conn.commit()

        # Upload to connector
        try:
            from services.connector_service import upload_document_to_connector

            result = await upload_document_to_connector(doc_id, current_user['organization_id'])

            # Update status to completed
            cursor.execute('''
                UPDATE document_metadata
                SET status = 'completed',
                    uploaded_to_connector = 1
                WHERE id = ?
            ''', (doc_id,))

            conn.commit()

            logger.info(f"Document {doc_id} approved and uploaded successfully")

            return {
                'success': True,
                'message': result.get('message', 'Document approved and uploaded'),
                'status': 'completed',
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

            raise HTTPException(status_code=500, detail=str(e))

    finally:
        conn.close()


@router.get("/ai-learning-stats")
async def get_ai_learning_statistics(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get AI learning statistics for the current user's organization.
    Shows how much the AI has learned from corrections.
    """
    try:
        organization_id = current_user['organization_id']

        # Get learning statistics
        stats = ai_learning_service.get_learning_statistics(organization_id)

        # Get error-prone fields (top 10)
        error_prone = ai_learning_service.get_error_prone_fields(organization_id, min_corrections=3)

        return {
            'success': True,
            'organization_id': organization_id,
            'statistics': stats,
            'error_prone_fields': error_prone[:10],  # Top 10
            'learning_active': stats['total_corrections'] >= 3
        }

    except Exception as e:
        logger.error(f"Failed to get learning statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{doc_id}/folder-preview")
async def get_folder_preview(
    doc_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get Google Drive folder path preview for a document.
    Shows where the document will be organized based on extracted data.

    Args:
        doc_id: Document ID
        current_user: Current authenticated user

    Returns:
        Dict with folder_path, folder_levels, and connector_type
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Get document
        cursor.execute('''
            SELECT * FROM document_metadata
            WHERE id = ? AND organization_id = ?
        ''', (doc_id, current_user['organization_id']))

        doc = cursor.fetchone()
        if not doc:
            raise HTTPException(status_code=404, detail='Document not found')

        # Get organization's active connector config
        cursor.execute('''
            SELECT connector_type, config_encrypted
            FROM organization_settings
            WHERE organization_id = ? AND is_active = 1
            ORDER BY updated_at DESC
            LIMIT 1
        ''', (current_user['organization_id'],))

        connector_config = cursor.fetchone()

        if not connector_config:
            return {
                'connector_type': None,
                'folder_path': None,
                'message': 'No active connector configured'
            }

        connector_type = connector_config['connector_type']

        # Only Google Drive has dynamic folder structure
        if connector_type != 'google_drive':
            return {
                'connector_type': connector_type,
                'folder_path': None,
                'message': f'{connector_type} does not use folder organization'
            }

        # Parse config and extracted data
        config_dict = json.loads(connector_config['config_encrypted'])
        extracted_data_dict = json.loads(doc['extracted_data']) if doc['extracted_data'] else {}

        # Get Google Drive config
        gd_config = config_dict.get('google_drive', config_dict)

        # Build folder path preview using the same logic as the connector
        from models import ExtractedData, DocumentCategory
        from connectors.google_drive_connector import GoogleDriveConnector, CATEGORY_FOLDERS

        # Transform extracted data: extract just the 'value' from each field
        # Database stores: {"vendor": {"value": "ABC", "confidence": 0.8}}
        # Model expects: {"vendor": "ABC"}
        extracted_values = {}
        for key, field_data in extracted_data_dict.items():
            if isinstance(field_data, dict) and 'value' in field_data:
                extracted_values[key] = field_data['value']
            else:
                extracted_values[key] = field_data

        # Convert extracted data dict to ExtractedData model
        extracted_data = ExtractedData(**extracted_values)

        # Get category
        category_str = doc['category']
        try:
            category = DocumentCategory(category_str) if category_str else DocumentCategory.OTHER
        except ValueError:
            category = DocumentCategory.OTHER

        # Get folder structure config
        primary_level = gd_config.get('primary_level', 'category')
        secondary_level = gd_config.get('secondary_level', 'vendor')
        tertiary_level = gd_config.get('tertiary_level', 'none')
        root_folder_name = gd_config.get('root_folder_name', 'DocuFlow')

        # Use connector's helper method to extract folder values
        connector = GoogleDriveConnector()

        folder_levels = []
        level_details = []

        for level_type in [primary_level, secondary_level, tertiary_level]:
            if level_type and level_type != 'none':
                folder_name = connector._extract_folder_value(level_type, extracted_data, category)
                if folder_name:
                    # Sanitize folder name
                    folder_name = connector._sanitize_filename_part(folder_name)
                    folder_levels.append(folder_name)
                    level_details.append({
                        'level_type': level_type,
                        'folder_name': folder_name,
                        'source_field': _get_source_field_for_level(level_type)
                    })
                else:
                    level_details.append({
                        'level_type': level_type,
                        'folder_name': None,
                        'source_field': _get_source_field_for_level(level_type),
                        'missing': True
                    })

        # If no levels extracted, fallback to category
        if not folder_levels:
            category_folder = CATEGORY_FOLDERS.get(category, "Other")
            folder_levels.append(category_folder)
            level_details.append({
                'level_type': 'category',
                'folder_name': category_folder,
                'source_field': 'category'
            })

        # Build full path
        folder_path = f"/{root_folder_name}/" + "/".join(folder_levels) + "/"

        return {
            'connector_type': connector_type,
            'folder_path': folder_path,
            'root_folder': root_folder_name,
            'folder_levels': folder_levels,
            'level_details': level_details,
            'structure_config': {
                'primary': primary_level,
                'secondary': secondary_level,
                'tertiary': tertiary_level
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate folder preview: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        conn.close()


def _get_source_field_for_level(level_type: str) -> str:
    """Get the source field name that populates a folder level."""
    field_mapping = {
        'category': 'category',
        'vendor': 'vendor_name',
        'client': 'client',
        'company': 'company',
        'year': 'invoice_date (year)',
        'year_month': 'invoice_date (year-month)',
        'document_type': 'document_type',
        'person_name': 'person_name'
    }
    return field_mapping.get(level_type, level_type)


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Delete a pending document and its associated data.

    Args:
        doc_id: Document ID to delete
        current_user: Current authenticated user

    Returns:
        Success message

    Raises:
        HTTPException: If document not found or user unauthorized
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check document exists and user has permission
        cursor.execute('''
            SELECT id, file_path, status, organization_id
            FROM document_metadata
            WHERE id = ?
        ''', (doc_id,))

        doc = cursor.fetchone()

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        # Verify user has access to this document's organization
        if doc['organization_id'] != current_user['organization_id']:
            raise HTTPException(status_code=403, detail="Not authorized to delete this document")

        # Only allow deletion of pending or rejected documents
        if doc['status'] not in ['pending_review', 'rejected']:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete document with status '{doc['status']}'. Only pending or rejected documents can be deleted."
            )

        # Delete associated field corrections
        cursor.execute('DELETE FROM field_corrections WHERE document_id = ?', (doc_id,))

        # Delete the document metadata
        cursor.execute('DELETE FROM document_metadata WHERE id = ?', (doc_id,))

        # Delete the physical file if it exists
        if doc['file_path'] and os.path.exists(doc['file_path']):
            try:
                os.remove(doc['file_path'])
                logger.info(f"Deleted file: {doc['file_path']}")
            except Exception as e:
                logger.warning(f"Could not delete file {doc['file_path']}: {e}")

        conn.commit()

        logger.info(f"Document {doc_id} deleted by user {current_user['email']}")

        return {
            "success": True,
            "message": "Document deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to delete document {doc_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        conn.close()
