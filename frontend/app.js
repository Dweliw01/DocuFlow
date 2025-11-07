/**
 * Frontend JavaScript for Document Digitization Service
 * Handles file uploads, progress tracking, and results display
 */

// API configuration
const API_BASE = '/api';

// Application state
let selectedFiles = [];
let currentBatchId = null;

// DOM Elements
const uploadSection = document.getElementById('uploadSection');
const uploadBox = document.getElementById('uploadBox');
const fileInput = document.getElementById('fileInput');
const browseBtn = document.getElementById('browseBtn');
const fileList = document.getElementById('fileList');
const uploadControls = document.getElementById('uploadControls');
const uploadBtn = document.getElementById('uploadBtn');
const clearBtn = document.getElementById('clearBtn');
const processingSection = document.getElementById('processingSection');
const progressFill = document.getElementById('progressFill');
const processingStatus = document.getElementById('processingStatus');
const processingDetails = document.getElementById('processingDetails');
const resultsSection = document.getElementById('resultsSection');
const resultsSummary = document.getElementById('resultsSummary');
const resultsDetails = document.getElementById('resultsDetails');
const downloadBtn = document.getElementById('downloadBtn');
const newBatchBtn = document.getElementById('newBatchBtn');

// ============================================================================
// Event Listeners
// ============================================================================

browseBtn.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', handleFileSelect);
uploadBox.addEventListener('click', (e) => {
    // Don't trigger if clicking the button
    if (e.target !== browseBtn) {
        fileInput.click();
    }
});
uploadBox.addEventListener('dragover', handleDragOver);
uploadBox.addEventListener('dragleave', handleDragLeave);
uploadBox.addEventListener('drop', handleDrop);
uploadBtn.addEventListener('click', uploadDocuments);
clearBtn.addEventListener('click', clearFiles);
downloadBtn.addEventListener('click', downloadResults);
newBatchBtn.addEventListener('click', resetApp);

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
    if (selectedFiles.length === 0) return;

    // Show processing section
    uploadSection.classList.add('hidden');
    processingSection.classList.remove('hidden');

    try {
        // Create FormData with files
        const formData = new FormData();
        selectedFiles.forEach(file => {
            formData.append('files', file);
        });

        // Upload files
        processingStatus.textContent = 'Uploading files...';
        progressFill.style.width = '10%';

        const response = await fetch(`${API_BASE}/upload`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Upload failed');
        }

        const data = await response.json();
        currentBatchId = data.batch_id;

        processingStatus.textContent = 'Upload complete! Processing documents...';
        progressFill.style.width = '20%';

        // Poll for results
        await pollBatchStatus();

    } catch (error) {
        console.error('Upload error:', error);
        alert('Upload failed: ' + error.message);
        resetApp();
    }
}

async function pollBatchStatus() {
    const pollInterval = 500; // Poll every 0.5 seconds for faster updates
    let lastProcessedCount = 0;

    // Add initial message
    addProcessingLog(`🚀 Starting batch processing: ${selectedFiles.length} files`, 'info');

    while (true) {
        try {
            const response = await fetch(`${API_BASE}/status/${currentBatchId}`);

            if (!response.ok) {
                throw new Error('Failed to fetch status');
            }

            const data = await response.json();

            // Debug: Log what we're receiving
            console.log('Status update:', {
                processed: data.processed_files,
                total: data.total_files,
                lastProcessed: lastProcessedCount,
                resultsLength: data.results ? data.results.length : 0,
                status: data.status
            });

            // Update progress bar (20% reserved for upload, 70% for processing, 10% for organizing)
            const processingProgress = (data.processed_files / data.total_files) * 70;
            const totalProgress = 20 + processingProgress;
            progressFill.style.width = totalProgress + '%';

            // Update status text
            processingStatus.textContent = `Processing: ${data.processed_files} of ${data.total_files} documents...`;

            // Show newly processed files as console output
            if (data.results && data.results.length > lastProcessedCount) {
                console.log('✨ New results found!', data.results.length - lastProcessedCount);
                const newResults = data.results.slice(lastProcessedCount);
                console.log('New results array:', newResults);
                newResults.forEach(result => {
                    if (result.error) {
                        addProcessingLog(`❌ ${result.filename} - Error: ${result.error}`, 'error');
                    } else {
                        addProcessingLog(`✓ ${result.filename} → ${result.category} (confidence: ${(result.confidence * 100).toFixed(0)}%, time: ${result.processing_time.toFixed(2)}s)`, 'success');
                    }
                });
                lastProcessedCount = data.results.length;
                console.log(`Updated lastProcessedCount to: ${lastProcessedCount}`);
            } else {
                console.log('No new results. lastProcessedCount:', lastProcessedCount, 'results length:', data.results ? data.results.length : 0);
            }

            // Check if completed
            if (data.status === 'completed') {
                addProcessingLog('📦 Organizing files and creating ZIP...', 'info');
                processingStatus.textContent = 'Organizing files and creating ZIP...';
                progressFill.style.width = '100%';

                // Small delay to show 100% progress
                await new Promise(resolve => setTimeout(resolve, 500));

                addProcessingLog('✅ Processing complete!', 'success');
                showResults(data);
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
    console.log(`[addProcessingLog] ${type.toUpperCase()}: ${message}`);

    const logEntry = document.createElement('div');
    logEntry.className = `log-entry log-${type}`;
    logEntry.textContent = message;

    processingDetails.appendChild(logEntry);
    console.log(`[addProcessingLog] Total logs now: ${processingDetails.children.length}`);

    // Auto-scroll to bottom
    processingDetails.scrollTop = processingDetails.scrollHeight;
}

// ============================================================================
// Results Display
// ============================================================================

function showResults(data) {
    // Hide processing, show results
    processingSection.classList.add('hidden');
    resultsSection.classList.remove('hidden');

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
}

function getConfidenceClass(confidence) {
    if (confidence >= 0.8) return 'confidence-high';
    if (confidence >= 0.5) return 'confidence-medium';
    return 'confidence-low';
}

function getCategoryIcon(category) {
    const icons = {
        'Invoice': '📄',
        'Receipt': '🧾',
        'Contract': '📝',
        'Legal Document': '⚖️',
        'HR Document': '👥',
        'Tax Document': '💰',
        'Financial Statement': '📊',
        'Correspondence': '✉️',
        'Other': '📋'
    };
    return icons[category] || '📄';
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
                    <span class="doc-filename">📄 ${doc.filename}</span>
                </div>
                <span class="confidence-badge ${getConfidenceClass(doc.confidence)}">
                    ${(doc.confidence * 100).toFixed(0)}%
                </span>
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

    // Build key-value pairs
    const sections = [];

    // Primary info (most important)
    const primaryInfo = [];
    if (data.amount) primaryInfo.push({ icon: '💵', label: 'Amount', value: data.amount, primary: true });
    if (data.date) primaryInfo.push({ icon: '📅', label: 'Date', value: data.date });
    if (data.due_date) primaryInfo.push({ icon: '⏰', label: 'Due Date', value: data.due_date });

    if (primaryInfo.length > 0) {
        sections.push({ title: 'Financial Details', items: primaryInfo });
    }

    // Parties
    const parties = [];
    if (data.vendor) parties.push({ icon: '🏢', label: 'Vendor', value: data.vendor });
    if (data.client) parties.push({ icon: '👤', label: 'Client', value: data.client });
    if (data.person_name) parties.push({ icon: '👤', label: 'Contact', value: data.person_name });
    if (data.company) parties.push({ icon: '🏢', label: 'Company', value: data.company });

    if (parties.length > 0) {
        sections.push({ title: 'Parties', items: parties });
    }

    // Document details
    const docDetails = [];
    if (data.document_type) docDetails.push({ icon: '📋', label: 'Type', value: data.document_type });
    if (data.document_number) docDetails.push({ icon: '#️⃣', label: 'Number', value: data.document_number });
    if (data.reference_number) docDetails.push({ icon: '🔗', label: 'Reference', value: data.reference_number });

    if (docDetails.length > 0) {
        sections.push({ title: 'Document Info', items: docDetails });
    }

    // Contact
    const contact = [];
    if (data.phone) contact.push({ icon: '📞', label: 'Phone', value: data.phone });
    if (data.email) contact.push({ icon: '📧', label: 'Email', value: data.email });
    if (data.address) contact.push({ icon: '📍', label: 'Address', value: data.address });

    if (contact.length > 0) {
        sections.push({ title: 'Contact', items: contact });
    }

    return `
        <div class="doc-card-body" id="data-${docId}">
            ${sections.map(section => `
                <div class="data-section-card">
                    <div class="data-section-header">${section.title}</div>
                    <div class="data-items">
                        ${section.items.map(item => `
                            <div class="data-item ${item.primary ? 'primary' : ''}">
                                <span class="data-icon">${item.icon}</span>
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
                    <div class="data-section-header">📋 Line Items (${data.line_items.length})</div>
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
            ${data.other_data && Object.keys(data.other_data).length > 0 ? `
                <div class="data-section-card">
                    <div class="data-section-header">Additional Details</div>
                    <div class="data-items-compact">
                        ${Object.entries(data.other_data).slice(0, 5).map(([key, value]) => `
                            <div class="data-item-compact">
                                <span class="data-label-compact">${key.replace(/_/g, ' ')}:</span>
                                <span class="data-value-compact">${value}</span>
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
    // Reset state
    selectedFiles = [];
    currentBatchId = null;
    fileInput.value = '';

    // Reset UI
    uploadSection.classList.remove('hidden');
    processingSection.classList.add('hidden');
    resultsSection.classList.add('hidden');

    renderFileList();
    progressFill.style.width = '0%';
    processingDetails.innerHTML = '';
}

// ============================================================================
// Initialization
// ============================================================================

console.log('Document Digitization Service initialized');
console.log('Ready to process documents!');
