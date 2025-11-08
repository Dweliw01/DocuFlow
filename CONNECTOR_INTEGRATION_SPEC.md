# DocuFlow - Connector Integration Specification

## Project Overview

**DocuFlow** is a premium AI-powered document processing platform that:
- Extracts text from PDFs using Tesseract OCR
- Categorizes documents using Claude Haiku 4.5 AI (9 categories)
- Extracts structured data (vendors, amounts, dates, contact info)
- Extracts line items from invoices (quantities, prices, SKUs)
- Provides professional SaaS-quality UI
- Batch processes documents with real-time progress tracking

**GitHub:** https://github.com/Dweliw01/DocuFlow.git

**Existing DocuWare Connector:** https://github.com/Dweliw01/docuware-client.git

---

## Current Tech Stack

### Backend
- **Framework:** Python + FastAPI
- **AI:** Claude Haiku 4.5 (Anthropic)
- **OCR:** Tesseract
- **Data Models:** Pydantic
- **Processing:** Async batch processing

### Frontend
- **Design:** Premium SaaS UI (Inter font, modern CSS)
- **JavaScript:** Vanilla JS
- **Features:** Expandable cards, line items tables, real-time progress

### Extracted Data Fields
```python
- document_type
- person_name
- company
- vendor
- client
- date / due_date
- amount / currency
- document_number / reference_number
- address / email / phone
- line_items[] (quantity, unit, unit_price, amount, sku)
- other_data{}
```

---

## New Feature: Document Management System Connectors

### Goal
Enable users to automatically upload processed documents to their chosen Document Management System (DMS) or cloud storage.

### Connectors to Support
1. **DocuWare** (Priority 1 - Most Complex, Highest Value)
2. **Google Drive** (Priority 2 - Most Popular)
3. **OneDrive** (Priority 3 - Enterprise Focus)

### Key Design Decisions

#### 1. Single Destination Upload
- ✅ **User selects ONE destination** (not all three simultaneously)
- Cleaner UX, faster processing, less complexity
- User picks: None / DocuWare / Google Drive / OneDrive

#### 2. No Hardcoded Credentials
- ✅ **All credentials entered via UI**
- Secure, encrypted storage per user/session
- Multi-tenant architecture
- Enterprise-ready approach

#### 3. Dynamic Configuration Discovery
- ✅ **Auto-discover user's DocuWare structure**
- Load file cabinets dynamically
- Load storage dialogs dynamically
- Load index fields dynamically
- Intelligent field mapping

---

## DocuWare Integration - Dynamic Discovery Architecture

### Core Concept: "Zero Configuration" Integration

Users authenticate → System discovers their DocuWare structure → Intelligent mapping → Upload

### Step-by-Step Flow

#### Step 1: Authentication
**User Input (UI):**
- DocuWare Server URL (e.g., `https://company.docuware.cloud`)
- Username
- Password (masked)

**Action:**
- Test connection with credentials
- Retrieve OAuth2 token or session
- Show "✓ Connected" status

#### Step 2: Discover File Cabinets
**API Call:**
```
GET /FileCabinets
```

**Response:**
```json
[
  { "id": "abc123", "name": "Accounting" },
  { "id": "def456", "name": "HR Documents" },
  { "id": "ghi789", "name": "Contracts" }
]
```

**UI Display:**
- Dropdown: "Select File Cabinet"
- Options auto-populated from API response
- User selects target cabinet (e.g., "Accounting")

#### Step 3: Discover Storage Dialogs
**API Call:**
```
GET /FileCabinets/{cabinetId}/Dialogs
```

**Response:**
```json
[
  { "id": "dialog1", "name": "Invoice Entry" },
  { "id": "dialog2", "name": "Receipt Entry" },
  { "id": "dialog3", "name": "Purchase Order Entry" }
]
```

**UI Display:**
- Dropdown: "Select Storage Dialog"
- Options auto-populated based on selected cabinet
- User selects dialog (e.g., "Invoice Entry")

#### Step 4: Discover Index Fields
**API Call:**
```
GET /FileCabinets/{cabinetId}/Dialogs/{dialogId}/Fields
```

**Response:**
```json
[
  {
    "name": "VENDOR_NAME",
    "type": "Text",
    "required": true,
    "maxLength": 100
  },
  {
    "name": "INVOICE_NUMBER",
    "type": "Text",
    "required": true,
    "maxLength": 50
  },
  {
    "name": "INVOICE_DATE",
    "type": "Date",
    "required": true
  },
  {
    "name": "AMOUNT",
    "type": "Decimal",
    "required": true
  },
  {
    "name": "CURRENCY",
    "type": "Text",
    "required": false,
    "maxLength": 3
  },
  {
    "name": "PO_NUMBER",
    "type": "Text",
    "required": false,
    "maxLength": 50
  }
]
```

**UI Display:**
- Show detected fields in a table/list
- Indicate required vs optional
- Display field types
- Show field constraints

#### Step 5: Intelligent Field Mapping
**Auto-Mapping Logic:**
```python
# DocuFlow extracted fields → DocuWare index fields
{
  "vendor": "VENDOR_NAME",           # 100% match
  "document_number": "INVOICE_NUMBER", # 85% fuzzy match
  "date": "INVOICE_DATE",            # 80% match
  "amount": "AMOUNT",                # 100% match
  "currency": "CURRENCY",            # 100% match
  "reference_number": "PO_NUMBER"    # 70% match
}
```

**UI Display:**
- Show proposed mapping
- Allow manual override via dropdown
- Highlight unmapped required fields
- Warning if required field has no source

#### Step 6: Save Configuration
- Encrypt credentials
- Store mapping preferences
- Save selected cabinet/dialog
- Ready for document upload

---

## UI Design Mockup

### Settings Page - DocuWare Configuration

```
┌─────────────────────────────────────────────────────────────┐
│  DocuFlow Settings                                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  📤 Upload Destination                                      │
│  ┌─────────────────────────────────────┐                   │
│  │ Select Upload Destination:          │                   │
│  │ ⚪ None (Local only)                │                   │
│  │ 🔵 DocuWare                         │                   │
│  │ ⚪ Google Drive                     │                   │
│  │ ⚪ OneDrive                         │                   │
│  └─────────────────────────────────────┘                   │
│                                                             │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  🔌 DocuWare Configuration                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  Server URL                                        │   │
│  │  ┌───────────────────────────────────────────┐    │   │
│  │  │ https://company.docuware.cloud           │    │   │
│  │  └───────────────────────────────────────────┘    │   │
│  │                                                     │   │
│  │  Username                                          │   │
│  │  ┌───────────────────────────────────────────┐    │   │
│  │  │ john.doe@company.com                     │    │   │
│  │  └───────────────────────────────────────────┘    │   │
│  │                                                     │   │
│  │  Password                                          │   │
│  │  ┌───────────────────────────────────────────┐    │   │
│  │  │ ••••••••••••                             │    │   │
│  │  └───────────────────────────────────────────┘    │   │
│  │                                                     │   │
│  │  [Test Connection]                                 │   │
│  │  ✓ Connected successfully                          │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  📁 File Cabinet Selection                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Select File Cabinet                               │   │
│  │  ┌───────────────────────────────────────────┐    │   │
│  │  │ Accounting                            ▼  │    │   │
│  │  └───────────────────────────────────────────┘    │   │
│  │  • Accounting                                      │   │
│  │  • HR Documents                                    │   │
│  │  • Contracts                                       │   │
│  │                                                     │   │
│  │  Select Storage Dialog                             │   │
│  │  ┌───────────────────────────────────────────┐    │   │
│  │  │ Invoice Entry                         ▼  │    │   │
│  │  └───────────────────────────────────────────┘    │   │
│  │  • Invoice Entry                                   │   │
│  │  • Receipt Entry                                   │   │
│  │  • Purchase Order Entry                            │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  🏷️  Detected Index Fields                                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  Field Name          Type      Required            │   │
│  │  ───────────────────────────────────────────       │   │
│  │  VENDOR_NAME         Text      ✓ Yes              │   │
│  │  INVOICE_NUMBER      Text      ✓ Yes              │   │
│  │  INVOICE_DATE        Date      ✓ Yes              │   │
│  │  AMOUNT              Decimal   ✓ Yes              │   │
│  │  CURRENCY            Text        No               │   │
│  │  PO_NUMBER           Text        No               │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  🔗 Field Mapping                                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  DocuFlow Field  →  DocuWare Field                │   │
│  │  ──────────────────────────────────────────        │   │
│  │  vendor          →  [VENDOR_NAME         ▼]      │   │
│  │  document_number →  [INVOICE_NUMBER      ▼]      │   │
│  │  date            →  [INVOICE_DATE        ▼]      │   │
│  │  amount          →  [AMOUNT              ▼]      │   │
│  │  currency        →  [CURRENCY            ▼]      │   │
│  │  reference_num   →  [PO_NUMBER           ▼]      │   │
│  │                                                     │   │
│  │  ⚠️ Warning: 0 required fields unmapped            │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  [Save Configuration]  [Cancel]                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Backend Architecture

### New Directory Structure

```
backend/
├── connectors/
│   ├── __init__.py
│   ├── base_connector.py          # Abstract base class
│   ├── docuware_connector.py      # DocuWare integration
│   ├── google_drive_connector.py  # Google Drive (future)
│   ├── onedrive_connector.py      # OneDrive (future)
│   └── connector_manager.py       # Orchestration & selection
├── models.py                       # Add connector config models
├── routes/
│   ├── connector_routes.py        # New: /api/connectors endpoints
│   └── upload.py                  # Update: Add post-processing upload
├── services/
│   ├── encryption_service.py      # New: Credential encryption
│   └── field_mapping_service.py   # New: Smart field mapping
└── config.py                       # Add connector settings
```

### New Data Models

```python
# Connector Configuration
class ConnectorType(str, Enum):
    NONE = "none"
    DOCUWARE = "docuware"
    GOOGLE_DRIVE = "google_drive"
    ONEDRIVE = "onedrive"

class DocuWareConfig(BaseModel):
    server_url: str
    username: str
    encrypted_password: str
    cabinet_id: str
    cabinet_name: str
    dialog_id: str
    dialog_name: str
    field_mapping: Dict[str, str]  # DocuFlow field -> DocuWare field

class ConnectorConfig(BaseModel):
    connector_type: ConnectorType
    docuware: Optional[DocuWareConfig] = None
    # google_drive: Optional[GoogleDriveConfig] = None  # Future
    # onedrive: Optional[OneDriveConfig] = None          # Future

class FileCabinet(BaseModel):
    id: str
    name: str
    description: Optional[str] = None

class StorageDialog(BaseModel):
    id: str
    name: str
    description: Optional[str] = None

class IndexField(BaseModel):
    name: str
    type: str  # Text, Date, Decimal, Integer, etc.
    required: bool
    max_length: Optional[int] = None
    validation: Optional[str] = None
```

### API Endpoints

```python
# New Connector Routes

# Test connection
POST /api/connectors/docuware/test
Body: { "server_url": "...", "username": "...", "password": "..." }
Response: { "success": true, "message": "Connected successfully" }

# Get file cabinets
POST /api/connectors/docuware/cabinets
Body: { "server_url": "...", "username": "...", "password": "..." }
Response: { "cabinets": [{"id": "...", "name": "..."}, ...] }

# Get storage dialogs for cabinet
POST /api/connectors/docuware/dialogs
Body: { "server_url": "...", "username": "...", "password": "...", "cabinet_id": "..." }
Response: { "dialogs": [{"id": "...", "name": "..."}, ...] }

# Get index fields for dialog
POST /api/connectors/docuware/fields
Body: { "server_url": "...", "username": "...", "password": "...", "cabinet_id": "...", "dialog_id": "..." }
Response: { "fields": [{"name": "...", "type": "...", "required": true}, ...] }

# Save connector configuration
POST /api/connectors/config
Body: { "connector_type": "docuware", "docuware": {...} }
Response: { "success": true, "message": "Configuration saved" }

# Get current configuration
GET /api/connectors/config
Response: { "connector_type": "docuware", "docuware": {...} }
```

### Processing Flow with Upload

```python
# Updated processing flow in upload.py

async def process_batch(files):
    # 1. OCR extraction (existing)
    extracted_text = await ocr_service.extract_text(file)

    # 2. AI categorization + data extraction (existing)
    category, confidence, extracted_data = await ai_service.categorize_document(extracted_text)

    # 3. Store results locally (existing)
    result = DocumentResult(...)

    # 4. NEW: Upload to configured connector
    connector_config = get_user_connector_config()
    if connector_config.connector_type != ConnectorType.NONE:
        upload_result = await connector_manager.upload_document(
            file_path=result.processed_path,
            extracted_data=result.extracted_data,
            config=connector_config
        )
        result.upload_status = upload_result

    return result
```

---

## DocuWare Connector Implementation

### Base Connector Interface

```python
# connectors/base_connector.py

from abc import ABC, abstractmethod

class BaseConnector(ABC):
    @abstractmethod
    async def test_connection(self, credentials: dict) -> bool:
        """Test if credentials are valid"""
        pass

    @abstractmethod
    async def upload_document(self, file_path: str, metadata: dict) -> dict:
        """Upload document with metadata"""
        pass
```

### DocuWare Connector

```python
# connectors/docuware_connector.py

class DocuWareConnector(BaseConnector):
    def __init__(self):
        # Use existing docuware-client library
        self.client = None

    async def authenticate(self, server_url: str, username: str, password: str):
        """Authenticate and create client session"""
        # Initialize docuware-client
        # OAuth2 or cookie authentication
        pass

    async def get_file_cabinets(self) -> List[FileCabinet]:
        """Retrieve list of file cabinets"""
        # API: GET /FileCabinets
        pass

    async def get_storage_dialogs(self, cabinet_id: str) -> List[StorageDialog]:
        """Get storage dialogs for a cabinet"""
        # API: GET /FileCabinets/{id}/Dialogs
        pass

    async def get_index_fields(self, cabinet_id: str, dialog_id: str) -> List[IndexField]:
        """Get index field schema for a dialog"""
        # API: GET /FileCabinets/{id}/Dialogs/{id}/Fields
        pass

    async def upload_document(self, file_path: str, metadata: dict, cabinet_id: str, dialog_id: str) -> dict:
        """Upload document with indexed fields"""
        # 1. Read file
        # 2. Prepare indexed fields based on metadata
        # 3. Validate required fields
        # 4. Upload via DocuWare API
        # 5. Return upload result
        pass
```

### Field Mapping Service

```python
# services/field_mapping_service.py

class FieldMappingService:
    def auto_map_fields(self,
                       docuflow_fields: Dict[str, Any],
                       docuware_fields: List[IndexField]) -> Dict[str, str]:
        """
        Intelligently map DocuFlow extracted fields to DocuWare index fields
        Returns: { docuflow_field_name: docuware_field_name }
        """

        mapping = {}

        for df_field, df_value in docuflow_fields.items():
            if df_value is None:
                continue

            # Find best match
            best_match = self._find_best_match(df_field, docuware_fields)
            if best_match:
                mapping[df_field] = best_match.name

        return mapping

    def _find_best_match(self, field_name: str, target_fields: List[IndexField]) -> Optional[IndexField]:
        """
        Use fuzzy matching to find best DocuWare field

        Examples:
        - "vendor" matches "VENDOR_NAME" (90% score)
        - "document_number" matches "INVOICE_NUMBER" (85% score)
        - "amount" matches "AMOUNT" (100% score)
        """

        from difflib import SequenceMatcher

        best_score = 0
        best_field = None

        field_name_lower = field_name.lower().replace('_', '')

        for target_field in target_fields:
            target_name_lower = target_field.name.lower().replace('_', '')

            # Direct substring match
            if field_name_lower in target_name_lower:
                score = 0.9
            else:
                # Fuzzy match
                score = SequenceMatcher(None, field_name_lower, target_name_lower).ratio()

            if score > best_score:
                best_score = score
                best_field = target_field

        # Return if confidence > 70%
        return best_field if best_score > 0.7 else None

    def validate_mapping(self,
                        mapping: Dict[str, str],
                        required_fields: List[str],
                        extracted_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate that all required DocuWare fields have mapped sources
        Returns: (is_valid, list_of_missing_fields)
        """

        mapped_target_fields = set(mapping.values())
        missing_fields = []

        for required_field in required_fields:
            if required_field not in mapped_target_fields:
                missing_fields.append(required_field)

        is_valid = len(missing_fields) == 0
        return is_valid, missing_fields
```

### Encryption Service

```python
# services/encryption_service.py

from cryptography.fernet import Fernet
import os

class EncryptionService:
    def __init__(self):
        # Get encryption key from environment
        key = os.getenv('ENCRYPTION_KEY')
        if not key:
            # Generate and save key (first run)
            key = Fernet.generate_key()
            # Store securely
        self.cipher = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt sensitive data (passwords)"""
        return self.cipher.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt sensitive data"""
        return self.cipher.decrypt(ciphertext.encode()).decode()
```

---

## Frontend Implementation

### New Settings Page

```javascript
// frontend/settings.js (NEW FILE)

class ConnectorSettings {
    constructor() {
        this.connectorType = 'none';
        this.docuwareConfig = null;
    }

    async testDocuWareConnection(serverUrl, username, password) {
        const response = await fetch('/api/connectors/docuware/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ server_url: serverUrl, username, password })
        });
        return await response.json();
    }

    async loadFileCabinets(serverUrl, username, password) {
        const response = await fetch('/api/connectors/docuware/cabinets', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ server_url: serverUrl, username, password })
        });
        const data = await response.json();
        this.populateCabinetsDropdown(data.cabinets);
    }

    async loadStorageDialogs(serverUrl, username, password, cabinetId) {
        const response = await fetch('/api/connectors/docuware/dialogs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ server_url: serverUrl, username, password, cabinet_id: cabinetId })
        });
        const data = await response.json();
        this.populateDialogsDropdown(data.dialogs);
    }

    async loadIndexFields(serverUrl, username, password, cabinetId, dialogId) {
        const response = await fetch('/api/connectors/docuware/fields', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                server_url: serverUrl,
                username,
                password,
                cabinet_id: cabinetId,
                dialog_id: dialogId
            })
        });
        const data = await response.json();
        this.displayIndexFields(data.fields);
        this.buildFieldMapping(data.fields);
    }

    buildFieldMapping(docuwareFields) {
        // Auto-generate field mapping UI
        const docuflowFields = [
            'vendor', 'document_number', 'date', 'due_date',
            'amount', 'currency', 'reference_number', 'person_name',
            'company', 'client', 'address', 'email', 'phone'
        ];

        const mappingHtml = docuflowFields.map(dfField => `
            <div class="mapping-row">
                <span class="df-field">${dfField}</span>
                <span class="arrow">→</span>
                <select class="dw-field-select" data-df-field="${dfField}">
                    <option value="">-- Not Mapped --</option>
                    ${docuwareFields.map(dwField =>
                        `<option value="${dwField.name}">${dwField.name}</option>`
                    ).join('')}
                </select>
            </div>
        `).join('');

        document.getElementById('fieldMapping').innerHTML = mappingHtml;
    }

    async saveConfiguration() {
        const config = {
            connector_type: this.connectorType,
            docuware: {
                server_url: document.getElementById('dwServerUrl').value,
                username: document.getElementById('dwUsername').value,
                password: document.getElementById('dwPassword').value,
                cabinet_id: document.getElementById('dwCabinet').value,
                cabinet_name: document.getElementById('dwCabinet').selectedOptions[0].text,
                dialog_id: document.getElementById('dwDialog').value,
                dialog_name: document.getElementById('dwDialog').selectedOptions[0].text,
                field_mapping: this.collectFieldMapping()
            }
        };

        const response = await fetch('/api/connectors/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });

        return await response.json();
    }

    collectFieldMapping() {
        const mapping = {};
        document.querySelectorAll('.dw-field-select').forEach(select => {
            const dfField = select.dataset.dfField;
            const dwField = select.value;
            if (dwField) {
                mapping[dfField] = dwField;
            }
        });
        return mapping;
    }
}
```

### Add Navigation to Settings

```javascript
// Update frontend/index.html - add navigation
<nav class="navbar">
    <div class="nav-container">
        <div class="nav-brand">
            <svg class="brand-icon">...</svg>
            <span class="brand-name">DocuFlow</span>
        </div>
        <div class="nav-links">
            <a href="/" class="nav-link">Process Documents</a>
            <a href="/settings.html" class="nav-link">Settings</a>  <!-- NEW -->
            <span class="nav-status">
                <span class="status-dot"></span>
                System Online
            </span>
        </div>
    </div>
</nav>
```

---

## Security Considerations

### 1. Credential Storage
- **Encrypt passwords** using Fernet (symmetric encryption)
- Store encryption key in environment variable
- Never log credentials
- Clear credentials from memory after use

### 2. Session Management
- Option A: Store in encrypted database per user
- Option B: Session-based (re-enter each time) - more secure for MVP
- Recommendation: Start with Option B, migrate to Option A for production

### 3. API Security
- All connector endpoints require authentication
- Rate limiting on connection tests
- Input validation on all fields
- Sanitize DocuWare server URLs

### 4. Data Privacy
- User credentials never sent to our servers in plain text
- End-to-end encryption for credential storage
- Option to clear saved credentials
- Compliance with GDPR/data regulations

---

## Data Validation & Error Handling

### Before Upload to DocuWare

```python
def validate_before_upload(extracted_data: ExtractedData,
                          field_mapping: Dict[str, str],
                          index_fields: List[IndexField]) -> Tuple[bool, List[str]]:
    """
    Validate extracted data against DocuWare field requirements
    """
    errors = []

    # 1. Check required fields have values
    for field in index_fields:
        if field.required:
            docuflow_field = find_source_field(field.name, field_mapping)
            if not docuflow_field or not getattr(extracted_data, docuflow_field):
                errors.append(f"Required field '{field.name}' has no value")

    # 2. Validate data types
    for df_field, dw_field in field_mapping.items():
        value = getattr(extracted_data, df_field)
        if value:
            field_def = find_field_definition(dw_field, index_fields)
            if not validate_type(value, field_def.type):
                errors.append(f"Field '{dw_field}' expects {field_def.type}, got {type(value)}")

    # 3. Validate max lengths
    for df_field, dw_field in field_mapping.items():
        value = getattr(extracted_data, df_field)
        if value and isinstance(value, str):
            field_def = find_field_definition(dw_field, index_fields)
            if field_def.max_length and len(value) > field_def.max_length:
                errors.append(f"Field '{dw_field}' exceeds max length of {field_def.max_length}")

    is_valid = len(errors) == 0
    return is_valid, errors
```

### Type Conversions

```python
def convert_value_for_docuware(value: Any, field_type: str) -> Any:
    """
    Convert extracted value to DocuWare field type
    """
    if field_type == "Date":
        # Convert "2024-01-15" or "01/15/2024" to ISO format
        return parse_date(value).isoformat()

    elif field_type == "Decimal":
        # Convert "$1,234.56" to 1234.56
        return parse_currency(value)

    elif field_type == "Integer":
        # Convert "10" or "10.0" to 10
        return int(float(value))

    elif field_type == "Text":
        # Ensure string
        return str(value)

    return value
```

---

## Implementation Phases

### Phase 1: DocuWare MVP (Week 1-2)
**Goal:** Basic DocuWare integration with manual field mapping

- [ ] Backend: Install and configure docuware-client library
- [ ] Backend: Create base connector interface
- [ ] Backend: Implement DocuWare connector (auth, upload)
- [ ] Backend: Add encryption service
- [ ] Backend: Create connector routes
- [ ] Frontend: Build settings page HTML/CSS
- [ ] Frontend: Implement connection test UI
- [ ] Frontend: Basic credential form
- [ ] Testing: Test with real DocuWare instance

### Phase 2: Dynamic Discovery (Week 3)
**Goal:** Auto-load cabinets, dialogs, and fields

- [ ] Backend: Implement cabinet discovery API
- [ ] Backend: Implement dialog discovery API
- [ ] Backend: Implement field discovery API
- [ ] Frontend: Dynamic dropdowns for cabinets/dialogs
- [ ] Frontend: Display discovered index fields
- [ ] Testing: Test with multiple cabinet configurations

### Phase 3: Smart Field Mapping (Week 4)
**Goal:** Intelligent auto-mapping + manual override

- [ ] Backend: Build field mapping service
- [ ] Backend: Implement fuzzy matching algorithm
- [ ] Backend: Add validation logic
- [ ] Frontend: Auto-mapping UI
- [ ] Frontend: Manual override dropdowns
- [ ] Frontend: Show mapping confidence scores
- [ ] Frontend: Warning for unmapped required fields

### Phase 4: Integration & Polish (Week 5)
**Goal:** Connect to main processing flow

- [ ] Backend: Integrate upload into batch processing
- [ ] Backend: Add upload status to results
- [ ] Frontend: Show upload progress in results
- [ ] Frontend: "View in DocuWare" links
- [ ] Testing: End-to-end processing with upload
- [ ] Documentation: User guide for setup

### Phase 5: Google Drive (Week 6-7)
**Goal:** Add Google Drive connector

- [ ] Backend: Implement Google Drive connector
- [ ] Backend: OAuth2 flow
- [ ] Frontend: Google Drive settings UI
- [ ] Testing: Upload to Google Drive

### Phase 6: OneDrive (Week 8-9)
**Goal:** Add OneDrive/SharePoint connector

- [ ] Backend: Implement OneDrive connector
- [ ] Backend: Microsoft Graph API integration
- [ ] Frontend: OneDrive settings UI
- [ ] Testing: Upload to OneDrive

---

## Testing Checklist

### DocuWare Connector Tests

- [ ] Test connection with valid credentials
- [ ] Test connection with invalid credentials
- [ ] Load file cabinets successfully
- [ ] Handle no cabinets gracefully
- [ ] Load storage dialogs for cabinet
- [ ] Handle cabinet with no dialogs
- [ ] Load index fields for dialog
- [ ] Handle missing/malformed fields
- [ ] Auto-map fields with high confidence
- [ ] Handle unmapped required fields
- [ ] Upload document with valid data
- [ ] Handle upload failures
- [ ] Validate required fields before upload
- [ ] Convert data types correctly
- [ ] Handle max length validation
- [ ] Encrypt/decrypt passwords correctly
- [ ] Test with multiple DocuWare instances

---

## Success Metrics

### Technical Metrics
- ✅ Connection test success rate > 95%
- ✅ Auto-mapping accuracy > 80%
- ✅ Upload success rate > 95%
- ✅ Field validation catches 100% of type errors

### User Experience Metrics
- ✅ Settings configuration time < 5 minutes
- ✅ Zero manual field entry after initial setup
- ✅ Upload adds < 5 seconds to processing time
- ✅ User can see document in DocuWare immediately

---

## Open Questions

1. **Credential Storage:**
   - Session-based (re-enter) vs Database (persist)?
   - Recommendation: Start session-based for MVP

2. **Multi-User Support:**
   - Single shared config vs per-user configs?
   - Recommendation: Single config for MVP, multi-user for production

3. **Batch Upload:**
   - Upload each document as processed, or batch at end?
   - Recommendation: Upload as processed for real-time feedback

4. **Error Handling:**
   - Fail entire batch if one upload fails?
   - Recommendation: Continue processing, mark individual failures

5. **Line Items:**
   - How to handle line items in DocuWare (table field vs separate entries)?
   - Need to investigate DocuWare's table field support

---

## Resources

### Documentation
- DocuWare REST API: https://developer.docuware.com/
- Your DocuWare Client: https://github.com/Dweliw01/docuware-client
- Google Drive API: https://developers.google.com/drive/api
- Microsoft Graph API: https://docs.microsoft.com/en-us/graph/

### Libraries
- `docuware-client` - Your existing connector
- `cryptography` - For encryption
- `google-api-python-client` - Google Drive
- `msal` - Microsoft authentication

---

## Notes from Discussion

- User wants ONE destination (not simultaneous uploads)
- No hardcoded credentials - all UI-based entry
- Dynamic discovery is crucial for flexibility
- Field mapping must be intelligent with manual override
- Security and encryption are priorities
- MVP focus on DocuWare first, then expand

---

**Last Updated:** 2025-01-07
**Status:** Ready for Implementation
**GitHub Repo:** https://github.com/Dweliw01/DocuFlow.git
