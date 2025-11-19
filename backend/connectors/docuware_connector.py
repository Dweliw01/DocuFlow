"""
DocuWare Connector for uploading documents with dynamic discovery.
Uses the official docuware-client library with OAuth2 authentication.
"""
import docuware
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path
import sys
import asyncio
import logging
import json
sys.path.append(str(Path(__file__).parent.parent))

from connectors.base_connector import BaseConnector
from models import FileCabinet, StorageDialog, IndexField, TableColumn
from services.field_mapping_service import get_field_mapping_service

logger = logging.getLogger(__name__)


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
        self.field_definitions_cache = {}  # Cache field definitions by cabinet_id
        self.current_credentials_key = None  # Track current account (server_url + username)
        self.last_auth_attempt = None  # Track last authentication attempt time
        self.auth_failure_count = 0  # Track consecutive auth failures

    def _has_valid_session(self) -> bool:
        """
        Check if we have a valid session.

        Returns:
            True if session exists and is valid
        """
        return self.session is not None and self.client is not None

    def clear_cache(self):
        """
        Clear all cached data (cabinets, session, credentials).
        Called when configuration is cleared or account changes.
        """
        print(f"\n🗑️  Clearing DocuWare connector cache")
        print(f"   Clearing session, client, and all cached data")
        logger.info("Clearing DocuWare connector cache")

        self.cabinet_cache = {}
        self.field_definitions_cache = {}
        self.current_credentials_key = None
        self.client = None
        self.session = None
        self.last_auth_attempt = None
        self.auth_failure_count = 0

        print(f"   ✅ Cache cleared - ready for new configuration\n")

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
                logger.warning(f"Could not convert '{value}' to decimal, skipping field")
                return None

        # Handle Date fields - ensure YYYY-MM-DD format
        elif field_type in ['Date', 'DateTime']:
            # Date should already be in YYYY-MM-DD format from AI
            # Just validate and return
            import re
            if re.match(r'^\d{4}-\d{2}-\d{2}', value_str):
                return value_str
            else:
                logger.warning(f"Date '{value}' not in expected format, skipping field")
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

            logger.info(f"Testing connection to: {server_url}")

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
            logger.error(f"Connection error: {error_msg}")

            if "401" in error_msg or "Unauthorized" in error_msg:
                return False, "Invalid credentials"
            elif "404" in error_msg or "Not Found" in error_msg:
                return False, "Server URL not found. Please verify the URL."
            elif "Connection" in error_msg:
                return False, "Cannot connect to server. Check URL and network."
            else:
                return False, f"Connection failed: {error_msg}"

    def _test_connection_sync(self, server_url: str, username: str, password: str) -> Tuple[bool, str]:
        """
        Synchronous connection test.
        IMPORTANT: Stores the authenticated session so it can be reused later!
        """
        try:
            import time

            # Create credentials key to track account changes
            credentials_key = f"{server_url}|{username}"

            # If credentials changed, clear the cache and reset auth tracking
            if self.current_credentials_key != credentials_key:
                logger.info("Credentials changed, clearing cabinet cache")
                self.cabinet_cache = {}
                self.current_credentials_key = credentials_key
                self.auth_failure_count = 0

            # Add delay if test was called too recently (prevent rapid-fire testing)
            if self.last_auth_attempt:
                time_since_last = time.time() - self.last_auth_attempt
                if time_since_last < 3.0:  # Minimum 3 seconds between test attempts
                    sleep_time = 3.0 - time_since_last
                    print(f"⏳ Waiting {sleep_time:.1f}s before testing (prevents account lockout)")
                    logger.warning(f"Throttling test connection (sleeping {sleep_time:.1f}s)")
                    time.sleep(sleep_time)

            self.last_auth_attempt = time.time()

            # Create client and store it so we can reuse the session
            print(f"🔐 Testing connection to DocuWare...")
            logger.info("Testing connection to DocuWare")
            self.client = docuware.DocuwareClient(server_url)

            # Attempt login (OAuth2 by default) and store the session
            self.session = self.client.login(username, password)

            if self.session:
                print(f"   ✅ Connected successfully - session saved for reuse")
                logger.info("✓ Connected successfully with OAuth2")
                self.auth_failure_count = 0  # Reset on success
                return True, "Connected successfully"
            else:
                self.auth_failure_count += 1
                print(f"   ❌ Login failed")
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
            logger.error(f"Authentication failed: {e}")
            return None

    def _authenticate_sync(self, server_url: str, username: str, password: str) -> Optional[Any]:
        """Synchronous authentication."""
        try:
            import time

            # Create credentials key to track account changes
            credentials_key = f"{server_url}|{username}"

            # Check if credentials changed
            credentials_changed = self.current_credentials_key != credentials_key

            # DEBUG: Log credential comparison
            logger.debug(f"[AUTH DEBUG] Current key: '{self.current_credentials_key}'")
            logger.debug(f"[AUTH DEBUG] New key: '{credentials_key}'")
            logger.debug(f"[AUTH DEBUG] Credentials changed: {credentials_changed}")
            logger.debug(f"[AUTH DEBUG] Has valid session: {self._has_valid_session()}")

            # If we have a valid session and credentials haven't changed, reuse it!
            if self._has_valid_session() and not credentials_changed:
                logger.info("♻️  Reusing existing authenticated session")
                print(f"   ♻️  Reusing existing authenticated session")
                return self.session

            # If credentials changed, clear the cache and reset failure counter
            if credentials_changed:
                logger.warning(f"Credentials changed from '{self.current_credentials_key}' to '{credentials_key}' - clearing cabinet cache")
                self.cabinet_cache = {}
                self.current_credentials_key = credentials_key
                self.auth_failure_count = 0

            # Check if we've had too many recent failures (possible account lockout)
            if self.auth_failure_count >= 3:
                print(f"⛔ Authentication blocked after {self.auth_failure_count} consecutive failures - your DocuWare account may be locked!")
                logger.error(f"Authentication blocked after {self.auth_failure_count} consecutive failures - account may be locked")
                return None

            # Add delay between authentication attempts to prevent rapid retries
            if self.last_auth_attempt:
                time_since_last = time.time() - self.last_auth_attempt
                if time_since_last < 2.0:  # Minimum 2 seconds between auth attempts
                    sleep_time = 2.0 - time_since_last
                    logger.warning(f"Throttling authentication attempt (sleeping {sleep_time:.1f}s)")
                    time.sleep(sleep_time)

            self.last_auth_attempt = time.time()
            print(f"🔐 Authenticating to DocuWare (attempt {self.auth_failure_count + 1})...")
            logger.info(f"Authenticating to DocuWare (attempt {self.auth_failure_count + 1})")

            # Only create a new client if we don't have one or credentials changed
            if not self.client or credentials_changed:
                logger.debug(f"[AUTH DEBUG] Creating new DocuWare client for {server_url}")
                self.client = docuware.DocuwareClient(server_url)
            else:
                logger.debug(f"[AUTH DEBUG] Reusing existing DocuWare client")

            self.session = self.client.login(username, password)

            # Reset failure counter on success
            self.auth_failure_count = 0
            print(f"   ✅ Authentication successful")
            logger.info("Authentication successful")
            return self.session

        except Exception as e:
            self.auth_failure_count += 1
            print(f"   ❌ Auth error (failure #{self.auth_failure_count}): {e}")
            logger.error(f"Auth error (failure #{self.auth_failure_count}): {e}")
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
            # Only authenticate if we don't have a valid session
            if not self._has_valid_session():
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
            logger.error(f"Failed to get file cabinets: {e}")
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
            logger.info(f"Found {len(cabinets)} file cabinets")
            return cabinets
        except Exception as e:
            logger.error(f"Error getting cabinets: {e}", exc_info=True)
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
            # Only authenticate if we don't have a valid session
            if not self._has_valid_session():
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
            logger.error(f"Failed to get storage dialogs: {e}")
            return []

    def _get_dialogs_sync(self, cabinet_id: str) -> List[StorageDialog]:
        """Synchronous dialog retrieval."""
        try:
            dialogs = []

            # Get cabinet from cache
            if cabinet_id not in self.cabinet_cache:
                logger.warning(f"Cabinet {cabinet_id} not in cache")
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
                    logger.warning(f"Error getting default dialog: {e}")

            logger.info(f"Found {len(dialogs)} dialogs for cabinet {cabinet_id}")
            return dialogs
        except Exception as e:
            logger.error(f"Error getting dialogs: {e}", exc_info=True)
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
            # Only authenticate if we don't have a valid session
            if not self._has_valid_session():
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
            logger.error(f"Failed to get index fields: {e}")
            return []

    def _get_fields_sync(self, cabinet_id: str, dialog_id: str) -> List[IndexField]:
        """
        Synchronous field retrieval using dialog definition API (primary)
        with fallback to document-based retrieval.

        Primary: Dialog definition API - works even with empty cabinets
        Fallback: Document-based retrieval - used if dialog API fails
        """
        try:
            fields = []

            # PRIMARY METHOD: Get dialog definition first
            # This contains complete field schema including table column definitions
            dialog_definition = self._get_dialog_definition(cabinet_id, dialog_id)
            use_dialog_definition = bool(dialog_definition and dialog_definition.get('Fields'))

            if use_dialog_definition:
                logger.info(f"Using dialog definition API for field discovery (cabinet {cabinet_id}, dialog {dialog_id})")

                # Parse fields from dialog definition
                for field_def in dialog_definition.get('Fields', []):
                    field_name = field_def.get('DBFieldName')
                    field_label = field_def.get('DlgLabel', field_name)  # Use dialog label (what users see in DocuWare)
                    field_type = field_def.get('DWFieldType', 'Text')
                    field_length = field_def.get('Length')
                    field_required = field_def.get('NotEmpty', False)
                    is_system = field_def.get('IsSystemField', False)

                    # Skip system fields
                    if self._is_system_field(field_name) or is_system:
                        continue

                    # Check if this is a table field
                    is_table = (field_type == 'Table')
                    table_columns = None

                    if is_table:
                        # Parse table columns from dialog definition
                        table_columns = self._parse_table_columns_from_dialog(dialog_definition, field_name)
                        logger.debug(f"Table field {field_name}: Found {len(table_columns) if table_columns else 0} columns from dialog definition")

                    # Map DocuWare types to our types
                    type_mapping = {
                        'Text': 'String',
                        'Decimal': 'Decimal',
                        'Int': 'Int',
                        'DateTime': 'DateTime',
                        'Date': 'Date',
                        'Memo': 'Memo',
                        'Table': 'Table'
                    }
                    mapped_type = type_mapping.get(field_type, 'String')

                    fields.append(IndexField(
                        name=field_name,
                        label=field_label,  # Display name for frontend
                        type=mapped_type,
                        required=field_required,
                        max_length=field_length,
                        validation=None,
                        is_system_field=is_system,
                        is_table_field=is_table,
                        table_columns=table_columns
                    ))

                logger.info(f"Found {len(fields)} fields from dialog definition")
                return fields

            # FALLBACK METHOD: Document-based retrieval if dialog definition unavailable
            logger.info(f"Dialog definition unavailable, falling back to document-based field discovery")

            # Get cabinet from cache, or populate cache if empty
            if cabinet_id not in self.cabinet_cache:
                logger.debug(f"Cabinet {cabinet_id} not in cache, populating...")
                # Populate cache by iterating organizations
                for org in self.client.organizations:
                    for cabinet in org.file_cabinets:
                        self.cabinet_cache[cabinet.id] = cabinet
                        if cabinet.id == cabinet_id:
                            break

            # Get cabinet from cache
            if cabinet_id not in self.cabinet_cache:
                logger.error(f"Cabinet {cabinet_id} not found after populating cache")
                return []

            cabinet = self.cabinet_cache[cabinet_id]

            # Build URL to get document by ID
            base_url = self.client.conn.base_url
            import requests

            # Try to find a document with table field data
            # We'll try document IDs 1-10, looking for one with populated table fields
            doc_data = None
            doc_ids_to_try = list(range(1, 11))  # Try IDs 1-10

            # First, try document ID 1
            for doc_id in doc_ids_to_try:
                doc_url = f"{base_url}/DocuWare/Platform/FileCabinets/{cabinet_id}/Documents/{doc_id}"
                try:
                    response = self.client.conn.session.get(
                        doc_url,
                        headers={"Accept": "application/json"}
                    )

                    if response.status_code == 200:
                        doc_data = response.json()
                        logger.debug(f"Successfully retrieved document ID {doc_id}")

                        # Check if this document has table fields with data
                        has_table_data = self._document_has_table_data(doc_data)
                        if has_table_data:
                            logger.debug(f"Document {doc_id} has table field data, using it for field discovery")
                            break
                        else:
                            logger.debug(f"Document {doc_id} has no table data, trying next...")

                except Exception as e:
                    logger.debug(f"Could not retrieve document ID {doc_id}: {e}")
                    continue

            # If none of the first 10 worked, try searching for any document
            if not doc_data:
                logger.debug("No documents found in IDs 1-10, searching for first available document...")
                search_url = f"{base_url}/DocuWare/Platform/FileCabinets/{cabinet_id}/Documents"
                search_response = self.client.conn.session.get(
                    search_url,
                    headers={"Accept": "application/json"},
                    params={"count": 20}  # Get first 20 documents
                )

                if search_response.status_code == 200:
                    search_data = search_response.json()
                    items = search_data.get('Items', [])

                    # Try each document until we find one with table data
                    for item in items:
                        doc_id = item.get('Id')
                        try:
                            doc_url = f"{base_url}/DocuWare/Platform/FileCabinets/{cabinet_id}/Documents/{doc_id}"
                            response = self.client.conn.session.get(
                                doc_url,
                                headers={"Accept": "application/json"}
                            )

                            if response.status_code == 200:
                                doc_data = response.json()
                                if self._document_has_table_data(doc_data):
                                    logger.debug(f"Found document {doc_id} with table data")
                                    break
                        except:
                            continue

            if not doc_data:
                raise Exception("Could not find any documents in the file cabinet")

            # Parse fields from document
            if 'Fields' in doc_data:
                for field_data in doc_data['Fields']:
                    field_name = field_data.get('FieldName')
                    field_label = field_data.get('FieldLabel', field_name)
                    is_system_field = field_data.get('SystemField', False)
                    is_read_only = field_data.get('ReadOnly', False)
                    item_element_name = field_data.get('ItemElementName', 'String')

                    # Skip system fields (unless needed)
                    if self._is_system_field(field_name):
                        continue

                    # Check if this is a table field
                    is_table = item_element_name == 'Table'
                    table_columns = None

                    if is_table:
                        # Parse table columns
                        table_columns = self._parse_table_columns(field_data)
                        logger.debug(f"Table field {field_name}: Found {len(table_columns) if table_columns else 0} columns")

                    fields.append(IndexField(
                        name=field_name,
                        label=field_label,  # Display name for frontend
                        type=item_element_name,
                        required=False,  # Default to optional - DocuWare API doesn't expose required field info
                        max_length=None,
                        validation=None,
                        is_system_field=is_system_field,
                        is_table_field=is_table,
                        table_columns=table_columns
                    ))

            logger.info(f"Found {len(fields)} fields (including table fields) for cabinet {cabinet_id}")
            return fields

        except Exception as e:
            logger.error(f"Error getting fields from document: {e}", exc_info=True)
            return []

    def _document_has_table_data(self, doc_data: Dict[str, Any]) -> bool:
        """
        Check if a document has table fields with populated data.

        Args:
            doc_data: Document data from API

        Returns:
            True if document has table fields with rows
        """
        try:
            fields = doc_data.get('Fields', [])
            for field in fields:
                if field.get('ItemElementName') == 'Table':
                    item = field.get('Item', {})
                    if isinstance(item, dict) and item.get('$type') == 'DocumentIndexFieldTable':
                        rows = item.get('Row', [])
                        if rows and len(rows) > 0:
                            return True
            return False
        except Exception:
            return False

    def _get_dialog_definition(self, cabinet_id: str, dialog_id: str) -> Dict[str, Any]:
        """
        Get dialog definition from DocuWare API.
        This contains field schema including table field column definitions.

        Args:
            cabinet_id: File cabinet ID
            dialog_id: Dialog ID

        Returns:
            Dialog definition dictionary
        """
        try:
            base_url = self.client.conn.base_url
            dialog_url = f"{base_url}/DocuWare/Platform/FileCabinets/{cabinet_id}/Dialogs/{dialog_id}"

            logger.debug(f"Fetching dialog definition from: {dialog_url}")

            response = self.client.conn.session.get(
                dialog_url,
                headers={"Accept": "application/json"}
            )

            if response.status_code == 200:
                dialog_data = response.json()
                logger.debug(f"Successfully retrieved dialog definition for dialog {dialog_id}")
                return dialog_data
            else:
                logger.warning(f"Failed to get dialog definition: HTTP {response.status_code}")
                return {}

        except Exception as e:
            logger.error(f"Error fetching dialog definition: {e}", exc_info=True)
            return {}

    def _parse_table_columns_from_dialog(self, dialog_definition: Dict[str, Any], table_field_name: str) -> List[TableColumn]:
        """
        Parse table field column definitions from dialog definition.
        This works even if the cabinet is empty.

        Args:
            dialog_definition: Dialog definition from API
            table_field_name: Name of the table field

        Returns:
            List of TableColumn objects
        """
        columns = []

        try:
            # Dialog definition contains field definitions
            fields = dialog_definition.get('Fields', [])

            for field_def in fields:
                if field_def.get('DBFieldName') == table_field_name:
                    # Found our table field
                    logger.debug(f"Found table field definition: {json.dumps(field_def, indent=2)}")

                    field_type = field_def.get('DWFieldType')

                    # Table fields have DWFieldType = 'Table'
                    if field_type == 'Table':
                        # Table field column definitions are in DialogTableFieldColumns
                        table_columns_def = field_def.get('DialogTableFieldColumns', [])
                        logger.debug(f"DialogTableFieldColumns found: {len(table_columns_def)} columns")

                        for col_def in table_columns_def:
                            col_name = col_def.get('DBFieldName')
                            col_label = col_def.get('DlgLabel', col_name)  # Use DlgLabel for dialog fields
                            col_type = col_def.get('DWFieldType', 'Text')
                            col_length = col_def.get('Length')
                            col_required = col_def.get('NotEmpty', False)

                            # Map DocuWare field types to our types
                            type_mapping = {
                                'Text': 'String',
                                'Decimal': 'Decimal',
                                'Int': 'Int',
                                'DateTime': 'DateTime',
                                'Date': 'Date',
                                'Memo': 'Memo'
                            }
                            mapped_type = type_mapping.get(col_type, 'String')

                            columns.append(TableColumn(
                                name=col_name,
                                label=col_label,
                                type=mapped_type,
                                required=col_required,
                                max_length=col_length
                            ))

                        logger.debug(f"Parsed {len(columns)} columns from dialog definition for table {table_field_name}")
                        break

        except Exception as e:
            logger.error(f"Error parsing table columns from dialog: {e}", exc_info=True)

        return columns

    def _parse_table_columns(self, field_data: Dict[str, Any]) -> List[TableColumn]:
        """
        Parse table field column definitions from field data.

        Args:
            field_data: Field data dictionary from document

        Returns:
            List of TableColumn objects
        """
        columns = []

        try:
            item = field_data.get('Item', {})
            if isinstance(item, dict) and item.get('$type') == 'DocumentIndexFieldTable':
                rows = item.get('Row', [])

                # Get column definitions from first row
                if rows and len(rows) > 0:
                    first_row = rows[0]
                    column_values = first_row.get('ColumnValue', [])

                    for col_data in column_values:
                        col_name = col_data.get('FieldName')
                        col_label = col_data.get('FieldLabel', col_name)
                        col_type = col_data.get('ItemElementName', 'String')
                        col_required = not col_data.get('IsNull', True)

                        columns.append(TableColumn(
                            name=col_name,
                            label=col_label,
                            type=col_type,
                            required=col_required
                        ))

                    logger.debug(f"Parsed {len(columns)} columns from table field")

        except Exception as e:
            logger.error(f"Error parsing table columns: {e}", exc_info=True)

        return columns

    def _build_table_field_data(
        self,
        table_field_name: str,
        columns: List[Dict[str, str]],
        line_items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Build DocuWare table field data structure from line items.

        Args:
            table_field_name: Name of the table field
            columns: List of column definitions with name, label, type
            line_items: List of line item dictionaries extracted from document

        Returns:
            DocuWare table field entry ready for upload
        """
        try:
            # Map line item fields to column DISPLAY NAMES (more consistent across cabinets)
            # This mapping connects AI-extracted field names to DocuWare column display labels
            # Using display names instead of DB field names makes this work across different
            # cabinet configurations (e.g., "Rate" works whether DB field is RATE1, ITEM__RATE, etc.)
            # IMPORTANT: List more specific terms first, avoid overly generic terms
            field_mapping = {
                'sku': ['Item Number', 'SKU', 'Product Code', 'Item Code', 'Product Service', 'Product/Service'],
                'description': ['Description', 'Desc', 'Item Description', 'Product Name', 'Item Desc'],
                'quantity': ['Qty', 'Quantity', 'Item Qty'],
                'unit_price': ['Rate', 'Unit Price', 'Price', 'Item Rate', 'Unit Cost'],
                'amount': ['Amount', 'Line Amount', 'Line Total', 'Item Amount', 'Total'],
                'tax': ['Tax', 'Taxable', 'Tax Amount', 'Sales Tax'],
                'unit': ['Unit', 'UOM', 'Unit of Measure'],
                'discount': ['Discount', 'Disc']
            }

            # Build rows from line items
            rows = []

            for line_item in line_items:
                # Build column values for this row
                column_values = []

                for column in columns:
                    col_name = column['name']  # DB field name (used for upload)
                    col_label = column.get('label', col_name)  # Display name (used for matching)
                    col_type = column.get('type', 'String')

                    # Find matching value from line_item using display label
                    # This makes matching more consistent across different cabinets
                    value = self._find_line_item_value(line_item, col_label, field_mapping)

                    # Determine ItemElementName based on column type
                    if col_type in ['Decimal', 'Currency', 'Money']:
                        item_element_name = 'Decimal'
                        # Clean up value for decimal fields
                        if value:
                            value = self._sanitize_field_value(value, 'Decimal')
                    elif col_type in ['Int', 'Integer']:
                        item_element_name = 'Int'
                        if value:
                            value = self._sanitize_field_value(value, 'Int')
                    else:
                        item_element_name = 'String'
                        if value:
                            value = str(value)

                    # Build column value entry
                    col_entry = {
                        "FieldName": col_name,
                        "ItemElementName": item_element_name
                    }

                    # Only add Item if we have a value
                    if value is not None and value != "":
                        col_entry["Item"] = value

                    column_values.append(col_entry)

                # Add row
                rows.append({
                    "ColumnValue": column_values
                })

            # Build table field structure
            table_field = {
                "FieldName": table_field_name,
                "Item": {
                    "$type": "DocumentIndexFieldTable",
                    "Row": rows
                },
                "ItemElementName": "Table"
            }

            return table_field

        except Exception as e:
            logger.error(f"Error building table field data: {e}", exc_info=True)
            return None

    def _find_line_item_value(
        self,
        line_item: Dict[str, Any],
        column_label: str,
        field_mapping: Dict[str, List[str]]
    ) -> Any:
        """
        Find the appropriate value from a line item for a given column.

        Args:
            line_item: Line item dictionary
            column_label: DocuWare column display label (not DB field name)
            field_mapping: Mapping of line item fields to possible column display labels

        Returns:
            Value from line item or None
        """
        column_upper = column_label.upper()

        # First pass: Check for exact matches
        for line_field, possible_columns in field_mapping.items():
            for possible_name in possible_columns:
                if column_upper == possible_name.upper():
                    value = line_item.get(line_field)
                    if value is not None:
                        logger.debug(f"[TABLE MAPPING] Exact match: '{column_label}' -> {line_field} = {value}")
                        return value

        # Second pass: Check if column label contains the possible name (with word boundaries)
        # This allows "Item Number" to match "Item" but not "Item" to match "Item Number"
        for line_field, possible_columns in field_mapping.items():
            for possible_name in possible_columns:
                possible_name_upper = possible_name.upper()
                # Only match if possible_name is a complete word in column_upper
                # E.g., "ITEM NUMBER" contains "ITEM" as a word (separated by space)
                # But "ITEM" does not contain "ITEM NUMBER"
                if len(possible_name_upper) < len(column_upper):
                    # Check if possible_name is at the start followed by separator
                    if column_upper.startswith(possible_name_upper + '_') or column_upper.startswith(possible_name_upper + ' '):
                        value = line_item.get(line_field)
                        if value is not None:
                            logger.debug(f"[TABLE MAPPING] Prefix match: '{column_label}' -> {line_field} = {value}")
                            return value
                    # Check if possible_name is at the end preceded by separator
                    if column_upper.endswith('_' + possible_name_upper) or column_upper.endswith(' ' + possible_name_upper):
                        value = line_item.get(line_field)
                        if value is not None:
                            logger.debug(f"[TABLE MAPPING] Suffix match: '{column_label}' -> {line_field} = {value}")
                            return value
                    # Check if possible_name is in the middle with separators
                    if '_' + possible_name_upper + '_' in column_upper or ' ' + possible_name_upper + ' ' in column_upper:
                        value = line_item.get(line_field)
                        if value is not None:
                            logger.debug(f"[TABLE MAPPING] Middle match: '{column_label}' -> {line_field} = {value}")
                            return value

        logger.warning(f"[TABLE MAPPING] No match found for column label: '{column_label}'")
        # If no mapping found, return None
        return None

    def _clean_field_value(self, field_name: str, value: Any) -> str:
        """
        Clean field values for DocuWare, especially numeric/currency fields.

        Args:
            field_name: Name of the field
            value: Raw value

        Returns:
            Cleaned value suitable for DocuWare
        """
        if value is None or value == '':
            return ''

        str_value = str(value)

        # Fields that might contain currency or numeric values with formatting
        numeric_fields = ['AMOUNT', 'TOTAL', 'SUBTOTAL', 'TAX', 'PRICE', 'COST', 'RATE']

        # Check if this field name contains any numeric field keywords
        is_numeric = any(keyword in field_name.upper() for keyword in numeric_fields)

        if is_numeric:
            # Remove currency symbols and thousand separators
            cleaned = str_value.replace('$', '').replace('€', '').replace('£', '')
            cleaned = cleaned.replace(',', '').replace(' ', '').strip()

            # Validate it's a valid number
            try:
                float(cleaned)
                logger.debug(f"Cleaned numeric field {field_name}: '{str_value}' -> '{cleaned}'")
                return cleaned
            except ValueError:
                # Not a valid number, return as-is
                pass

        return str_value

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
                "selected_fields": ["VENDOR", "ORDER_DATE", ...],
                "selected_table_columns": {"ITEM_DETAILS": [{"name": "ITEM__QTY", ...}, ...]}
            }

        Returns:
            Upload result with status and document ID
        """
        try:
            cabinet_id = storage_config['cabinet_id']
            dialog_id = storage_config['dialog_id']
            selected_fields = storage_config.get('selected_fields', [])
            selected_table_columns = storage_config.get('selected_table_columns', {})

            # Only authenticate if we don't have a valid session
            if not self._has_valid_session():
                session = await self.authenticate(credentials)
                if not session:
                    return {
                        "success": False,
                        "message": "Authentication failed",
                        "error": "Could not authenticate with DocuWare"
                    }

            # Get field definitions to sanitize data (use cache to avoid repeated API calls)
            cache_key = f"{cabinet_id}_{dialog_id}"
            if cache_key in self.field_definitions_cache:
                field_definitions = self.field_definitions_cache[cache_key]
                logger.debug("Using cached field definitions")
            else:
                field_definitions = await self.get_index_fields(credentials, cabinet_id, dialog_id)
                self.field_definitions_cache[cache_key] = field_definitions
                logger.debug("Cached field definitions for future uploads")

            field_types = {field.name: field.type for field in field_definitions}

            # Metadata is already in DocuWare field format - filter to selected fields and sanitize
            index_data = {}

            for field, value in metadata.items():
                # Skip line_items - they'll be handled separately for table fields
                if field == 'line_items':
                    continue

                if field in selected_fields and value is not None and value != "":
                    # Sanitize value based on field type
                    sanitized_value = self._sanitize_field_value(value, field_types.get(field, 'Text'))
                    if sanitized_value is not None and sanitized_value != "":
                        index_data[field] = sanitized_value

            # Extract line_items for table fields
            line_items = metadata.get('line_items', [])
            logger.debug(f"Preparing upload with {len(line_items)} line items")

            # Upload document in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._upload_document_sync,
                file_path,
                cabinet_id,
                index_data,
                line_items,
                selected_table_columns
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
        index_data: Dict[str, Any],
        line_items: List[Dict[str, Any]] = None,
        selected_table_columns: Dict[str, List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Synchronous document upload using DocuWare REST API.

        Args:
            file_path: Path to PDF file to upload
            cabinet_id: DocuWare cabinet ID
            index_data: Index field data (field_name -> value)
            line_items: List of line items extracted from document
            selected_table_columns: Dict of table_field_name -> list of column definitions
        """
        try:
            if line_items is None:
                line_items = []
            if selected_table_columns is None:
                selected_table_columns = {}
            # Get cabinet from cache, or populate cache if empty
            if cabinet_id not in self.cabinet_cache:
                logger.debug(f"Cabinet {cabinet_id} not in cache, populating...")
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

            logger.debug(f"Upload response status: {response.status_code}")
            response.raise_for_status()

            # Parse XML response to get document ID
            try:
                # Response is XML
                root = ET.fromstring(response.text)
                # Extract Id attribute
                document_id = root.get('Id')
                print(f"      📄 Document uploaded, ID: {document_id}")
                logger.debug(f"Uploaded document, got ID: {document_id}")
            except Exception as e:
                logger.warning(f"Could not parse XML response: {e}")
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
            if document_id and document_id != "unknown" and (index_data or selected_table_columns):
                logger.debug(f"Updating document {document_id} with index data: {index_data}")

                # Build update URL
                update_url = f"{full_url}/{document_id}/Fields"

                # Build JSON payload for field update
                fields_payload = {
                    "Field": []
                }

                # Add regular index fields
                for field_name, value in index_data.items():
                    # Clean numeric/currency values for decimal fields
                    cleaned_value = self._clean_field_value(field_name, value)

                    field_entry = {
                        "FieldName": field_name,
                        "Item": str(cleaned_value),
                        "ItemElementName": "String"
                    }
                    fields_payload["Field"].append(field_entry)

                # Add table fields if we have line items and selected columns
                if line_items and selected_table_columns:
                    logger.debug(f"Building table fields from {len(line_items)} line items")

                    for table_field_name, columns in selected_table_columns.items():
                        table_data = self._build_table_field_data(
                            table_field_name,
                            columns,
                            line_items
                        )

                        if table_data:
                            fields_payload["Field"].append(table_data)
                            logger.debug(f"✓ Built table field {table_field_name} with {len(line_items)} rows")

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

                logger.debug(f"Index update response status: {update_response.status_code}")
                if update_response.status_code not in [200, 201, 204]:
                    print(f"      ❌ Index update failed: {update_response.text}")
                    logger.error(f"Index update failed: {update_response.text}")
                else:
                    print(f"      ✅ Index fields updated")
                    logger.debug("✓ Index fields updated successfully")

            return {
                "success": True,
                "document_id": str(document_id),
                "url": f"{self.client.conn.base_url}/DocuWare/Platform/WebClient/#{cabinet_id}/{document_id}",
                "message": "Uploaded successfully"
            }

        except Exception as e:
            logger.error(f"Upload failed: {str(e)}", exc_info=True)
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

        IMPORTANT: Only fails validation for required fields that are CRITICALLY needed.
        Fields that commonly don't appear on documents (TAX, DUE_DATE, etc.) are treated as warnings.

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
                logger.warning(f"Could not fetch index fields for validation: {e}")

        # Build a map of field names to their definitions
        field_defs = {field.name: field for field in index_fields}

        # Fields that commonly don't exist on documents - treat as non-critical
        # These are often workflow/processing fields added by DocuWare, not on original documents
        # Also includes fields that only exist on certain document types (invoices vs shipping docs)
        non_critical_fields = [
            'TAX', 'DUE_DATE', 'CUSTOMER_PO', 'SUBTOTAL', 'SHIP_DATE', 'DELIVERY_DATE',
            'CUSTOMER_DLVERY_DATE', 'CUSTOMER_DELIVERY_DATE', 'DELIVERY_REQUESTED',
            'QB_UPLOAD_STATUS', 'STATUS', 'UPLOAD_STATUS', 'PROCESSED', 'APPROVED',
            'CUSTOMER_REGION', 'REGION', 'TERRITORY', 'SALES_REP', 'SALES_REPS',
            'PO_AUTO_NUM', 'AUTO_NUM', 'SEQUENCE',
            'INVOICE_NUMBER', 'INVOICE_NO', 'INVOCE_NO_', 'INV_NO',  # Not on shipping/customs docs
            'TOTAL_AMOUNT', 'AMOUNT', 'TOTAL',  # Not on packing lists/BOLs
            'ORDER_NUMBER', 'ORDER_NO', 'PO_NUMBER', 'P_O_NUMBER',  # May not be on all doc types
            'EMPLOYEE_ID', 'FIRST_NAME', 'LAST_NAME', 'FULL_NAME'  # HR fields - often handwritten or in unexpected locations
        ]

        # Check selected fields
        for field_name in selected_fields:
            value = metadata.get(field_name)

            # Check if this DocuWare field is required
            field_def = field_defs.get(field_name)
            is_required = field_def.required if field_def else False

            if (value is None or value == "") and is_required:
                # Check if this is a non-critical field
                if field_name.upper() in non_critical_fields:
                    # Treat as warning, not error
                    warnings.append(f"Required field '{field_name}' has no value (document may not have this field)")
                else:
                    # Critical required field is missing
                    errors.append(f"Required field '{field_name}' has no value")
            elif (value is None or value == "") and not is_required:
                # Optional field is missing - just a warning, not an error
                warnings.append(f"Optional field '{field_name}' has no value")

        # Log warnings (but don't fail validation)
        if warnings:
            logger.debug(f"Validation warnings: {', '.join(warnings)}")

        is_valid = len(errors) == 0
        return is_valid, errors
