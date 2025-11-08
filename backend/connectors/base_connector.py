"""
Base connector interface for Document Management System integrations.
All connectors must implement this interface.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Tuple, Optional


class BaseConnector(ABC):
    """
    Abstract base class for all DMS connectors.
    Defines the interface that all connectors must implement.
    """

    @abstractmethod
    async def test_connection(self, credentials: Dict[str, str]) -> Tuple[bool, str]:
        """
        Test if credentials are valid and connection can be established.

        Args:
            credentials: Dictionary containing connection credentials
                        (server_url, username, password, etc.)

        Returns:
            Tuple of (success: bool, message: str)
            Example: (True, "Connected successfully")
        """
        pass

    @abstractmethod
    async def get_storage_locations(self, credentials: Dict[str, str]) -> List[Dict[str, str]]:
        """
        Get available storage locations (file cabinets, folders, etc.).

        Args:
            credentials: Authentication credentials

        Returns:
            List of storage locations with id and name
            Example: [{"id": "abc123", "name": "Accounting"}, ...]
        """
        pass

    @abstractmethod
    async def upload_document(
        self,
        file_path: str,
        metadata: Dict[str, Any],
        credentials: Dict[str, str],
        storage_config: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Upload document to the DMS with metadata.

        Args:
            file_path: Path to the document file
            metadata: Extracted document metadata
            credentials: Authentication credentials
            storage_config: Storage location and configuration

        Returns:
            Upload result with status and details
            Example: {
                "success": True,
                "document_id": "12345",
                "url": "https://...",
                "message": "Uploaded successfully"
            }
        """
        pass

    @abstractmethod
    async def validate_metadata(
        self,
        metadata: Dict[str, Any],
        storage_config: Dict[str, str],
        credentials: Optional[Dict[str, str]] = None
    ) -> Tuple[bool, List[str]]:
        """
        Validate metadata against storage location requirements.

        Args:
            metadata: Metadata to validate
            storage_config: Storage location configuration with field requirements
            credentials: Optional credentials to fetch field definitions

        Returns:
            Tuple of (is_valid: bool, errors: List[str])
        """
        pass
