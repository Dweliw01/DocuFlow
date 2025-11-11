"""
Data models for the Document Digitization MVP.
Uses Pydantic for data validation and serialization.
"""
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime


class DocumentCategory(str, Enum):
    """
    Supported document categories for classification.
    AI will categorize each document into one of these types.
    """
    INVOICE = "Invoice"
    CONTRACT = "Contract"
    RECEIPT = "Receipt"
    LEGAL = "Legal Document"
    HR = "HR Document"
    TAX = "Tax Document"
    FINANCIAL = "Financial Statement"
    CORRESPONDENCE = "Correspondence"
    OTHER = "Other"


class LineItem(BaseModel):
    """
    Individual line item from an invoice, receipt, or purchase order.
    """
    description: Optional[str] = None  # Item/service description
    quantity: Optional[str] = None  # Quantity (e.g., "10", "2.5")
    unit: Optional[str] = None  # Unit of measure (e.g., "EA", "boxes", "hours")
    unit_price: Optional[str] = None  # Price per unit
    amount: Optional[str] = None  # Line total
    sku: Optional[str] = None  # Product/SKU code
    tax: Optional[str] = None  # Tax for this line item
    discount: Optional[str] = None  # Discount applied


class ExtractedData(BaseModel):
    """
    Structured data extracted from document via OCR and AI.
    Fields are optional as not all documents contain all information.
    """
    document_type: Optional[str] = None  # More specific type (e.g., "Purchase Invoice", "Employment Contract")
    person_name: Optional[str] = None  # Name of person on the document
    company: Optional[str] = None  # Company name (general)
    vendor: Optional[str] = None  # Vendor/supplier name (for invoices/receipts)
    client: Optional[str] = None  # Client/customer name
    date: Optional[str] = None  # Primary date (issue date, contract date, etc.)
    due_date: Optional[str] = None  # Due date (for invoices/payments)
    amount: Optional[str] = None  # Total amount
    currency: Optional[str] = None  # Currency code (USD, EUR, etc.)
    document_number: Optional[str] = None  # Invoice #, Contract #, Receipt #, etc.
    reference_number: Optional[str] = None  # PO #, Reference #, Case #, etc.
    address: Optional[str] = None  # Address found on document
    email: Optional[str] = None  # Email address
    phone: Optional[str] = None  # Phone number
    line_items: Optional[List[LineItem]] = None  # Line items for invoices/receipts
    other_data: Optional[Dict[str, Any]] = Field(default_factory=dict)  # Any other relevant data

    @validator('address', 'phone', 'email', pre=True)
    def convert_list_to_string(cls, v):
        """Convert lists to strings by joining with commas. AI sometimes returns multiple values."""
        if isinstance(v, list):
            return ', '.join(str(item) for item in v if item)
        return v


class ProcessingStatus(str, Enum):
    """
    Status of a document processing batch.
    Tracks the lifecycle: pending -> processing -> completed/failed
    """
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentResult(BaseModel):
    """
    Result of processing a single document.
    Contains categorization info, confidence score, extracted text preview, and structured data.
    """
    filename: str
    original_path: str
    category: DocumentCategory
    confidence: float = Field(ge=0.0, le=1.0)  # Between 0 and 1
    processed_path: Optional[str] = None
    extracted_text_preview: str  # First 500 chars of extracted text
    extracted_data: Optional[ExtractedData] = None  # Structured data extracted from document
    error: Optional[str] = None
    processing_time: float  # seconds
    upload_result: Optional['UploadResult'] = None  # Result of connector upload (if configured)

    class Config:
        """Allow enum values in JSON responses"""
        use_enum_values = True


class BatchUploadResponse(BaseModel):
    """
    Response returned immediately after file upload.
    Processing happens in background, client uses batch_id to check status.
    """
    batch_id: str
    total_files: int
    status: ProcessingStatus
    started_at: datetime

    class Config:
        """Allow enum values in JSON responses"""
        use_enum_values = True


class BatchResultResponse(BaseModel):
    """
    Complete result of a batch processing job.
    Includes summary statistics and detailed results for each document.
    """
    batch_id: str
    status: ProcessingStatus
    total_files: int
    processed_files: int
    successful: int
    failed: int
    results: List[DocumentResult]
    processing_summary: dict  # Category -> count mapping
    download_url: Optional[str] = None

    class Config:
        """Allow enum values in JSON responses"""
        use_enum_values = True


# ============================================================================
# Connector Models - Document Management System Integration
# ============================================================================


class ConnectorType(str, Enum):
    """
    Supported document management system connectors.
    User selects ONE destination for document upload.
    """
    NONE = "none"
    DOCUWARE = "docuware"
    GOOGLE_DRIVE = "google_drive"
    ONEDRIVE = "onedrive"


class FileCabinet(BaseModel):
    """
    DocuWare file cabinet (or equivalent storage location in other systems).
    """
    id: str
    name: str
    description: Optional[str] = None


class StorageDialog(BaseModel):
    """
    DocuWare storage dialog (defines the entry form and fields).
    """
    id: str
    name: str
    description: Optional[str] = None


class TableColumn(BaseModel):
    """
    Column definition for a DocuWare table field.
    """
    name: str  # Column field name (e.g., ITEM__PRODUCT_SERVICE)
    label: str  # Column display label (e.g., ITEM NUMBER)
    type: str  # Data type (String, Decimal, Int, etc.)
    required: bool = False


class IndexField(BaseModel):
    """
    Document index field in DocuWare (metadata field).
    """
    name: str
    type: str  # Text, Date, Decimal, Integer, Table, etc.
    required: bool
    max_length: Optional[int] = None
    validation: Optional[str] = None
    is_system_field: bool = False  # True for DocuWare system fields (DWDOCID, etc.)
    is_table_field: bool = False  # True for table fields
    table_columns: Optional[List['TableColumn']] = None  # Column definitions if this is a table field


class DocuWareConfig(BaseModel):
    """
    DocuWare connector configuration.
    Stores connection details and selected fields for AI extraction.
    """
    server_url: str
    username: str
    encrypted_password: str
    cabinet_id: str
    cabinet_name: str
    dialog_id: str
    dialog_name: str
    selected_fields: List[str]  # List of DocuWare field names to extract
    selected_table_columns: Optional[Dict[str, List[Dict[str, str]]]] = Field(default_factory=dict)  # Table field name -> list of column definitions


class GoogleDriveConfig(BaseModel):
    """
    Google Drive connector configuration (future).
    """
    access_token: str
    refresh_token: str
    folder_id: Optional[str] = None
    folder_name: Optional[str] = None


class OneDriveConfig(BaseModel):
    """
    OneDrive connector configuration (future).
    """
    access_token: str
    refresh_token: str
    site_id: Optional[str] = None
    folder_id: Optional[str] = None
    folder_name: Optional[str] = None


class ConnectorConfig(BaseModel):
    """
    Main connector configuration.
    User selects one connector type and provides its configuration.
    """
    connector_type: ConnectorType
    docuware: Optional[DocuWareConfig] = None
    google_drive: Optional[GoogleDriveConfig] = None
    onedrive: Optional[OneDriveConfig] = None

    class Config:
        """Allow enum values in JSON responses"""
        use_enum_values = True


class ConnectorTestResponse(BaseModel):
    """
    Response from testing a connector connection.
    """
    success: bool
    message: str


class UploadResult(BaseModel):
    """
    Result of uploading a document to a connector.
    """
    success: bool
    document_id: Optional[str] = None
    url: Optional[str] = None
    message: str
    error: Optional[str] = None
