"""
Google Drive Connector for DocuFlow
Handles OAuth2 authentication, folder management, and file uploads to Google Drive.
"""
import os
import re
import logging
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from datetime import datetime
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

import sys
sys.path.append(str(Path(__file__).parent.parent))

from models import ExtractedData, DocumentCategory

logger = logging.getLogger(__name__)

# Google Drive API scopes
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# Category folder mapping
CATEGORY_FOLDERS = {
    DocumentCategory.INVOICE: "Invoices",
    DocumentCategory.CONTRACT: "Contracts",
    DocumentCategory.RECEIPT: "Receipts",
    DocumentCategory.LEGAL: "Legal Documents",
    DocumentCategory.HR: "HR Documents",
    DocumentCategory.TAX: "Tax Documents",
    DocumentCategory.FINANCIAL: "Financial Statements",
    DocumentCategory.CORRESPONDENCE: "Correspondence",
    DocumentCategory.OTHER: "Other"
}


class GoogleDriveConnector:
    """
    Connector for Google Drive integration.
    Handles OAuth2, folder creation, and file uploads with metadata.
    """

    def __init__(self):
        """Initialize Google Drive connector."""
        self.service = None
        self.credentials = None
        self.root_folder_id = None
        self.folder_cache = {}  # Cache folder IDs to avoid repeated API calls
        logger.info("[OK] Google Drive Connector initialized")

    async def authenticate(self, credentials_dict: Dict[str, str]) -> bool:
        """
        Authenticate with Google Drive using OAuth2.

        Args:
            credentials_dict: Contains 'refresh_token' or triggers OAuth flow

        Returns:
            True if authentication successful, False otherwise
        """
        try:
            # Check if we have a refresh token
            if 'refresh_token' in credentials_dict:
                # Use existing refresh token
                self.credentials = Credentials(
                    token=None,
                    refresh_token=credentials_dict['refresh_token'],
                    token_uri='https://oauth2.googleapis.com/token',
                    client_id=credentials_dict.get('client_id'),
                    client_secret=credentials_dict.get('client_secret'),
                    scopes=SCOPES
                )

                # Refresh the token
                if self.credentials.expired:
                    self.credentials.refresh(Request())

            else:
                # Need to do OAuth flow (would be done via frontend redirect)
                logger.error("OAuth2 flow needed - no refresh token provided")
                return False

            # Build Drive service
            self.service = build('drive', 'v3', credentials=self.credentials)

            # Test connection
            about = self.service.about().get(fields='user').execute()
            logger.info(f"✓ Authenticated as: {about['user']['emailAddress']}")

            return True

        except Exception as e:
            logger.error(f"Google Drive authentication failed: {e}")
            return False

    async def test_connection(self, credentials_dict: Dict[str, str]) -> Tuple[bool, str]:
        """
        Test Google Drive connection.

        Args:
            credentials_dict: OAuth credentials

        Returns:
            Tuple of (success, message)
        """
        try:
            success = await self.authenticate(credentials_dict)

            if success:
                # Get user info
                about = self.service.about().get(fields='user,storageQuota').execute()
                email = about['user']['emailAddress']

                # Get storage info
                quota = about.get('storageQuota', {})
                used = int(quota.get('usage', 0))
                limit = int(quota.get('limit', 0))

                used_gb = used / (1024**3)
                limit_gb = limit / (1024**3) if limit > 0 else 0

                if limit > 0:
                    message = f"Connected as {email} ({used_gb:.1f}GB / {limit_gb:.1f}GB used)"
                else:
                    message = f"Connected as {email} (Unlimited storage)"

                return True, message
            else:
                return False, "Authentication failed"

        except HttpError as e:
            logger.error(f"Drive API error: {e}")
            return False, f"Drive API error: {e.reason}"
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False, f"Connection error: {str(e)}"

    async def get_or_create_root_folder(self, folder_name: str = "DocuFlow") -> Optional[str]:
        """
        Get or create the root DocuFlow folder.

        Args:
            folder_name: Name of root folder

        Returns:
            Folder ID or None if failed
        """
        try:
            # Search for existing folder
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)'
            ).execute()

            files = results.get('files', [])

            if files:
                # Folder exists
                folder_id = files[0]['id']
                logger.info(f"✓ Found existing folder '{folder_name}': {folder_id}")
                self.root_folder_id = folder_id
                return folder_id

            # Create new folder
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }

            folder = self.service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()

            folder_id = folder['id']
            logger.info(f"✓ Created new folder '{folder_name}': {folder_id}")

            self.root_folder_id = folder_id
            return folder_id

        except HttpError as e:
            logger.error(f"Failed to create root folder: {e}")
            return None

    async def get_or_create_category_folder(self, category: DocumentCategory) -> Optional[str]:
        """
        Get or create category subfolder.

        Args:
            category: Document category

        Returns:
            Folder ID or None if failed
        """
        try:
            # Handle both enum and string values
            if isinstance(category, str):
                # Convert string to enum
                try:
                    category = DocumentCategory(category)
                except ValueError:
                    # If invalid category string, default to OTHER
                    category = DocumentCategory.OTHER

            # Check cache first
            cache_key = f"{self.root_folder_id}_{category.value}"
            if cache_key in self.folder_cache:
                return self.folder_cache[cache_key]

            # Get category folder name
            folder_name = CATEGORY_FOLDERS.get(category, "Other")

            # Search for existing subfolder
            query = f"name='{folder_name}' and '{self.root_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)'
            ).execute()

            files = results.get('files', [])

            if files:
                # Folder exists
                folder_id = files[0]['id']
                logger.info(f"✓ Found category folder '{folder_name}': {folder_id}")
                self.folder_cache[cache_key] = folder_id
                return folder_id

            # Create new category folder
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [self.root_folder_id]
            }

            folder = self.service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()

            folder_id = folder['id']
            logger.info(f"✓ Created category folder '{folder_name}': {folder_id}")

            self.folder_cache[cache_key] = folder_id
            return folder_id

        except HttpError as e:
            logger.error(f"Failed to create category folder: {e}")
            return None

    def generate_filename(self, extracted_data: ExtractedData, original_filename: str) -> str:
        """
        Generate smart filename from extracted data.
        Format: {date}_{vendor}_{amount}_{doc_number}.pdf

        Args:
            extracted_data: Extracted document data
            original_filename: Original file name

        Returns:
            Generated filename
        """
        parts = []

        # 1. Date (YYYY-MM-DD)
        if extracted_data.date:
            try:
                # Handle various date formats
                date_str = extracted_data.date
                if 'T' in date_str:
                    date_str = date_str.split('T')[0]
                parts.append(date_str)
            except:
                parts.append(datetime.now().strftime('%Y-%m-%d'))
        else:
            parts.append(datetime.now().strftime('%Y-%m-%d'))

        # 2. Vendor/Company name
        vendor_name = extracted_data.vendor or extracted_data.client or extracted_data.company or "Unknown"
        # Sanitize vendor name (remove special characters)
        vendor_clean = self._sanitize_filename_part(vendor_name)
        if vendor_clean:
            parts.append(vendor_clean[:50])  # Max 50 chars for vendor

        # 3. Amount
        if extracted_data.amount:
            amount_str = str(extracted_data.amount)
            # Remove currency symbols and clean
            amount_clean = re.sub(r'[^\d\.]', '', amount_str)
            if amount_clean:
                currency = extracted_data.currency or "$"
                parts.append(f"{currency}{amount_clean}")

        # 4. Document number
        doc_num = extracted_data.document_number or extracted_data.reference_number
        if doc_num:
            doc_clean = self._sanitize_filename_part(str(doc_num))
            if doc_clean:
                parts.append(doc_clean[:30])  # Max 30 chars

        # Get file extension from original
        ext = Path(original_filename).suffix or '.pdf'

        # Join parts
        filename = '_'.join(parts) + ext

        # Final sanitization and length check
        filename = self._sanitize_filename(filename)

        # Ensure reasonable length (Drive max is 255, but keep shorter)
        if len(filename) > 200:
            # Truncate middle parts, keep date and extension
            filename = parts[0] + '_' + '_'.join(parts[1:])[:150] + ext
            filename = self._sanitize_filename(filename)

        logger.info(f"Generated filename: {filename}")
        return filename

    def _sanitize_filename_part(self, text: str) -> str:
        """Sanitize a part of the filename."""
        if not text:
            return ""

        # Remove invalid characters for filenames
        invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
        text = re.sub(invalid_chars, '', text)

        # Replace spaces and multiple underscores
        text = text.replace(' ', '-')
        text = re.sub(r'-+', '-', text)
        text = re.sub(r'_+', '_', text)

        # Remove leading/trailing dashes and underscores
        text = text.strip('-_')

        return text

    def _sanitize_filename(self, filename: str) -> str:
        """Final sanitization of complete filename."""
        # Remove any remaining invalid characters
        invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
        filename = re.sub(invalid_chars, '', filename)

        # Ensure no duplicate separators
        filename = re.sub(r'_+', '_', filename)
        filename = re.sub(r'-+', '-', filename)

        return filename

    def _extract_folder_value(self, level: str, extracted_data: ExtractedData, category: DocumentCategory) -> Optional[str]:
        """
        Extract folder name value based on folder level type.

        Args:
            level: Folder level type (category, vendor, client, year, etc.)
            extracted_data: Extracted document data
            category: Document category

        Returns:
            Folder name string or None if not available
        """
        if level == 'category':
            # Use category mapping
            return CATEGORY_FOLDERS.get(category, "Other")

        elif level == 'vendor':
            return extracted_data.vendor or None

        elif level == 'client':
            return extracted_data.client or None

        elif level == 'company':
            return extracted_data.company or None

        elif level == 'year':
            if extracted_data.date:
                try:
                    # Extract year from date (handle various formats)
                    date_str = extracted_data.date.split('T')[0] if 'T' in extracted_data.date else extracted_data.date
                    year = date_str.split('-')[0]
                    return year
                except:
                    return datetime.now().strftime('%Y')
            return datetime.now().strftime('%Y')

        elif level == 'year_month':
            if extracted_data.date:
                try:
                    # Extract year-month from date
                    date_str = extracted_data.date.split('T')[0] if 'T' in extracted_data.date else extracted_data.date
                    parts = date_str.split('-')
                    return f"{parts[0]}-{parts[1]}"
                except:
                    return datetime.now().strftime('%Y-%m')
            return datetime.now().strftime('%Y-%m')

        elif level == 'document_type':
            return extracted_data.document_type or category.value

        elif level == 'person_name':
            return extracted_data.person_name or None

        elif level == 'none':
            return None

        return None

    async def build_dynamic_folder_path(
        self,
        extracted_data: ExtractedData,
        category: DocumentCategory,
        storage_config: Dict[str, Any]
    ) -> Optional[str]:
        """
        Build dynamic folder path based on folder structure configuration.
        Creates nested folders as needed.

        Args:
            extracted_data: Extracted document data
            category: Document category
            storage_config: Google Drive configuration with folder structure settings

        Returns:
            Final folder ID or None if failed
        """
        try:
            # Get folder structure configuration
            primary_level = storage_config.get('primary_level', 'category')
            secondary_level = storage_config.get('secondary_level', 'vendor')
            tertiary_level = storage_config.get('tertiary_level', 'none')

            # Build list of folder levels
            levels = []
            for level in [primary_level, secondary_level, tertiary_level]:
                if level and level != 'none':
                    folder_name = self._extract_folder_value(level, extracted_data, category)
                    if folder_name:
                        # Sanitize folder name
                        folder_name = self._sanitize_filename_part(folder_name)
                        levels.append(folder_name)

            # If no levels extracted, fallback to category only
            if not levels:
                levels.append(CATEGORY_FOLDERS.get(category, "Other"))

            # Create nested folders starting from root
            current_folder_id = self.root_folder_id
            folder_path_parts = []

            for folder_name in levels:
                # Check cache
                cache_key = f"{current_folder_id}_{folder_name}"
                if cache_key in self.folder_cache:
                    current_folder_id = self.folder_cache[cache_key]
                    folder_path_parts.append(folder_name)
                    continue

                # Search for existing folder
                query = f"name='{folder_name}' and '{current_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
                results = self.service.files().list(
                    q=query,
                    spaces='drive',
                    fields='files(id, name)'
                ).execute()

                files = results.get('files', [])

                if files:
                    # Folder exists
                    current_folder_id = files[0]['id']
                else:
                    # Create new folder
                    file_metadata = {
                        'name': folder_name,
                        'mimeType': 'application/vnd.google-apps.folder',
                        'parents': [current_folder_id]
                    }

                    folder = self.service.files().create(
                        body=file_metadata,
                        fields='id'
                    ).execute()

                    current_folder_id = folder['id']
                    logger.info(f"✓ Created folder: {folder_name}")

                # Cache the folder ID
                self.folder_cache[cache_key] = current_folder_id
                folder_path_parts.append(folder_name)

            logger.info(f"✓ Dynamic folder path: {'/'.join(folder_path_parts)}/")
            return current_folder_id

        except Exception as e:
            logger.error(f"Failed to build dynamic folder path: {e}")
            return None

    async def upload_document(
        self,
        pdf_path: Path,
        extracted_data: ExtractedData,
        category: DocumentCategory,
        storage_config: Dict[str, Any]
    ) -> Optional[Dict[str, str]]:
        """
        Upload document to Google Drive with metadata.

        Args:
            pdf_path: Path to PDF file
            extracted_data: Extracted document data
            category: Document category
            storage_config: Google Drive configuration

        Returns:
            Dict with file_id, web_view_link, and folder_path, or None if failed
        """
        try:
            # Handle both enum and string values for category
            if isinstance(category, str):
                try:
                    category = DocumentCategory(category)
                except ValueError:
                    category = DocumentCategory.OTHER

            if not self.service:
                logger.error("Not authenticated to Google Drive")
                return None

            # Ensure root folder exists
            if not self.root_folder_id:
                root_folder = storage_config.get('root_folder_name', 'DocuFlow')
                self.root_folder_id = await self.get_or_create_root_folder(root_folder)

            if not self.root_folder_id:
                logger.error("Failed to get/create root folder")
                return None

            # Build dynamic folder path based on configuration
            folder_id = await self.build_dynamic_folder_path(extracted_data, category, storage_config)

            if not folder_id:
                logger.error("Failed to build dynamic folder path")
                return None

            # Generate filename
            original_filename = pdf_path.name
            new_filename = self.generate_filename(extracted_data, original_filename)

            # Check for duplicates and handle
            final_filename = await self._handle_duplicate_filename(new_filename, folder_id)

            # Prepare metadata
            file_metadata = {
                'name': final_filename,
                'parents': [folder_id],
                'appProperties': self._build_metadata(extracted_data, category)
            }

            # Upload file
            media = MediaFileUpload(
                str(pdf_path),
                mimetype='application/pdf',
                resumable=True
            )

            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,webViewLink,name'
            ).execute()

            logger.info(f"✓ Uploaded to Drive: {file['name']} (ID: {file['id']})")

            category_folder_name = CATEGORY_FOLDERS.get(category, "Other")

            return {
                'file_id': file['id'],
                'web_view_link': file.get('webViewLink'),
                'filename': file['name'],
                'folder_path': f"/DocuFlow/{category_folder_name}/"
            }

        except HttpError as e:
            logger.error(f"Drive upload failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Upload error: {e}")
            return None

    async def _handle_duplicate_filename(self, filename: str, folder_id: str) -> str:
        """
        Handle duplicate filenames by adding (1), (2), etc.

        Args:
            filename: Proposed filename
            folder_id: Parent folder ID

        Returns:
            Final filename (potentially with number suffix)
        """
        try:
            # Check if file exists
            query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)'
            ).execute()

            files = results.get('files', [])

            if not files:
                # No duplicate, use original name
                return filename

            # File exists, add number suffix
            base_name = Path(filename).stem
            extension = Path(filename).suffix

            counter = 1
            while True:
                new_filename = f"{base_name} ({counter}){extension}"

                # Check if this numbered version exists
                query = f"name='{new_filename}' and '{folder_id}' in parents and trashed=false"
                results = self.service.files().list(
                    q=query,
                    spaces='drive',
                    fields='files(id)'
                ).execute()

                if not results.get('files'):
                    logger.info(f"Renamed duplicate: {filename} → {new_filename}")
                    return new_filename

                counter += 1

                # Safety limit
                if counter > 100:
                    # Fallback: add timestamp
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    return f"{base_name}_{timestamp}{extension}"

        except Exception as e:
            logger.error(f"Error checking duplicates: {e}")
            # If check fails, add timestamp to be safe
            base_name = Path(filename).stem
            extension = Path(filename).suffix
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            return f"{base_name}_{timestamp}{extension}"

    def _build_metadata(self, extracted_data: ExtractedData, category: DocumentCategory) -> Dict[str, str]:
        """
        Build custom metadata properties for Drive file.

        Args:
            extracted_data: Extracted document data
            category: Document category

        Returns:
            Dict of custom app properties
        """
        # Handle both enum and string values for category
        category_str = category.value if hasattr(category, 'value') else str(category)

        metadata = {
            'docuflow_version': '1.0',
            'category': category_str,
            'processed_timestamp': datetime.now().isoformat()
        }

        # Add extracted fields (only non-null values)
        field_mapping = {
            'document_type': extracted_data.document_type,
            'vendor': extracted_data.vendor,
            'client': extracted_data.client,
            'company': extracted_data.company,
            'person_name': extracted_data.person_name,
            'date': extracted_data.date,
            'due_date': extracted_data.due_date,
            'amount': str(extracted_data.amount) if extracted_data.amount else None,
            'currency': extracted_data.currency,
            'document_number': extracted_data.document_number,
            'reference_number': extracted_data.reference_number,
            'email': extracted_data.email,
            'phone': extracted_data.phone,
            'address': extracted_data.address
        }

        for key, value in field_mapping.items():
            if value is not None and value != '':
                # Drive app properties must be strings, max 124 bytes per value
                str_value = str(value)[:120]  # Limit to 120 chars to be safe
                metadata[key] = str_value

        # Add line items count (not full data to save space)
        if extracted_data.line_items:
            metadata['line_items_count'] = str(len(extracted_data.line_items))

        return metadata

    def clear_cache(self):
        """Clear cached folder IDs."""
        self.folder_cache = {}
        logger.info("Google Drive cache cleared")
