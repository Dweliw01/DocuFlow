"""
API routes for connector configuration and management.
Handles DocuWare/Google Drive/OneDrive connector setup.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from models import (
    ConnectorConfig,
    ConnectorTestResponse,
    FileCabinet,
    StorageDialog,
    IndexField,
    ExtractedData
)
from connectors.connector_manager import get_connector_manager
from services.encryption_service import get_encryption_service
from services.field_mapping_service import get_field_mapping_service

router = APIRouter(prefix="/api/connectors", tags=["connectors"])

# Service instances - use the SAME connector instance as upload routes
# This prevents creating multiple authentication sessions
connector_manager = get_connector_manager()
docuware_connector = connector_manager.docuware_connector
encryption_service = get_encryption_service()
field_mapping_service = get_field_mapping_service()

# In-memory storage for current session (for MVP)
# In production, this should be stored in a database per user
current_connector_config: Optional[ConnectorConfig] = None


# ============================================================================
# Request/Response Models
# ============================================================================

class DocuWareCredentials(BaseModel):
    server_url: str
    username: str
    password: str


class DocuWareDialogsRequest(BaseModel):
    server_url: str
    username: str
    password: str
    cabinet_id: str


class DocuWareFieldsRequest(BaseModel):
    server_url: str
    username: str
    password: str
    cabinet_id: str
    dialog_id: str


class AutoMapRequest(BaseModel):
    extracted_data: ExtractedData
    index_fields: List[IndexField]


# ============================================================================
# DocuWare Connector Endpoints
# ============================================================================

@router.post("/docuware/test", response_model=ConnectorTestResponse)
async def test_docuware_connection(credentials: DocuWareCredentials):
    """
    Test DocuWare connection with provided credentials.

    Args:
        credentials: Server URL, username, and password

    Returns:
        ConnectorTestResponse with success status and message
    """
    try:
        creds_dict = credentials.dict()
        success, message = await docuware_connector.test_connection(creds_dict)

        return ConnectorTestResponse(
            success=success,
            message=message
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Connection test failed: {str(e)}")


@router.post("/docuware/cabinets")
async def get_docuware_cabinets(credentials: DocuWareCredentials):
    """
    Get list of file cabinets from DocuWare.

    Args:
        credentials: Server URL, username, and password

    Returns:
        Dictionary with cabinets list
    """
    try:
        creds_dict = credentials.dict()
        cabinets = await docuware_connector.get_file_cabinets(creds_dict)

        return {
            "cabinets": [cabinet.dict() for cabinet in cabinets]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get cabinets: {str(e)}")


@router.post("/docuware/dialogs")
async def get_docuware_dialogs(request: DocuWareDialogsRequest):
    """
    Get storage dialogs for a file cabinet.

    Args:
        request: Credentials and cabinet_id

    Returns:
        Dictionary with dialogs list
    """
    try:
        creds_dict = {
            "server_url": request.server_url,
            "username": request.username,
            "password": request.password
        }

        dialogs = await docuware_connector.get_storage_dialogs(
            creds_dict,
            request.cabinet_id
        )

        return {
            "dialogs": [dialog.dict() for dialog in dialogs]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get dialogs: {str(e)}")


@router.post("/docuware/fields")
async def get_docuware_fields(request: DocuWareFieldsRequest):
    """
    Get index fields for a storage dialog.

    Args:
        request: Credentials, cabinet_id, and dialog_id

    Returns:
        Dictionary with fields list
    """
    try:
        creds_dict = {
            "server_url": request.server_url,
            "username": request.username,
            "password": request.password
        }

        fields = await docuware_connector.get_index_fields(
            creds_dict,
            request.cabinet_id,
            request.dialog_id
        )

        return {
            "fields": [field.dict() for field in fields]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get fields: {str(e)}")


# ============================================================================
# Field Mapping Endpoints
# ============================================================================

@router.post("/field-suggestions")
async def get_field_suggestions(request: List[IndexField]):
    """
    Get smart field mapping suggestions based on common field name patterns.
    Used during configuration setup to suggest which fields to select.

    Args:
        request: List of available DocuWare index fields

    Returns:
        Dictionary with suggested fields and confidence scores
    """
    try:
        # Common extracted data fields that we typically look for
        common_source_fields = [
            'document_type', 'vendor', 'client', 'company', 'person_name',
            'date', 'due_date', 'amount', 'currency', 'document_number',
            'reference_number', 'address', 'email', 'phone'
        ]

        suggestions = {}
        confidence_scores = {}

        # For each common field, find best matching target field
        for source_field in common_source_fields:
            best_match, confidence = field_mapping_service._find_best_match_with_confidence(
                source_field,
                request,
                confidence_threshold=0.5  # Lower threshold for suggestions
            )

            if best_match:
                suggestions[source_field] = best_match.name
                confidence_scores[best_match.name] = confidence

        # Also identify required fields that need attention
        required_fields = [field.name for field in request if field.required]

        return {
            "suggestions": suggestions,
            "confidence_scores": confidence_scores,
            "required_fields": required_fields,
            "total_fields": len(request),
            "suggested_field_count": len(suggestions)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate suggestions: {str(e)}")


@router.post("/auto-map")
async def auto_map_fields(request: AutoMapRequest):
    """
    Automatically map extracted data fields to target system fields with confidence scores.

    Args:
        request: Extracted data and target index fields

    Returns:
        Proposed field mapping with confidence scores and validation results
    """
    try:
        # Get mapping with confidence scores
        mapping, confidence_scores = field_mapping_service.auto_map_fields_with_confidence(
            request.extracted_data,
            request.index_fields
        )

        # Validate mapping
        is_valid, missing_fields = field_mapping_service.validate_mapping(
            mapping,
            request.index_fields,
            request.extracted_data
        )

        return {
            "mapping": mapping,
            "confidence_scores": confidence_scores,
            "is_valid": is_valid,
            "missing_fields": missing_fields
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auto-mapping failed: {str(e)}")


# ============================================================================
# Configuration Management Endpoints
# ============================================================================

@router.post("/config")
async def save_connector_config(config: ConnectorConfig):
    """
    Save connector configuration.

    Args:
        config: Complete connector configuration

    Returns:
        Success message
    """
    global current_connector_config

    try:
        # Encrypt password if DocuWare connector
        if config.docuware:
            # Encrypt the password
            encrypted_password = encryption_service.encrypt(config.docuware.encrypted_password)
            config.docuware.encrypted_password = encrypted_password

        # Store configuration (in-memory for MVP)
        current_connector_config = config

        return {
            "success": True,
            "message": "Configuration saved successfully"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save configuration: {str(e)}")


@router.get("/config")
async def get_connector_config():
    """
    Get current connector configuration.

    Returns:
        Current ConnectorConfig (with encrypted password)
    """
    global current_connector_config

    if current_connector_config is None:
        return {
            "connector_type": "none",
            "docuware": None,
            "google_drive": None,
            "onedrive": None
        }

    return current_connector_config.dict()


@router.delete("/config")
async def clear_connector_config():
    """
    Clear connector configuration.

    Returns:
        Success message
    """
    global current_connector_config
    current_connector_config = None

    # Clear DocuWare connector cache
    docuware_connector.clear_cache()

    return {
        "success": True,
        "message": "Configuration cleared"
    }


# ============================================================================
# Helper function for getting decrypted config
# ============================================================================

def get_current_config_with_decrypted_password() -> Optional[tuple]:
    """
    Get current connector config with decrypted password.

    Returns:
        Tuple of (config, decrypted_password) or None
    """
    global current_connector_config

    if current_connector_config is None:
        return None

    if current_connector_config.docuware:
        decrypted_password = encryption_service.decrypt(
            current_connector_config.docuware.encrypted_password
        )
        return (current_connector_config, decrypted_password)

    return (current_connector_config, None)
