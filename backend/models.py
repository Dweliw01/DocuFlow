"""
Data models for the Document Digitization MVP.
Uses Pydantic for data validation and serialization.
"""
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime


# ============================================================================
# User Models - Authentication and Authorization
# ============================================================================


class User(BaseModel):
    """
    User account model.
    Represents an authenticated user in the system.
    """
    id: int
    auth0_user_id: str
    email: str
    name: Optional[str] = None
    organization_id: Optional[int] = None  # Link to organization
    role: Optional[str] = "member"  # owner/admin/member
    created_at: datetime
    last_login: Optional[datetime] = None


class Auth0Config(BaseModel):
    """
    Auth0 configuration for frontend.
    Returned to client for authentication setup.
    """
    domain: str
    client_id: str
    audience: str


class LoginResponse(BaseModel):
    """
    Response after successful login.
    Contains user info and access token.
    """
    user: User
    message: str = "Login successful"


# ============================================================================
# Multi-Tenant Organization Models
# ============================================================================


class Organization(BaseModel):
    """
    Organization/tenant model.
    Represents a customer business using DocuFlow.
    """
    id: int
    name: str
    created_at: datetime
    subscription_plan: str = "trial"  # trial/starter/pro/enterprise/custom
    billing_email: Optional[str] = None
    status: str = "active"  # active/suspended/trial/cancelled
    metadata: Optional[Dict[str, Any]] = None


class OrganizationCreate(BaseModel):
    """
    Request model for creating a new organization.
    Used during user onboarding.
    """
    name: str
    billing_email: str
    subscription_plan: str = "trial"


class OrganizationUpdate(BaseModel):
    """
    Request model for updating organization details.
    """
    name: Optional[str] = None
    billing_email: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class OrganizationSettings(BaseModel):
    """
    Organization-level settings model.
    Replaces user-level connector configurations.
    """
    id: int
    organization_id: int
    connector_type: str  # docuware/google_drive
    config_encrypted: str  # Encrypted JSON
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    created_by_user_id: Optional[int] = None


class Subscription(BaseModel):
    """
    Subscription/billing configuration for an organization.
    Supports multiple billing models.
    """
    id: int
    organization_id: int
    plan_type: str = "per_document"  # per_document/tiered/custom

    # Per-document billing
    price_per_document: Optional[float] = 0.10

    # Tiered billing
    monthly_base_fee: Optional[float] = None
    monthly_document_limit: Optional[int] = None
    overage_price_per_document: Optional[float] = None

    # Payment integration
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None

    # Billing cycle
    billing_cycle_start: Optional[datetime] = None
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None

    # Status
    status: str = "active"  # active/past_due/cancelled

    created_at: datetime
    updated_at: datetime


class SubscriptionUpdate(BaseModel):
    """
    Request model for updating subscription.
    """
    plan_type: Optional[str] = None
    price_per_document: Optional[float] = None
    monthly_base_fee: Optional[float] = None
    monthly_document_limit: Optional[int] = None
    overage_price_per_document: Optional[float] = None


class UsageLog(BaseModel):
    """
    Usage tracking log for billing.
    Records all billable actions.
    """
    id: int
    organization_id: int
    user_id: Optional[int] = None
    action_type: str  # document_upload/document_processed/ocr_extraction
    document_count: int = 1
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None
    billed: bool = False
    billing_period: Optional[str] = None  # e.g., "2025-01"


class UsageStats(BaseModel):
    """
    Aggregated usage statistics for an organization.
    Used for displaying current usage in UI.
    """
    organization_id: int
    billing_period: str
    total_documents_processed: int
    total_documents_uploaded: int
    total_ocr_extractions: int
    total_cost: float
    documents_by_category: Dict[str, int] = Field(default_factory=dict)
    usage_by_user: Dict[str, int] = Field(default_factory=dict)


class OrganizationUserInvite(BaseModel):
    """
    Request model for inviting a user to an organization.
    """
    email: str
    role: str = "member"  # owner/admin/member
    name: Optional[str] = None


class OrganizationWithUsers(BaseModel):
    """
    Organization model with user list.
    Used for admin pages.
    """
    organization: Organization
    users: List[User]
    subscription: Optional[Subscription] = None


# ============================================================================
# Document Processing Models
# ============================================================================


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
    id: Optional[int] = None  # Document database ID (for review/edit functionality)
    filename: str
    original_path: str
    category: DocumentCategory
    confidence: float = Field(ge=0.0, le=1.0)  # Between 0 and 1
    processed_path: Optional[str] = None
    extracted_text_preview: str  # First 500 chars of extracted text
    extracted_data: Optional[ExtractedData] = None  # Structured data extracted from document
    connector_type: Optional[str] = None  # Which connector this document was processed with
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


class FolderStructureLevel(str, Enum):
    """
    Available folder organization levels for dynamic folder structure.
    Users can configure primary, secondary, and tertiary folder levels.
    """
    CATEGORY = "category"  # Document category (Invoice, Receipt, Contract, etc.)
    VENDOR = "vendor"  # Vendor/supplier name
    CLIENT = "client"  # Client/customer name
    COMPANY = "company"  # Company name (general)
    YEAR = "year"  # Year from document date (2025, 2024, etc.)
    YEAR_MONTH = "year_month"  # Year-Month from document date (2025-01, 2025-02, etc.)
    DOCUMENT_TYPE = "document_type"  # Specific document type (Purchase Invoice, W2, etc.)
    PERSON_NAME = "person_name"  # Person name (for HR/personal docs)
    NONE = "none"  # No folder level (skip)


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
    name: str  # DB field name (e.g., INVOICE_NUMBER)
    label: Optional[str] = None  # Display label (e.g., "Invoice Number")
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
    Google Drive connector configuration.
    Stores OAuth2 credentials and folder preferences.
    """
    refresh_token: str  # OAuth2 refresh token
    client_id: str  # OAuth2 client ID
    client_secret: str  # OAuth2 client secret
    root_folder_name: Optional[str] = "DocuFlow"  # Root folder name in Drive
    root_folder_id: Optional[str] = None  # Cached root folder ID
    auto_create_folders: bool = True  # Auto-create category subfolders

    # Dynamic folder structure configuration
    primary_level: FolderStructureLevel = FolderStructureLevel.CATEGORY  # First folder level
    secondary_level: FolderStructureLevel = FolderStructureLevel.VENDOR  # Second folder level
    tertiary_level: FolderStructureLevel = FolderStructureLevel.NONE  # Third folder level (optional)


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
