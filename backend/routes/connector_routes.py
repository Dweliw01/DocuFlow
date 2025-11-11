"""
API routes for connector configuration and management.
Handles DocuWare/Google Drive/OneDrive connector setup.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional
import sys
import secrets
import os
from pathlib import Path
from datetime import datetime
from fastapi.responses import RedirectResponse, HTMLResponse
from google_auth_oauthlib.flow import Flow
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
from config import settings

router = APIRouter(prefix="/api/connectors", tags=["connectors"])

# Service instances - use the SAME connector instance as upload routes
# This prevents creating multiple authentication sessions
connector_manager = get_connector_manager()
docuware_connector = connector_manager.docuware_connector
google_drive_connector = connector_manager.google_drive_connector
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
# Google Drive Connector Endpoints
# ============================================================================

# OAuth state management (in-memory for single user)
# In production with multiple users, use Redis or database
oauth_state_storage = {}


class GoogleDriveSetupRequest(BaseModel):
    root_folder_name: str = "DocuFlow"


@router.get("/google-drive/oauth-start")
async def start_google_drive_oauth():
    """
    Start Google Drive OAuth2 flow.
    Generates authorization URL and redirects user to Google login.

    Returns:
        OAuth authorization URL
    """
    try:
        # Get OAuth credentials from settings
        client_id = settings.google_oauth_client_id
        client_secret = settings.google_oauth_client_secret

        if not client_id or not client_secret:
            raise HTTPException(
                status_code=500,
                detail="Google OAuth credentials not configured. Please set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in .env file"
            )

        # Redirect URI (must match what's configured in Google Cloud Console)
        redirect_uri = settings.google_oauth_redirect_uri

        # Create OAuth flow
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri]
                }
            },
            scopes=['https://www.googleapis.com/auth/drive.file']
        )
        flow.redirect_uri = redirect_uri

        # Generate state token for CSRF protection
        state = secrets.token_urlsafe(32)
        oauth_state_storage[state] = {
            'created_at': datetime.now().isoformat()
        }

        # Generate authorization URL
        authorization_url, _ = flow.authorization_url(
            access_type='offline',  # Get refresh token
            include_granted_scopes='true',
            state=state,
            prompt='consent'  # Force consent screen to get refresh token
        )

        return {
            "authorization_url": authorization_url,
            "state": state
        }

    except Exception as e:
        logger.error(f"OAuth start failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start OAuth: {str(e)}")


@router.get("/google-drive/oauth-callback")
async def google_drive_oauth_callback(code: str, state: str):
    """
    Handle OAuth2 callback from Google.
    Exchanges authorization code for tokens and saves configuration.

    Args:
        code: Authorization code from Google
        state: State token for CSRF protection

    Returns:
        HTML page with success message
    """
    try:
        # Verify state token
        if state not in oauth_state_storage:
            raise HTTPException(status_code=400, detail="Invalid state token. Please try again.")

        # Remove used state token
        del oauth_state_storage[state]

        # Get OAuth credentials from settings
        client_id = settings.google_oauth_client_id
        client_secret = settings.google_oauth_client_secret
        redirect_uri = settings.google_oauth_redirect_uri

        # Create OAuth flow
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri]
                }
            },
            scopes=['https://www.googleapis.com/auth/drive.file']
        )
        flow.redirect_uri = redirect_uri

        # Exchange authorization code for tokens
        flow.fetch_token(code=code)
        credentials = flow.credentials

        # Save Google Drive configuration
        global current_connector_config
        current_connector_config = ConnectorConfig(
            connector_type="google_drive",
            google_drive={
                "refresh_token": credentials.refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
                "root_folder_name": "DocuFlow",
                "auto_create_folders": True
            }
        )

        # Authenticate the connector with the new tokens
        creds_dict = {
            "refresh_token": credentials.refresh_token,
            "client_id": client_id,
            "client_secret": client_secret
        }
        await google_drive_connector.authenticate(creds_dict)

        # Return success page that closes the window and notifies parent
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Google Drive Connected</title>
            <style>
                body {
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                }
                .container {
                    background: white;
                    padding: 3rem;
                    border-radius: 1rem;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    text-align: center;
                    max-width: 400px;
                }
                .success-icon {
                    font-size: 4rem;
                    margin-bottom: 1rem;
                }
                h1 {
                    color: #10b981;
                    margin: 0 0 1rem 0;
                }
                p {
                    color: #6b7280;
                    margin: 0 0 1.5rem 0;
                }
                .close-btn {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    border: none;
                    padding: 0.75rem 2rem;
                    border-radius: 0.5rem;
                    font-size: 1rem;
                    font-weight: 600;
                    cursor: pointer;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="success-icon">✓</div>
                <h1>Google Drive Connected!</h1>
                <p>Your Google Drive has been successfully connected to DocuFlow.</p>
                <button class="close-btn" onclick="closeWindow()">Close Window</button>
            </div>
            <script>
                // Notify parent window if opened in popup
                if (window.opener) {
                    window.opener.postMessage({ type: 'GOOGLE_OAUTH_SUCCESS' }, '*');
                }

                function closeWindow() {
                    window.close();
                    // If window doesn't close (some browsers block it), redirect to settings
                    setTimeout(() => {
                        window.location.href = '/settings.html';
                    }, 500);
                }

                // Auto-close after 3 seconds if opened in popup
                if (window.opener) {
                    setTimeout(closeWindow, 3000);
                }
            </script>
        </body>
        </html>
        """

        return HTMLResponse(content=html_content)

    except Exception as e:
        logger.error(f"OAuth callback failed: {str(e)}")
        # Return error page
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Connection Failed</title>
            <style>
                body {{
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #f43f5e 0%, #dc2626 100%);
                }}
                .container {{
                    background: white;
                    padding: 3rem;
                    border-radius: 1rem;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    text-align: center;
                    max-width: 400px;
                }}
                .error-icon {{
                    font-size: 4rem;
                    margin-bottom: 1rem;
                }}
                h1 {{
                    color: #dc2626;
                    margin: 0 0 1rem 0;
                }}
                p {{
                    color: #6b7280;
                    margin: 0 0 1.5rem 0;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="error-icon">✗</div>
                <h1>Connection Failed</h1>
                <p>{str(e)}</p>
                <button onclick="window.close()" style="padding: 0.75rem 2rem; border-radius: 0.5rem; border: none; background: #dc2626; color: white; cursor: pointer;">Close</button>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content, status_code=500)


@router.get("/google-drive/status")
async def get_google_drive_status():
    """
    Check if Google Drive is currently connected.

    Returns:
        Connection status
    """
    global current_connector_config

    if current_connector_config and current_connector_config.connector_type == "google_drive":
        return {
            "connected": True,
            "root_folder_name": current_connector_config.google_drive.root_folder_name,
            "primary_level": current_connector_config.google_drive.primary_level,
            "secondary_level": current_connector_config.google_drive.secondary_level,
            "tertiary_level": current_connector_config.google_drive.tertiary_level
        }

    return {
        "connected": False
    }


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
