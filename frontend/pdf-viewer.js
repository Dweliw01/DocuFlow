/**
 * PDF Viewer with Document Review Workflow
 * Handles PDF rendering, field editing, corrections, and approval
 */

// Global state
let currentDocument = null;
let currentPdf = null;
let currentPage = 1;
let totalPages = 0;
let corrections = {};
let currentEditingField = null;
let highlightMode = false;
let highlightTargetField = null;

// PDF.js configuration
pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

// Get document ID from URL
const urlParams = new URLSearchParams(window.location.search);
const docId = urlParams.get('id');

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    if (!docId) {
        showToast('No document ID provided', 'error');
        setTimeout(() => window.location.href = '/dashboard.html', 2000);
        return;
    }

    // Initialize resizable divider
    initializeResizableDivider();

    await loadDocument();
});

/**
 * Load document data from API
 */
async function loadDocument() {
    try {
        const token = await getToken();
        if (!token) {
            window.location.href = '/login.html';
            return;
        }

        // Fetch document data
        const response = await fetch(`/api/documents/${docId}`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) {
            throw new Error('Failed to load document');
        }

        currentDocument = await response.json();

        // Update UI with document info
        document.getElementById('doc-title').textContent = currentDocument.filename;

        // Display overall confidence
        updateOverallConfidence(currentDocument.confidence_score);

        // Render fields
        renderFields(currentDocument.extracted_data, currentDocument.corrections);

        // Load folder preview for Google Drive
        await loadFolderPreview();

        // Load PDF
        await loadPdf(currentDocument.id);

    } catch (error) {
        console.error('Error loading document:', error);
        showToast('Failed to load document: ' + error.message, 'error');
    }
}

/**
 * Update overall confidence badge
 */
function updateOverallConfidence(score) {
    const badge = document.getElementById('overall-confidence');
    const percentage = Math.round(score * 100);

    let className = 'confidence-badge ';
    let icon = '';
    let label = '';

    if (score >= 0.9) {
        className += 'confidence-high';
        icon = 'fa-check-circle';
        label = `High Confidence ${percentage}%`;
    } else if (score >= 0.7) {
        className += 'confidence-medium';
        icon = 'fa-exclamation-triangle';
        label = `Medium Confidence ${percentage}%`;
    } else {
        className += 'confidence-low';
        icon = 'fa-times-circle';
        label = `Low Confidence ${percentage}%`;
    }

    badge.className = className;
    badge.innerHTML = `<i class="fa-solid ${icon}"></i> ${label}`;
}

/**
 * Render extracted fields in the sidebar
 */
function renderFields(extractedData, existingCorrections) {
    const container = document.getElementById('fields-content');

    // Define field groups
    const fieldGroups = {
        'Financial': ['amount', 'total', 'subtotal', 'tax', 'balance'],
        'Dates': ['date', 'due_date', 'invoice_date', 'order_date'],
        'Parties': ['vendor', 'client', 'customer', 'supplier', 'company'],
        'Document Info': ['document_number', 'invoice_number', 'po_number', 'reference_number'],
        'Contact': ['phone', 'email', 'address']
    };

    let html = '';

    // Render each group
    for (const [groupName, fieldList] of Object.entries(fieldGroups)) {
        const groupFields = [];

        for (const fieldName of fieldList) {
            if (extractedData.hasOwnProperty(fieldName)) {
                const fieldData = extractedData[fieldName];
                const correction = existingCorrections[fieldName];
                groupFields.push({ name: fieldName, data: fieldData, correction });
            }
        }

        // Only render group if it has fields
        if (groupFields.length > 0) {
            html += `<div class="field-group">`;
            html += `<div class="field-group-title">${groupName}</div>`;

            for (const field of groupFields) {
                html += renderField(field.name, field.data, field.correction);
            }

            html += `</div>`;
        }
    }

    // Render fields from other_data
    if (extractedData.other_data && typeof extractedData.other_data === 'object') {
        const otherDataFields = [];
        for (const [fieldName, value] of Object.entries(extractedData.other_data)) {
            if (value !== null && value !== undefined) {
                const correction = existingCorrections[fieldName];
                otherDataFields.push({
                    name: fieldName,
                    data: { value: value, confidence: 0.85 },
                    correction
                });
            }
        }

        if (otherDataFields.length > 0) {
            html += `<div class="field-group">`;
            html += `<div class="field-group-title">DocuWare Fields</div>`;

            for (const field of otherDataFields) {
                html += renderField(field.name, field.data, field.correction);
            }

            html += `</div>`;
        }
    }

    // Render additional fields not in any group
    const knownFields = Object.values(fieldGroups).flat();
    const additionalFields = [];

    for (const [fieldName, fieldData] of Object.entries(extractedData)) {
        if (!knownFields.includes(fieldName) &&
            fieldName !== 'line_items' &&
            fieldName !== 'other_data') {
            const correction = existingCorrections[fieldName];
            additionalFields.push({ name: fieldName, data: fieldData, correction });
        }
    }

    if (additionalFields.length > 0) {
        html += `<div class="field-group">`;
        html += `<div class="field-group-title">Additional Fields</div>`;

        for (const field of additionalFields) {
            html += renderField(field.name, field.data, field.correction);
        }

        html += `</div>`;
    }

    // Render line items table
    if (extractedData.line_items && Array.isArray(extractedData.line_items) && extractedData.line_items.length > 0) {
        html += `<div class="field-group">`;
        html += `<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">`;
        html += `<div class="field-group-title" style="margin-bottom: 0;">Line Items (${extractedData.line_items.length})</div>`;
        html += `<button onclick="openLineItemsModal()" style="padding: 0.5rem 1rem; background: #3b82f6; color: white; border: none; border-radius: 6px; font-size: 0.875rem; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 0.5rem;">
            <i class="fa-solid fa-edit"></i> Edit Line Items
        </button>`;
        html += `</div>`;
        html += renderLineItemsTable(extractedData.line_items);
        html += `</div>`;
    }

    container.innerHTML = html;
}

/**
 * Render line items as a table
 */
function renderLineItemsTable(lineItems) {
    if (!lineItems || lineItems.length === 0) return '';

    // Get all unique column names from all line items
    const columns = new Set();
    lineItems.forEach(item => {
        Object.keys(item).forEach(key => {
            if (item[key] !== null && item[key] !== undefined) {
                columns.add(key);
            }
        });
    });

    const columnArray = Array.from(columns);

    let html = `
        <div style="overflow-x: auto; margin-top: 0.5rem;">
            <table style="width: 100%; border-collapse: collapse; font-size: 0.875rem;">
                <thead>
                    <tr style="background: #f3f4f6; border-bottom: 2px solid #e5e7eb;">`;

    // Render headers
    columnArray.forEach(col => {
        const displayName = col.split('_').map(w =>
            w.charAt(0).toUpperCase() + w.slice(1)
        ).join(' ');
        html += `<th style="padding: 0.75rem; text-align: left; font-weight: 600; color: #374151;">${displayName}</th>`;
    });

    html += `</tr></thead><tbody>`;

    // Render rows
    lineItems.forEach((item, index) => {
        html += `<tr style="border-bottom: 1px solid #e5e7eb; ${index % 2 === 0 ? 'background: white;' : 'background: #f9fafb;'}">`;
        columnArray.forEach(col => {
            const value = item[col] || '-';
            html += `<td style="padding: 0.75rem; color: #6b7280;">${value}</td>`;
        });
        html += `</tr>`;
    });

    html += `</tbody></table></div>`;

    return html;
}

/**
 * Render a single field
 */
function renderField(fieldName, fieldData, correction) {
    // Extract value and confidence
    let value, confidence;

    if (typeof fieldData === 'object' && fieldData.value !== undefined) {
        value = fieldData.value;
        confidence = fieldData.confidence || 0;
    } else {
        value = fieldData;
        confidence = 0.75; // Default confidence
    }

    // Use corrected value if exists
    const displayValue = correction ? correction.corrected_value : value;
    const isCorrected = !!correction;

    // Format field name for display
    const displayName = fieldName
        .split('_')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');

    // Confidence badge
    const confPercentage = Math.round(confidence * 100);
    let confClass = 'field-confidence ';
    if (confidence >= 0.9) confClass += 'confidence-high';
    else if (confidence >= 0.7) confClass += 'confidence-medium';
    else confClass += 'confidence-low';

    return `
        <div class="field-item" data-field="${fieldName}">
            <div class="field-label">
                <div class="field-name">
                    <i class="fa-solid fa-tag"></i>
                    ${displayName}
                    ${isCorrected ? '<i class="fa-solid fa-pencil" style="color: #3b82f6;"></i>' : ''}
                </div>
                <span class="${confClass}">${confPercentage}%</span>
            </div>
            <div class="field-value" onclick="startEditField('${fieldName}')" data-original="${value}">
                ${displayValue || '<em style="color: #9ca3af;">Empty</em>'}
            </div>
        </div>
    `;
}

/**
 * Start editing a field
 */
function startEditField(fieldName) {
    // Cancel any existing edit
    if (currentEditingField) {
        cancelEditField(currentEditingField);
    }

    currentEditingField = fieldName;
    const fieldItem = document.querySelector(`[data-field="${fieldName}"]`);
    const valueDiv = fieldItem.querySelector('.field-value');
    const currentValue = valueDiv.textContent.trim();

    // Replace with input
    fieldItem.classList.add('editing');
    valueDiv.innerHTML = `
        <input type="text" class="field-input" value="${currentValue}"
               onkeydown="handleFieldKeydown(event, '${fieldName}')" autofocus>
        <div class="field-actions">
            <button class="btn-save" onclick="saveFieldCorrection('${fieldName}')">
                <i class="fa-solid fa-check"></i> Save
            </button>
            <button class="btn-cancel" onclick="cancelEditField('${fieldName}')">
                <i class="fa-solid fa-xmark"></i> Cancel
            </button>
        </div>
    `;

    // Enable highlight mode
    highlightMode = true;
    highlightTargetField = fieldName;
    document.getElementById('highlight-mode').classList.add('active');

    // Focus input
    const input = fieldItem.querySelector('.field-input');
    input.focus();
    input.select();
}

/**
 * Handle keyboard shortcuts in field input
 */
function handleFieldKeydown(event, fieldName) {
    if (event.key === 'Enter') {
        event.preventDefault();
        saveFieldCorrection(fieldName);
    } else if (event.key === 'Escape') {
        event.preventDefault();
        cancelEditField(fieldName);
    }
}

/**
 * Save field correction
 */
async function saveFieldCorrection(fieldName) {
    const fieldItem = document.querySelector(`[data-field="${fieldName}"]`);
    const input = fieldItem.querySelector('.field-input');
    const newValue = input.value.trim();
    const originalValue = fieldItem.querySelector('.field-value').dataset.original;

    // Don't save if value unchanged
    if (newValue === originalValue) {
        cancelEditField(fieldName);
        return;
    }

    // Get original confidence
    const fieldData = currentDocument.extracted_data[fieldName];
    const originalConfidence = typeof fieldData === 'object' ? fieldData.confidence : 0.75;

    // Store correction
    corrections[fieldName] = {
        field_name: fieldName,
        original_value: originalValue,
        corrected_value: newValue,
        original_confidence: originalConfidence,
        method: highlightMode ? 'highlighted' : 'manual'
    };

    try {
        // Save to backend
        const token = await getToken();
        const response = await fetch(`/api/documents/${docId}/correct-field`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(corrections[fieldName])
        });

        if (!response.ok) {
            throw new Error('Failed to save correction');
        }

        // Update UI
        const valueDiv = fieldItem.querySelector('.field-value');
        valueDiv.textContent = newValue;
        valueDiv.dataset.original = originalValue;
        fieldItem.classList.remove('editing');

        // Add corrected indicator
        const fieldLabel = fieldItem.querySelector('.field-name');
        if (!fieldLabel.querySelector('.fa-pencil')) {
            fieldLabel.innerHTML += ' <i class="fa-solid fa-pencil" style="color: #3b82f6;"></i>';
        }

        showToast('Correction saved', 'success');

        // Refresh folder preview if field affects folder path
        await refreshFolderPreview();

    } catch (error) {
        console.error('Error saving correction:', error);
        showToast('Failed to save correction', 'error');
    }

    // Disable highlight mode
    highlightMode = false;
    highlightTargetField = null;
    document.getElementById('highlight-mode').classList.remove('active');
    currentEditingField = null;
}

/**
 * Cancel field editing
 */
function cancelEditField(fieldName) {
    const fieldItem = document.querySelector(`[data-field="${fieldName}"]`);
    const valueDiv = fieldItem.querySelector('.field-value');
    const originalValue = corrections[fieldName] ?
        corrections[fieldName].corrected_value :
        valueDiv.dataset.original;

    valueDiv.textContent = originalValue;
    fieldItem.classList.remove('editing');

    // Disable highlight mode
    highlightMode = false;
    highlightTargetField = null;
    document.getElementById('highlight-mode').classList.remove('active');
    currentEditingField = null;
}

/**
 * Load and render PDF
 */
async function loadPdf(documentId) {
    try {
        const token = await getToken();
        const pdfUrl = `/api/documents/${documentId}/view`;

        const loadingTask = pdfjsLib.getDocument({
            url: pdfUrl,
            httpHeaders: {
                'Authorization': `Bearer ${token}`
            }
        });

        currentPdf = await loadingTask.promise;
        totalPages = currentPdf.numPages;

        // Update page count
        document.getElementById('page-count').textContent = totalPages;

        // Enable navigation buttons
        updatePageButtons();

        // Render first page
        await renderPage(1);

        // Add text selection listener
        addTextSelectionListener();

    } catch (error) {
        console.error('Error loading PDF:', error);
        showToast('Failed to load PDF', 'error');
    }
}

/**
 * Render a specific page
 */
async function renderPage(pageNum) {
    try {
        const page = await currentPdf.getPage(pageNum);
        const canvas = document.getElementById('pdf-canvas');
        const context = canvas.getContext('2d');
        const textLayerDiv = document.getElementById('pdf-text-layer');

        // Calculate scale to fit container
        const pdfContainer = document.querySelector('.pdf-canvas-container');
        const containerWidth = pdfContainer ? pdfContainer.clientWidth - 80 : 800; // Subtract padding
        const viewport = page.getViewport({ scale: 1 });
        const scale = containerWidth / viewport.width;
        const scaledViewport = page.getViewport({ scale });

        // Set canvas dimensions
        canvas.height = scaledViewport.height;
        canvas.width = scaledViewport.width;

        // Render page on canvas
        const renderContext = {
            canvasContext: context,
            viewport: scaledViewport
        };

        await page.render(renderContext).promise;

        // Render text layer for selection (if element exists)
        if (textLayerDiv) {
            try {
                // Set text layer dimensions
                textLayerDiv.style.width = canvas.width + 'px';
                textLayerDiv.style.height = canvas.height + 'px';

                // Get text content
                const textContent = await page.getTextContent();
                textLayerDiv.innerHTML = ''; // Clear previous text

                // Render text items
                textContent.items.forEach(item => {
                    const textDiv = document.createElement('span');
                    textDiv.textContent = item.str;

                    // Calculate position and size
                    const tx = pdfjsLib.Util.transform(
                        scaledViewport.transform,
                        item.transform
                    );

                    textDiv.style.left = tx[4] + 'px';
                    textDiv.style.top = (tx[5] - item.height) + 'px';
                    textDiv.style.fontSize = (item.height * scale) + 'px';
                    textDiv.style.fontFamily = item.fontName;

                    textLayerDiv.appendChild(textDiv);
                });
            } catch (textError) {
                console.warn('Could not render text layer:', textError);
                // Continue without text selection
            }
        }

        // Update current page
        currentPage = pageNum;
        document.getElementById('page-num').textContent = pageNum;
        updatePageButtons();

    } catch (error) {
        console.error('Error rendering page:', error);
        showToast('Failed to render page', 'error');
    }
}

/**
 * Update page navigation buttons
 */
function updatePageButtons() {
    document.getElementById('prev-page').disabled = currentPage <= 1;
    document.getElementById('next-page').disabled = currentPage >= totalPages;
}

/**
 * Navigate to previous page
 */
document.getElementById('prev-page')?.addEventListener('click', () => {
    if (currentPage > 1) {
        renderPage(currentPage - 1);
    }
});

/**
 * Navigate to next page
 */
document.getElementById('next-page')?.addEventListener('click', () => {
    if (currentPage < totalPages) {
        renderPage(currentPage + 1);
    }
});

/**
 * Add text selection listener to PDF
 */
function addTextSelectionListener() {
    let lastFocusedInput = null;

    // Track the last focused input field (regular fields or line item fields)
    document.addEventListener('focusin', (e) => {
        if (e.target.matches('.field-input') ||
            e.target.matches('input[type="text"]') ||
            e.target.matches('input[type="number"]')) {
            lastFocusedInput = e.target;
        }
    });

    // Handle text selection from PDF
    document.addEventListener('mouseup', (e) => {
        const selectedText = window.getSelection().toString().trim();
        if (!selectedText) return;

        // Check if selection is from PDF area
        const pdfPanel = document.querySelector('.pdf-panel');
        if (!pdfPanel?.contains(e.target)) return;

        // Priority 1: Copy to highlight mode target field
        if (highlightMode && highlightTargetField) {
            const fieldItem = document.querySelector(`[data-field="${highlightTargetField}"]`);
            const input = fieldItem?.querySelector('.field-input');

            if (input) {
                input.value = selectedText;
                input.focus();
                showToast('Text copied to field', 'success');
                return;
            }
        }

        // Priority 2: Copy to last focused input (for line items editor)
        if (lastFocusedInput && document.body.contains(lastFocusedInput)) {
            lastFocusedInput.value = selectedText;
            lastFocusedInput.focus();
            showToast('Text copied to field', 'success');

            // If it's a line item field, trigger the update
            if (lastFocusedInput.dataset.lineitemIndex !== undefined) {
                const index = parseInt(lastFocusedInput.dataset.lineitemIndex);
                const field = lastFocusedInput.dataset.lineitemField;
                if (field) {
                    updateLineItemField(index, field, selectedText);
                }
            }
        }
    });
}

/**
 * Approve document and send to connector
 */
async function approveDocument() {
    if (!confirm('Are you sure you want to approve this document and send it to the connector?')) {
        return;
    }

    try {
        const token = await getToken();
        const response = await fetch(`/api/documents/${docId}/approve`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                corrections: Object.values(corrections)
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to approve document');
        }

        const result = await response.json();
        showToast('Document approved successfully!', 'success');

        // Redirect to dashboard after 2 seconds
        setTimeout(() => {
            window.location.href = '/dashboard.html';
        }, 2000);

    } catch (error) {
        console.error('Error approving document:', error);
        showToast('Failed to approve document: ' + error.message, 'error');
    }
}

/**
 * Reject document (set status to failed/rejected)
 */
async function rejectDocument() {
    const reason = prompt('Please provide a reason for rejecting this document:');
    if (!reason) return;

    try {
        const token = await getToken();

        // For now, we'll use a generic endpoint to update status
        // In production, you might want a dedicated reject endpoint
        showToast('Document rejection not yet implemented', 'error');

        // TODO: Implement rejection endpoint
        // const response = await fetch(`/api/documents/${docId}/reject`, {
        //     method: 'POST',
        //     headers: {
        //         'Authorization': `Bearer ${token}`,
        //         'Content-Type': 'application/json'
        //     },
        //     body: JSON.stringify({ reason })
        // });

    } catch (error) {
        console.error('Error rejecting document:', error);
        showToast('Failed to reject document', 'error');
    }
}

/**
 * Go back to dashboard
 */
function goBack() {
    if (Object.keys(corrections).length > 0) {
        if (!confirm('You have unsaved changes. Are you sure you want to leave?')) {
            return;
        }
    }
    window.location.href = '/dashboard.html';
}

/**
 * Show toast notification
 */
function showToast(message, type = 'success') {
    // Remove existing toasts
    const existingToast = document.querySelector('.toast');
    if (existingToast) {
        existingToast.remove();
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const icon = type === 'success' ? 'fa-check-circle' : 'fa-exclamation-circle';
    toast.innerHTML = `
        <i class="fa-solid ${icon}"></i>
        <span>${message}</span>
    `;

    document.body.appendChild(toast);

    // Auto-remove after 3 seconds
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease-out forwards';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Add slideOut animation
const style = document.createElement('style');
style.textContent = `
    @keyframes slideOut {
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// ============================================================================
// Line Items Editor
// ============================================================================

let editingLineItems = [];

/**
 * Open line items editor modal
 */
function openLineItemsModal() {
    // Get current line items or create empty array
    editingLineItems = currentDocument.extracted_data.line_items ?
        JSON.parse(JSON.stringify(currentDocument.extracted_data.line_items)) : [];

    // Render line items in modal
    renderLineItemsEditor();

    // Show modal
    document.getElementById('lineItemsModal').style.display = 'block';
}

/**
 * Close line items editor modal
 */
function closeLineItemsModal() {
    document.getElementById('lineItemsModal').style.display = 'none';
}

/**
 * Render line items in editor
 */
function renderLineItemsEditor() {
    const container = document.getElementById('lineItemsEditor');

    if (editingLineItems.length === 0) {
        container.innerHTML = `
            <div style="text-align: center; padding: 3rem; color: #9ca3af;">
                <i class="fa-solid fa-inbox" style="font-size: 3rem; margin-bottom: 1rem; opacity: 0.5;"></i>
                <p style="font-size: 1.125rem; font-weight: 500;">No line items yet</p>
                <p style="font-size: 0.875rem;">Click "Add Line Item" to get started</p>
            </div>
        `;
        return;
    }

    // Get all unique field names from all line items
    const allFields = new Set();
    editingLineItems.forEach(item => {
        Object.keys(item).forEach(key => allFields.add(key));
    });

    const fields = Array.from(allFields);

    let html = '';

    editingLineItems.forEach((item, index) => {
        html += `
            <div style="background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 1.5rem; margin-bottom: 1rem; position: relative;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                    <h3 style="font-size: 1rem; font-weight: 600; color: #374151;">
                        Item ${index + 1}
                    </h3>
                    <button onclick="deleteLineItem(${index})" style="background: #ef4444; color: white; border: none; padding: 0.5rem 1rem; border-radius: 6px; font-size: 0.875rem; cursor: pointer;">
                        <i class="fa-solid fa-trash"></i> Delete
                    </button>
                </div>
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem;">
        `;

        fields.forEach(field => {
            const value = item[field] || '';
            const displayName = field.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');

            html += `
                <div>
                    <label style="display: block; font-size: 0.875rem; font-weight: 500; color: #374151; margin-bottom: 0.5rem;">
                        ${displayName}
                    </label>
                    <input type="text"
                           value="${value}"
                           data-lineitem-index="${index}"
                           data-lineitem-field="${field}"
                           onchange="updateLineItemField(${index}, '${field}', this.value)"
                           style="width: 100%; padding: 0.75rem; border: 1px solid #d1d5db; border-radius: 6px; font-size: 0.875rem;">
                </div>
            `;
        });

        html += `
                </div>
            </div>
        `;
    });

    container.innerHTML = html;
}

/**
 * Add new line item
 */
function addLineItem() {
    // Create a new empty line item with same fields as others
    const newItem = {};

    if (editingLineItems.length > 0) {
        // Copy field structure from first item
        Object.keys(editingLineItems[0]).forEach(key => {
            newItem[key] = '';
        });
    } else {
        // Default fields for new line item
        newItem.description = '';
        newItem.quantity = '';
        newItem.unit = '';
        newItem.unit_price = '';
        newItem.amount = '';
    }

    editingLineItems.push(newItem);
    renderLineItemsEditor();
}

/**
 * Delete line item
 */
function deleteLineItem(index) {
    if (confirm('Are you sure you want to delete this line item?')) {
        editingLineItems.splice(index, 1);
        renderLineItemsEditor();
    }
}

/**
 * Update line item field
 */
function updateLineItemField(index, field, value) {
    editingLineItems[index][field] = value;
}

/**
 * Save line items
 */
async function saveLineItems() {
    try {
        // Save line items as a special correction
        corrections['_line_items'] = {
            field_name: '_line_items',
            original_value: JSON.stringify(currentDocument.extracted_data.line_items || []),
            corrected_value: JSON.stringify(editingLineItems),
            original_confidence: 1.0,
            method: 'manual'
        };

        // Update current document data
        currentDocument.extracted_data.line_items = editingLineItems;

        // Re-render fields to show updated table
        renderFields(currentDocument.extracted_data, {});

        // Close modal
        closeLineItemsModal();

        // Show success message
        showToast('Line items updated successfully', 'success');

    } catch (error) {
        console.error('Error saving line items:', error);
        showToast('Failed to save line items', 'error');
    }
}


/**
 * Initialize resizable divider between PDF and fields panels
 */
function initializeResizableDivider() {
    const resizeHandle = document.getElementById('resize-handle');
    const viewerContainer = document.querySelector('.viewer-container');
    const pdfPanel = document.querySelector('.pdf-panel');
    const fieldsPanel = document.querySelector('.fields-panel');

    if (!resizeHandle || !pdfPanel || !fieldsPanel) return;

    let isResizing = false;
    let startX = 0;
    let startPdfWidth = 0;

    resizeHandle.addEventListener('mousedown', (e) => {
        isResizing = true;
        startX = e.clientX;
        startPdfWidth = pdfPanel.offsetWidth;

        // Prevent text selection during resize
        document.body.style.userSelect = 'none';
        document.body.style.cursor = 'col-resize';

        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isResizing) return;

        const deltaX = e.clientX - startX;
        const containerWidth = viewerContainer.offsetWidth;
        const newPdfWidth = startPdfWidth + deltaX;

        // Calculate percentages with min/max constraints
        const minWidth = containerWidth * 0.3; // Min 30%
        const maxWidth = containerWidth * 0.8; // Max 80%

        if (newPdfWidth >= minWidth && newPdfWidth <= maxWidth) {
            const pdfPercentage = (newPdfWidth / containerWidth) * 100;
            const fieldsPercentage = 100 - pdfPercentage - 0.5; // 0.5% for divider

            pdfPanel.style.flex = `0 0 ${pdfPercentage}%`;
            fieldsPanel.style.flex = `0 0 ${fieldsPercentage}%`;
        }
    });

    document.addEventListener('mouseup', () => {
        if (isResizing) {
            isResizing = false;
            document.body.style.userSelect = '';
            document.body.style.cursor = '';
        }
    });
}

/**
 * Load and display Google Drive folder path preview
 */
async function loadFolderPreview() {
    try {
        const token = await getToken();
        if (!token) return;

        const response = await fetch(`/api/documents/${docId}/folder-preview`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) {
            console.error('Failed to load folder preview');
            return;
        }

        const data = await response.json();
        renderFolderPreview(data);

    } catch (error) {
        console.error('Error loading folder preview:', error);
    }
}

/**
 * Render folder path preview in the UI
 */
function renderFolderPreview(data) {
    const preview = document.getElementById('folder-preview');
    const content = document.getElementById('folder-preview-content');

    // Only show for Google Drive
    if (data.connector_type !== 'google_drive') {
        preview.classList.remove('visible');
        return;
    }

    // Show the preview section
    preview.classList.add('visible');

    // Check if folder path exists
    if (!data.folder_path) {
        content.innerHTML = `
            <div class="folder-warning">
                <i class="fa-solid fa-triangle-exclamation"></i>
                <div class="folder-warning-text">
                    Unable to determine folder path. Some required fields may be missing.
                </div>
            </div>
        `;
        return;
    }

    // Render folder path
    let html = `
        <div class="folder-path">
            ${data.folder_path.split('/').filter(p => p).map(folder =>
                `<i class="fa-solid fa-folder"></i>${folder}`
            ).join(' <i class="fa-solid fa-chevron-right" style="color: #9ca3af; font-size: 0.75rem; margin: 0 0.25rem;"></i> ')}
        </div>
    `;

    // Show which fields populate each level
    if (data.level_details && data.level_details.length > 0) {
        const missingLevels = data.level_details.filter(l => l.missing);

        if (missingLevels.length > 0) {
            html += `
                <div class="folder-warning">
                    <i class="fa-solid fa-triangle-exclamation"></i>
                    <div class="folder-warning-text">
                        <strong>Missing data for folders:</strong> ${missingLevels.map(l => l.source_field).join(', ')}
                        <br>These folders will be skipped in the path.
                    </div>
                </div>
            `;
        }

        html += `
            <div class="folder-preview-info">
                <i class="fa-solid fa-info-circle"></i>
                Based on: ${data.level_details.filter(l => !l.missing).map(l => l.source_field).join(' → ')}
            </div>
        `;
    }

    content.innerHTML = html;
}

/**
 * Refresh folder preview (call after field updates)
 */
async function refreshFolderPreview() {
    // Debounce to avoid too many API calls
    if (window.folderPreviewTimeout) {
        clearTimeout(window.folderPreviewTimeout);
    }

    window.folderPreviewTimeout = setTimeout(() => {
        loadFolderPreview();
    }, 500); // Wait 500ms after last field change
}
