"""
Service for uploading documents to configured connectors.
Handles loading document data, applying corrections, and coordinating upload.
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from database import get_db_connection
from connectors.connector_manager import get_connector_manager
from services.encryption_service import get_encryption_service
from models import ExtractedData, ConnectorConfig, ConnectorType, DocumentCategory, LineItem
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Get encryption service instance
encryption_service = get_encryption_service()


def apply_corrections_to_extracted_data(extracted_data_dict: Dict[str, Any], corrections: list) -> Dict[str, Any]:
    """
    Apply field corrections to extracted data.

    Args:
        extracted_data_dict: Original extracted data as dict
        corrections: List of correction records from database

    Returns:
        Updated extracted_data dict with corrections applied
    """
    # Make a copy to avoid mutating original
    corrected_data = extracted_data_dict.copy()

    for correction in corrections:
        field_name = correction['field_name']
        corrected_value = correction['corrected_value']

        # Handle special _line_items field
        if field_name == '_line_items':
            try:
                corrected_data['line_items'] = json.loads(corrected_value)
                logger.info(f"[AI LEARNING] Applied line items correction: {len(corrected_data['line_items'])} items")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse line_items correction: {e}")
                continue

        # Handle DocuWare fields in other_data
        elif 'other_data' in corrected_data and field_name in corrected_data.get('other_data', {}):
            corrected_data['other_data'][field_name] = corrected_value
            logger.debug(f"Applied correction to other_data.{field_name}: {corrected_value}")

        # Handle standard fields
        elif field_name in corrected_data:
            corrected_data[field_name] = corrected_value
            logger.debug(f"Applied correction to {field_name}: {corrected_value}")

        # Handle nested fields (e.g., "vendor.name")
        elif '.' in field_name:
            parts = field_name.split('.')
            target = corrected_data
            for part in parts[:-1]:
                if part not in target:
                    target[part] = {}
                target = target[part]
            target[parts[-1]] = corrected_value
            logger.debug(f"Applied correction to nested field {field_name}: {corrected_value}")

        # New field - add to other_data or root
        else:
            if 'other_data' not in corrected_data:
                corrected_data['other_data'] = {}
            corrected_data['other_data'][field_name] = corrected_value
            logger.debug(f"Applied correction to new field {field_name}: {corrected_value}")

    return corrected_data


async def upload_document_to_connector(doc_id: int, organization_id: int) -> Dict[str, Any]:
    """
    Upload document to configured connector with all corrections applied.

    Args:
        doc_id: Document ID
        organization_id: Organization ID

    Returns:
        Dict with success status, message, and upload details

    Raises:
        Exception: If upload fails
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. Get document metadata
        cursor.execute('''
            SELECT * FROM document_metadata
            WHERE id = ? AND organization_id = ?
        ''', (doc_id, organization_id))

        doc = cursor.fetchone()
        if not doc:
            raise ValueError(f"Document {doc_id} not found")

        # 2. Get all corrections for this document
        cursor.execute('''
            SELECT field_name, corrected_value, correction_method
            FROM field_corrections
            WHERE document_id = ?
            ORDER BY created_at ASC
        ''', (doc_id,))

        corrections = cursor.fetchall()

        # 3. Load and apply corrections to extracted data
        extracted_data_dict = json.loads(doc['extracted_data']) if doc['extracted_data'] else {}

        if corrections:
            logger.info(f"[AI LEARNING] Applying {len(corrections)} user corrections to document {doc_id}")
            for correction in corrections:
                logger.debug(f"  - {correction['field_name']}: '{correction['corrected_value']}'")
            extracted_data_dict = apply_corrections_to_extracted_data(extracted_data_dict, corrections)
            logger.info(f"[AI LEARNING] Corrections applied - document ready for upload with learned values")

        # 4. Get connector configuration for organization
        cursor.execute('''
            SELECT connector_type, config_encrypted, is_active
            FROM organization_settings
            WHERE organization_id = ? AND is_active = 1
            ORDER BY updated_at DESC
            LIMIT 1
        ''', (organization_id,))

        connector_config = cursor.fetchone()

        if not connector_config:
            raise ValueError(f"No active connector configured for organization {organization_id}")

        connector_type = connector_config['connector_type']
        config_encrypted = connector_config['config_encrypted']

        # 5. Decrypt configuration
        config_dict = json.loads(config_encrypted)

        # Decrypt password if present (for DocuWare)
        # Check both root level and nested docuware object
        if connector_type == 'docuware':
            dw_config = config_dict.get('docuware', config_dict)
            if 'encrypted_password' in dw_config:
                try:
                    decrypted_pwd = encryption_service.decrypt(dw_config['encrypted_password'])
                    dw_config['decrypted_password'] = decrypted_pwd
                    # Also set at root level for compatibility
                    config_dict['decrypted_password'] = decrypted_pwd
                    logger.info(f"✓ Successfully decrypted password for DocuWare connector")
                except Exception as e:
                    logger.error(f"✗ Failed to decrypt password: {e}")
                    dw_config['decrypted_password'] = None
                    config_dict['decrypted_password'] = None

        # 6. Build ConnectorConfig model
        connector_config_obj = _build_connector_config(connector_type, config_dict)

        # 7. Build ExtractedData model
        extracted_data_obj = _build_extracted_data(extracted_data_dict)

        # 8. Get document category
        category = DocumentCategory(doc['category']) if doc['category'] else DocumentCategory.OTHER

        # 9. Upload to connector
        logger.info(f"Uploading document {doc_id} to {connector_type}")

        connector_manager = get_connector_manager()
        upload_result = await connector_manager.upload_document(
            file_path=doc['file_path'],
            extracted_data=extracted_data_obj,
            config=connector_config_obj,
            decrypted_password=config_dict.get('decrypted_password'),
            category=category
        )

        if not upload_result.success:
            raise Exception(f"Upload failed: {upload_result.error or upload_result.message}")

        logger.info(f"Document {doc_id} uploaded successfully. Document ID: {upload_result.document_id}")

        return {
            'success': True,
            'message': upload_result.message,
            'document_id': upload_result.document_id,
            'url': upload_result.url,
            'connector_type': connector_type
        }

    except Exception as e:
        logger.error(f"Failed to upload document {doc_id}: {e}", exc_info=True)
        raise

    finally:
        conn.close()


def _build_connector_config(connector_type: str, config_dict: Dict[str, Any]) -> ConnectorConfig:
    """Build ConnectorConfig model from dict."""
    from models import DocuWareConfig, GoogleDriveConfig, FolderStructureLevel

    if connector_type == 'docuware':
        # Check if config is nested under 'docuware' key
        dw_config = config_dict.get('docuware', config_dict)

        docuware_config = DocuWareConfig(
            server_url=dw_config.get('server_url', ''),
            username=dw_config.get('username', ''),
            encrypted_password=dw_config.get('encrypted_password', ''),
            cabinet_id=dw_config.get('cabinet_id', ''),
            cabinet_name=dw_config.get('cabinet_name', ''),
            dialog_id=dw_config.get('dialog_id'),
            dialog_name=dw_config.get('dialog_name', ''),
            selected_fields=dw_config.get('selected_fields', []),
            selected_table_columns=dw_config.get('selected_table_columns', {})
        )

        return ConnectorConfig(
            connector_type=ConnectorType.DOCUWARE,
            docuware=docuware_config
        )

    elif connector_type == 'google_drive':
        # Check if config is nested under 'google_drive' key
        gd_config = config_dict.get('google_drive', config_dict)

        # Parse folder organization levels
        primary = gd_config.get('primary_level', 'category')
        secondary = gd_config.get('secondary_level', 'year')
        tertiary = gd_config.get('tertiary_level', 'month')

        google_drive_config = GoogleDriveConfig(
            refresh_token=gd_config.get('refresh_token', ''),
            client_id=gd_config.get('client_id', ''),
            client_secret=gd_config.get('client_secret', ''),
            root_folder_name=gd_config.get('root_folder_name', 'DocuFlow'),
            primary_level=FolderStructureLevel(primary),
            secondary_level=FolderStructureLevel(secondary),
            tertiary_level=FolderStructureLevel(tertiary)
        )

        return ConnectorConfig(
            connector_type=ConnectorType.GOOGLE_DRIVE,
            google_drive=google_drive_config
        )

    else:
        return ConnectorConfig(connector_type=ConnectorType.NONE)


def _build_extracted_data(data_dict: Dict[str, Any]) -> ExtractedData:
    """Build ExtractedData model from dict."""

    def extract_value(field_data):
        """Extract value from field data (handles both plain values and {value, confidence} objects)."""
        if field_data is None:
            return None
        if isinstance(field_data, dict) and 'value' in field_data:
            return field_data['value']
        return field_data

    # Convert line_items to LineItem objects if present
    line_items = None
    if 'line_items' in data_dict and data_dict['line_items']:
        line_items = []
        for item in data_dict['line_items']:
            if isinstance(item, dict):
                line_items.append(LineItem(**item))
            else:
                line_items.append(item)

    return ExtractedData(
        vendor_name=extract_value(data_dict.get('vendor_name')),
        vendor_address=extract_value(data_dict.get('vendor_address')),
        invoice_number=extract_value(data_dict.get('invoice_number')),
        invoice_date=extract_value(data_dict.get('invoice_date')),
        due_date=extract_value(data_dict.get('due_date')),
        total_amount=extract_value(data_dict.get('total_amount')),
        currency=extract_value(data_dict.get('currency')),
        tax_amount=extract_value(data_dict.get('tax_amount')),
        line_items=line_items,
        other_data=data_dict.get('other_data', {})
    )
