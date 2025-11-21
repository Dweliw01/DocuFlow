"""
Connector Manager for orchestrating document uploads to different DMS systems.
Handles connector selection and upload coordination.
"""
from typing import Dict, Any, Optional
from pathlib import Path
import sys
import logging

sys.path.append(str(Path(__file__).parent.parent))

from models import ConnectorType, ConnectorConfig, ExtractedData, UploadResult, DocumentCategory
from connectors.docuware_connector import DocuWareConnector
from connectors.google_drive_connector import GoogleDriveConnector

logger = logging.getLogger(__name__)


class ConnectorManager:
    """
    Manager for coordinating document uploads across different connectors.
    Handles connector instantiation and upload orchestration.
    """

    def __init__(self):
        """Initialize connector manager with available connectors."""
        self.docuware_connector = DocuWareConnector()
        self.google_drive_connector = GoogleDriveConnector()
        # Future connectors:
        # self.onedrive_connector = OneDriveConnector()

    async def upload_document(
        self,
        file_path: str,
        extracted_data: ExtractedData,
        config: ConnectorConfig,
        decrypted_password: Optional[str] = None,
        category: DocumentCategory = DocumentCategory.OTHER
    ) -> UploadResult:
        """
        Upload document to configured connector.

        Args:
            file_path: Path to the document file
            extracted_data: Extracted document data
            config: Connector configuration
            decrypted_password: Decrypted password (if applicable)

        Returns:
            UploadResult with status and details
        """
        try:
            # Check connector type
            if config.connector_type == ConnectorType.NONE:
                return UploadResult(
                    success=True,
                    message="No connector configured (local only)"
                )

            elif config.connector_type == ConnectorType.DOCUWARE:
                return await self._upload_to_docuware(
                    file_path,
                    extracted_data,
                    config.docuware,
                    decrypted_password
                )

            elif config.connector_type == ConnectorType.GOOGLE_DRIVE:
                return await self._upload_to_google_drive(
                    file_path,
                    extracted_data,
                    category,
                    config.google_drive,
                    decrypted_password
                )

            elif config.connector_type == ConnectorType.ONEDRIVE:
                # Future implementation
                return UploadResult(
                    success=False,
                    message="OneDrive connector not yet implemented",
                    error="Coming soon"
                )

            else:
                return UploadResult(
                    success=False,
                    message="Unknown connector type",
                    error=f"Connector type '{config.connector_type}' not supported"
                )

        except Exception as e:
            return UploadResult(
                success=False,
                message="Upload failed",
                error=str(e)
            )

    async def _upload_to_docuware(
        self,
        file_path: str,
        extracted_data: ExtractedData,
        docuware_config,
        decrypted_password: Optional[str]
    ) -> UploadResult:
        """
        Upload document to DocuWare.

        Args:
            file_path: Document file path
            extracted_data: Extracted data
            docuware_config: DocuWare configuration
            decrypted_password: Decrypted password

        Returns:
            UploadResult
        """
        try:
            # Prepare credentials
            credentials = {
                "server_url": docuware_config.server_url,
                "username": docuware_config.username,
                "password": decrypted_password or docuware_config.encrypted_password
            }

            # Prepare storage config
            storage_config = {
                "cabinet_id": docuware_config.cabinet_id,
                "dialog_id": docuware_config.dialog_id,
                "selected_fields": docuware_config.selected_fields,
                "selected_table_columns": docuware_config.selected_table_columns or {}
            }

            # Extract metadata - use other_data if available (dynamic extraction)
            # Otherwise fall back to standard fields
            if extracted_data and extracted_data.other_data:
                # Dynamic extraction - data is already in DocuWare field names
                metadata = extracted_data.other_data.copy()

                # Add line items if present (convert from LineItem objects to dicts)
                if extracted_data.line_items:
                    metadata['line_items'] = [item.dict() for item in extracted_data.line_items]
            else:
                # Legacy fallback - use standard extracted data
                metadata = extracted_data.dict(exclude_none=True) if extracted_data else {}

            # Validate metadata before upload
            is_valid, errors = await self.docuware_connector.validate_metadata(
                metadata,
                storage_config,
                credentials  # Pass credentials so we can check required fields
            )

            if not is_valid:
                return UploadResult(
                    success=False,
                    message="Validation failed",
                    error=f"Missing required fields: {', '.join(errors)}"
                )

            # Upload document
            upload_result = await self.docuware_connector.upload_document(
                file_path=file_path,
                metadata=metadata,
                credentials=credentials,
                storage_config=storage_config
            )

            # Convert to UploadResult model
            return UploadResult(
                success=upload_result.get('success', False),
                document_id=upload_result.get('document_id'),
                url=upload_result.get('url'),
                message=upload_result.get('message', ''),
                error=upload_result.get('error')
            )

        except Exception as e:
            return UploadResult(
                success=False,
                message="DocuWare upload error",
                error=str(e)
            )

    async def _upload_to_google_drive(
        self,
        file_path: str,
        extracted_data: ExtractedData,
        category: DocumentCategory,
        google_drive_config,
        decrypted_password: Optional[str]
    ) -> UploadResult:
        """
        Upload document to Google Drive.

        Args:
            file_path: Document file path
            extracted_data: Extracted data
            category: Document category for folder organization
            google_drive_config: Google Drive configuration
            decrypted_password: Decrypted refresh token (not used yet for MVP)

        Returns:
            UploadResult
        """
        try:
            # Prepare credentials
            credentials = {
                "refresh_token": google_drive_config.refresh_token,
                "client_id": google_drive_config.client_id,
                "client_secret": google_drive_config.client_secret
            }

            # Authenticate if not already
            if not self.google_drive_connector.service:
                authenticated = await self.google_drive_connector.authenticate(credentials)
                if not authenticated:
                    return UploadResult(
                        success=False,
                        message="Google Drive authentication failed",
                        error="Failed to authenticate with Google Drive"
                    )

            # Prepare storage config (use user's configured folder organization from frontend)
            # Extract folder organization levels - handle both Enum and string values
            primary = google_drive_config.primary_level
            secondary = google_drive_config.secondary_level
            tertiary = google_drive_config.tertiary_level

            storage_config = {
                "root_folder_name": google_drive_config.root_folder_name or "DocuFlow",
                "primary_level": primary.value if hasattr(primary, 'value') else primary,
                "secondary_level": secondary.value if hasattr(secondary, 'value') else secondary,
                "tertiary_level": tertiary.value if hasattr(tertiary, 'value') else tertiary
            }

            logger.info(f"Google Drive folder structure: {storage_config['primary_level']} → {storage_config['secondary_level']} → {storage_config['tertiary_level']}")

            # Upload document
            result = await self.google_drive_connector.upload_document(
                pdf_path=Path(file_path),
                extracted_data=extracted_data,
                category=category,
                storage_config=storage_config
            )

            if result:
                return UploadResult(
                    success=True,
                    document_id=result['file_id'],
                    url=result.get('web_view_link'),
                    message=f"Uploaded to Google Drive: {result['folder_path']}{result['filename']}"
                )
            else:
                return UploadResult(
                    success=False,
                    message="Google Drive upload failed",
                    error="Upload returned None"
                )

        except Exception as e:
            return UploadResult(
                success=False,
                message="Google Drive upload error",
                error=str(e)
            )


# Singleton instance
_connector_manager = None


def get_connector_manager() -> ConnectorManager:
    """
    Get singleton instance of ConnectorManager.

    Returns:
        ConnectorManager instance
    """
    global _connector_manager
    if _connector_manager is None:
        _connector_manager = ConnectorManager()
    return _connector_manager
