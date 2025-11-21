/**
 * Frontend JavaScript for Document Digitization Service
 * Handles file uploads, progress tracking, and results display
 */

// API configuration
const API_BASE = '/api';

// Application state
let selectedFiles = [];
let currentBatchId = null;
let currentOrganization = null;
let usageStats = null;

// DOM Elements (will be initialized after DOM loads)
let uploadSection, uploadBox, fileInput, browseBtn, fileList, uploadControls;
let uploadBtn, clearBtn, processingSection, progressFill, processingStatus;
let processingDetails, resultsSection, resultsSummary, resultsDetails;
let downloadBtn, newBatchBtn;

// ============================================================================
// Initialization
// ============================================================================

/**
 * Initialize DOM elements and event listeners
 * Called after DOM is fully loaded
 */
function initializeApp() {
    // Get DOM elements
    uploadSection = document.getElementById('uploadSection');
    uploadBox = document.getElementById('uploadBox');
    fileInput = document.getElementById('fileInput');
    browseBtn = document.getElementById('browseBtn');
    fileList = document.getElementById('fileList');
    uploadControls = document.getElementById('uploadControls');
    uploadBtn = document.getElementById('uploadBtn');
    clearBtn = document.getElementById('clearBtn');
    processingSection = document.getElementById('processingSection');
    progressFill = document.getElementById('progressFill');
    processingStatus = document.getElementById('processingStatus');
    processingDetails = document.getElementById('processingDetails');
    resultsSection = document.getElementById('resultsSection');
    resultsSummary = document.getElementById('resultsSummary');
    resultsDetails = document.getElementById('resultsDetails');
    downloadBtn = document.getElementById('downloadBtn');
    newBatchBtn = document.getElementById('newBatchBtn');

    // Attach event listeners only if elements exist
    if (browseBtn) browseBtn.addEventListener('click', () => fileInput.click());
    if (fileInput) fileInput.addEventListener('change', handleFileSelect);
    if (uploadBox) {
        uploadBox.addEventListener('click', (e) => {
            // Don't trigger if clicking the button
            if (e.target !== browseBtn && !e.target.closest('.btn')) {
                fileInput.click();
            }
        });
        uploadBox.addEventListener('dragover', handleDragOver);
        uploadBox.addEventListener('dragleave', handleDragLeave);
        uploadBox.addEventListener('drop', handleDrop);
    }
    if (uploadBtn) uploadBtn.addEventListener('click', uploadDocuments);
    if (clearBtn) clearBtn.addEventListener('click', clearFiles);
    if (downloadBtn) downloadBtn.addEventListener('click', downloadResults);
    if (newBatchBtn) newBatchBtn.addEventListener('click', resetApp);

    console.log('[App] Initialized with upload button:', uploadBtn ? 'Found' : 'Not found');
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeApp);
} else {
    initializeApp();
}

// ============================================================================
// File Selection Handlers
// ============================================================================

function handleFileSelect(e) {
    const files = Array.from(e.target.files);
    addFiles(files);
}

function handleDragOver(e) {
    e.preventDefault();
    uploadBox.classList.add('drag-over');
}

function handleDragLeave(e) {
    e.preventDefault();
    uploadBox.classList.remove('drag-over');
}

function handleDrop(e) {
    e.preventDefault();
    uploadBox.classList.remove('drag-over');
    const files = Array.from(e.dataTransfer.files).filter(f => f.name.endsWith('.pdf'));
    addFiles(files);
}

function addFiles(files) {
    // Validate file count
    if (selectedFiles.length + files.length > 100) {
        alert('Maximum 100 files allowed per batch');
        return;
    }

    // Validate file types and sizes
    const validFiles = files.filter(file => {
        if (!file.name.endsWith('.pdf')) {
            alert(`${file.name} is not a PDF file`);
            return false;
        }
        if (file.size > 50 * 1024 * 1024) {
            alert(`${file.name} exceeds 50MB limit`);
            return false;
        }
        return true;
    });

    selectedFiles.push(...validFiles);
    renderFileList();
}

function renderFileList() {
    console.log('[FileList] Rendering file list, files:', selectedFiles.length);
    console.log('[FileList] Elements exist?', {fileList: !!fileList, uploadControls: !!uploadControls});

    if (!fileList || !uploadControls) {
        console.error('[FileList] Required DOM elements not found!');
        return;
    }

    if (selectedFiles.length === 0) {
        fileList.classList.add('hidden');
        uploadControls.classList.add('hidden');
        return;
    }

    fileList.classList.remove('hidden');
    uploadControls.classList.remove('hidden');

    fileList.innerHTML = `
        <h3>Selected Files · ${selectedFiles.length}</h3>
        ${selectedFiles.map((file, index) => `
            <div class="file-item">
                <span class="file-item-icon">📄</span>
                <span class="file-item-name">${file.name}</span>
                <span class="file-item-size">${formatFileSize(file.size)}</span>
            </div>
        `).join('')}
    `;

    console.log('[FileList] File list rendered, controls shown');
}

function clearFiles() {
    selectedFiles = [];
    fileInput.value = '';
    renderFileList();
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// ============================================================================
// Upload and Processing
// ============================================================================

async function uploadDocuments() {
    console.log('[Upload] uploadDocuments called, selectedFiles:', selectedFiles.length);

    if (selectedFiles.length === 0) {
        console.warn('[Upload] No files selected');
        alert('Please select files to upload');
        return;
    }

    // Show processing section
    console.log('[Upload] Hiding upload section, showing processing section');
    console.log('[Upload] uploadSection exists?', !!uploadSection);
    console.log('[Upload] processingSection exists?', !!processingSection);

    if (uploadSection) {
        uploadSection.classList.add('hidden');
        console.log('[Upload] uploadSection hidden');
    } else {
        console.error('[Upload] uploadSection not found!');
    }

    if (processingSection) {
        processingSection.classList.remove('hidden');
        console.log('[Upload] processingSection shown');
        // Scroll to processing section
        setTimeout(() => {
            processingSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 100);
    } else {
        console.error('[Upload] processingSection not found!');
    }

    try {
        // Create FormData with files
        const formData = new FormData();
        selectedFiles.forEach(file => {
            formData.append('files', file);
            console.log('[Upload] Added file:', file.name, file.size);
        });

        // Upload files
        console.log('[Upload] Starting upload...');
        if (processingStatus) processingStatus.textContent = 'Uploading files...';
        if (progressFill) progressFill.style.width = '10%';

        const response = await authenticatedFetch(`${API_BASE}/upload`, {
            method: 'POST',
            body: formData
        });

        console.log('[Upload] Response status:', response.status);

        if (!response.ok) {
            const error = await response.json();
            console.error('[Upload] Server error:', error);
            throw new Error(error.detail || 'Upload failed');
        }

        const data = await response.json();
        currentBatchId = data.batch_id;
        console.log('[Upload] Batch created:', currentBatchId);

        if (processingStatus) processingStatus.textContent = 'Upload complete! Processing documents...';
        if (progressFill) progressFill.style.width = '20%';

        // Poll for results
        await pollBatchStatus();

    } catch (error) {
        console.error('[Upload] Upload error:', error);
        alert('Upload failed: ' + error.message + '\n\nCheck the browser console for details.');
        resetApp();
    }
}

async function pollBatchStatus() {
    const pollInterval = 500; // Poll every 0.5 seconds for faster updates
    let lastProcessedCount = 0;

    console.log('[Poll] Starting to poll batch status for:', currentBatchId);
    console.log('[Poll] processingDetails exists?', !!processingDetails);
    console.log('[Poll] progressFill exists?', !!progressFill);
    console.log('[Poll] processingStatus exists?', !!processingStatus);

    // Add initial message
    addProcessingLog(`🚀 Starting batch processing: ${selectedFiles.length} files`, 'info');

    let pollCount = 0;
    while (true) {
        pollCount++;
        console.log(`[Poll] Poll attempt #${pollCount}`);

        try {
            const response = await authenticatedFetch(`${API_BASE}/status/${currentBatchId}`);
            console.log(`[Poll] Response status: ${response.status}`);

            if (!response.ok) {
                throw new Error('Failed to fetch status');
            }

            const data = await response.json();
            console.log(`[Poll] Batch status:`, data.status, `Processed: ${data.processed_files}/${data.total_files}`);

            // Update progress bar (20% reserved for upload, 70% for processing, 10% for organizing)
            const processingProgress = (data.processed_files / data.total_files) * 70;
            const totalProgress = 20 + processingProgress;
            progressFill.style.width = totalProgress + '%';

            // Update status text
            processingStatus.textContent = `Processing: ${data.processed_files} of ${data.total_files} documents...`;

            // Show newly processed files as console output
            if (data.results && data.results.length > lastProcessedCount) {
                const newResults = data.results.slice(lastProcessedCount);
                newResults.forEach(result => {
                    if (result.error) {
                        addProcessingLog(`❌ ${result.filename} - Error: ${result.error}`, 'error');
                    } else {
                        addProcessingLog(`✓ ${result.filename} → ${result.category} (confidence: ${(result.confidence * 100).toFixed(0)}%, time: ${result.processing_time.toFixed(2)}s)`, 'success');
                    }
                });
                lastProcessedCount = data.results.length;
            }

            // Check if completed
            if (data.status === 'completed') {
                console.log('[Poll] Batch completed! Showing results...');
                addProcessingLog('📦 Organizing files and creating ZIP...', 'info');
                if (processingStatus) processingStatus.textContent = 'Organizing files and creating ZIP...';
                if (progressFill) progressFill.style.width = '100%';

                // Small delay to show 100% progress
                await new Promise(resolve => setTimeout(resolve, 500));

                addProcessingLog('✅ Processing complete!', 'success');
                console.log('[Poll] Calling showResults with data:', data);
                showResults(data);
                console.log('[Poll] showResults completed, breaking poll loop');
                break;
            }

            // Wait before next poll
            await new Promise(resolve => setTimeout(resolve, pollInterval));

        } catch (error) {
            console.error('Polling error:', error);
            // Continue polling even if one request fails
            await new Promise(resolve => setTimeout(resolve, pollInterval));
        }
    }
}

function addProcessingLog(message, type = 'info') {
    console.log(`[ProcessingLog] ${type.toUpperCase()}: ${message}`);

    if (!processingDetails) {
        console.error('[ProcessingLog] processingDetails element not found!');
        return;
    }

    const logEntry = document.createElement('div');
    logEntry.className = `log-entry log-${type}`;
    logEntry.textContent = message;

    processingDetails.appendChild(logEntry);
    console.log('[ProcessingLog] Log entry added, total entries:', processingDetails.children.length);

    // Auto-scroll to bottom
    processingDetails.scrollTop = processingDetails.scrollHeight;
}

// ============================================================================
// Results Display
// ============================================================================

function showResults(data) {
    console.log('[Results] Showing results for batch:', currentBatchId);
    console.log('[Results] Data:', data);

    // Hide processing, show results
    console.log('[Results] Hiding processing section, showing results section');
    processingSection.classList.add('hidden');
    resultsSection.classList.remove('hidden');

    // Scroll to top of results section
    resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

    // Display summary statistics
    resultsSummary.innerHTML = `
        <div class="stat-card">
            <div class="stat-number">${data.successful}</div>
            <div class="stat-label">Successfully Processed</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">${data.failed}</div>
            <div class="stat-label">Failed</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">${Object.keys(data.processing_summary).length}</div>
            <div class="stat-label">Categories</div>
        </div>
    `;

    // Group results by category
    const byCategory = {};
    data.results.forEach(result => {
        if (!result.error) {
            if (!byCategory[result.category]) {
                byCategory[result.category] = [];
            }
            byCategory[result.category].push(result);
        }
    });

    // Display results grouped by category with extracted data
    resultsDetails.innerHTML = Object.keys(byCategory)
        .sort()
        .map(category => `
            <div class="category-section">
                <div class="category-header">
                    <span class="category-icon">${getCategoryIcon(category)}</span>
                    <span class="category-title">${category}</span>
                    <span class="category-badge">${byCategory[category].length}</span>
                </div>
                <div class="doc-grid">
                    ${byCategory[category].map((doc, index) => {
                        const docId = `doc-${category.replace(/\s+/g, '-')}-${index}`;
                        return renderDocumentCard(doc, docId);
                    }).join('')}
                </div>
            </div>
        `).join('');

    // Show failed documents if any
    const failedDocs = data.results.filter(r => r.error);
    if (failedDocs.length > 0) {
        resultsDetails.innerHTML += `
            <div class="category-group" style="border-left-color: #f56565;">
                <div class="category-header" style="color: #c53030;">
                    Failed Documents <span class="category-count">(${failedDocs.length})</span>
                </div>
                ${failedDocs.map(doc => `
                    <div class="document-item">
                        <span class="document-name">${doc.filename}</span>
                        <span style="color: #c53030; font-size: 0.9em;">${doc.error}</span>
                    </div>
                `).join('')}
            </div>
        `;
    }

    // Refresh dashboard stats to show updated document counts
    // Add a small delay to give backend time to update usage logs
    console.log('[Results] Refreshing dashboard stats in 2 seconds...');
    setTimeout(() => {
        console.log('[Results] Now refreshing stats and pending documents...');
        loadStatsOverview().catch(err => console.error('[Results] Failed to refresh stats:', err));
        loadRecentActivity().catch(err => console.error('[Results] Failed to refresh activity:', err));
        loadPendingDocuments().catch(err => console.error('[Results] Failed to refresh pending documents:', err));
    }, 2000);
}

function getConfidenceClass(confidence) {
    if (confidence >= 0.8) return 'confidence-high';
    if (confidence >= 0.5) return 'confidence-medium';
    return 'confidence-low';
}

function getCategoryIcon(category) {
    // Professional Font Awesome icons
    const icons = {
        'Invoice': '<i class="fa-solid fa-file-invoice"></i>',
        'Receipt': '<i class="fa-solid fa-receipt"></i>',
        'Contract': '<i class="fa-solid fa-file-contract"></i>',
        'Legal Document': '<i class="fa-solid fa-gavel"></i>',
        'HR Document': '<i class="fa-solid fa-users"></i>',
        'Tax Document': '<i class="fa-solid fa-file-invoice-dollar"></i>',
        'Financial Statement': '<i class="fa-solid fa-chart-line"></i>',
        'Correspondence': '<i class="fa-solid fa-envelope"></i>',
        'Other': '<i class="fa-solid fa-file"></i>'
    };
    return icons[category] || '<i class="fa-solid fa-file"></i>';
}

function renderDocumentCard(doc, docId) {
    const hasData = doc.extracted_data && Object.keys(doc.extracted_data).some(key =>
        doc.extracted_data[key] !== null && doc.extracted_data[key] !== undefined
    );

    return `
        <div class="doc-card">
            <div class="doc-card-header" onclick="toggleExtractedData('${docId}')">
                <div class="doc-card-title">
                    <span class="doc-expand-icon" id="icon-${docId}">
                        <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                            <path d="M4 2l4 4-4 4" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/>
                        </svg>
                    </span>
                    <span class="doc-filename">${doc.filename}</span>
                </div>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                    <span class="confidence-badge ${getConfidenceClass(doc.confidence)}">
                        ${(doc.confidence * 100).toFixed(0)}%
                    </span>
                    ${doc.id ? `
                        <button onclick="event.stopPropagation(); window.location.href='pdf-viewer.html?id=${doc.id}'" style="
                            background: #3b82f6;
                            color: white;
                            border: none;
                            padding: 0.375rem 0.75rem;
                            border-radius: 6px;
                            font-weight: 600;
                            font-size: 0.875rem;
                            cursor: pointer;
                            transition: background 0.2s;
                            white-space: nowrap;
                        " onmouseover="this.style.background='#2563eb'" onmouseout="this.style.background='#3b82f6'">
                            Review
                            <i class="fa-solid fa-arrow-right" style="margin-left: 0.25rem;"></i>
                        </button>
                        <button onclick="event.stopPropagation(); dismissDocument(${doc.id})" style="
                            background: #ef4444;
                            color: white;
                            border: none;
                            padding: 0.375rem;
                            border-radius: 6px;
                            font-weight: 600;
                            font-size: 0.875rem;
                            cursor: pointer;
                            transition: background 0.2s;
                            width: 32px;
                            height: 32px;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                        " onmouseover="this.style.background='#dc2626'" onmouseout="this.style.background='#ef4444'" title="Dismiss">
                            <i class="fa-solid fa-times"></i>
                        </button>
                    ` : ''}
                </div>
            </div>
            ${hasData ? renderExtractedDataCard(doc, docId) : ''}
        </div>
    `;
}

function renderExtractedDataCard(doc, docId) {
    if (!doc.extracted_data) {
        return '';
    }

    const data = doc.extracted_data;

    // Debug logging for line items
    if (data.line_items && data.line_items.length > 0) {
        console.log(`[ExtractedData] Document ${doc.filename} has ${data.line_items.length} line items:`, data.line_items);
    }

    // Build key-value pairs
    const sections = [];

    // Primary info (most important)
    const primaryInfo = [];
    if (data.amount) primaryInfo.push({ icon: '<i class="fa-solid fa-dollar-sign"></i>', label: 'Amount', value: data.amount, primary: true });
    if (data.date) primaryInfo.push({ icon: '<i class="fa-solid fa-calendar"></i>', label: 'Date', value: data.date });
    if (data.due_date) primaryInfo.push({ icon: '<i class="fa-solid fa-clock"></i>', label: 'Due Date', value: data.due_date });

    if (primaryInfo.length > 0) {
        sections.push({ title: 'Financial Details', items: primaryInfo });
    }

    // Parties
    const parties = [];
    if (data.vendor) parties.push({ icon: '<i class="fa-solid fa-building"></i>', label: 'Vendor', value: data.vendor });
    if (data.client) parties.push({ icon: '<i class="fa-solid fa-user"></i>', label: 'Client', value: data.client });
    if (data.person_name) parties.push({ icon: '<i class="fa-solid fa-user"></i>', label: 'Contact', value: data.person_name });
    if (data.company) parties.push({ icon: '<i class="fa-solid fa-building"></i>', label: 'Company', value: data.company });

    if (parties.length > 0) {
        sections.push({ title: 'Parties', items: parties });
    }

    // Document details
    const docDetails = [];
    if (data.document_type) docDetails.push({ icon: '<i class="fa-solid fa-file-lines"></i>', label: 'Type', value: data.document_type });
    if (data.document_number) docDetails.push({ icon: '<i class="fa-solid fa-hashtag"></i>', label: 'Number', value: data.document_number });
    if (data.reference_number) docDetails.push({ icon: '<i class="fa-solid fa-link"></i>', label: 'Reference', value: data.reference_number });

    if (docDetails.length > 0) {
        sections.push({ title: 'Document Info', items: docDetails });
    }

    // Contact
    const contact = [];
    if (data.phone) contact.push({ icon: '<i class="fa-solid fa-phone"></i>', label: 'Phone', value: data.phone });
    if (data.email) contact.push({ icon: '<i class="fa-solid fa-envelope"></i>', label: 'Email', value: data.email });
    if (data.address) contact.push({ icon: '<i class="fa-solid fa-location-dot"></i>', label: 'Address', value: data.address });

    if (contact.length > 0) {
        sections.push({ title: 'Contact', items: contact });
    }

    // Dynamic additional fields - show any fields not already displayed
    const knownFields = [
        'amount', 'date', 'due_date',  // Financial
        'vendor', 'client', 'person_name', 'company',  // Parties
        'document_type', 'document_number', 'reference_number',  // Document
        'phone', 'email', 'address',  // Contact
        'line_items'  // Line items handled separately
    ];

    const internalFields = [
        'id', 'user_id', 'organization_id', 'created_at', 'updated_at',
        'document_id', 'upload_id', 'status', 'connector_id'
    ];

    const additionalFields = [];

    // Helper function to format field names nicely
    function formatFieldName(fieldName) {
        return fieldName
            .split('_')
            .map(word => word.charAt(0).toUpperCase() + word.slice(1))
            .join(' ');
    }

    // Loop through all fields in the data object
    for (let key in data) {
        if (data.hasOwnProperty(key)) {
            const value = data[key];

            // Skip if it's a known field, internal field, or empty value
            if (!knownFields.includes(key) &&
                !internalFields.includes(key) &&
                value !== null &&
                value !== undefined &&
                value !== '') {

                // Only add simple values (not objects or arrays)
                if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
                    additionalFields.push({
                        icon: '<i class="fa-solid fa-tag"></i>',
                        label: formatFieldName(key),
                        value: String(value)
                    });
                }
            }
        }
    }

    // Add additional fields section if there are any
    if (additionalFields.length > 0) {
        sections.push({ title: 'Additional Fields', items: additionalFields });
    }

    return `
        <div class="doc-card-body" id="data-${docId}">
            ${sections.map(section => `
                <div class="data-section-card">
                    <div class="data-section-header">${section.title}</div>
                    <div class="data-items">
                        ${section.items.map(item => `
                            <div class="data-item ${item.primary ? 'primary' : ''}">
                                ${item.icon ? `<span class="data-icon">${item.icon}</span>` : ''}
                                <div class="data-content">
                                    <div class="data-label">${item.label}</div>
                                    <div class="data-value">${item.value}</div>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `).join('')}
            ${data.line_items && data.line_items.length > 0 ? `
                <div class="data-section-card">
                    <div class="data-section-header"><i class="fa-solid fa-table"></i> Line Items (${data.line_items.length})</div>
                    <div class="line-items-table">
                        <table class="items-table">
                            <thead>
                                <tr>
                                    <th>Description</th>
                                    <th>Qty</th>
                                    <th>Unit</th>
                                    <th>Unit Price</th>
                                    <th>Amount</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${data.line_items.map((item, index) => `
                                    <tr>
                                        <td class="item-description">
                                            ${item.description || '-'}
                                            ${item.sku ? `<div class="item-sku">SKU: ${item.sku}</div>` : ''}
                                        </td>
                                        <td>${item.quantity || '-'}</td>
                                        <td>${item.unit || '-'}</td>
                                        <td>${item.unit_price || '-'}</td>
                                        <td class="item-amount">${item.amount || '-'}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            ` : ''}
            ${data.other_data && Object.keys(data.other_data).length > 0 && doc.connector_type && doc.connector_type !== 'none' ? `
                <div class="data-section-card">
                    <div class="data-section-header">
                        <i class="fa-solid ${doc.connector_type === 'docuware' ? 'fa-database' : doc.connector_type === 'google_drive' ? 'fa-brands fa-google-drive' : 'fa-cloud'}"></i>
                        ${doc.connector_type === 'docuware' ? 'DocuWare Fields' : doc.connector_type === 'google_drive' ? 'Google Drive Fields' : 'Connector Fields'}
                    </div>
                    <div class="data-items-compact">
                        ${Object.entries(data.other_data).map(([key, value]) => `
                            <div class="data-item-compact">
                                <span class="data-label-compact">${key.replace(/_/g, ' ')}:</span>
                                <span class="data-value-compact">${value || '-'}</span>
                            </div>
                        `).join('')}
                    </div>
                </div>
            ` : ''}
        </div>
    `;
}

// Make toggleExtractedData globally accessible
window.toggleExtractedData = function(docId) {
    const dataSection = document.getElementById(`data-${docId}`);
    const icon = document.getElementById(`icon-${docId}`);

    if (dataSection && icon) {
        const isExpanded = dataSection.classList.contains('expanded');

        if (isExpanded) {
            dataSection.classList.remove('expanded');
            icon.classList.remove('expanded');
        } else {
            dataSection.classList.add('expanded');
            icon.classList.add('expanded');
        }
    }
}

function downloadResults() {
    // Trigger download
    window.location.href = `${API_BASE}/download/${currentBatchId}`;
}

function resetApp() {
    console.log('[App] Resetting app for new batch');

    // Reset state
    selectedFiles = [];
    currentBatchId = null;
    fileInput.value = '';

    // Reset UI
    console.log('[App] Showing upload section, hiding processing and results');
    uploadSection.classList.remove('hidden');
    processingSection.classList.add('hidden');
    resultsSection.classList.add('hidden');

    renderFileList();
    progressFill.style.width = '0%';
    processingDetails.innerHTML = '';

    // Scroll to top of page
    window.scrollTo({ top: 0, behavior: 'smooth' });

    // Refresh dashboard stats
    console.log('[App] Refreshing dashboard stats...');
    loadStatsOverview().catch(err => console.error('[App] Failed to refresh stats:', err));
}

// ============================================================================
// Dashboard & Organization Context
// ============================================================================

/**
 * Load complete dashboard (main entry point for dashboard page)
 */
async function loadDashboard() {
    console.log('[Dashboard] Loading dashboard...');

    try {
        // Display user info first
        if (typeof displayUserInfo === 'function') {
            await displayUserInfo('userInfo');
        }

        await Promise.all([
            loadOrganizationContext(),
            loadStatsOverview(),
            loadRecentActivity(),
            loadPendingDocuments()
        ]);

        // Set up refresh button
        const refreshBtn = document.getElementById('refreshActivityBtn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', loadRecentActivity);
        }

        console.log('[Dashboard] Dashboard loaded successfully');
    } catch (error) {
        console.error('[Dashboard] Error loading dashboard:', error);
    }
}

/**
 * Load organization context and usage stats
 */
async function loadOrganizationContext() {
    try {
        // Load organization data
        const orgResponse = await authenticatedFetch('/api/organizations/current');
        if (orgResponse.ok) {
            const data = await orgResponse.json();
            currentOrganization = data.organization;
            console.log('[App] Loaded organization:', currentOrganization);

            // Update navbar with organization name
            updateOrganizationDisplay();
        }

        // Load usage stats
        const usageResponse = await authenticatedFetch('/api/organizations/usage');
        if (usageResponse.ok) {
            usageStats = await usageResponse.json();
            console.log('[App] Loaded usage stats:', usageStats);
        }

        // Load subscription status
        const subResponse = await authenticatedFetch('/api/organizations/subscription-status');
        if (subResponse.ok) {
            const subscriptionStatus = await subResponse.json();
            console.log('[App] Loaded subscription status:', subscriptionStatus);

            // Display subscription banner
            displaySubscriptionBanner(subscriptionStatus);
        }
    } catch (error) {
        console.error('[App] Error loading organization context:', error);
    }
}

/**
 * Update organization name display in navbar
 */
function updateOrganizationDisplay() {
    if (!currentOrganization) return;

    // Find the nav status element and add organization name
    const navStatus = document.querySelector('.nav-status');
    if (navStatus) {
        // Add organization name before status
        const orgName = document.createElement('span');
        orgName.className = 'nav-org-name';
        orgName.style.cssText = `
            color: var(--gray-700);
            font-weight: 600;
            margin-right: 1.5rem;
            padding-right: 1.5rem;
            border-right: 1px solid var(--gray-300);
        `;
        orgName.textContent = currentOrganization.name;

        navStatus.parentNode.insertBefore(orgName, navStatus);
    }
}

/**
 * Update usage stats display
 */
function updateUsageDisplay() {
    if (!usageStats) return;

    // Check if usage display element exists, create if not
    let usageDisplay = document.getElementById('usageDisplay');
    if (!usageDisplay) {
        const heroContent = document.querySelector('.hero-content');
        if (heroContent) {
            usageDisplay = document.createElement('div');
            usageDisplay.id = 'usageDisplay';
            usageDisplay.className = 'usage-stats';
            usageDisplay.style.cssText = `
                display: flex;
                gap: 2rem;
                margin-top: 2rem;
                padding: 1.5rem;
                background: rgba(255, 255, 255, 0.9);
                backdrop-filter: blur(12px);
                border-radius: var(--radius-lg);
                box-shadow: var(--shadow-sm);
            `;
            heroContent.appendChild(usageDisplay);
        }
    }

    if (usageDisplay) {
        usageDisplay.innerHTML = `
            <div class="usage-stat">
                <div style="font-size: 0.875rem; color: var(--gray-600); margin-bottom: 0.25rem;">
                    Documents This Month
                </div>
                <div style="font-size: 1.75rem; font-weight: 700; color: var(--primary-600);">
                    ${usageStats.total_documents_processed || 0}
                </div>
            </div>
            <div class="usage-stat">
                <div style="font-size: 0.875rem; color: var(--gray-600); margin-bottom: 0.25rem;">
                    Estimated Cost
                </div>
                <div style="font-size: 1.75rem; font-weight: 700; color: var(--gray-900);">
                    $${(usageStats.total_cost || 0).toFixed(2)}
                </div>
            </div>
            <div class="usage-stat">
                <div style="font-size: 0.875rem; color: var(--gray-600); margin-bottom: 0.25rem;">
                    Billing Period
                </div>
                <div style="font-size: 1.75rem; font-weight: 700; color: var(--gray-900);">
                    ${usageStats.billing_period || 'N/A'}
                </div>
            </div>
        `;
    }
}

/**
 * Display subscription status banner
 */
function displaySubscriptionBanner(status) {
    const banner = document.getElementById('subscriptionBanner');
    if (!banner) return;

    // Handle errors gracefully
    if (!status || !status.subscription) {
        console.warn('[App] Invalid subscription status, hiding banner');
        banner.style.display = 'none';
        return;
    }

    const sub = status.subscription;
    const usage = status.usage;
    const warning = status.warning;

    // Determine banner style based on status
    let bannerStyle = 'info';
    let bannerColor = '#3b82f6';
    let bgColor = '#eff6ff';
    let borderColor = '#93c5fd';

    if (sub.is_expired) {
        bannerStyle = 'critical';
        bannerColor = '#dc2626';
        bgColor = '#fee2e2';
        borderColor = '#fca5a5';
    } else if (warning.show && warning.level === 'critical') {
        bannerStyle = 'critical';
        bannerColor = '#dc2626';
        bgColor = '#fee2e2';
        borderColor = '#fca5a5';
    } else if (warning.show && warning.level === 'warning') {
        bannerStyle = 'warning';
        bannerColor = '#f59e0b';
        bgColor = '#fef3c7';
        borderColor = '#fcd34d';
    } else if (sub.is_trial) {
        bannerStyle = 'trial';
        bannerColor = '#8b5cf6';
        bgColor = '#f3e8ff';
        borderColor = '#c4b5fd';
    }

    // Build usage progress bar (if limited)
    let progressBar = '';
    if (!usage.is_unlimited && usage.document_limit) {
        const percent = usage.usage_percent || 0;
        let barColor = '#3b82f6';
        if (percent >= 100) barColor = '#dc2626';
        else if (percent >= 90) barColor = '#f59e0b';
        else if (percent >= 75) barColor = '#eab308';

        progressBar = `
            <div style="flex: 1; max-width: 300px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                    <span style="font-size: 0.875rem; font-weight: 600; color: ${bannerColor};">
                        ${usage.documents_processed} / ${usage.document_limit} documents
                    </span>
                    <span style="font-size: 0.75rem; color: var(--gray-600);">
                        ${usage.documents_remaining} remaining
                    </span>
                </div>
                <div style="width: 100%; height: 8px; background: rgba(0,0,0,0.1); border-radius: 4px; overflow: hidden;">
                    <div style="width: ${percent}%; height: 100%; background: ${barColor}; transition: width 0.3s;"></div>
                </div>
            </div>
        `;
    }

    // Build trial expiration notice
    let expirationNotice = '';
    if (sub.is_trial && sub.trial_end_date) {
        const endDate = new Date(sub.trial_end_date);
        const daysLeft = Math.ceil((endDate - new Date()) / (1000 * 60 * 60 * 24));

        if (daysLeft > 0) {
            expirationNotice = `<span style="font-size: 0.875rem; color: ${bannerColor};">Trial expires in ${daysLeft} days</span>`;
        }
    }

    // Build warning message
    let warningMsg = '';
    if (sub.is_expired) {
        warningMsg = 'Your trial has expired. Upgrade to continue processing documents.';
    } else if (warning.show) {
        warningMsg = warning.message;
    }

    banner.innerHTML = `
        <div style="
            margin: 1rem auto;
            max-width: 1200px;
            padding: 1rem 1.5rem;
            background: ${bgColor};
            border: 2px solid ${borderColor};
            border-radius: var(--radius-lg);
            display: flex;
            align-items: center;
            gap: 1.5rem;
            flex-wrap: wrap;
        ">
            <div style="flex: 0 0 auto;">
                <div style="font-weight: 700; font-size: 1rem; color: ${bannerColor}; margin-bottom: 0.25rem;">
                    ${sub.plan_name}
                </div>
                ${expirationNotice}
                ${warningMsg ? `<div style="font-size: 0.875rem; color: ${bannerColor}; margin-top: 0.25rem;">${warningMsg}</div>` : ''}
            </div>
            ${progressBar}
            ${sub.is_expired ? `
                <div style="margin-left: auto;">
                    <a href="/settings.html" style="
                        padding: 0.5rem 1rem;
                        background: ${bannerColor};
                        color: white;
                        border-radius: 0.5rem;
                        text-decoration: none;
                        font-weight: 600;
                        font-size: 0.875rem;
                    ">Upgrade Now</a>
                </div>
            ` : ''}
        </div>
    `;

    banner.style.display = 'block';
}

/**
 * Load and display stats overview cards
 */
async function loadStatsOverview() {
    const container = document.getElementById('statsOverview');
    if (!container) return;

    try {
        // Get subscription status (add timestamp to prevent caching)
        const timestamp = new Date().getTime();
        const subResponse = await authenticatedFetch(`/api/organizations/subscription-status?t=${timestamp}`);
        if (!subResponse.ok) {
            throw new Error('Failed to load subscription status');
        }

        const status = await subResponse.json();
        console.log('[StatsOverview] API response:', status);

        // Validate response
        if (!status || !status.subscription || !status.usage || !status.cost) {
            throw new Error('Invalid subscription status response');
        }

        const sub = status.subscription;
        const usage = status.usage;
        const cost = status.cost;

        console.log('[StatsOverview] Documents processed:', usage.documents_processed);
        console.log('[StatsOverview] Total cost:', cost.total);

        // Build stats cards
        const cards = [];

        // Card 1: Current Plan
        cards.push(`
            <div style="
                background: #0066cc;
                border-radius: var(--radius-xl);
                padding: 1.5rem;
                color: white;
                box-shadow: var(--shadow-lg);
            ">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.75rem;">
                    <div style="font-size: 0.875rem; opacity: 0.9;">Current Plan</div>
                    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" stroke="white" stroke-width="2" opacity="0.3">
                        <path d="M16 8v16M8 16h16" stroke-linecap="round"/>
                    </svg>
                </div>
                <div style="font-size: 1.75rem; font-weight: 700; margin-bottom: 0.5rem;">
                    ${sub.plan_name}
                </div>
                <div style="font-size: 0.875rem; opacity: 0.9;">
                    ${sub.is_trial ?
                        (sub.trial_end_date ?
                            `Expires ${new Date(sub.trial_end_date).toLocaleDateString()}` :
                            'Trial active') :
                        'Active subscription'}
                </div>
            </div>
        `);

        // Card 2: Documents Processed
        cards.push(`
            <div style="
                background: white;
                border-radius: var(--radius-xl);
                padding: 1.5rem;
                box-shadow: var(--shadow-md);
                border: 2px solid var(--gray-100);
            ">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.75rem;">
                    <div style="font-size: 0.875rem; color: var(--gray-600);">Documents Processed</div>
                    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" stroke="#10b981" stroke-width="2" opacity="0.3">
                        <path d="M10 12h12M10 16h12M10 20h8" stroke-linecap="round"/>
                    </svg>
                </div>
                <div style="font-size: 1.75rem; font-weight: 700; color: var(--gray-900); margin-bottom: 0.5rem;">
                    ${usage.documents_processed}${usage.document_limit ? ` / ${usage.document_limit}` : ''}
                </div>
                <div style="font-size: 0.875rem; color: var(--gray-600);">
                    ${usage.is_unlimited ? 'Unlimited' : `${usage.documents_remaining || 0} remaining`} this month
                </div>
            </div>
        `);

        // Card 3: Total Cost
        cards.push(`
            <div style="
                background: white;
                border-radius: var(--radius-xl);
                padding: 1.5rem;
                box-shadow: var(--shadow-md);
                border: 2px solid var(--gray-100);
            ">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.75rem;">
                    <div style="font-size: 0.875rem; color: var(--gray-600);">Total Cost</div>
                    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" stroke="#f59e0b" stroke-width="2" opacity="0.3">
                        <circle cx="16" cy="16" r="10"/>
                        <path d="M16 10v12M12 14h4a2 2 0 010 4h-4" stroke-linecap="round"/>
                    </svg>
                </div>
                <div style="font-size: 1.75rem; font-weight: 700; color: var(--gray-900); margin-bottom: 0.5rem;">
                    $${cost.total.toFixed(2)}
                </div>
                <div style="font-size: 0.875rem; color: var(--gray-600);">
                    ${usage.current_period}
                    ${cost.base_fee > 0 ? ` (Base: $${cost.base_fee.toFixed(2)})` : ''}
                </div>
            </div>
        `);

        container.innerHTML = cards.join('');

    } catch (error) {
        console.error('[Dashboard] Error loading stats overview:', error);
        container.innerHTML = `
            <div style="
                grid-column: 1 / -1;
                padding: 2rem;
                text-align: center;
                color: var(--gray-500);
                background: white;
                border-radius: var(--radius-xl);
                box-shadow: var(--shadow-md);
            ">
                Failed to load stats. Please refresh the page.
            </div>
        `;
    }
}

/**
 * Load and display recent activity
 */
async function loadRecentActivity() {
    const container = document.getElementById('recentActivity');
    if (!container) return;

    // Show loading state
    container.innerHTML = `
        <div style="text-align: center; padding: 3rem; color: var(--gray-500);">
            <div class="spinner" style="margin: 0 auto 1rem;"></div>
            <p>Loading recent activity...</p>
        </div>
    `;

    try {
        // Get recent batches
        const response = await authenticatedFetch('/api/batches');
        if (!response.ok) {
            throw new Error('Failed to load batches');
        }

        const batches = await response.json();

        if (!batches || batches.length === 0) {
            container.innerHTML = `
                <div style="text-align: center; padding: 3rem; color: var(--gray-500);">
                    <svg width="48" height="48" viewBox="0 0 48 48" fill="none" style="margin: 0 auto 1rem; opacity: 0.5;">
                        <circle cx="24" cy="24" r="22" stroke="currentColor" stroke-width="2" stroke-dasharray="4 4"/>
                        <path d="M24 16v16M16 24h16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    </svg>
                    <p>No recent activity. Upload documents to get started!</p>
                </div>
            `;
            return;
        }

        // Display batches (show first 5)
        const recentBatches = batches.slice(0, 5);
        const batchesHTML = recentBatches.map((batch, index) => {
            const createdAt = new Date(batch.created_at);
            const statusColors = {
                'completed': { bg: '#d1fae5', text: '#10b981' },
                'processing': { bg: '#dbeafe', text: '#3b82f6' },
                'pending': { bg: '#fef3c7', text: '#f59e0b' },
                'failed': { bg: '#fee2e2', text: '#ef4444' }
            };
            const colors = statusColors[batch.status] || statusColors['pending'];
            const batchElementId = `batch-${batch.id}`;
            const expandedId = `expanded-${batch.id}`;

            return `
                <div id="${batchElementId}" style="border-bottom: 1px solid var(--gray-200);">
                    <div style="
                        display: flex;
                        align-items: center;
                        justify-content: space-between;
                        padding: 1rem;
                        transition: background 0.2s;
                        cursor: pointer;
                    " onmouseover="this.style.background='var(--gray-50)'" onmouseout="this.style.background='white'" onclick="toggleBatchDetails('${batch.id}')">
                        <div style="flex: 1;">
                            <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem;">
                                <svg id="expand-icon-${batch.id}" width="16" height="16" viewBox="0 0 16 16" fill="currentColor" style="color: var(--gray-600); transition: transform 0.2s;">
                                    <path d="M5 6l3 3 3-3" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
                                </svg>
                                <div style="
                                    width: 8px;
                                    height: 8px;
                                    border-radius: 50%;
                                    background: ${colors.text};
                                "></div>
                                <div style="font-weight: 600; color: var(--gray-900);">
                                    Batch #${batch.id.substring(0, 8)}
                                </div>
                                <div style="
                                    padding: 0.25rem 0.75rem;
                                    background: ${colors.bg};
                                    color: ${colors.text};
                                    border-radius: 1rem;
                                    font-size: 0.75rem;
                                    font-weight: 600;
                                    text-transform: uppercase;
                                ">
                                    ${batch.status}
                                </div>
                            </div>
                            <div style="font-size: 0.875rem; color: var(--gray-600); margin-left: 2rem;">
                                ${batch.total_files} files • ${batch.successful || 0} successful • ${batch.failed || 0} failed
                            </div>
                        </div>
                        <div style="text-align: right; color: var(--gray-500); font-size: 0.875rem;">
                            ${createdAt.toLocaleDateString()} ${createdAt.toLocaleTimeString()}
                        </div>
                    </div>
                    <div id="${expandedId}" style="
                        max-height: 0;
                        overflow: hidden;
                        transition: max-height 0.3s ease-out;
                        background: var(--gray-50);
                    ">
                        <div style="padding: 1.5rem;">
                            <!-- Expanded content will be loaded here -->
                        </div>
                    </div>
                </div>
            `;
        }).join('');

        container.innerHTML = batchesHTML;

    } catch (error) {
        console.error('[Dashboard] Error loading recent activity:', error);
        container.innerHTML = `
            <div style="text-align: center; padding: 3rem; color: var(--gray-500);">
                <p>Failed to load recent activity. Please try again.</p>
            </div>
        `;
    }
}

/**
 * Dismiss a document from the review queue
 */
window.dismissDocument = async function(docId) {
    if (!confirm('Are you sure you want to dismiss this document? It will be removed from your review queue.')) {
        return;
    }

    try {
        const response = await authenticatedFetch(`/api/documents/${docId}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            throw new Error('Failed to dismiss document');
        }

        // Refresh pending documents and stats
        await loadPendingDocuments();
        await loadStatsOverview();
        await loadRecentActivity();

        console.log(`[Dashboard] Document ${docId} dismissed successfully`);

    } catch (error) {
        console.error('[Dashboard] Error dismissing document:', error);
        alert('Failed to dismiss document: ' + error.message);
    }
};

/**
 * Load pending review documents
 */
async function loadPendingDocuments() {
    console.log('[Dashboard] Loading pending documents...');
    const section = document.getElementById('pendingReviewSection');
    const container = document.getElementById('pendingDocuments');
    const countBadge = document.getElementById('pendingCount');

    if (!section || !container) {
        console.warn('[Dashboard] Pending review section elements not found');
        return;
    }

    try {
        // Get pending documents
        console.log('[Dashboard] Fetching from /api/documents/pending...');
        const response = await authenticatedFetch('/api/documents/pending');
        if (!response.ok) {
            throw new Error('Failed to load pending documents');
        }

        const data = await response.json();
        const documents = data.documents || [];

        console.log(`[Dashboard] Received ${documents.length} pending documents:`, documents);

        if (documents.length === 0) {
            // Hide section if no pending documents
            console.log('[Dashboard] No pending documents, hiding section');
            section.style.display = 'none';
            return;
        }

        // Show section and update count
        section.style.display = 'block';
        countBadge.textContent = documents.length;

        // Render documents
        const documentsHTML = documents.map(doc => {
            const createdAt = new Date(doc.created_at);
            const confidence = Math.round((doc.confidence_score || 0) * 100);

            // Confidence badge styling
            let confidenceClass = 'confidence-high';
            let confidenceIcon = 'fa-check-circle';
            if (confidence < 90) {
                confidenceClass = confidence >= 70 ? 'confidence-medium' : 'confidence-low';
                confidenceIcon = confidence >= 70 ? 'fa-exclamation-triangle' : 'fa-times-circle';
            }

            return `
                <div style="
                    border: 1px solid var(--gray-200);
                    border-radius: var(--radius-lg);
                    padding: 1.25rem;
                    margin-bottom: 1rem;
                    transition: all 0.2s;
                    cursor: pointer;
                    background: white;
                " onmouseover="this.style.borderColor='#3b82f6'; this.style.background='#eff6ff';"
                   onmouseout="this.style.borderColor='var(--gray-200)'; this.style.background='white';"
                   onclick="window.location.href='/pdf-viewer.html?id=${doc.id}'">
                    <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 0.75rem;">
                        <div style="flex: 1;">
                            <div style="font-weight: 600; color: var(--gray-900); font-size: 1rem; margin-bottom: 0.25rem;">
                                <i class="fa-solid fa-file-pdf" style="color: #ef4444; margin-right: 0.5rem;"></i>
                                ${doc.filename}
                            </div>
                            <div style="font-size: 0.875rem; color: var(--gray-600);">
                                ${doc.category || 'Uncategorized'} • ${createdAt.toLocaleDateString()} ${createdAt.toLocaleTimeString()}
                            </div>
                        </div>
                        <div style="display: flex; align-items: center; gap: 0.75rem;">
                            <div class="${confidenceClass}" style="
                                padding: 0.375rem 0.75rem;
                                border-radius: 6px;
                                font-size: 0.85rem;
                                font-weight: 600;
                                white-space: nowrap;
                            ">
                                <i class="fa-solid ${confidenceIcon}"></i> ${confidence}%
                            </div>
                            <button onclick="event.stopPropagation(); window.location.href='pdf-viewer.html?id=${doc.id}'" style="
                                background: #3b82f6;
                                color: white;
                                border: none;
                                padding: 0.5rem 1rem;
                                border-radius: 6px;
                                font-weight: 600;
                                font-size: 0.875rem;
                                cursor: pointer;
                                transition: background 0.2s;
                            " onmouseover="this.style.background='#2563eb'" onmouseout="this.style.background='#3b82f6'">
                                Review
                                <i class="fa-solid fa-arrow-right" style="margin-left: 0.5rem;"></i>
                            </button>
                            <button onclick="event.stopPropagation(); dismissDocument(${doc.id})" style="
                                background: #ef4444;
                                color: white;
                                border: none;
                                padding: 0.5rem;
                                border-radius: 6px;
                                font-weight: 600;
                                font-size: 0.875rem;
                                cursor: pointer;
                                transition: background 0.2s;
                                width: 36px;
                                height: 36px;
                                display: flex;
                                align-items: center;
                                justify-content: center;
                            " onmouseover="this.style.background='#dc2626'" onmouseout="this.style.background='#ef4444'" title="Dismiss">
                                <i class="fa-solid fa-times"></i>
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

        container.innerHTML = documentsHTML;
        console.log('[Dashboard] Successfully rendered pending documents section');

    } catch (error) {
        console.error('[Dashboard] Error loading pending documents:', error);
        section.style.display = 'none';
    }
}

/**
 * Toggle batch details expansion
 */
window.toggleBatchDetails = async function(batchId) {
    const expandedSection = document.getElementById(`expanded-${batchId}`);
    const expandIcon = document.getElementById(`expand-icon-${batchId}`);

    if (!expandedSection) return;

    const isExpanded = expandedSection.style.maxHeight && expandedSection.style.maxHeight !== '0px';

    if (isExpanded) {
        // Collapse
        expandedSection.style.maxHeight = '0px';
        expandedSection.style.overflowY = 'hidden';
        if (expandIcon) expandIcon.style.transform = 'rotate(0deg)';
    } else {
        // Expand with scrollable content
        expandedSection.style.maxHeight = '80vh'; // 80% of viewport height
        expandedSection.style.overflowY = 'auto'; // Enable scrolling
        if (expandIcon) expandIcon.style.transform = 'rotate(180deg)';

        // Load batch details if not already loaded
        const content = expandedSection.querySelector('div');
        if (content && content.innerHTML.includes('<!-- Expanded content will be loaded here -->')) {
            await loadBatchDetails(batchId, content);
        }
    }
}

/**
 * Load and display batch details with document cards
 */
async function loadBatchDetails(batchId, containerElement) {
    console.log('[BatchDetails] Loading details for batch:', batchId);

    // Show loading state
    containerElement.innerHTML = `
        <div style="text-align: center; padding: 2rem;">
            <div class="spinner" style="margin: 0 auto 1rem;"></div>
            <p style="color: var(--gray-600);">Loading batch details...</p>
        </div>
    `;

    try {
        // Fetch batch status (which includes full results)
        const response = await authenticatedFetch(`${API_BASE}/status/${batchId}`);

        if (!response.ok) {
            throw new Error('Failed to fetch batch details');
        }

        const data = await response.json();
        console.log('[BatchDetails] Batch data:', data);

        // Render batch details similar to results view
        renderBatchDetailsView(data, containerElement);

    } catch (error) {
        console.error('[BatchDetails] Error loading batch details:', error);
        containerElement.innerHTML = `
            <div style="text-align: center; padding: 2rem; color: var(--gray-500);">
                <p>Failed to load batch details. Please try again.</p>
            </div>
        `;
    }
}

/**
 * Render batch details with document cards
 */
function renderBatchDetailsView(data, containerElement) {
    // Build summary stats
    const summaryHTML = `
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem; margin-bottom: 1.5rem;">
            <div style="background: white; padding: 1rem; border-radius: 0.5rem; border: 1px solid var(--gray-200);">
                <div style="font-size: 0.75rem; color: var(--gray-600); margin-bottom: 0.25rem;">Processed</div>
                <div style="font-size: 1.5rem; font-weight: 700; color: #10b981;">${data.successful}</div>
            </div>
            <div style="background: white; padding: 1rem; border-radius: 0.5rem; border: 1px solid var(--gray-200);">
                <div style="font-size: 0.75rem; color: var(--gray-600); margin-bottom: 0.25rem;">Failed</div>
                <div style="font-size: 1.5rem; font-weight: 700; color: ${data.failed > 0 ? '#ef4444' : 'var(--gray-400)'};">${data.failed}</div>
            </div>
            <div style="background: white; padding: 1rem; border-radius: 0.5rem; border: 1px solid var(--gray-200);">
                <div style="font-size: 0.75rem; color: var(--gray-600); margin-bottom: 0.25rem;">Categories</div>
                <div style="font-size: 1.5rem; font-weight: 700; color: var(--gray-900);">${Object.keys(data.processing_summary || {}).length}</div>
            </div>
        </div>
    `;

    // Group results by category
    const byCategory = {};
    if (data.results && data.results.length > 0) {
        data.results.forEach(result => {
            if (!result.error) {
                if (!byCategory[result.category]) {
                    byCategory[result.category] = [];
                }
                byCategory[result.category].push(result);
            }
        });
    }

    // Build document cards grouped by category
    const documentsHTML = Object.keys(byCategory)
        .sort()
        .map(category => `
            <div style="margin-bottom: 1.5rem;">
                <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem;">
                    <span style="font-size: 1.5rem;">${getCategoryIcon(category)}</span>
                    <span style="font-size: 1.125rem; font-weight: 600; color: var(--gray-900);">${category}</span>
                    <span style="
                        padding: 0.25rem 0.75rem;
                        background: var(--gray-100);
                        color: var(--gray-700);
                        border-radius: 1rem;
                        font-size: 0.75rem;
                        font-weight: 600;
                    ">${byCategory[category].length}</span>
                </div>
                <div style="display: grid; gap: 1rem;">
                    ${byCategory[category].map((doc, index) => {
                        const docId = `batch-doc-${data.batch_id}-${category.replace(/\s+/g, '-')}-${index}`;
                        return renderDocumentCard(doc, docId);
                    }).join('')}
                </div>
            </div>
        `).join('');

    // Show failed documents if any
    const failedDocs = (data.results || []).filter(r => r.error);
    const failedHTML = failedDocs.length > 0 ? `
        <div style="margin-top: 1.5rem; padding: 1rem; background: #fee2e2; border-radius: 0.5rem; border: 1px solid #fca5a5;">
            <div style="font-weight: 600; color: #dc2626; margin-bottom: 0.75rem;">
                Failed Documents (${failedDocs.length})
            </div>
            ${failedDocs.map(doc => `
                <div style="display: flex; justify-content: space-between; padding: 0.5rem 0; border-bottom: 1px solid #fca5a5;">
                    <span style="color: var(--gray-900);">${doc.filename}</span>
                    <span style="color: #dc2626; font-size: 0.875rem;">${doc.error}</span>
                </div>
            `).join('')}
        </div>
    ` : '';

    // Download button if available
    const downloadHTML = data.download_url ? `
        <div style="margin-top: 1.5rem; text-align: center;">
            <a href="${data.download_url}" class="btn btn-primary" style="
                display: inline-flex;
                align-items: center;
                gap: 0.5rem;
                padding: 0.75rem 1.5rem;
                background: #0066cc;
                color: white;
                border-radius: 0.5rem;
                text-decoration: none;
                font-weight: 600;
            ">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M10 5V2H6v3H3l5 5 5-5h-3zM2 13h12v2H2v-2z"/>
                </svg>
                Download Organized Documents
            </a>
        </div>
    ` : '';

    containerElement.innerHTML = summaryHTML + documentsHTML + failedHTML + downloadHTML;

    console.log(`[BatchDetails] Rendered ${Object.keys(byCategory).length} categories with cards in expanded state by default`);
}

// ============================================================================
// Initialization
// ============================================================================
