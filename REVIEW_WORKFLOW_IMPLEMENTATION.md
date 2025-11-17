# Document Review & Correction Workflow - Implementation Guide

## Table of Contents
1. [Overview](#overview)
2. [User Workflows](#user-workflows)
3. [Architecture](#architecture)
4. [Database Schema](#database-schema)
5. [Backend Implementation](#backend-implementation)
6. [Frontend Implementation](#frontend-implementation)
7. [Auto-Upload Settings](#auto-upload-settings)
8. [Testing Checklist](#testing-checklist)

---

## Overview

### Feature Summary
Implement a document review and correction workflow that allows users to:
1. View uploaded documents in a PDF viewer
2. See AI-extracted index fields with confidence scores
3. Correct wrong fields by highlighting text in the PDF
4. Approve documents for upload to connectors (DocuWare/Google Drive)
5. Configure auto-upload settings based on AI confidence

### Key Benefits
- **Data Quality:** Ensures accurate data before sending to connectors
- **User Control:** Explicit approval required before documents leave the system
- **AI Learning:** System gets smarter from user corrections
- **Efficiency:** Auto-upload high-confidence documents as AI improves

---

## User Workflows

### Workflow 1: Initial Setup (Review All Documents)

```
1. User uploads PDF to DocuFlow
2. AI processes and extracts data
3. Document → Status: "pending_review"
4. User clicks "Review" on document card
5. Split-screen opens:
   ├─ Left: PDF viewer (text selection enabled)
   └─ Right: Extracted index fields with confidence scores
6. User reviews each field:
   ├─ If correct: Leave as-is
   └─ If wrong: Highlight correct text in PDF → Copy to field
7. User clicks "Approve & Send to [Connector]"
8. Document → Status: "approved"
9. Backend sends document to configured connector
10. Document → Status: "completed"
```

### Workflow 2: After AI Training (Smart Auto-Upload)

```
1. User uploads PDF to DocuFlow
2. AI processes and extracts data
3. System calculates overall confidence score
4. Decision tree:
   ├─ If confidence ≥ 90%:
   │  ├─ Document → Status: "approved"
   │  ├─ Auto-upload to connector
   │  └─ Document → Status: "completed"
   └─ If confidence < 90%:
      ├─ Document → Status: "pending_review"
      └─ User must review (Workflow 1)
```

### Workflow 3: Highlight-to-Copy Interaction

```
1. User in review screen sees wrong field:
   "Vendor: Acme Crp  ⚠ 67% confidence"

2. User highlights "Acme Corporation" in PDF

3. Popup appears near selection:
   ┌─────────────────────────────────┐
   │ Copy "Acme Corporation" to:     │
   ├─────────────────────────────────┤
   │ ● Vendor                        │
   │ ○ Client                        │
   │ ○ Company                       │
   ├─────────────────────────────────┤
   │ [Copy] [Cancel]                 │
   └─────────────────────────────────┘

4. User selects "Vendor" and clicks "Copy"

5. Field updates immediately:
   "Vendor: Acme Corporation  ✓"

6. Correction saved to corrections array (not DB yet)

7. When user clicks "Approve & Send":
   ├─ Save all corrections to database
   └─ Send document with corrected data
```

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Dashboard          PDF Viewer        Settings Page         │
│  ├─ Pending queue   ├─ PDF.js        ├─ Review mode        │
│  ├─ Stats           ├─ Text select   ├─ Confidence slider  │
│  └─ Review btn      ├─ Field panel   └─ Save settings      │
│                     └─ Approve btn                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                            │
                            ↓ API Calls
┌─────────────────────────────────────────────────────────────┐
│                         Backend                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  API Routes              Services           Database        │
│  ├─ GET /documents      ├─ AI Service     ├─ documents     │
│  ├─ GET /doc/{id}/view  ├─ Confidence     ├─ corrections   │
│  ├─ POST /doc/{id}/     ├─ Connectors     └─ orgs          │
│  │   correct-field      └─ Processing                      │
│  ├─ POST /doc/{id}/                                         │
│  │   approve                                                │
│  └─ GET /settings                                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                            │
                            ↓ Upload approved docs
┌─────────────────────────────────────────────────────────────┐
│                      Connectors                             │
├─────────────────────────────────────────────────────────────┤
│  DocuWare API          Google Drive API                     │
│  └─ Upload with index  └─ Upload to folder                  │
└─────────────────────────────────────────────────────────────┘
```

### Document Status Flow

```
┌──────────┐   AI Process   ┌─────────────────┐
│ uploaded │ ─────────────> │ pending_review  │
└──────────┘                └─────────────────┘
                                     │
                    User reviews     │
                    & approves       │
                                     ↓
                            ┌─────────────┐   Send to     ┌───────────┐
                            │  approved   │ ────────────> │ completed │
                            └─────────────┘   connector   └───────────┘
                                     ↑
                    Auto-upload      │
                    (high confidence)│
                                     │
```

---

## Database Schema

### 1. Add Status Column to `document_metadata`

```sql
-- Migration: Add status column
ALTER TABLE document_metadata
ADD COLUMN status TEXT DEFAULT 'pending_review';

-- Valid values: 'uploaded', 'processing', 'pending_review', 'approved', 'completed', 'failed'

-- Add confidence score column
ALTER TABLE document_metadata
ADD COLUMN confidence_score REAL DEFAULT 0.0;

-- Index for faster queries
CREATE INDEX idx_document_status ON document_metadata(status);
CREATE INDEX idx_document_org_status ON document_metadata(organization_id, status);
```

### 2. Create `field_corrections` Table

```sql
CREATE TABLE field_corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL,
    document_id INTEGER NOT NULL,
    field_name TEXT NOT NULL,
    original_value TEXT,
    corrected_value TEXT NOT NULL,
    original_confidence REAL,
    correction_method TEXT DEFAULT 'manual',  -- 'manual', 'highlighted', 'suggested'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT,  -- User email/ID who made correction

    FOREIGN KEY (organization_id) REFERENCES organizations(id),
    FOREIGN KEY (document_id) REFERENCES document_metadata(id) ON DELETE CASCADE
);

CREATE INDEX idx_corrections_doc ON field_corrections(document_id);
CREATE INDEX idx_corrections_org ON field_corrections(organization_id);
CREATE INDEX idx_corrections_field ON field_corrections(field_name);
```

### 3. Add Settings to `organizations` Table

```sql
-- Migration: Add review settings to organizations
ALTER TABLE organizations
ADD COLUMN review_mode TEXT DEFAULT 'review_all';
-- Values: 'review_all', 'smart', 'auto_upload'

ALTER TABLE organizations
ADD COLUMN confidence_threshold REAL DEFAULT 0.90;
-- Threshold for smart mode (0.0 - 1.0)

ALTER TABLE organizations
ADD COLUMN auto_upload_enabled BOOLEAN DEFAULT 0;
-- Overall toggle
```

---

## Backend Implementation

### Phase 1: Document Status Management

#### File: `backend/routes/upload.py`

**Modify upload processing to set status:**

```python
@upload_bp.route('/process', methods=['POST'])
@token_required
def process_documents(current_user):
    # ... existing upload code ...

    # After AI extraction
    extracted_data = ai_service.extract_data(file_path)
    confidence_score = calculate_overall_confidence(extracted_data)

    # Create document metadata
    doc_metadata = DocumentMetadata(
        organization_id=org_id,
        filename=filename,
        file_path=file_path,
        category=category,
        extracted_data=json.dumps(extracted_data),
        status='pending_review',  # NEW: Set initial status
        confidence_score=confidence_score,  # NEW: Store confidence
        connector_type=connector_type,
        created_at=datetime.utcnow()
    )

    db.session.add(doc_metadata)
    db.session.commit()

    # Check if should auto-upload based on settings
    org_settings = get_organization_settings(org_id)

    if should_auto_upload(org_settings, confidence_score):
        # Auto-approve and upload
        approve_and_upload_document(doc_metadata.id, org_settings)

    return jsonify({
        'success': True,
        'document_id': doc_metadata.id,
        'status': doc_metadata.status,
        'confidence': confidence_score
    })
```

#### File: `backend/services/confidence_service.py` (NEW)

```python
"""
Confidence score calculation for extracted data.
Initially uses heuristic-based scoring, can be upgraded to ML-based later.
"""

def calculate_field_confidence(field_name, value):
    """
    Calculate confidence score for a single field.
    Returns float between 0.0 and 1.0.
    """
    if not value or str(value).strip() == '':
        return 0.3  # Low confidence for empty fields

    value_str = str(value).strip()

    # Amount field validation
    if field_name in ['amount', 'total', 'subtotal']:
        if re.match(r'^\$?[\d,]+\.\d{2}$', value_str):
            return 0.95  # High confidence - proper currency format
        elif re.match(r'^\$?[\d,]+', value_str):
            return 0.75  # Medium - has numbers
        else:
            return 0.50  # Low - doesn't look like amount

    # Date field validation
    if field_name in ['date', 'due_date', 'invoice_date']:
        try:
            # Try parsing as date
            from dateutil import parser
            parser.parse(value_str)
            return 0.93  # High confidence - valid date
        except:
            return 0.55  # Low - not a valid date

    # Email validation
    if field_name == 'email':
        if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', value_str):
            return 0.96  # High confidence - valid email format
        else:
            return 0.50

    # Phone validation
    if field_name == 'phone':
        if re.match(r'^[\d\s\-\(\)\.]{10,}$', value_str):
            return 0.88  # High confidence - looks like phone
        else:
            return 0.60

    # Vendor/Company names
    if field_name in ['vendor', 'client', 'company']:
        if len(value_str) >= 3 and len(value_str) <= 100:
            return 0.80  # Medium-high confidence
        else:
            return 0.60

    # Document numbers
    if field_name in ['document_number', 'invoice_number', 'po_number', 'reference_number']:
        if len(value_str) >= 3:
            return 0.85
        else:
            return 0.55

    # Default: if we have a value, medium confidence
    if len(value_str) > 0:
        return 0.75

    return 0.50


def calculate_overall_confidence(extracted_data):
    """
    Calculate overall confidence score for entire document.
    Returns weighted average of field confidences.
    """
    if not extracted_data:
        return 0.0

    # Weight important fields higher
    field_weights = {
        'amount': 2.0,
        'date': 1.5,
        'vendor': 1.5,
        'document_number': 1.2,
        'invoice_number': 1.2,
    }

    total_score = 0.0
    total_weight = 0.0

    for field_name, value in extracted_data.items():
        # Skip line items and metadata
        if field_name in ['line_items', 'id', 'user_id', 'created_at']:
            continue

        confidence = calculate_field_confidence(field_name, value)
        weight = field_weights.get(field_name, 1.0)

        total_score += confidence * weight
        total_weight += weight

    if total_weight == 0:
        return 0.0

    overall = total_score / total_weight
    return round(overall, 2)


def add_confidence_to_extracted_data(extracted_data):
    """
    Transform extracted data to include confidence scores.

    Input:  {'vendor': 'Acme Corp', 'amount': '$1,234'}
    Output: {
        'vendor': {'value': 'Acme Corp', 'confidence': 0.80},
        'amount': {'value': '$1,234', 'confidence': 0.95}
    }
    """
    scored_data = {}

    for field_name, value in extracted_data.items():
        # Skip special fields
        if field_name in ['line_items']:
            scored_data[field_name] = value
            continue

        confidence = calculate_field_confidence(field_name, value)
        scored_data[field_name] = {
            'value': value,
            'confidence': confidence
        }

    return scored_data
```

#### File: `backend/routes/document_routes.py` (NEW)

```python
from flask import Blueprint, jsonify, request, send_file
from backend.auth import token_required
from backend.database import get_db_connection
from backend.models import DocumentMetadata, FieldCorrection
import json
from datetime import datetime

document_bp = Blueprint('documents', __name__)

@document_bp.route('/api/documents/<int:doc_id>', methods=['GET'])
@token_required
def get_document(current_user, doc_id):
    """Get document details with extracted data and confidence scores"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get document
    cursor.execute('''
        SELECT * FROM document_metadata
        WHERE id = ? AND organization_id = ?
    ''', (doc_id, current_user['organization_id']))

    doc = cursor.fetchone()
    if not doc:
        return jsonify({'error': 'Document not found'}), 404

    # Get corrections for this document
    cursor.execute('''
        SELECT * FROM field_corrections
        WHERE document_id = ?
        ORDER BY created_at DESC
    ''', (doc_id,))

    corrections = cursor.fetchall()
    conn.close()

    # Parse extracted data
    extracted_data = json.loads(doc['extracted_data'])

    # Apply corrections to extracted data
    corrections_dict = {}
    for corr in corrections:
        corrections_dict[corr['field_name']] = {
            'original_value': corr['original_value'],
            'corrected_value': corr['corrected_value'],
            'original_confidence': corr['original_confidence'],
            'method': corr['correction_method'],
            'created_at': corr['created_at']
        }

    return jsonify({
        'id': doc['id'],
        'filename': doc['filename'],
        'file_path': doc['file_path'],
        'category': doc['category'],
        'status': doc['status'],
        'confidence_score': doc['confidence_score'],
        'extracted_data': extracted_data,
        'corrections': corrections_dict,
        'created_at': doc['created_at']
    })


@document_bp.route('/api/documents/<int:doc_id>/view', methods=['GET'])
@token_required
def view_document(current_user, doc_id):
    """Serve PDF file for viewing in browser"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT file_path FROM document_metadata
        WHERE id = ? AND organization_id = ?
    ''', (doc_id, current_user['organization_id']))

    doc = cursor.fetchone()
    conn.close()

    if not doc:
        return jsonify({'error': 'Document not found'}), 404

    return send_file(
        doc['file_path'],
        mimetype='application/pdf',
        as_attachment=False  # Display in browser, not download
    )


@document_bp.route('/api/documents/<int:doc_id>/correct-field', methods=['POST'])
@token_required
def correct_field(current_user, doc_id):
    """Save a field correction"""
    data = request.get_json()

    field_name = data.get('field_name')
    original_value = data.get('original_value')
    corrected_value = data.get('corrected_value')
    original_confidence = data.get('original_confidence', 0.0)
    method = data.get('method', 'manual')  # 'manual' or 'highlighted'

    if not field_name or corrected_value is None:
        return jsonify({'error': 'Missing required fields'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Verify document belongs to user's organization
    cursor.execute('''
        SELECT id FROM document_metadata
        WHERE id = ? AND organization_id = ?
    ''', (doc_id, current_user['organization_id']))

    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Document not found'}), 404

    # Save correction
    cursor.execute('''
        INSERT INTO field_corrections
        (organization_id, document_id, field_name, original_value,
         corrected_value, original_confidence, correction_method, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        current_user['organization_id'],
        doc_id,
        field_name,
        original_value,
        corrected_value,
        original_confidence,
        method,
        current_user['email']
    ))

    conn.commit()
    correction_id = cursor.lastrowid
    conn.close()

    return jsonify({
        'success': True,
        'correction_id': correction_id
    })


@document_bp.route('/api/documents/<int:doc_id>/approve', methods=['POST'])
@token_required
def approve_document(current_user, doc_id):
    """Approve document and send to connector"""
    data = request.get_json()
    corrections = data.get('corrections', [])  # Array of corrections to save

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get document
    cursor.execute('''
        SELECT * FROM document_metadata
        WHERE id = ? AND organization_id = ?
    ''', (doc_id, current_user['organization_id']))

    doc = cursor.fetchone()
    if not doc:
        conn.close()
        return jsonify({'error': 'Document not found'}), 404

    # Save any pending corrections
    for correction in corrections:
        cursor.execute('''
            INSERT INTO field_corrections
            (organization_id, document_id, field_name, original_value,
             corrected_value, original_confidence, correction_method, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            current_user['organization_id'],
            doc_id,
            correction['field_name'],
            correction.get('original_value'),
            correction['corrected_value'],
            correction.get('original_confidence', 0.0),
            correction.get('method', 'manual'),
            current_user['email']
        ))

    # Update document status
    cursor.execute('''
        UPDATE document_metadata
        SET status = 'approved'
        WHERE id = ?
    ''', (doc_id,))

    conn.commit()
    conn.close()

    # Send to connector
    try:
        from backend.services.connector_service import upload_to_connector
        result = upload_to_connector(doc_id, current_user['organization_id'])

        # Update status to completed
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE document_metadata
            SET status = 'completed'
            WHERE id = ?
        ''', (doc_id,))
        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': 'Document approved and uploaded to connector',
            'result': result
        })

    except Exception as e:
        # Update status to failed
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE document_metadata
            SET status = 'failed'
            WHERE id = ?
        ''', (doc_id,))
        conn.commit()
        conn.close()

        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@document_bp.route('/api/documents/pending', methods=['GET'])
@token_required
def get_pending_documents(current_user):
    """Get all documents pending review for current organization"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, filename, category, confidence_score, created_at
        FROM document_metadata
        WHERE organization_id = ? AND status = 'pending_review'
        ORDER BY created_at DESC
    ''', (current_user['organization_id'],))

    docs = cursor.fetchall()
    conn.close()

    return jsonify({
        'documents': [dict(doc) for doc in docs],
        'count': len(docs)
    })
```

### Phase 2: Auto-Upload Settings

#### File: `backend/routes/organization_routes.py`

**Add settings endpoints:**

```python
@org_bp.route('/api/organizations/settings', methods=['GET'])
@token_required
def get_organization_settings(current_user):
    """Get organization review settings"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT review_mode, confidence_threshold, auto_upload_enabled
        FROM organizations
        WHERE id = ?
    ''', (current_user['organization_id'],))

    settings = cursor.fetchone()
    conn.close()

    if not settings:
        return jsonify({'error': 'Organization not found'}), 404

    return jsonify({
        'review_mode': settings['review_mode'],
        'confidence_threshold': settings['confidence_threshold'],
        'auto_upload_enabled': settings['auto_upload_enabled']
    })


@org_bp.route('/api/organizations/settings', methods=['PUT'])
@token_required
def update_organization_settings(current_user):
    """Update organization review settings"""
    data = request.get_json()

    review_mode = data.get('review_mode')
    confidence_threshold = data.get('confidence_threshold')
    auto_upload_enabled = data.get('auto_upload_enabled')

    # Validate inputs
    valid_modes = ['review_all', 'smart', 'auto_upload']
    if review_mode and review_mode not in valid_modes:
        return jsonify({'error': 'Invalid review_mode'}), 400

    if confidence_threshold is not None:
        if not (0.0 <= confidence_threshold <= 1.0):
            return jsonify({'error': 'confidence_threshold must be between 0.0 and 1.0'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Build update query dynamically
    updates = []
    params = []

    if review_mode:
        updates.append('review_mode = ?')
        params.append(review_mode)

    if confidence_threshold is not None:
        updates.append('confidence_threshold = ?')
        params.append(confidence_threshold)

    if auto_upload_enabled is not None:
        updates.append('auto_upload_enabled = ?')
        params.append(auto_upload_enabled)

    if not updates:
        return jsonify({'error': 'No settings to update'}), 400

    params.append(current_user['organization_id'])

    cursor.execute(f'''
        UPDATE organizations
        SET {', '.join(updates)}
        WHERE id = ?
    ''', params)

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Settings updated'})
```

#### File: `backend/services/auto_upload_service.py` (NEW)

```python
"""
Service to determine if document should be auto-uploaded based on settings.
"""

def should_auto_upload(org_settings, confidence_score):
    """
    Determine if document should be auto-uploaded.

    Args:
        org_settings: Dict with review_mode, confidence_threshold
        confidence_score: Overall confidence score (0.0 - 1.0)

    Returns:
        Boolean: True if should auto-upload, False if needs review
    """
    review_mode = org_settings.get('review_mode', 'review_all')

    # Review all documents mode
    if review_mode == 'review_all':
        return False

    # Auto-upload all mode (no review)
    if review_mode == 'auto_upload':
        return True

    # Smart mode - check confidence threshold
    if review_mode == 'smart':
        threshold = org_settings.get('confidence_threshold', 0.90)
        return confidence_score >= threshold

    # Default: require review
    return False


def approve_and_upload_document(doc_id, org_settings):
    """
    Auto-approve and upload document to connector.
    Called when should_auto_upload returns True.
    """
    from backend.database import get_db_connection
    from backend.services.connector_service import upload_to_connector

    conn = get_db_connection()
    cursor = conn.cursor()

    # Update status to approved
    cursor.execute('''
        UPDATE document_metadata
        SET status = 'approved'
        WHERE id = ?
    ''', (doc_id,))

    conn.commit()
    org_id = org_settings.get('organization_id')

    # Upload to connector
    try:
        result = upload_to_connector(doc_id, org_id)

        # Update status to completed
        cursor.execute('''
            UPDATE document_metadata
            SET status = 'completed'
            WHERE id = ?
        ''', (doc_id,))

        conn.commit()
        conn.close()

        return {'success': True, 'auto_uploaded': True}

    except Exception as e:
        # Update status to failed
        cursor.execute('''
            UPDATE document_metadata
            SET status = 'failed'
            WHERE id = ?
        ''', (doc_id,))

        conn.commit()
        conn.close()

        raise e
```

---

## Frontend Implementation

### Phase 1: PDF Viewer Component

#### File: `frontend/pdf-viewer.html` (NEW)

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Document Review - DocuFlow</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link rel="stylesheet" href="styles.css">
    <style>
        /* PDF Viewer Layout */
        .review-container {
            display: flex;
            height: 100vh;
            background: #f9fafb;
        }

        .pdf-panel {
            flex: 1;
            background: white;
            border-right: 1px solid #e5e7eb;
            display: flex;
            flex-direction: column;
        }

        .fields-panel {
            width: 400px;
            background: white;
            display: flex;
            flex-direction: column;
            overflow-y: auto;
        }

        .panel-header {
            padding: 1rem 1.5rem;
            border-bottom: 1px solid #e5e7eb;
            background: white;
        }

        .panel-title {
            font-size: 1.125rem;
            font-weight: 600;
            color: #111827;
        }

        /* PDF Viewer */
        #pdf-container {
            flex: 1;
            overflow: auto;
            padding: 2rem;
            background: #f3f4f6;
        }

        #pdf-canvas {
            max-width: 100%;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }

        .pdf-controls {
            padding: 1rem;
            border-top: 1px solid #e5e7eb;
            display: flex;
            align-items: center;
            gap: 1rem;
            background: white;
        }

        .pdf-controls button {
            padding: 0.5rem 1rem;
            background: #f3f4f6;
            border: 1px solid #e5e7eb;
            border-radius: 0.375rem;
            cursor: pointer;
            font-size: 0.875rem;
        }

        .pdf-controls button:hover {
            background: #e5e7eb;
        }

        /* Field Items */
        .fields-list {
            flex: 1;
            overflow-y: auto;
            padding: 1rem;
        }

        .field-item {
            padding: 1rem;
            border: 1px solid #e5e7eb;
            border-radius: 0.5rem;
            margin-bottom: 0.75rem;
            background: white;
        }

        .field-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.5rem;
        }

        .field-label {
            font-size: 0.875rem;
            font-weight: 500;
            color: #6b7280;
        }

        .confidence-badge {
            padding: 0.25rem 0.5rem;
            border-radius: 0.25rem;
            font-size: 0.75rem;
            font-weight: 600;
        }

        .confidence-high {
            background: #d1fae5;
            color: #065f46;
        }

        .confidence-medium {
            background: #fef3c7;
            color: #92400e;
        }

        .confidence-low {
            background: #fee2e2;
            color: #991b1b;
        }

        .field-value {
            font-size: 1rem;
            color: #111827;
            padding: 0.5rem;
            border: 1px solid transparent;
            border-radius: 0.375rem;
            cursor: pointer;
            transition: all 0.2s;
        }

        .field-value:hover {
            border-color: #e5e7eb;
            background: #f9fafb;
        }

        .field-value.editing {
            border-color: #0066cc;
            background: white;
        }

        .field-value input {
            width: 100%;
            padding: 0.5rem;
            border: 1px solid #e5e7eb;
            border-radius: 0.375rem;
            font-size: 1rem;
        }

        .field-actions {
            display: flex;
            gap: 0.5rem;
            margin-top: 0.5rem;
        }

        .field-actions button {
            padding: 0.375rem 0.75rem;
            font-size: 0.75rem;
            border-radius: 0.375rem;
            border: none;
            cursor: pointer;
            font-weight: 500;
        }

        .btn-save {
            background: #0066cc;
            color: white;
        }

        .btn-cancel {
            background: #f3f4f6;
            color: #6b7280;
        }

        /* Selection Popup */
        .selection-popup {
            position: fixed;
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 0.5rem;
            box-shadow: 0 10px 15px rgba(0, 0, 0, 0.1);
            padding: 1rem;
            z-index: 1000;
            display: none;
        }

        .selection-popup.active {
            display: block;
        }

        .selection-text {
            font-size: 0.875rem;
            color: #6b7280;
            margin-bottom: 0.5rem;
        }

        .selection-value {
            font-size: 1rem;
            font-weight: 600;
            color: #111827;
            margin-bottom: 1rem;
            padding: 0.5rem;
            background: #f9fafb;
            border-radius: 0.375rem;
        }

        .field-options {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }

        .field-option {
            padding: 0.5rem;
            border: 1px solid #e5e7eb;
            border-radius: 0.375rem;
            cursor: pointer;
            font-size: 0.875rem;
            transition: all 0.2s;
        }

        .field-option:hover {
            border-color: #0066cc;
            background: #f0f9ff;
        }

        /* Action Bar */
        .action-bar {
            padding: 1rem 1.5rem;
            border-top: 1px solid #e5e7eb;
            background: white;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .btn-approve {
            padding: 0.75rem 1.5rem;
            background: #0066cc;
            color: white;
            border: none;
            border-radius: 0.5rem;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .btn-approve:hover {
            background: #0052a3;
        }

        .btn-approve:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .corrections-count {
            font-size: 0.875rem;
            color: #6b7280;
        }
    </style>
</head>
<body>
    <div class="review-container">
        <!-- PDF Panel -->
        <div class="pdf-panel">
            <div class="panel-header">
                <div class="panel-title">
                    <i class="fa-solid fa-file-pdf"></i>
                    <span id="document-name">Loading...</span>
                </div>
            </div>

            <div id="pdf-container">
                <canvas id="pdf-canvas"></canvas>
            </div>

            <div class="pdf-controls">
                <button id="zoom-out"><i class="fa-solid fa-minus"></i></button>
                <button id="zoom-in"><i class="fa-solid fa-plus"></i></button>
                <span id="zoom-level">100%</span>
                <button id="fit-width">Fit Width</button>
            </div>
        </div>

        <!-- Fields Panel -->
        <div class="fields-panel">
            <div class="panel-header">
                <div class="panel-title">Index Fields</div>
            </div>

            <div class="fields-list" id="fields-list">
                <!-- Fields populated by JavaScript -->
            </div>

            <div class="action-bar">
                <div class="corrections-count">
                    <span id="corrections-count">0</span> corrections made
                </div>
                <button class="btn-approve" id="approve-btn">
                    <i class="fa-solid fa-check"></i>
                    Approve & Send
                </button>
            </div>
        </div>
    </div>

    <!-- Selection Popup -->
    <div class="selection-popup" id="selection-popup">
        <div class="selection-text">Copy selected text to:</div>
        <div class="selection-value" id="selected-text"></div>
        <div class="field-options" id="field-options">
            <!-- Field options populated dynamically -->
        </div>
    </div>

    <!-- PDF.js Library -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
    <script src="auth.js"></script>
    <script src="pdf-viewer.js"></script>
</body>
</html>
```

#### File: `frontend/pdf-viewer.js` (NEW)

```javascript
// Get document ID from URL
const urlParams = new URLSearchParams(window.location.search);
const documentId = urlParams.get('id');

let pdfDoc = null;
let pageNum = 1;
let pageRendering = false;
let pageNumPending = null;
let scale = 1.5;
let corrections = [];
let extractedData = {};

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    if (!documentId) {
        alert('No document ID provided');
        window.location.href = '/dashboard.html';
        return;
    }

    await loadDocument();
    setupEventListeners();
});

// Load document data
async function loadDocument() {
    try {
        const token = localStorage.getItem('auth_token');

        // Get document metadata and extracted data
        const response = await fetch(`/api/documents/${documentId}`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) throw new Error('Failed to load document');

        const doc = await response.json();

        // Set document name
        document.getElementById('document-name').textContent = doc.filename;

        // Store extracted data
        extractedData = doc.extracted_data;

        // Load existing corrections if any
        if (doc.corrections) {
            Object.entries(doc.corrections).forEach(([field, correction]) => {
                corrections.push({
                    field_name: field,
                    original_value: correction.original_value,
                    corrected_value: correction.corrected_value,
                    original_confidence: correction.original_confidence,
                    method: correction.method
                });
            });
        }

        // Render fields
        renderFields();

        // Load PDF
        await loadPDF();

    } catch (error) {
        console.error('Error loading document:', error);
        alert('Error loading document');
    }
}

// Load and render PDF
async function loadPDF() {
    const url = `/api/documents/${documentId}/view`;

    pdfjsLib.GlobalWorkerOptions.workerSrc =
        'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

    const loadingTask = pdfjsLib.getDocument(url);

    try {
        pdfDoc = await loadingTask.promise;
        renderPage(pageNum);
    } catch (error) {
        console.error('Error loading PDF:', error);
        alert('Error loading PDF');
    }
}

// Render PDF page
function renderPage(num) {
    pageRendering = true;

    pdfDoc.getPage(num).then(page => {
        const canvas = document.getElementById('pdf-canvas');
        const ctx = canvas.getContext('2d');
        const viewport = page.getViewport({ scale: scale });

        canvas.height = viewport.height;
        canvas.width = viewport.width;

        const renderContext = {
            canvasContext: ctx,
            viewport: viewport
        };

        const renderTask = page.render(renderContext);

        renderTask.promise.then(() => {
            pageRendering = false;
            if (pageNumPending !== null) {
                renderPage(pageNumPending);
                pageNumPending = null;
            }

            // Enable text selection layer
            return page.getTextContent();
        }).then(textContent => {
            // Create text layer for selection
            // (Simplified - full implementation would use PDF.js text layer)
        });
    });
}

// Render fields panel
function renderFields() {
    const fieldsList = document.getElementById('fields-list');
    fieldsList.innerHTML = '';

    Object.entries(extractedData).forEach(([fieldName, fieldData]) => {
        // Skip special fields
        if (fieldName === 'line_items') return;

        const value = fieldData.value || fieldData;
        const confidence = fieldData.confidence || 0.75;

        // Check if field has been corrected
        const correction = corrections.find(c => c.field_name === fieldName);
        const displayValue = correction ? correction.corrected_value : value;
        const isEdited = !!correction;

        const fieldItem = createFieldElement(
            fieldName,
            displayValue,
            confidence,
            isEdited
        );

        fieldsList.appendChild(fieldItem);
    });

    updateCorrectionsCount();
}

// Create field element
function createFieldElement(fieldName, value, confidence, isEdited) {
    const div = document.createElement('div');
    div.className = 'field-item';
    div.dataset.fieldName = fieldName;

    const confidenceBadge = getConfidenceBadge(confidence);
    const editedIndicator = isEdited ? ' ✏️' : '';

    div.innerHTML = `
        <div class="field-header">
            <span class="field-label">${formatFieldName(fieldName)}${editedIndicator}</span>
            ${confidenceBadge}
        </div>
        <div class="field-value" data-field="${fieldName}">
            ${value || '—'}
        </div>
    `;

    // Add click-to-edit
    const valueEl = div.querySelector('.field-value');
    valueEl.addEventListener('click', () => enableEditMode(fieldName, valueEl));

    return div;
}

// Get confidence badge HTML
function getConfidenceBadge(confidence) {
    let className, label;

    if (confidence >= 0.9) {
        className = 'confidence-high';
        label = `✓ ${Math.round(confidence * 100)}%`;
    } else if (confidence >= 0.7) {
        className = 'confidence-medium';
        label = `⚠ ${Math.round(confidence * 100)}%`;
    } else {
        className = 'confidence-low';
        label = `❌ ${Math.round(confidence * 100)}%`;
    }

    return `<span class="confidence-badge ${className}">${label}</span>`;
}

// Format field name
function formatFieldName(fieldName) {
    return fieldName
        .split('_')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
}

// Enable edit mode for field
function enableEditMode(fieldName, valueEl) {
    const currentValue = valueEl.textContent;

    valueEl.classList.add('editing');
    valueEl.innerHTML = `
        <input type="text" value="${currentValue}" id="edit-${fieldName}">
        <div class="field-actions">
            <button class="btn-save" onclick="saveFieldEdit('${fieldName}')">Save</button>
            <button class="btn-cancel" onclick="cancelFieldEdit('${fieldName}')">Cancel</button>
        </div>
    `;

    document.getElementById(`edit-${fieldName}`).focus();
}

// Save field edit
window.saveFieldEdit = function(fieldName) {
    const input = document.getElementById(`edit-${fieldName}`);
    const newValue = input.value;

    const originalData = extractedData[fieldName];
    const originalValue = originalData.value || originalData;
    const originalConfidence = originalData.confidence || 0.75;

    // Add to corrections array
    const existingIndex = corrections.findIndex(c => c.field_name === fieldName);

    if (existingIndex >= 0) {
        corrections[existingIndex].corrected_value = newValue;
    } else {
        corrections.push({
            field_name: fieldName,
            original_value: originalValue,
            corrected_value: newValue,
            original_confidence: originalConfidence,
            method: 'manual'
        });
    }

    // Re-render fields
    renderFields();
}

// Cancel field edit
window.cancelFieldEdit = function(fieldName) {
    renderFields();
}

// Setup event listeners
function setupEventListeners() {
    // PDF controls
    document.getElementById('zoom-in').addEventListener('click', () => {
        scale += 0.25;
        renderPage(pageNum);
        document.getElementById('zoom-level').textContent = `${Math.round(scale * 100)}%`;
    });

    document.getElementById('zoom-out').addEventListener('click', () => {
        if (scale > 0.5) {
            scale -= 0.25;
            renderPage(pageNum);
            document.getElementById('zoom-level').textContent = `${Math.round(scale * 100)}%`;
        }
    });

    // Text selection in PDF
    document.getElementById('pdf-container').addEventListener('mouseup', handleTextSelection);

    // Approve button
    document.getElementById('approve-btn').addEventListener('click', approveDocument);
}

// Handle text selection
function handleTextSelection(e) {
    const selection = window.getSelection();
    const selectedText = selection.toString().trim();

    if (selectedText.length > 0) {
        showSelectionPopup(selectedText, e.pageX, e.pageY);
    } else {
        hideSelectionPopup();
    }
}

// Show selection popup
function showSelectionPopup(text, x, y) {
    const popup = document.getElementById('selection-popup');
    const textEl = document.getElementById('selected-text');
    const optionsEl = document.getElementById('field-options');

    textEl.textContent = text;

    // Create field options
    optionsEl.innerHTML = '';
    Object.keys(extractedData).forEach(fieldName => {
        if (fieldName === 'line_items') return;

        const option = document.createElement('div');
        option.className = 'field-option';
        option.textContent = formatFieldName(fieldName);
        option.addEventListener('click', () => {
            copyToField(fieldName, text);
            hideSelectionPopup();
        });

        optionsEl.appendChild(option);
    });

    // Position popup near selection
    popup.style.left = `${x}px`;
    popup.style.top = `${y}px`;
    popup.classList.add('active');
}

// Hide selection popup
function hideSelectionPopup() {
    document.getElementById('selection-popup').classList.remove('active');
}

// Copy selected text to field
function copyToField(fieldName, value) {
    const originalData = extractedData[fieldName];
    const originalValue = originalData.value || originalData;
    const originalConfidence = originalData.confidence || 0.75;

    // Add to corrections
    const existingIndex = corrections.findIndex(c => c.field_name === fieldName);

    if (existingIndex >= 0) {
        corrections[existingIndex].corrected_value = value;
        corrections[existingIndex].method = 'highlighted';
    } else {
        corrections.push({
            field_name: fieldName,
            original_value: originalValue,
            corrected_value: value,
            original_confidence: originalConfidence,
            method: 'highlighted'
        });
    }

    // Re-render fields
    renderFields();

    // Clear selection
    window.getSelection().removeAllRanges();
}

// Update corrections count
function updateCorrectionsCount() {
    document.getElementById('corrections-count').textContent = corrections.length;
}

// Approve document
async function approveDocument() {
    const btn = document.getElementById('approve-btn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Approving...';

    try {
        const token = localStorage.getItem('auth_token');

        const response = await fetch(`/api/documents/${documentId}/approve`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                corrections: corrections
            })
        });

        if (!response.ok) throw new Error('Failed to approve document');

        const result = await response.json();

        alert('Document approved and sent to connector!');
        window.location.href = '/dashboard.html';

    } catch (error) {
        console.error('Error approving document:', error);
        alert('Error approving document: ' + error.message);

        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-check"></i> Approve & Send';
    }
}
```

### Phase 2: Dashboard Updates

#### File: `frontend/dashboard.html`

**Add pending review section:**

```html
<!-- Add after upload section, before documents list -->
<div class="pending-review-section" id="pending-review-section" style="display: none;">
    <div class="section-header">
        <h2>
            <i class="fa-solid fa-clock"></i>
            Pending Review
            <span class="badge" id="pending-count">0</span>
        </h2>
        <p>Review and approve these documents before they're sent to your connector</p>
    </div>

    <div id="pending-documents-list"></div>
</div>
```

#### File: `frontend/app.js`

**Add functions to load pending documents:**

```javascript
// Load pending review documents
async function loadPendingDocuments() {
    try {
        const token = localStorage.getItem('auth_token');
        const response = await fetch('/api/documents/pending', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) throw new Error('Failed to load pending documents');

        const data = await response.json();

        if (data.count > 0) {
            document.getElementById('pending-review-section').style.display = 'block';
            document.getElementById('pending-count').textContent = data.count;
            renderPendingDocuments(data.documents);
        } else {
            document.getElementById('pending-review-section').style.display = 'none';
        }

    } catch (error) {
        console.error('Error loading pending documents:', error);
    }
}

// Render pending documents
function renderPendingDocuments(documents) {
    const container = document.getElementById('pending-documents-list');
    container.innerHTML = '';

    documents.forEach(doc => {
        const card = createPendingDocumentCard(doc);
        container.appendChild(card);
    });
}

// Create pending document card
function createPendingDocumentCard(doc) {
    const div = document.createElement('div');
    div.className = 'document-card pending';

    const confidenceBadge = doc.confidence_score >= 0.9 ?
        `<span class="badge success">High Confidence</span>` :
        doc.confidence_score >= 0.7 ?
        `<span class="badge warning">Medium Confidence</span>` :
        `<span class="badge error">Low Confidence</span>`;

    div.innerHTML = `
        <div class="doc-card-header">
            <i class="fa-solid fa-file-pdf"></i>
            <div class="doc-info">
                <h3>${doc.filename}</h3>
                <p>Category: ${doc.category || 'Uncategorized'}</p>
            </div>
            ${confidenceBadge}
        </div>
        <div class="doc-card-actions">
            <button class="btn btn-primary" onclick="reviewDocument(${doc.id})">
                <i class="fa-solid fa-eye"></i>
                Review & Approve
            </button>
        </div>
    `;

    return div;
}

// Navigate to review page
window.reviewDocument = function(docId) {
    window.location.href = `/pdf-viewer.html?id=${docId}`;
}

// Call on page load
document.addEventListener('DOMContentLoaded', () => {
    loadPendingDocuments();
    // ... existing code ...
});
```

### Phase 3: Settings Page

#### File: `frontend/settings.html`

**Add review settings section:**

```html
<!-- Add new section after connectors -->
<div class="settings-section">
    <h2>
        <i class="fa-solid fa-gears"></i>
        Review & Auto-Upload Settings
    </h2>
    <p class="section-description">
        Configure when documents require manual review before being sent to your connector
    </p>

    <div class="settings-form">
        <div class="form-group">
            <label class="radio-group-label">Processing Mode</label>

            <label class="radio-option">
                <input type="radio" name="review_mode" value="review_all" id="mode-review-all">
                <div class="radio-content">
                    <div class="radio-title">Review All Documents</div>
                    <div class="radio-description">
                        Every document must be manually reviewed and approved before upload
                    </div>
                </div>
            </label>

            <label class="radio-option recommended">
                <input type="radio" name="review_mode" value="smart" id="mode-smart">
                <div class="radio-content">
                    <div class="radio-title">
                        Smart Review
                        <span class="badge">Recommended</span>
                    </div>
                    <div class="radio-description">
                        Auto-upload high-confidence documents, review low-confidence ones
                    </div>
                </div>
            </label>

            <div class="confidence-slider" id="confidence-slider" style="display: none;">
                <label>Auto-upload when AI confidence is ≥ <span id="threshold-value">90</span>%</label>
                <input type="range"
                       id="confidence-threshold"
                       min="50"
                       max="100"
                       value="90"
                       step="5">
                <div class="slider-labels">
                    <span>50%</span>
                    <span>75%</span>
                    <span>100%</span>
                </div>
            </div>

            <label class="radio-option warning">
                <input type="radio" name="review_mode" value="auto_upload" id="mode-auto">
                <div class="radio-content">
                    <div class="radio-title">
                        Always Auto-Upload
                        <span class="badge error">⚠️ Not Recommended</span>
                    </div>
                    <div class="radio-description">
                        All documents uploaded automatically without review. Use only when AI is fully trained.
                    </div>
                </div>
            </label>
        </div>

        <div class="form-actions">
            <button type="button" class="btn btn-primary" id="save-review-settings">
                <i class="fa-solid fa-save"></i>
                Save Settings
            </button>
        </div>
    </div>
</div>
```

#### File: `frontend/settings.js`

**Add settings management:**

```javascript
// Load review settings
async function loadReviewSettings() {
    try {
        const token = localStorage.getItem('auth_token');
        const response = await fetch('/api/organizations/settings', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) throw new Error('Failed to load settings');

        const settings = await response.json();

        // Set radio button
        document.getElementById(`mode-${settings.review_mode}`).checked = true;

        // Set confidence threshold
        const threshold = Math.round(settings.confidence_threshold * 100);
        document.getElementById('confidence-threshold').value = threshold;
        document.getElementById('threshold-value').textContent = threshold;

        // Show/hide confidence slider
        if (settings.review_mode === 'smart') {
            document.getElementById('confidence-slider').style.display = 'block';
        }

    } catch (error) {
        console.error('Error loading settings:', error);
    }
}

// Save review settings
document.getElementById('save-review-settings').addEventListener('click', async () => {
    const reviewMode = document.querySelector('input[name="review_mode"]:checked').value;
    const confidenceThreshold = document.getElementById('confidence-threshold').value / 100;

    try {
        const token = localStorage.getItem('auth_token');
        const response = await fetch('/api/organizations/settings', {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                review_mode: reviewMode,
                confidence_threshold: confidenceThreshold
            })
        });

        if (!response.ok) throw new Error('Failed to save settings');

        alert('Review settings saved successfully!');

    } catch (error) {
        console.error('Error saving settings:', error);
        alert('Failed to save settings');
    }
});

// Show/hide confidence slider
document.querySelectorAll('input[name="review_mode"]').forEach(radio => {
    radio.addEventListener('change', (e) => {
        if (e.target.value === 'smart') {
            document.getElementById('confidence-slider').style.display = 'block';
        } else {
            document.getElementById('confidence-slider').style.display = 'none';
        }
    });
});

// Update threshold value display
document.getElementById('confidence-threshold').addEventListener('input', (e) => {
    document.getElementById('threshold-value').textContent = e.target.value;
});

// Load on page load
document.addEventListener('DOMContentLoaded', () => {
    loadReviewSettings();
});
```

---

## Auto-Upload Settings

### Configuration Options

#### Mode 1: Review All Documents
```javascript
{
  "review_mode": "review_all",
  "confidence_threshold": 0.90  // Ignored in this mode
}
```
- **Behavior:** All documents go to "pending_review" status
- **User action:** Must review and approve every document
- **Use case:** Initial setup, learning phase

#### Mode 2: Smart Review (Recommended)
```javascript
{
  "review_mode": "smart",
  "confidence_threshold": 0.90  // Adjustable 0.50 - 1.00
}
```
- **Behavior:**
  - Confidence ≥ 90% → Auto-upload
  - Confidence < 90% → Pending review
- **User action:** Only review low-confidence documents
- **Use case:** AI has been trained, mostly accurate

#### Mode 3: Always Auto-Upload
```javascript
{
  "review_mode": "auto_upload",
  "confidence_threshold": 0.90  // Ignored in this mode
}
```
- **Behavior:** All documents auto-upload immediately
- **User action:** None required
- **Use case:** AI fully trained, 95%+ accuracy

---

## Testing Checklist

### Backend Tests

- [ ] Database migrations run successfully
- [ ] `field_corrections` table created
- [ ] Document status updates correctly
- [ ] Confidence scores calculated accurately
- [ ] Auto-upload logic works for each mode
- [ ] API endpoints return correct data:
  - [ ] GET `/api/documents/:id`
  - [ ] GET `/api/documents/:id/view`
  - [ ] POST `/api/documents/:id/correct-field`
  - [ ] POST `/api/documents/:id/approve`
  - [ ] GET `/api/documents/pending`
  - [ ] GET `/api/organizations/settings`
  - [ ] PUT `/api/organizations/settings`

### Frontend Tests

- [ ] PDF viewer loads and displays document
- [ ] Text selection works in PDF
- [ ] Fields display with confidence badges
- [ ] Click-to-edit field works
- [ ] Highlight-to-copy works
- [ ] Selection popup appears correctly
- [ ] Corrections save to array
- [ ] Approve button sends corrections
- [ ] Dashboard shows pending documents
- [ ] Settings page loads current settings
- [ ] Settings save correctly
- [ ] Confidence slider updates value

### Integration Tests

- [ ] Upload document → Status = "pending_review"
- [ ] Review document → Correct fields → Approve
- [ ] Document sends to connector with corrected data
- [ ] Status updates: pending_review → approved → completed
- [ ] Auto-upload works for high-confidence docs
- [ ] Low-confidence docs require review
- [ ] Settings change affects upload behavior
- [ ] Corrections stored in database
- [ ] Multiple corrections on same field (last wins)

### User Flow Tests

#### Flow 1: Manual Review
1. Upload document
2. Document appears in "Pending Review"
3. Click "Review & Approve"
4. PDF viewer opens
5. See fields with confidence scores
6. Correct wrong field by highlighting text
7. Click "Approve & Send"
8. Document uploads to connector
9. Document removed from pending list

#### Flow 2: Auto-Upload (Smart Mode)
1. Set mode to "Smart" with 90% threshold
2. Upload high-confidence document (95%)
3. Document auto-uploads immediately
4. Upload low-confidence document (75%)
5. Document appears in "Pending Review"
6. Review and approve manually

#### Flow 3: Settings Change
1. Start with "Review All" mode
2. Review 50 documents, make corrections
3. AI confidence improves to 92% average
4. Change to "Smart" mode
5. Upload new document with 94% confidence
6. Verify it auto-uploads

---

## Deployment Steps

1. **Database Migration:**
   ```bash
   python backend/migrations/add_review_workflow.py
   ```

2. **Backend Deployment:**
   - Deploy new API endpoints
   - Update upload processing logic
   - Deploy confidence calculation service

3. **Frontend Deployment:**
   - Upload `pdf-viewer.html`
   - Upload `pdf-viewer.js`
   - Update `dashboard.html` and `app.js`
   - Update `settings.html` and `settings.js`

4. **Testing:**
   - Test with sample documents
   - Verify auto-upload modes
   - Check connector integration

5. **User Communication:**
   - Notify users of new review workflow
   - Provide training on PDF viewer
   - Explain auto-upload settings

---

## Future Enhancements

### Phase 2 Features (Post-Launch)

1. **Bulk Review Mode:**
   - Review multiple documents in sequence
   - Keyboard shortcuts for faster review
   - "Approve All" for batch operations

2. **AI Learning from Corrections:**
   - Use corrections to fine-tune extraction
   - Suggest corrections based on patterns
   - Vendor name normalization

3. **Mobile App:**
   - Mobile PDF viewer
   - Quick review on phone/tablet
   - Push notifications for pending docs

4. **Advanced Analytics:**
   - Accuracy tracking over time
   - Most common corrections
   - Time saved metrics

5. **Approval Workflows:**
   - Multi-step approval (Accountant → Manager)
   - Delegation and permissions
   - Approval history and audit trail

---

## Support and Troubleshooting

### Common Issues

**PDF not loading:**
- Check file path in database
- Verify file exists in storage
- Check PDF.js CDN availability

**Text selection not working:**
- PDF must have text layer (not scanned image)
- Use OCR for scanned documents first

**Auto-upload not working:**
- Check organization settings
- Verify confidence threshold
- Check connector configuration

**Corrections not saving:**
- Check authentication token
- Verify database permissions
- Check API endpoint logs

---

## Conclusion

This implementation guide provides a complete roadmap for building the Document Review & Correction Workflow feature for DocuFlow. Follow the phases sequentially, test thoroughly at each step, and deploy incrementally to minimize risk.

**Estimated Total Implementation Time:** 40-50 hours
- Backend: 20-25 hours
- Frontend: 15-20 hours
- Testing: 5-10 hours

**Priority Order:**
1. Phase 1: Basic review workflow (20 hours)
2. Phase 2: Auto-upload settings (10 hours)
3. Phase 3: Polish and optimization (10 hours)

Good luck with implementation! 🚀
