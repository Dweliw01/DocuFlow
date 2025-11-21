"""
API routes for connector configuration and management.
Handles DocuWare/Google Drive/OneDrive connector setup.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, List, Optional
import sys
import secrets
import os
import logging
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
from auth import get_current_user
from database import (
    save_connector_config,
    get_active_connector_config,
    delete_connector_config
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/connectors", tags=["connectors"])

# Service instances - use the SAME connector instance as upload routes
# This prevents creating multiple authentication sessions
connector_manager = get_connector_manager()
docuware_connector = connector_manager.docuware_connector
google_drive_connector = connector_manager.google_drive_connector
encryption_service = get_encryption_service()
field_mapping_service = get_field_mapping_service()


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
async def start_google_drive_oauth(current_user: dict = Depends(get_current_user)):
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
            'created_at': datetime.now().isoformat(),
            'user_id': current_user["id"],
            'email': current_user["email"]
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
        logger.error(f"OAuth start failed: {str(e)}", exc_info=True)
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

        # Get user info from state storage
        state_data = oauth_state_storage[state]
        user_id = state_data.get("user_id")
        user_email = state_data.get("email")

        # Remove used state token
        del oauth_state_storage[state]

        if not user_id:
            raise HTTPException(status_code=400, detail="Invalid session. Please try again.")

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

        # Create connector configuration
        connector_config = ConnectorConfig(
            connector_type="google_drive",
            google_drive={
                "refresh_token": credentials.refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
                "root_folder_name": "DocuFlow",
                "auto_create_folders": True,
                "primary_level": "category",
                "secondary_level": "vendor",
                "tertiary_level": "year_month"
            }
        )

        # Save configuration to database
        config_id = await save_connector_config(
            user_id=user_id,
            connector_type="google_drive",
            config_data=connector_config.dict()
        )
        logger.info(f"Saved Google Drive config {config_id} for user {user_email}")

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
        logger.error(f"OAuth callback failed: {str(e)}", exc_info=True)
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
async def get_google_drive_status(current_user: dict = Depends(get_current_user)):
    """
    Check if Google Drive is currently connected.

    Returns:
        Connection status
    """
    connector_config = await get_active_connector_config(
        user_id=current_user["id"],
        connector_type="google_drive"
    )

    if connector_config:
        config_data = connector_config.get("config_data", {})
        google_drive_config = config_data.get("google_drive", {})

        return {
            "connected": True,
            "root_folder_name": google_drive_config.get("root_folder_name", "DocuFlow"),
            "primary_level": google_drive_config.get("primary_level", "category"),
            "secondary_level": google_drive_config.get("secondary_level", "vendor"),
            "tertiary_level": google_drive_config.get("tertiary_level", "year_month")
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
async def save_connector_configuration(
    config: ConnectorConfig,
    current_user: dict = Depends(get_current_user)
):
    """
    Save connector configuration for current user.
    Stores in database with encryption for sensitive data.

    Args:
        config: Complete connector configuration
        current_user: Authenticated user from JWT token

    Returns:
        Success message
    """
    try:
        # Encrypt password if DocuWare connector
        if config.docuware:
            encrypted_password = encryption_service.encrypt(config.docuware.encrypted_password)
            config.docuware.encrypted_password = encrypted_password

        # Save to database (per user)
        # connector_type might be a string or enum, handle both
        connector_type_str = config.connector_type if isinstance(config.connector_type, str) else config.connector_type.value

        config_id = await save_connector_config(
            user_id=current_user["id"],
            connector_type=connector_type_str,
            config_data=config.dict()
        )

        # DON'T clear connector cache - reuse the authenticated session!
        # The session that just successfully tested the connection should be kept for uploads
        logger.info(f"Keeping authenticated session for {connector_type_str} connector")

        # Only clear cache if explicitly requested or on logout
        # if connector_type_str == "docuware":
        #     docuware_connector.clear_cache()
        # elif connector_type_str == "google_drive":
        #     google_drive_connector.root_folder_id = None
        #     google_drive_connector.folder_cache = {}

        logger.info(f"Saved {config.connector_type} config {config_id} for user {current_user['email']}")

        return {
            "success": True,
            "message": "Configuration saved successfully",
            "config_id": config_id
        }

    except Exception as e:
        logger.error(f"Failed to save connector config: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save configuration: {str(e)}")


@router.get("/config")
async def get_connector_configuration(current_user: dict = Depends(get_current_user)):
    """
    Get current connector configuration for authenticated user.

    Args:
        current_user: Authenticated user from JWT token

    Returns:
        Current ConnectorConfig (with encrypted password)
    """
    # Load from database
    docuware_config = await get_active_connector_config(current_user["id"], "docuware")
    google_drive_config = await get_active_connector_config(current_user["id"], "google_drive")
    onedrive_config = await get_active_connector_config(current_user["id"], "onedrive")

    # Determine active connector type
    if docuware_config:
        connector_type = "docuware"
    elif google_drive_config:
        connector_type = "google_drive"
    elif onedrive_config:
        connector_type = "onedrive"
    else:
        connector_type = "none"

    # Extract the nested config data (config is saved as full ConnectorConfig object)
    # So docuware_config actually contains {connector_type, docuware: {...}, google_drive, onedrive}
    # We need to extract just the connector-specific part
    return {
        "connector_type": connector_type,
        "docuware": docuware_config.get("docuware") if docuware_config else None,
        "google_drive": google_drive_config.get("google_drive") if google_drive_config else None,
        "onedrive": onedrive_config.get("onedrive") if onedrive_config else None
    }


@router.delete("/config")
async def clear_connector_configuration(
    connector_type: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Clear connector configuration for current user.

    Args:
        connector_type: Type of connector to clear (docuware, google_drive, onedrive)
        current_user: Authenticated user from JWT token

    Returns:
        Success message
    """
    try:
        await delete_connector_config(current_user["id"], connector_type)

        # Clear connector cache when configuration is deleted
        if connector_type == "docuware":
            docuware_connector.clear_cache()
            logger.info(f"Cleared DocuWare cache for user {current_user['email']}")
        elif connector_type == "google_drive":
            google_drive_connector.root_folder_id = None
            google_drive_connector.folder_cache = {}
            logger.info(f"Cleared Google Drive cache for user {current_user['email']}")

        logger.info(f"Cleared {connector_type} config for user {current_user['email']}")

        return {
            "success": True,
            "message": f"{connector_type} configuration cleared"
        }

    except Exception as e:
        logger.error(f"Failed to clear connector config: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to clear configuration: {str(e)}")


# ============================================================================
# Helper function for getting decrypted config
# ============================================================================

async def get_current_config_with_decrypted_password(user_id: int) -> Optional[tuple]:
    """
    Get current connector config with decrypted password for a specific user.

    Args:
        user_id: User ID to load configuration for

    Returns:
        Tuple of (ConnectorConfig, decrypted_password) or None
    """
    try:
        # Load from database
        docuware_config = await get_active_connector_config(user_id, "docuware")
        google_drive_config = await get_active_connector_config(user_id, "google_drive")

        if not docuware_config and not google_drive_config:
            return None

        # Determine which connector is configured (only one should be active at a time)
        # Check DocuWare first
        if docuware_config:
            dw_config_data = docuware_config.get("docuware")
            # Validate that DocuWare has required fields
            if dw_config_data and dw_config_data.get("server_url") and dw_config_data.get("username"):
                # Decrypt password
                encrypted_password = dw_config_data.get("encrypted_password")
                decrypted_password = encryption_service.decrypt(encrypted_password) if encrypted_password else None

                config = ConnectorConfig(
                    connector_type="docuware",
                    docuware=dw_config_data,
                    google_drive=None,
                    onedrive=None
                )
                logger.info(f"Using DocuWare connector for user {user_id}")
                return (config, decrypted_password)
            else:
                logger.debug(f"DocuWare config exists but missing required fields for user {user_id}")

        # Check Google Drive
        if google_drive_config:
            gd_config_data = google_drive_config.get("google_drive")
            # Validate that Google Drive has required fields
            if gd_config_data and (gd_config_data.get("credentials") or gd_config_data.get("refresh_token")):
                config = ConnectorConfig(
                    connector_type="google_drive",
                    docuware=None,
                    google_drive=gd_config_data,
                    onedrive=None
                )
                logger.info(f"Using Google Drive connector for user {user_id}")
                return (config, None)
            else:
                logger.debug(f"Google Drive config exists but missing required fields for user {user_id}")

        # No valid connector found
        logger.info(f"No valid connector configuration found for user {user_id}")
        return None

    except Exception as e:
        logger.error(f"Error loading connector config for user {user_id}: {str(e)}")
        return None
