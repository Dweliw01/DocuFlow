/**
 * Settings Page JavaScript
 * Handles connector configuration UI and API interactions
 */

// ============================================================================
// State Management
// ============================================================================

const state = {
    connectorType: 'none',
    credentials: {
        serverUrl: '',
        username: '',
        password: ''
    },
    cabinets: [],
    dialogs: [],
    indexFields: [],
    selectedCabinet: null,
    selectedDialog: null,
    fieldMapping: {},
    fieldSuggestions: {},
    confidenceScores: {},
    requiredFields: []
};

// ============================================================================
// Initialize Page
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    loadExistingConfig();
});

function setupEventListeners() {
    // Connector type selection
    document.querySelectorAll('input[name="connector"]').forEach(radio => {
        radio.addEventListener('change', handleConnectorChange);
    });

    // DocuWare connection test
    document.getElementById('test-connection-btn').addEventListener('click', testConnection);

    // Google Drive buttons
    document.getElementById('gdrive-test-connection-btn').addEventListener('click', testGoogleDriveConnection);
    document.getElementById('gdrive-oauth-help-btn').addEventListener('click', showGoogleDriveOAuthHelp);

    // Cabinet selection
    document.getElementById('dw-cabinet').addEventListener('change', handleCabinetChange);

    // Dialog selection
    document.getElementById('dw-dialog').addEventListener('change', handleDialogChange);

    // Load fields
    document.getElementById('load-fields-btn').addEventListener('click', loadIndexFields);

    // Save configuration
    document.getElementById('save-config-btn').addEventListener('click', saveConfiguration);

    // Edit configuration
    document.getElementById('edit-config-btn').addEventListener('click', editConfiguration);

    // Clear configuration
    document.getElementById('clear-config-btn').addEventListener('click', clearConfiguration);
}

// ============================================================================
// Connector Selection
// ============================================================================

function handleConnectorChange(event) {
    state.connectorType = event.target.value;

    // Hide all config sections
    document.getElementById('docuware-config').style.display = 'none';
    document.getElementById('google-drive-config').style.display = 'none';
    document.getElementById('cabinet-selection').style.display = 'none';
    document.getElementById('index-fields-section').style.display = 'none';
    document.getElementById('field-mapping-section').style.display = 'none';
    document.getElementById('save-section').style.display = 'none';

    // Show relevant section
    if (state.connectorType === 'docuware') {
        document.getElementById('docuware-config').style.display = 'block';
    } else if (state.connectorType === 'google_drive') {
        document.getElementById('google-drive-config').style.display = 'block';
    } else if (state.connectorType === 'none') {
        // Show save section for "none" option
        document.getElementById('save-section').style.display = 'block';
    }
}

// ============================================================================
// DocuWare Connection
// ============================================================================

async function testConnection() {
    const serverUrl = document.getElementById('dw-server-url').value.trim();
    const username = document.getElementById('dw-username').value.trim();
    const password = document.getElementById('dw-password').value;

    // Validation
    if (!serverUrl || !username || !password) {
        showAlert('connection-status', 'error', 'Please fill in all fields');
        return;
    }

    // Update state
    state.credentials = { serverUrl, username, password };

    // Show loading
    const btn = document.getElementById('test-connection-btn');
    btn.disabled = true;
    btn.textContent = 'Testing...';

    try {
        const response = await fetch('/api/connectors/docuware/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                server_url: serverUrl,
                username: username,
                password: password
            })
        });

        const result = await response.json();

        if (result.success) {
            showAlert('connection-status', 'success', '✓ ' + result.message);

            // Load file cabinets
            await loadFileCabinets();

            // Show cabinet selection
            document.getElementById('cabinet-selection').style.display = 'block';
        } else {
            showAlert('connection-status', 'error', '✗ ' + result.message);
        }

    } catch (error) {
        showAlert('connection-status', 'error', 'Connection error: ' + error.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="btn-icon">🔌</span> Test Connection';
    }
}

// ============================================================================
// File Cabinets
// ============================================================================

async function loadFileCabinets() {
    try {
        const response = await fetch('/api/connectors/docuware/cabinets', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                server_url: state.credentials.serverUrl,
                username: state.credentials.username,
                password: state.credentials.password
            })
        });

        const result = await response.json();
        state.cabinets = result.cabinets || [];

        // Populate dropdown
        const select = document.getElementById('dw-cabinet');
        select.innerHTML = '<option value="">Select a file cabinet...</option>';

        state.cabinets.forEach(cabinet => {
            const option = document.createElement('option');
            option.value = cabinet.id;
            option.textContent = cabinet.name;
            select.appendChild(option);
        });

        // If editing existing config, restore cabinet selection
        if (state.editingConfig && state.editingConfig.cabinetId) {
            select.value = state.editingConfig.cabinetId;
            state.selectedCabinet = state.cabinets.find(c => c.id === state.editingConfig.cabinetId);

            // Automatically load dialogs for the selected cabinet
            if (state.selectedCabinet) {
                await loadStorageDialogs(state.editingConfig.cabinetId);
            }
        }

    } catch (error) {
        console.error('Failed to load cabinets:', error);
        showAlert('connection-status', 'error', 'Failed to load file cabinets');
    }
}

function handleCabinetChange(event) {
    const cabinetId = event.target.value;

    if (!cabinetId) {
        // Reset dialog selection
        document.getElementById('dw-dialog').disabled = true;
        document.getElementById('load-fields-btn').disabled = true;
        return;
    }

    state.selectedCabinet = state.cabinets.find(c => c.id === cabinetId);

    // Load dialogs for this cabinet
    loadStorageDialogs(cabinetId);
}

// ============================================================================
// Storage Dialogs
// ============================================================================

async function loadStorageDialogs(cabinetId) {
    try {
        const response = await fetch('/api/connectors/docuware/dialogs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                server_url: state.credentials.serverUrl,
                username: state.credentials.username,
                password: state.credentials.password,
                cabinet_id: cabinetId
            })
        });

        const result = await response.json();
        state.dialogs = result.dialogs || [];

        // Populate dropdown
        const select = document.getElementById('dw-dialog');
        select.innerHTML = '<option value="">Select a storage dialog...</option>';
        select.disabled = false;

        state.dialogs.forEach(dialog => {
            const option = document.createElement('option');
            option.value = dialog.id;
            option.textContent = dialog.name;
            select.appendChild(option);
        });

        // If editing existing config, restore dialog selection
        if (state.editingConfig && state.editingConfig.dialogId) {
            select.value = state.editingConfig.dialogId;
            state.selectedDialog = state.dialogs.find(d => d.id === state.editingConfig.dialogId);
            document.getElementById('load-fields-btn').disabled = false;

            // Automatically load index fields
            await loadIndexFields();
        }

    } catch (error) {
        console.error('Failed to load dialogs:', error);
        showAlert('connection-status', 'error', 'Failed to load storage dialogs');
    }
}

function handleDialogChange(event) {
    const dialogId = event.target.value;

    if (!dialogId) {
        document.getElementById('load-fields-btn').disabled = true;
        return;
    }

    state.selectedDialog = state.dialogs.find(d => d.id === dialogId);
    document.getElementById('load-fields-btn').disabled = false;
}

// ============================================================================
// Index Fields
// ============================================================================

async function loadIndexFields() {
    const btn = document.getElementById('load-fields-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="btn-icon">⏳</span> Loading...';

    try {
        const response = await fetch('/api/connectors/docuware/fields', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                server_url: state.credentials.serverUrl,
                username: state.credentials.username,
                password: state.credentials.password,
                cabinet_id: state.selectedCabinet.id,
                dialog_id: state.selectedDialog.id
            })
        });

        const result = await response.json();
        state.indexFields = result.fields || [];

        // Get smart field suggestions with confidence scores
        await getFieldSuggestions(state.indexFields);

        // Display fields table
        displayIndexFields(state.indexFields);

        // Show index fields section
        document.getElementById('index-fields-section').style.display = 'block';

        // Build field selection with suggestions
        buildFieldSelection(state.indexFields);

        // Show field selection section
        document.getElementById('field-mapping-section').style.display = 'block';

        // Show save button
        document.getElementById('save-section').style.display = 'block';

    } catch (error) {
        console.error('Failed to load index fields:', error);
        showAlert('connection-status', 'error', 'Failed to load index fields');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="btn-icon">🏷️</span> Load Index Fields';
    }
}

async function getFieldSuggestions(fields) {
    try {
        const response = await fetch('/api/connectors/field-suggestions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(fields)
        });

        const result = await response.json();

        state.fieldSuggestions = result.suggestions || {};
        state.confidenceScores = result.confidence_scores || {};
        state.requiredFields = result.required_fields || [];

        console.log(`✨ Found ${result.suggested_field_count} suggested field mappings`);
    } catch (error) {
        console.error('Failed to get field suggestions:', error);
        // Don't fail the whole flow if suggestions fail
        state.fieldSuggestions = {};
        state.confidenceScores = {};
    }
}

function displayIndexFields(fields) {
    const container = document.getElementById('fields-table-container');

    const table = `
        <table class="fields-table">
            <thead>
                <tr>
                    <th>Field Name</th>
                    <th>Type</th>
                    <th>Required</th>
                    <th>Max Length</th>
                </tr>
            </thead>
            <tbody>
                ${fields.map(field => {
                    if (field.is_table_field && field.table_columns) {
                        // Display table field with nested columns
                        return `
                            <tr class="table-field-row">
                                <td><strong>${field.name}</strong> <span class="table-indicator">📋 Table Field</span></td>
                                <td><span class="field-type">${field.type}</span></td>
                                <td class="${field.required ? 'field-required' : 'field-optional'}">
                                    ${field.required ? '✓ Yes' : 'No'}
                                </td>
                                <td>-</td>
                            </tr>
                            ${field.table_columns.map(col => `
                                <tr class="table-column-row">
                                    <td style="padding-left: 30px;">↳ ${col.label} <span class="column-name">(${col.name})</span></td>
                                    <td><span class="field-type field-type-small">${col.type}</span></td>
                                    <td class="${col.required ? 'field-required' : 'field-optional'}">
                                        ${col.required ? '✓ Yes' : 'No'}
                                    </td>
                                    <td>-</td>
                                </tr>
                            `).join('')}
                        `;
                    } else {
                        // Regular field
                        return `
                            <tr>
                                <td><strong>${field.name}</strong></td>
                                <td><span class="field-type">${field.type}</span></td>
                                <td class="${field.required ? 'field-required' : 'field-optional'}">
                                    ${field.required ? '✓ Yes' : 'No'}
                                </td>
                                <td>${field.max_length || '-'}</td>
                            </tr>
                        `;
                    }
                }).join('')}
            </tbody>
        </table>
    `;

    container.innerHTML = table;
}

// ============================================================================
// Field Mapping
// ============================================================================

function buildFieldSelection(docuwareFields) {
    const container = document.getElementById('field-mapping-container');

    // Filter out system fields and separate table fields from regular fields
    const userFields = docuwareFields.filter(field => !field.is_system_field);
    const regularFields = userFields.filter(field => !field.is_table_field);
    const tableFields = userFields.filter(field => field.is_table_field);

    // Group regular fields by required vs optional
    const requiredFields = regularFields.filter(field => field.required);
    const optionalFields = regularFields.filter(field => !field.required);

    // Helper function to get confidence badge
    const getConfidenceBadge = (fieldName) => {
        const confidence = state.confidenceScores[fieldName];
        if (!confidence) return '';

        if (confidence >= 0.9) {
            return `<span class="confidence-badge confidence-high" title="High confidence match (${Math.round(confidence * 100)}%)">✓ ${Math.round(confidence * 100)}%</span>`;
        } else if (confidence >= 0.7) {
            return `<span class="confidence-badge confidence-medium" title="Medium confidence match (${Math.round(confidence * 100)}%)">~ ${Math.round(confidence * 100)}%</span>`;
        } else {
            return `<span class="confidence-badge confidence-low" title="Low confidence match (${Math.round(confidence * 100)}%)">? ${Math.round(confidence * 100)}%</span>`;
        }
    };

    // Helper to check if field is suggested (has good confidence)
    const isSuggested = (fieldName) => {
        return Object.values(state.fieldSuggestions).includes(fieldName);
    };

    const selectionHtml = `
        <div class="field-selection-container">
            ${requiredFields.length > 0 ? `
                <div class="field-group">
                    <h3 class="field-group-title">
                        Required Fields <span class="field-count">(${requiredFields.length})</span>
                        ${requiredFields.length > 0 ? '<span class="info-icon" title="These fields must be filled for DocuWare">ℹ️</span>' : ''}
                    </h3>
                    <p class="field-group-description">These fields are required by DocuWare and should be extracted from documents</p>
                    <div class="field-checkboxes">
                        ${requiredFields.map(field => {
                            const suggested = isSuggested(field.name);
                            const confidenceBadge = getConfidenceBadge(field.name);
                            return `
                            <label class="field-checkbox ${suggested ? 'field-suggested' : ''}">
                                <input
                                    type="checkbox"
                                    class="field-checkbox-input"
                                    data-field-name="${field.name}"
                                    data-required="true"
                                    ${suggested ? 'checked' : ''}
                                >
                                <span class="field-name">${field.name}</span>
                                <span class="field-badge field-badge-required">Required</span>
                                ${confidenceBadge}
                                ${suggested ? '<span class="suggested-icon" title="AI will likely find this field">✨</span>' : ''}
                            </label>
                        `}).join('')}
                    </div>
                </div>
            ` : ''}

            ${optionalFields.length > 0 ? `
                <div class="field-group">
                    <h3 class="field-group-title">Optional Fields <span class="field-count">(${optionalFields.length})</span></h3>
                    <p class="field-group-description">Select which optional fields AI should try to extract</p>
                    <div class="field-checkboxes">
                        ${optionalFields.map(field => {
                            const suggested = isSuggested(field.name);
                            const confidenceBadge = getConfidenceBadge(field.name);
                            return `
                            <label class="field-checkbox ${suggested ? 'field-suggested' : ''}">
                                <input
                                    type="checkbox"
                                    class="field-checkbox-input"
                                    data-field-name="${field.name}"
                                    data-required="false"
                                    ${suggested ? 'checked' : ''}
                                >
                                <span class="field-name">${field.name}</span>
                                ${confidenceBadge}
                                ${suggested ? '<span class="suggested-icon" title="AI will likely find this field">✨</span>' : ''}
                            </label>
                        `}).join('')}
                    </div>
                </div>
            ` : ''}

            ${tableFields.length > 0 ? `
                <div class="field-group">
                    <h3 class="field-group-title">Table Fields <span class="field-count">(${tableFields.length})</span></h3>
                    <p class="field-group-description">Select table field columns to populate with AI-extracted line items</p>
                    ${tableFields.map(tableField => {
                        const columns = tableField.table_columns || [];
                        if (columns.length === 0) {
                            return `
                                <div class="table-field-section">
                                    <h4 class="table-field-name">📋 ${tableField.name}</h4>
                                    <p class="table-field-description" style="color: #dc3545;">
                                        ⚠️ No columns found for this table field. The table may be empty in DocuWare.
                                    </p>
                                </div>
                            `;
                        }
                        return `
                            <div class="table-field-section">
                                <h4 class="table-field-name">📋 ${tableField.name}</h4>
                                <p class="table-field-description">Select which columns to populate from line item data:</p>
                                <div class="field-checkboxes table-column-checkboxes">
                                    ${columns.map(column => `
                                        <label class="field-checkbox">
                                            <input
                                                type="checkbox"
                                                class="field-checkbox-input table-column-input"
                                                data-table-field="${tableField.name}"
                                                data-column-name="${column.name}"
                                                data-column-label="${column.label}"
                                                data-column-type="${column.type}"
                                            >
                                            <span class="field-name">${column.label}</span>
                                            <span class="field-badge field-badge-type">${column.type}</span>
                                        </label>
                                    `).join('')}
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            ` : ''}

            <div class="field-selection-summary">
                <strong>Selected:</strong> <span id="selected-field-count">0</span> fields/columns
            </div>
        </div>
    `;

    container.innerHTML = selectionHtml;

    // If editing existing config, restore saved selections
    if (state.editingConfig && state.editingConfig.selectedFields) {
        restoreFieldSelections(state.editingConfig.selectedFields);
    }

    // Add change listeners
    document.querySelectorAll('.field-checkbox-input').forEach(checkbox => {
        checkbox.addEventListener('change', updateFieldSelectionCount);
    });

    // Initial count update
    updateFieldSelectionCount();
}

function restoreFieldSelections(selectedFields) {
    selectedFields.forEach(fieldName => {
        const checkbox = document.querySelector(`[data-field-name="${fieldName}"]`);
        if (checkbox) {
            checkbox.checked = true;
        }
    });
}

function updateFieldSelectionCount() {
    const selectedCount = document.querySelectorAll('.field-checkbox-input:checked').length;
    const countSpan = document.getElementById('selected-field-count');
    if (countSpan) {
        countSpan.textContent = selectedCount;
    }
}

function autoMapFields(docuflowFields, docuwareFields) {
    docuflowFields.forEach(dfField => {
        const select = document.querySelector(`[data-df-field="${dfField}"]`);

        // Find best match
        const match = findBestFieldMatch(dfField, docuwareFields);

        if (match) {
            select.value = match.name;
        }
    });
}

function findBestFieldMatch(docuflowField, docuwareFields) {
    const dfLower = docuflowField.toLowerCase().replace('_', '');

    // Direct or close matches
    for (const dwField of docuwareFields) {
        const dwLower = dwField.name.toLowerCase().replace('_', '');

        // Exact match
        if (dfLower === dwLower) {
            return dwField;
        }

        // Substring match
        if (dwLower.includes(dfLower) || dfLower.includes(dwLower)) {
            return dwField;
        }
    }

    // Semantic matches
    const semanticMap = {
        'vendor': ['vendor', 'supplier', 'seller'],
        'client': ['client', 'customer', 'buyer'],
        'document_number': ['invoice', 'doc', 'number'],
        'reference_number': ['reference', 'po', 'ref'],
        'date': ['date', 'invoice_date'],
        'due_date': ['due', 'payment'],
        'amount': ['amount', 'total', 'value']
    };

    const keywords = semanticMap[docuflowField] || [];

    for (const keyword of keywords) {
        for (const dwField of docuwareFields) {
            const dwLower = dwField.name.toLowerCase();
            if (dwLower.includes(keyword)) {
                return dwField;
            }
        }
    }

    return null;
}

function validateMapping() {
    // Collect current mapping
    state.fieldMapping = {};
    document.querySelectorAll('.dw-field-select').forEach(select => {
        const dfField = select.dataset.dfField;
        const dwField = select.value;
        if (dwField) {
            state.fieldMapping[dfField] = dwField;
        }
    });

    // Check for unmapped required fields
    const mappedDwFields = new Set(Object.values(state.fieldMapping));
    const unmappedRequired = state.indexFields
        .filter(field => field.required && !mappedDwFields.has(field.name));

    const warningDiv = document.getElementById('mapping-warning');

    if (unmappedRequired.length > 0) {
        const fieldNames = unmappedRequired.map(f => f.name).join(', ');
        document.getElementById('warning-text').textContent =
            `${unmappedRequired.length} required field(s) are not mapped: ${fieldNames}`;
        warningDiv.style.display = 'block';
    } else {
        warningDiv.style.display = 'none';
    }
}

// ============================================================================
// Validation
// ============================================================================

function validateRequiredFields(selectedFields) {
    // Check which required fields are NOT selected
    const missingRequired = state.requiredFields.filter(reqField =>
        !selectedFields.includes(reqField)
    );

    return {
        valid: missingRequired.length === 0,
        missingRequired: missingRequired
    };
}

async function showValidationWarning(missingFields) {
    const fieldList = missingFields.map(f => `• ${f}`).join('\n');

    const message = `⚠️ Warning: The following REQUIRED fields are not selected:\n\n${fieldList}\n\nDocuWare requires these fields to be filled. Documents without these fields may fail to upload.\n\nDo you want to continue anyway?`;

    return confirm(message);
}

// ============================================================================
// Save Configuration
// ============================================================================

async function saveConfiguration() {
    const btn = document.getElementById('save-config-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="btn-icon">⏳</span> Saving...';

    try {
        let config;

        if (state.connectorType === 'none') {
            // Save "none" configuration
            config = {
                connector_type: 'none',
                docuware: null,
                google_drive: null,
                onedrive: null
            };
        } else if (state.connectorType === 'docuware') {
            // Validate DocuWare configuration
            if (!state.credentials.serverUrl || !state.credentials.username || !state.credentials.password) {
                showAlert('connection-status', 'error', 'Please complete connection test first');
                return;
            }

            if (!state.selectedCabinet || !state.selectedDialog) {
                showAlert('connection-status', 'error', 'Please select file cabinet and storage dialog');
                return;
            }

            // Collect selected fields (regular fields only, not table columns)
            const selectedFields = Array.from(document.querySelectorAll('.field-checkbox-input:checked:not(.table-column-input)'))
                .map(checkbox => checkbox.dataset.fieldName);

            // Collect selected table columns
            const selectedTableColumns = {};
            document.querySelectorAll('.table-column-input:checked').forEach(checkbox => {
                const tableField = checkbox.dataset.tableField;
                const columnName = checkbox.dataset.columnName;
                const columnLabel = checkbox.dataset.columnLabel;
                const columnType = checkbox.dataset.columnType;

                if (!selectedTableColumns[tableField]) {
                    selectedTableColumns[tableField] = [];
                }

                selectedTableColumns[tableField].push({
                    name: columnName,
                    label: columnLabel,
                    type: columnType
                });
            });

            if (selectedFields.length === 0 && Object.keys(selectedTableColumns).length === 0) {
                showAlert('connection-status', 'error', 'Please select at least one field or table column');
                return;
            }

            // Validate required fields
            const validation = validateRequiredFields(selectedFields);
            if (!validation.valid) {
                const proceed = await showValidationWarning(validation.missingRequired);
                if (!proceed) {
                    return; // User cancelled
                }
            }

            // Build DocuWare config
            config = {
                connector_type: 'docuware',
                docuware: {
                    server_url: state.credentials.serverUrl,
                    username: state.credentials.username,
                    encrypted_password: state.credentials.password, // Will be encrypted by backend
                    cabinet_id: state.selectedCabinet.id,
                    cabinet_name: state.selectedCabinet.name,
                    dialog_id: state.selectedDialog.id,
                    dialog_name: state.selectedDialog.name,
                    selected_fields: selectedFields,
                    selected_table_columns: selectedTableColumns
                },
                google_drive: null,
                onedrive: null
            };
        } else if (state.connectorType === 'google_drive') {
            // Validate Google Drive configuration
            const clientId = document.getElementById('gdrive-client-id').value.trim();
            const clientSecret = document.getElementById('gdrive-client-secret').value.trim();
            const refreshToken = document.getElementById('gdrive-refresh-token').value.trim();
            const rootFolderName = document.getElementById('gdrive-folder-name').value.trim() || 'DocuFlow';

            if (!clientId || !clientSecret || !refreshToken) {
                showAlert('gdrive-connection-status', 'error', 'Please complete connection test first');
                return;
            }

            // Build Google Drive config
            config = {
                connector_type: 'google_drive',
                docuware: null,
                google_drive: {
                    client_id: clientId,
                    client_secret: clientSecret,
                    refresh_token: refreshToken,  // Will be encrypted by backend
                    root_folder_name: rootFolderName,
                    auto_create_folders: true
                },
                onedrive: null
            };
        }

        // Save configuration
        const response = await fetch('/api/connectors/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });

        const result = await response.json();

        if (result.success) {
            // Reload configuration to display it
            await loadExistingConfig();

            // Show success message
            document.getElementById('success-message').style.display = 'block';

            // Scroll to success message
            document.getElementById('success-message').scrollIntoView({
                behavior: 'smooth',
                block: 'center'
            });

            // Hide config sections after successful save
            setTimeout(() => {
                document.getElementById('docuware-config').style.display = 'none';
                document.getElementById('cabinet-selection').style.display = 'none';
                document.getElementById('index-fields-section').style.display = 'none';
                document.getElementById('field-mapping-section').style.display = 'none';
                document.getElementById('save-section').style.display = 'none';

                // Scroll to top to show the configuration display
                window.scrollTo({ top: 0, behavior: 'smooth' });
            }, 2000);
        } else {
            showAlert('connection-status', 'error', 'Failed to save configuration');
        }

    } catch (error) {
        console.error('Save configuration error:', error);
        showAlert('connection-status', 'error', 'Error saving configuration: ' + error.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="btn-icon">💾</span> Save Configuration';
    }
}

// ============================================================================
// Load Existing Configuration
// ============================================================================

async function loadExistingConfig() {
    try {
        const response = await fetch('/api/connectors/config');
        const config = await response.json();

        if (config.connector_type !== 'none' && config.connector_type) {
            // Display configuration summary
            displayConfigurationSummary(config);

            // Store in state for editing
            state.savedConfig = config;

        } else {
            // No configuration exists, hide the display
            document.getElementById('current-config-display').style.display = 'none';
        }

    } catch (error) {
        console.error('Failed to load existing config:', error);
        document.getElementById('current-config-display').style.display = 'none';
    }
}

function displayConfigurationSummary(config) {
    // Show the configuration display card
    document.getElementById('current-config-display').style.display = 'block';

    // Display connector type
    const connectorTypeMap = {
        'docuware': 'DocuWare',
        'google_drive': 'Google Drive',
        'onedrive': 'OneDrive'
    };
    document.getElementById('current-connector-type').textContent = connectorTypeMap[config.connector_type] || config.connector_type;

    // Display DocuWare-specific details
    if (config.connector_type === 'docuware' && config.docuware) {
        const dw = config.docuware;

        document.getElementById('docuware-summary').style.display = 'block';
        document.getElementById('current-server-url').textContent = dw.server_url;
        document.getElementById('current-username').textContent = dw.username;
        document.getElementById('current-cabinet').textContent = dw.cabinet_name || dw.cabinet_id;
        document.getElementById('current-dialog').textContent = dw.dialog_name || dw.dialog_id;

        const selectedCount = dw.selected_fields?.length || 0;
        document.getElementById('current-mappings-count').textContent = `${selectedCount} field${selectedCount !== 1 ? 's' : ''} selected`;
    } else {
        document.getElementById('docuware-summary').style.display = 'none';
    }
}

async function editConfiguration() {
    const config = state.savedConfig;

    if (!config) {
        showAlert('connection-status', 'error', 'No configuration to edit');
        return;
    }

    // Set connector type radio
    const radio = document.querySelector(`input[name="connector"][value="${config.connector_type}"]`);
    if (radio) {
        radio.checked = true;
        state.connectorType = config.connector_type;
    }

    // Show DocuWare config section
    if (config.connector_type === 'docuware' && config.docuware) {
        document.getElementById('docuware-config').style.display = 'block';

        const dw = config.docuware;

        // Pre-populate credentials (password will be empty for security)
        document.getElementById('dw-server-url').value = dw.server_url;
        document.getElementById('dw-username').value = dw.username;
        document.getElementById('dw-password').value = ''; // Don't show encrypted password
        document.getElementById('dw-password').placeholder = '(password unchanged - leave empty to keep current)';

        // Update state with credentials (we'll need to re-authenticate to load cabinets)
        state.credentials = {
            serverUrl: dw.server_url,
            username: dw.username,
            password: '' // Will need to be re-entered or fetched
        };

        // Show a message that they need to test connection first
        showAlert('connection-status', 'info', 'Please test connection to continue editing configuration');

        // Store the existing config for later restoration
        state.editingConfig = {
            cabinetId: dw.cabinet_id,
            cabinetName: dw.cabinet_name,
            dialogId: dw.dialog_id,
            dialogName: dw.dialog_name,
            selectedFields: dw.selected_fields
        };
    }

    // Scroll to the config section
    document.getElementById('docuware-config').scrollIntoView({
        behavior: 'smooth',
        block: 'start'
    });
}

async function clearConfiguration() {
    if (!confirm('Are you sure you want to clear the current configuration? This action cannot be undone.')) {
        return;
    }

    try {
        const response = await fetch('/api/connectors/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                connector_type: 'none',
                docuware: null,
                google_drive: null,
                onedrive: null
            })
        });

        const result = await response.json();

        if (result.success) {
            // Hide configuration display
            document.getElementById('current-config-display').style.display = 'none';

            // Reset state
            state.savedConfig = null;
            state.connectorType = 'none';

            // Reset radio buttons
            document.querySelector('input[name="connector"][value="none"]').checked = true;

            // Hide all config sections
            document.getElementById('docuware-config').style.display = 'none';
            document.getElementById('cabinet-selection').style.display = 'none';
            document.getElementById('index-fields-section').style.display = 'none';
            document.getElementById('field-mapping-section').style.display = 'none';
            document.getElementById('save-section').style.display = 'none';

            // Clear form fields
            document.getElementById('dw-server-url').value = '';
            document.getElementById('dw-username').value = '';
            document.getElementById('dw-password').value = '';

            showAlert('connection-status', 'success', 'Configuration cleared successfully');
        } else {
            showAlert('connection-status', 'error', 'Failed to clear configuration');
        }

    } catch (error) {
        console.error('Clear configuration error:', error);
        showAlert('connection-status', 'error', 'Error clearing configuration: ' + error.message);
    }
}

// ============================================================================
// Google Drive Connection
// ============================================================================

async function testGoogleDriveConnection() {
    const clientId = document.getElementById('gdrive-client-id').value.trim();
    const clientSecret = document.getElementById('gdrive-client-secret').value.trim();
    const refreshToken = document.getElementById('gdrive-refresh-token').value.trim();

    // Validation
    if (!clientId || !clientSecret || !refreshToken) {
        showAlert('gdrive-connection-status', 'error', 'Please fill in all OAuth2 credentials');
        return;
    }

    const btn = document.getElementById('gdrive-test-connection-btn');
    btn.disabled = true;
    btn.textContent = 'Testing...';

    try {
        const response = await fetch('/api/connectors/google-drive/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                client_id: clientId,
                client_secret: clientSecret,
                refresh_token: refreshToken
            })
        });

        const result = await response.json();

        if (result.success) {
            showAlert('gdrive-connection-status', 'success', '✓ ' + result.message);

            // Show save section
            document.getElementById('save-section').style.display = 'block';
        } else {
            showAlert('gdrive-connection-status', 'error', '✗ ' + result.message);
        }

    } catch (error) {
        showAlert('gdrive-connection-status', 'error', 'Connection error: ' + error.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="btn-icon">🔌</span> Test Connection';
    }
}

async function showGoogleDriveOAuthHelp() {
    try {
        const response = await fetch('/api/connectors/google-drive/oauth-url');
        const result = await response.json();

        // Build help message
        let helpMessage = `${result.message}\n\n`;
        helpMessage += result.instructions.join('\n') + '\n\n';
        helpMessage += `Visit: ${result.oauth_url}\n\n`;
        helpMessage += `${result.note}`;

        alert(helpMessage);

    } catch (error) {
        alert('Failed to load OAuth help: ' + error.message);
    }
}

// ============================================================================
// Utility Functions
// ============================================================================

function showAlert(containerId, type, message) {
    const container = document.getElementById(containerId);
    container.className = `alert alert-${type}`;
    container.textContent = message;
    container.style.display = 'block';

    // Auto-hide success messages after 5 seconds
    if (type === 'success') {
        setTimeout(() => {
            container.style.display = 'none';
        }, 5000);
    }
}
