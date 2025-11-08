"""
DocuWare Connector for uploading documents with dynamic discovery.
Uses the official docuware-client library with OAuth2 authentication.
"""
import docuware
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path
import sys
import asyncio
sys.path.append(str(Path(__file__).parent.parent))

from connectors.base_connector import BaseConnector
from models import FileCabinet, StorageDialog, IndexField
from services.field_mapping_service import get_field_mapping_service


class DocuWareConnector(BaseConnector):
    """
    DocuWare connector implementation using official docuware-client library.
    Supports OAuth2 authentication and dynamic discovery.
    """

    def __init__(self):
        """Initialize DocuWare connector."""
        self.client = None
        self.session = None
        self.field_mapping_service = get_field_mapping_service()
        self.cabinet_cache = {}  # Cache cabinet objects by ID
        self.current_credentials_key = None  # Track current account (server_url + username)

    def clear_cache(self):
        """
        Clear all cached data (cabinets, session, credentials).
        Called when configuration is cleared or account changes.
        """
        print("Clearing DocuWare connector cache")
        self.cabinet_cache = {}
        self.current_credentials_key = None
        self.client = None
        self.session = None

    def _is_system_field(self, field_name: str) -> bool:
        """
        Detect if a field is a DocuWare system field.
        System fields are auto-managed by DocuWare and not for user input.

        Args:
            field_name: Name of the field

        Returns:
            True if system field, False otherwise
        """
        field_name_upper = field_name.upper()

        # Common DocuWare system field prefixes and names
        system_prefixes = ['DW', 'SYS_']
        system_fields = [
            'DOCID', 'DOCUMENT_ID', 'DWDOCID',
            'STODATE', 'DWSTODATE', 'STORAGE_DATE',
            'STOUSER', 'DWSTOUSER', 'STORAGE_USER',
            'MODDATE', 'DWMODDATE', 'MODIFIED_DATE',
            'MODUSER', 'DWMODUSER', 'MODIFIED_USER',
            'CREATED_AT', 'CREATED_BY', 'UPDATED_AT', 'UPDATED_BY',
            'VERSION', 'STATUS', 'WORKFLOW_STATE'
        ]

        # Check if starts with system prefix
        for prefix in system_prefixes:
            if field_name_upper.startswith(prefix):
                return True

        # Check if exact match with system field
        if field_name_upper in system_fields:
            return True

        return False

    def _sanitize_field_value(self, value: Any, field_type: str) -> Any:
        """
        Sanitize field value based on DocuWare field type.
        Removes currency symbols, commas, etc. from numeric fields.

        Args:
            value: Raw field value
            field_type: DocuWare field type (e.g., 'Decimal', 'Text', 'Date')

        Returns:
            Sanitized value appropriate for the field type
        """
        if value is None or value == "":
            return value

        # Convert to string for processing
        value_str = str(value).strip()

        # Handle Decimal fields - remove currency symbols and commas
        if field_type in ['Decimal', 'Currency', 'Number', 'Int', 'Integer']:
            # Remove common currency symbols
            currency_symbols = ['$', '€', '£', '¥', '₹', '₽', 'USD', 'EUR', 'GBP', 'CAD', 'AUD']
            for symbol in currency_symbols:
                value_str = value_str.replace(symbol, '')

            # Remove commas (thousands separator)
            value_str = value_str.replace(',', '')

            # Remove spaces
            value_str = value_str.strip()

            # Validate it's a valid number
            try:
                # Try to convert to float to validate
                float(value_str)
                return value_str
            except ValueError:
                # Not a valid number, return None
                print(f"Warning: Could not convert '{value}' to decimal, skipping field")
                return None

        # Handle Date fields - ensure YYYY-MM-DD format
        elif field_type in ['Date', 'DateTime']:
            # Date should already be in YYYY-MM-DD format from AI
            # Just validate and return
            import re
            if re.match(r'^\d{4}-\d{2}-\d{2}', value_str):
                return value_str
            else:
                print(f"Warning: Date '{value}' not in expected format, skipping field")
                return None

        # For all other types (Text, etc.), return as-is
        return value_str

    def _normalize_server_url(self, server_url: str) -> str:
        """
        Normalize server URL by adding https:// if missing and removing trailing slash.

        Args:
            server_url: Raw server URL

        Returns:
            Normalized server URL
        """
        server_url = server_url.strip()

        # Add https:// if protocol is missing
        if not server_url.startswith(('http://', 'https://')):
            server_url = f'https://{server_url}'

        # Remove trailing slash and any path (docuware library needs just the base URL)
        from urllib.parse import urlparse
        parsed = urlparse(server_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    async def test_connection(self, credentials: Dict[str, str]) -> Tuple[bool, str]:
        """
        Test DocuWare connection with provided credentials.
        Uses OAuth2 authentication via official library.

        Args:
            credentials: {
                "server_url": "https://company.docuware.cloud",
                "username": "user@company.com",
                "password": "password"
            }

        Returns:
            (success: bool, message: str)
        """
        try:
            server_url = self._normalize_server_url(credentials['server_url'])
            username = credentials['username']
            password = credentials['password']

            print(f"Testing connection to: {server_url}")

            # Run synchronous docuware client in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._test_connection_sync,
                server_url,
                username,
                password
            )

            return result

        except Exception as e:
            error_msg = str(e)
            print(f"Connection error: {error_msg}")

            if "401" in error_msg or "Unauthorized" in error_msg:
                return False, "Invalid credentials"
            elif "404" in error_msg or "Not Found" in error_msg:
                return False, "Server URL not found. Please verify the URL."
            elif "Connection" in error_msg:
                return False, "Cannot connect to server. Check URL and network."
            else:
                return False, f"Connection failed: {error_msg}"

    def _test_connection_sync(self, server_url: str, username: str, password: str) -> Tuple[bool, str]:
        """Synchronous connection test."""
        try:
            # Create credentials key to track account changes
            credentials_key = f"{server_url}|{username}"

            # If credentials changed, clear the cache
            if self.current_credentials_key != credentials_key:
                print(f"Credentials changed, clearing cabinet cache")
                self.cabinet_cache = {}
                self.current_credentials_key = credentials_key

            # Create client
            client = docuware.DocuwareClient(server_url)

            # Attempt login (OAuth2 by default)
            session = client.login(username, password)

            if session:
                print("✓ Connected successfully with OAuth2")
                return True, "Connected successfully"
            else:
                return False, "Login failed"

        except Exception as e:
            raise

    async def authenticate(self, credentials: Dict[str, str]) -> Optional[Any]:
        """
        Authenticate with DocuWare and return session.

        Args:
            credentials: Server URL, username, password

        Returns:
            DocuWare session object or None
        """
        try:
            server_url = self._normalize_server_url(credentials['server_url'])
            username = credentials['username']
            password = credentials['password']

            # Run in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._authenticate_sync,
                server_url,
                username,
                password
            )

            return result

        except Exception as e:
            print(f"Authentication failed: {e}")
            return None

    def _authenticate_sync(self, server_url: str, username: str, password: str) -> Optional[Any]:
        """Synchronous authentication."""
        try:
            # Create credentials key to track account changes
            credentials_key = f"{server_url}|{username}"

            # If credentials changed, clear the cache
            if self.current_credentials_key != credentials_key:
                print(f"Credentials changed, clearing cabinet cache")
                self.cabinet_cache = {}
                self.current_credentials_key = credentials_key

            self.client = docuware.DocuwareClient(server_url)
            self.session = self.client.login(username, password)
            return self.session
        except Exception as e:
            print(f"Auth error: {e}")
            return None

    async def get_file_cabinets(self, credentials: Dict[str, str]) -> List[FileCabinet]:
        """
        Get list of file cabinets available to the user.

        Args:
            credentials: Server URL, username, password

        Returns:
            List of FileCabinet objects
        """
        try:
            # Always authenticate to ensure we're using the correct credentials
            session = await self.authenticate(credentials)
            if not session:
                return []

            # Run in thread pool
            loop = asyncio.get_event_loop()
            cabinets = await loop.run_in_executor(
                None,
                self._get_cabinets_sync
            )

            return cabinets

        except Exception as e:
            print(f"Failed to get file cabinets: {e}")
            return []

    def _get_cabinets_sync(self) -> List[FileCabinet]:
        """Synchronous cabinet retrieval."""
        try:
            cabinets = []
            # Iterate through organizations and their file cabinets
            for org in self.client.organizations:
                for cabinet in org.file_cabinets:
                    # Cache the cabinet object for later use
                    self.cabinet_cache[cabinet.id] = cabinet

                    cabinets.append(FileCabinet(
                        id=cabinet.id,
                        name=cabinet.name,
                        description=getattr(cabinet, 'description', None)
                    ))
            print(f"Found {len(cabinets)} file cabinets")
            return cabinets
        except Exception as e:
            print(f"Error getting cabinets: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def get_storage_dialogs(
        self,
        credentials: Dict[str, str],
        cabinet_id: str
    ) -> List[StorageDialog]:
        """
        Get storage dialogs for a file cabinet.

        Args:
            credentials: Server URL, username, password
            cabinet_id: File cabinet ID

        Returns:
            List of StorageDialog objects
        """
        try:
            # Always authenticate to ensure we're using the correct credentials
            session = await self.authenticate(credentials)
            if not session:
                return []

            loop = asyncio.get_event_loop()
            dialogs = await loop.run_in_executor(
                None,
                self._get_dialogs_sync,
                cabinet_id
            )

            return dialogs

        except Exception as e:
            print(f"Failed to get storage dialogs: {e}")
            return []

    def _get_dialogs_sync(self, cabinet_id: str) -> List[StorageDialog]:
        """Synchronous dialog retrieval."""
        try:
            dialogs = []

            # Get cabinet from cache
            if cabinet_id not in self.cabinet_cache:
                print(f"Cabinet {cabinet_id} not in cache")
                return []

            cabinet = self.cabinet_cache[cabinet_id]

            # Try to get dialogs - the library might have a dialogs attribute
            if hasattr(cabinet, 'dialogs'):
                for dialog in cabinet.dialogs:
                    dialogs.append(StorageDialog(
                        id=dialog.id,
                        name=getattr(dialog, 'display_name', getattr(dialog, 'name', dialog.id)),
                        description=getattr(dialog, 'description', None)
                    ))
            # Fallback: try search_dialog() for at least one dialog
            elif hasattr(cabinet, 'search_dialog'):
                try:
                    dialog = cabinet.search_dialog()
                    if dialog:
                        dialogs.append(StorageDialog(
                            id=dialog.id if hasattr(dialog, 'id') else 'default',
                            name=getattr(dialog, 'display_name', getattr(dialog, 'name', 'Default Dialog')),
                            description=getattr(dialog, 'description', None)
                        ))
                except Exception as e:
                    print(f"Error getting default dialog: {e}")

            print(f"Found {len(dialogs)} dialogs for cabinet {cabinet_id}")
            return dialogs
        except Exception as e:
            print(f"Error getting dialogs: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def get_index_fields(
        self,
        credentials: Dict[str, str],
        cabinet_id: str,
        dialog_id: str
    ) -> List[IndexField]:
        """
        Get index fields for a storage dialog.

        Args:
            credentials: Server URL, username, password
            cabinet_id: File cabinet ID
            dialog_id: Storage dialog ID

        Returns:
            List of IndexField objects
        """
        try:
            # Always authenticate to ensure we're using the correct credentials
            session = await self.authenticate(credentials)
            if not session:
                return []

            loop = asyncio.get_event_loop()
            fields = await loop.run_in_executor(
                None,
                self._get_fields_sync,
                cabinet_id,
                dialog_id
            )

            return fields

        except Exception as e:
            print(f"Failed to get index fields: {e}")
            return []

    def _get_fields_sync(self, cabinet_id: str, dialog_id: str) -> List[IndexField]:
        """Synchronous field retrieval."""
        try:
            fields = []

            # Get cabinet from cache, or populate cache if empty
            if cabinet_id not in self.cabinet_cache:
                print(f"Cabinet {cabinet_id} not in cache, populating...")
                # Populate cache by iterating organizations
                for org in self.client.organizations:
                    for cabinet in org.file_cabinets:
                        self.cabinet_cache[cabinet.id] = cabinet
                        if cabinet.id == cabinet_id:
                            break

            # Get cabinet from cache
            if cabinet_id not in self.cabinet_cache:
                print(f"ERROR: Cabinet {cabinet_id} not found after populating cache")
                return []

            cabinet = self.cabinet_cache[cabinet_id]

            # Get the dialog (use search_dialog if dialog_id matches)
            dialog = None
            if hasattr(cabinet, 'search_dialog'):
                try:
                    # Try getting dialog by name/id
                    if dialog_id == 'default':
                        dialog = cabinet.search_dialog()
                    else:
                        dialog = cabinet.search_dialog(dialog_id)
                except:
                    # Fallback to default dialog
                    dialog = cabinet.search_dialog()

            if not dialog:
                print(f"Could not get dialog {dialog_id}")
                return []

            # Get fields from dialog - they're in a dictionary
            if hasattr(dialog, 'fields'):
                for field_name, field in dialog.fields.items():
                    is_required = getattr(field, 'mandatory', False) or getattr(field, 'not_empty', False)
                    field_id = field.id if hasattr(field, 'id') else field_name

                    fields.append(IndexField(
                        name=field_id,
                        type=getattr(field, 'type', 'Text'),
                        required=is_required,
                        max_length=getattr(field, 'length', None),
                        validation=None,
                        is_system_field=self._is_system_field(field_id)
                    ))

            print(f"Found {len(fields)} fields for dialog {dialog_id}")
            return fields
        except Exception as e:
            print(f"Error getting fields: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def get_storage_locations(self, credentials: Dict[str, str]) -> List[Dict[str, str]]:
        """
        Get storage locations (file cabinets).
        Implementation of BaseConnector method.

        Args:
            credentials: Authentication credentials

        Returns:
            List of storage locations
        """
        cabinets = await self.get_file_cabinets(credentials)
        return [{"id": c.id, "name": c.name} for c in cabinets]

    async def upload_document(
        self,
        file_path: str,
        metadata: Dict[str, Any],
        credentials: Dict[str, str],
        storage_config: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Upload document to DocuWare with indexed fields.

        Args:
            file_path: Path to document file
            metadata: Extracted metadata (already in DocuWare field names)
            credentials: Server URL, username, password
            storage_config: {
                "cabinet_id": "...",
                "dialog_id": "...",
                "selected_fields": ["VENDOR", "ORDER_DATE", ...]
            }

        Returns:
            Upload result with status and document ID
        """
        try:
            cabinet_id = storage_config['cabinet_id']
            dialog_id = storage_config['dialog_id']
            selected_fields = storage_config.get('selected_fields', [])

            # Always authenticate to ensure we're using the correct credentials
            session = await self.authenticate(credentials)
            if not session:
                return {
                    "success": False,
                    "message": "Authentication failed",
                    "error": "Could not authenticate with DocuWare"
                }

            # Get field types to sanitize data properly
            field_definitions = await self.get_index_fields(credentials, cabinet_id, dialog_id)
            field_types = {field.name: field.type for field in field_definitions}

            # Metadata is already in DocuWare field format - filter to selected fields and sanitize
            index_data = {}
            for field, value in metadata.items():
                if field in selected_fields and value is not None and value != "":
                    # Sanitize value based on field type
                    sanitized_value = self._sanitize_field_value(value, field_types.get(field, 'Text'))
                    if sanitized_value is not None and sanitized_value != "":
                        index_data[field] = sanitized_value

            # Upload document in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._upload_document_sync,
                file_path,
                cabinet_id,
                index_data
            )

            return result

        except Exception as e:
            return {
                "success": False,
                "message": "Upload error",
                "error": str(e)
            }

    def _upload_document_sync(
        self,
        file_path: str,
        cabinet_id: str,
        index_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Synchronous document upload using DocuWare REST API."""
        try:
            # Get cabinet from cache, or populate cache if empty
            if cabinet_id not in self.cabinet_cache:
                print(f"Cabinet {cabinet_id} not in cache, populating...")
                # Populate cache by iterating organizations
                for org in self.client.organizations:
                    for cabinet in org.file_cabinets:
                        self.cabinet_cache[cabinet.id] = cabinet
                        if cabinet.id == cabinet_id:
                            break

            # Get cabinet from cache
            if cabinet_id not in self.cabinet_cache:
                raise Exception(f"Cabinet {cabinet_id} not found")

            cabinet = self.cabinet_cache[cabinet_id]

            # Step 1: Upload document file first (without index data)
            import requests
            from pathlib import Path
            import xml.etree.ElementTree as ET

            # Get the documents endpoint from cabinet
            documents_endpoint = cabinet.endpoints['documents']

            # Build full URL (endpoint is relative, need to add base URL)
            if not documents_endpoint.startswith('http'):
                # Get base URL from client connection
                base_url = self.client.conn.base_url
                full_url = f"{base_url}{documents_endpoint}"
            else:
                full_url = documents_endpoint

            # Prepare file upload
            with open(file_path, 'rb') as f:
                files = {'file': (Path(file_path).name, f, 'application/pdf')}

                # Upload file
                response = self.client.conn.session.post(
                    full_url,
                    files=files
                )

            print(f"Upload response status: {response.status_code}")
            response.raise_for_status()

            # Parse XML response to get document ID
            try:
                # Response is XML
                root = ET.fromstring(response.text)
                # Extract Id attribute
                document_id = root.get('Id')
                print(f"Uploaded document, got ID: {document_id}")
            except Exception as e:
                print(f"Could not parse XML response: {e}")
                # Fallback to extracting from location header
                location = response.headers.get('Location', '')
                if location:
                    import re
                    match = re.search(r'/Documents/(\d+)', location)
                    if match:
                        document_id = match.group(1)
                    else:
                        document_id = "unknown"
                else:
                    document_id = "unknown"

            # Step 2: Update document with index fields if we have data
            if document_id and document_id != "unknown" and index_data:
                print(f"Updating document {document_id} with index data: {index_data}")

                # Build update URL
                update_url = f"{full_url}/{document_id}/Fields"

                # Build JSON payload for field update
                fields_payload = {
                    "Field": []
                }

                for field_name, value in index_data.items():
                    field_entry = {
                        "FieldName": field_name,
                        "Item": str(value),
                        "ItemElementName": "String"
                    }
                    fields_payload["Field"].append(field_entry)

                # Update document fields
                headers = {
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                }

                update_response = self.client.conn.session.put(
                    update_url,
                    headers=headers,
                    json=fields_payload
                )

                print(f"Index update response status: {update_response.status_code}")
                if update_response.status_code not in [200, 201, 204]:
                    print(f"Index update failed: {update_response.text}")
                else:
                    print(f"✓ Index fields updated successfully")

            return {
                "success": True,
                "document_id": str(document_id),
                "url": f"{self.client.conn.base_url}/DocuWare/Platform/WebClient/#{cabinet_id}/{document_id}",
                "message": "Uploaded successfully"
            }

        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": f"Upload failed: {str(e)}",
                "error": str(e)
            }

    def _prepare_index_data(
        self,
        metadata: Dict[str, Any],
        field_mapping: Dict[str, str],
        index_fields: List[IndexField]
    ) -> Dict[str, Any]:
        """
        Prepare index data for DocuWare upload.

        Args:
            metadata: Extracted document metadata
            field_mapping: Mapping from DocuFlow fields to DocuWare fields
            index_fields: DocuWare index field definitions

        Returns:
            Dictionary of field_name: value for DocuWare API
        """
        index_data = {}

        for docuflow_field, docuware_field in field_mapping.items():
            # Get value from metadata
            value = metadata.get(docuflow_field)

            if value is not None and value != "":
                # Find field definition
                field_def = next((f for f in index_fields if f.name == docuware_field), None)

                if field_def:
                    # Convert value to appropriate type
                    converted_value = self.field_mapping_service.convert_value_for_field(
                        value,
                        field_def
                    )

                    if converted_value is not None:
                        index_data[docuware_field] = converted_value

        return index_data

    async def validate_metadata(
        self,
        metadata: Dict[str, Any],
        storage_config: Dict[str, str],
        credentials: Optional[Dict[str, str]] = None
    ) -> Tuple[bool, List[str]]:
        """
        Validate metadata against DocuWare field requirements.
        Only validates that REQUIRED DocuWare fields have values.
        Optional fields can be empty.

        Args:
            metadata: Extracted metadata (already in DocuWare field names)
            storage_config: Storage configuration with selected_fields
            credentials: Optional credentials to fetch field definitions

        Returns:
            (is_valid: bool, errors: List[str])
        """
        errors = []
        warnings = []

        # Check if required configuration is present
        if 'selected_fields' not in storage_config:
            errors.append("Selected fields not configured")
            return False, errors

        selected_fields = storage_config['selected_fields']

        # If credentials provided, get index fields to check requirements
        index_fields = []
        if credentials and 'cabinet_id' in storage_config and 'dialog_id' in storage_config:
            try:
                index_fields = await self.get_index_fields(
                    credentials,
                    storage_config['cabinet_id'],
                    storage_config['dialog_id']
                )
            except Exception as e:
                print(f"Could not fetch index fields for validation: {e}")

        # Build a map of field names to their definitions
        field_defs = {field.name: field for field in index_fields}

        # Check selected fields
        for field_name in selected_fields:
            value = metadata.get(field_name)

            # Check if this DocuWare field is required
            field_def = field_defs.get(field_name)
            is_required = field_def.required if field_def else False

            if (value is None or value == "") and is_required:
                # Required field is missing
                errors.append(f"Required field '{field_name}' has no value")
            elif (value is None or value == "") and not is_required:
                # Optional field is missing - just a warning, not an error
                warnings.append(f"Optional field '{field_name}' has no value")

        # Log warnings (but don't fail validation)
        if warnings:
            print(f"Validation warnings: {', '.join(warnings)}")

        is_valid = len(errors) == 0
        return is_valid, errors
