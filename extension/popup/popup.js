// ============================================
// Obscura - Improved Popup (popup.js)
// ============================================

// DOM Elements
const textInput = document.getElementById('textInput');
const charCount = document.getElementById('charCount');
const detectBtn = document.getElementById('detectBtn');
const anonymizeBtn = document.getElementById('anonymizeBtn');
const results = document.getElementById('results');
const resultsContent = document.getElementById('resultsContent');
const copyBtn = document.getElementById('copyBtn');
const loading = document.getElementById('loading');
const error = document.getElementById('error');
const statusDot = document.getElementById('statusDot');
const footerStatus = document.getElementById('footerStatus');
const sidePanelBtn = document.getElementById('sidePanelBtn');
const settingsBtn = document.getElementById('settingsBtn');
const statusMessage = document.getElementById('statusMessage');

// State
let currentResults = null;
let isConnected = false;
let connectionCheckTimeout = null;

// Enhanced Regex Patterns for Better Detection
const DETECTION_PATTERNS = {
    // Phone numbers (multiple formats)
    phone: [
        /\b(?:\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})\b/g,
        /\b(?:\+?91[-.\s]?)?[6-9]\d{9}\b/g, // India
        /\b(?:\+?44[-.\s]?)?(?:7\d{9}|20\d{8})\b/g, // UK
    ],

    // Email addresses
    email: /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/g,

    // Social Security Numbers (XXX-XX-XXXX)
    ssn: /\b(?!000|666|9\d{2})\d{3}-\d{2}-\d{4}\b/g,

    // Credit card numbers (16 digits, various formats)
    creditCard: /\b(?:\d{4}[-\s]?){3}\d{4}\b|\b\d{16}\b/g,

    // Dates (DD/MM/YYYY, MM/DD/YYYY, YYYY-MM-DD, etc.)
    date: [
        /\b(0?[1-9]|[12][0-9]|3[01])[\/\-\.]([01]?[0-9])[\/\-\.](19|20)?\d{2}\b/g, // DD/MM/YYYY or MM/DD/YYYY
        /\b(19|20)\d{2}[-\/\.](0?[1-9]|1[0-2])[-\/\.](0?[1-9]|[12][0-9]|3[01])\b/g, // YYYY-MM-DD
        /\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]?\s+\d{1,2},?\s+(19|20)\d{2}\b/gi, // Month DD, YYYY
    ],

    // Credit card keywords
    creditCardKeywords: /credit\s*card|visa|mastercard|amex|american\s*express|debit\s*card|card\s*number/gi,

    // Bank account numbers (5-17 digits)
    bankAccount: /\b\d{5,17}\b(?=\s*(account|acc\s*#|account\s*number))/gi,

    // IBAN (International Bank Account Number)
    iban: /\b[A-Z]{2}[0-9]{2}[A-Z0-9]{1,30}\b/g,

    // Passport numbers
    passport: /\b[A-Z]{1,2}\d{6,9}\b/g,

    // Driver license (US format)
    driverLicense: /\b[A-Z]\d{5,8}\b/g,

    // IP addresses
    ipAddress: /\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b/g,

    // URLs and websites
    url: /https?:\/\/(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&\/=]*)/g,

    // Names (common pattern - capitalized words)
    name: /\b(?:Mr|Mrs|Ms|Dr|Prof)\.\s+[A-Z][a-z]+\s+[A-Z][a-z]+\b/g,

    // Address patterns (street address format)
    address: /\b\d+\s+[A-Z][a-z]+\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct)\b/g,

    // ZIP codes (US format)
    zipCode: /\b\d{5}(?:-\d{4})?\b/g,

    // Medical record number
    medicalRecord: /(?:MRN|patient\s*id|medical\s*record)[\s:]*\d{5,10}/gi,

    // PAN (India - Permanent Account Number)
    pan: /\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b/g,

    // Aadhaar (India - 12 digit)
    aadhaar: /\b\d{4}\s*\d{4}\s*\d{4}\b/g,

    // MAC address
    macAddress: /\b(?:[0-9A-Fa-f]{2}[:-]){5}(?:[0-9A-Fa-f]{2})\b/g,
};

// Initialize
document.addEventListener('DOMContentLoaded', init);

function init() {
    console.log('✓ Obscura popup initialized');

    // Event listeners
    if (textInput) textInput.addEventListener('input', updateCharCount);
    if (detectBtn) detectBtn.addEventListener('click', () => detect('detect'));
    if (anonymizeBtn) anonymizeBtn.addEventListener('click', () => detect('anonymize'));
    if (copyBtn) copyBtn.addEventListener('click', copyResults);
    if (sidePanelBtn) sidePanelBtn.addEventListener('click', openSidePanel);
    if (settingsBtn) settingsBtn.addEventListener('click', openSettings);

    // Initial connection check
    checkConnection();

    // Check connection every 5 seconds
    if (connectionCheckTimeout) clearInterval(connectionCheckTimeout);
    connectionCheckTimeout = setInterval(checkConnection, 5000);

    console.log('[INIT] All event listeners attached');
}

// Update character count
function updateCharCount() {
    if (!textInput || !charCount) return;

    const length = textInput.value.length;
    charCount.textContent = length;

    if (length > 10000) {
        charCount.style.color = '#ef4444';
    } else if (length > 5000) {
        charCount.style.color = '#f97316';
    } else {
        charCount.style.color = '#999';
    }
}

// Open side panel
function openSidePanel() {
    chrome.sidePanel.open({ windowId: chrome.windows.WINDOW_ID_CURRENT });
}

// Open settings
function openSettings(e) {
    if (e) e.preventDefault();
    chrome.runtime.openOptionsPage();
}

// Connection check
function checkConnection() {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000);

    fetch('http://localhost:5001/api/health', {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal
    })
        .then(response => {
            clearTimeout(timeoutId);
            if (response.ok) {
                setConnected(true);
            } else {
                setConnected(false);
            }
        })
        .catch(error => {
            clearTimeout(timeoutId);
            setConnected(false);
        });
}

// Set connection status
function setConnected(connected) {
    isConnected = connected;

    if (connected) {
        if (statusDot) statusDot.classList.remove('offline');
        if (footerStatus) footerStatus.textContent = '✓ Connected to desktop app';
        if (detectBtn) detectBtn.disabled = false;
        if (anonymizeBtn) anonymizeBtn.disabled = false;
    } else {
        if (statusDot) statusDot.classList.add('offline');
        if (footerStatus) footerStatus.textContent = '✗ Desktop app offline';
        if (detectBtn) detectBtn.disabled = true;
        if (anonymizeBtn) anonymizeBtn.disabled = true;
    }
}

// Enhanced local detection (regex-based backup)
function detectLocalPII(text) {
    const entities = [];
    const detectedTypes = new Set();

    // Check phone numbers
    for (const pattern of DETECTION_PATTERNS.phone) {
        let match;
        while ((match = pattern.exec(text)) !== null) {
            entities.push({
                text: match[0],
                label: 'phone',
                start: match.index,
                end: match.index + match[0].length,
                score: 0.95
            });
            detectedTypes.add('phone');
        }
    }

    // Check emails
    let match;
    while ((match = DETECTION_PATTERNS.email.exec(text)) !== null) {
        entities.push({
            text: match[0],
            label: 'email',
            start: match.index,
            end: match.index + match[0].length,
            score: 0.98
        });
        detectedTypes.add('email');
    }

    // Check SSN
    while ((match = DETECTION_PATTERNS.ssn.exec(text)) !== null) {
        entities.push({
            text: match[0],
            label: 'ssn',
            start: match.index,
            end: match.index + match[0].length,
            score: 0.99
        });
        detectedTypes.add('ssn');
    }

    // Check credit cards
    while ((match = DETECTION_PATTERNS.creditCard.exec(text)) !== null) {
        entities.push({
            text: match[0],
            label: 'credit card',
            start: match.index,
            end: match.index + match[0].length,
            score: 0.97
        });
        detectedTypes.add('credit card');
    }

    // Check dates
    for (const pattern of DETECTION_PATTERNS.date) {
        pattern.lastIndex = 0; // Reset regex
        while ((match = pattern.exec(text)) !== null) {
            entities.push({
                text: match[0],
                label: 'date',
                start: match.index,
                end: match.index + match[0].length,
                score: 0.85
            });
            detectedTypes.add('date');
        }
    }

    // Check IP addresses
    while ((match = DETECTION_PATTERNS.ipAddress.exec(text)) !== null) {
        entities.push({
            text: match[0],
            label: 'ip address',
            start: match.index,
            end: match.index + match[0].length,
            score: 0.92
        });
        detectedTypes.add('ip address');
    }

    // Check IBAN
    while ((match = DETECTION_PATTERNS.iban.exec(text)) !== null) {
        entities.push({
            text: match[0],
            label: 'iban',
            start: match.index,
            end: match.index + match[0].length,
            score: 0.90
        });
        detectedTypes.add('iban');
    }

    // Check PAN (India)
    while ((match = DETECTION_PATTERNS.pan.exec(text)) !== null) {
        entities.push({
            text: match[0],
            label: 'pan',
            start: match.index,
            end: match.index + match[0].length,
            score: 0.93
        });
        detectedTypes.add('pan');
    }

    // Check Aadhaar (India)
    while ((match = DETECTION_PATTERNS.aadhaar.exec(text)) !== null) {
        entities.push({
            text: match[0],
            label: 'aadhaar',
            start: match.index,
            end: match.index + match[0].length,
            score: 0.91
        });
        detectedTypes.add('aadhaar');
    }

    // Check MAC address
    while ((match = DETECTION_PATTERNS.macAddress.exec(text)) !== null) {
        entities.push({
            text: match[0],
            label: 'mac address',
            start: match.index,
            end: match.index + match[0].length,
            score: 0.89
        });
        detectedTypes.add('mac address');
    }

    // Remove duplicates
    const uniqueEntities = [];
    const seen = new Set();

    entities.forEach(entity => {
        const key = `${entity.start}-${entity.end}`;
        if (!seen.has(key)) {
            seen.add(key);
            uniqueEntities.push(entity);
        }
    });

    return {
        status: 'success',
        entities: uniqueEntities.sort((a, b) => a.start - b.start),
        detectedTypes: Array.from(detectedTypes),
        source: 'local'
    };
}

// Main detection function
function detect(action) {
    if (!textInput) return;

    const text = textInput.value.trim();
    console.log(`[DETECT] Starting ${action} with ${text.length} chars`);

    if (!text) {
        showError('Please enter some text to analyze');
        return;
    }

    if (text.length < 3) {
        showError('Text is too short for accurate detection');
        return;
    }

    if (text.length > 50000) {
        showError('Text is too long (max 50,000 characters)');
        return;
    }

    showLoading(true);
    hideError();
    hideResults();

    // Use local detection if desktop app is offline
    if (!isConnected) {
        console.log('[DETECT] Desktop app offline, using local detection');
        const localResults = detectLocalPII(text);

        if (action === 'anonymize') {
            displayAnonymized(localResults, text);
        } else {
            displayDetection(localResults);
        }

        showLoading(false);
        return;
    }

    // Try desktop app first
    const startTime = Date.now();

    fetch('http://localhost:5001/api/detect-pii', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            text: text,
            labels: ['all'],
            threshold: 0.2,
            action: action,
            context_aware: true,
            semantic_analysis: true,
            detect_templates: true,
            multi_stage: true,
            normalize_text: true,
            config: {
                max_entities: 5000,
                entity_context_length: 100,
                merge_overlapping: true,
                score_normalization: true,
                aggressive_detection: true
            }
        })
    })
        .then(response => {
            const time = Date.now() - startTime;
            console.log(`[DETECT] Response received in ${time}ms, status: ${response.status}`);

            if (!response.ok) {
                throw new Error(`Server error: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            const processingTime = Date.now() - startTime;
            console.log(`[DETECT] ✅ Success in ${processingTime}ms`);

            if (data.status === 'success') {
                currentResults = data;

                // Save to history
                if (data.entities && data.entities.length > 0) {
                    chrome.runtime.sendMessage({
                        action: 'saveToHistory',
                        text: text.substring(0, 100),
                        entitiesCount: data.entities.length,
                        preset: 'all'
                    }).catch(err => console.log('History save error:', err));
                }

                if (action === 'anonymize') {
                    displayAnonymized(data, text);
                } else {
                    displayDetection(data);
                }
            } else {
                throw new Error(data.error || 'Processing failed');
            }
        })
        .catch(error => {
            console.error('[DETECT] Error:', error.message);
            // Fallback to local detection
            const localResults = detectLocalPII(text);
            if (action === 'anonymize') {
                displayAnonymized(localResults, text);
            } else {
                displayDetection(localResults);
            }
        })
        .finally(() => {
            showLoading(false);
        });
}

// Display detection results
function displayDetection(data) {
    if (!resultsContent) return;

    if (!data.entities || data.entities.length === 0) {
        resultsContent.innerHTML = '<div style="text-align: center; padding: 10px; color: #22c55e;">✅ No PII detected</div>';
        showResults();
        return;
    }

    // Group by entity type
    const byType = {};
    data.entities.forEach(entity => {
        const label = entity.label || 'unknown';
        if (!byType[label]) byType[label] = [];
        byType[label].push(entity);
    });

    resultsContent.innerHTML = '';

    // Sort by type
    const sortedLabels = Object.keys(byType).sort();

    sortedLabels.forEach(label => {
        const entities = byType[label];
        const riskLevel = getRiskLevel(label);

        const typeDiv = document.createElement('div');
        typeDiv.style.marginBottom = '10px';

        const typeLabel = document.createElement('div');
        typeLabel.style.cssText = 'font-weight: 600; color: #166534; font-size: 11px; margin-bottom: 6px; text-transform: uppercase;';
        typeLabel.textContent = `${label} (${entities.length}) ${riskLevel}`;
        typeDiv.appendChild(typeLabel);

        entities.slice(0, 5).forEach(entity => {
            const item = document.createElement('div');
            item.className = 'result-item';
            item.innerHTML = `<strong>${label}:</strong> ${escapeHtml(entity.text || '(empty)')}`;
            typeDiv.appendChild(item);
        });

        if (entities.length > 5) {
            const more = document.createElement('div');
            more.style.cssText = 'font-size: 11px; color: #666; font-style: italic; margin-top: 4px;';
            more.textContent = `... and ${entities.length - 5} more`;
            typeDiv.appendChild(more);
        }

        resultsContent.appendChild(typeDiv);
    });

    // Add summary
    const summary = document.createElement('div');
    summary.style.cssText = 'background: white; padding: 10px; border-radius: 6px; border-left: 3px solid #2563eb; font-size: 12px; color: #1e40af; margin-top: 10px;';
    summary.textContent = `Found ${data.entities.length} PII entities across ${sortedLabels.length} types`;
    resultsContent.appendChild(summary);

    showResults();
}

// Display anonymized text
function displayAnonymized(data, originalText) {
    if (!resultsContent) return;

    let anonymized = originalText;

    if (data.anonymized_text) {
        anonymized = data.anonymized_text;
    } else if (data.entities && data.entities.length > 0) {
        // Local anonymization
        const sortedEntities = [...data.entities].sort((a, b) => b.start - a.start);

        sortedEntities.forEach(entity => {
            const placeholder = `[${entity.label.toUpperCase().replace(/\s+/g, '_')}]`;
            anonymized = anonymized.substring(0, entity.start) + placeholder + anonymized.substring(entity.end);
        });
    }

    const div = document.createElement('div');
    div.style.cssText = 'background: white; padding: 12px; border-radius: 6px; font-family: monospace; white-space: pre-wrap; word-break: break-word; font-size: 12px; border: 1px solid #e5e7eb; line-height: 1.6; max-height: 300px; overflow-y: auto;';
    div.textContent = anonymized;

    resultsContent.innerHTML = '';
    resultsContent.appendChild(div);
    showResults();
}

// Get risk level
function getRiskLevel(label) {
    const high = ['ssn', 'credit card', 'passport', 'bank account', 'password', 'iban', 'pan', 'aadhaar'];
    const medium = ['email', 'phone', 'ip address', 'mac address'];

    const lower = label.toLowerCase();

    if (high.some(h => lower.includes(h))) return '🔴 HIGH';
    if (medium.some(m => lower.includes(m))) return '🟠 MEDIUM';
    return '🔵 LOW';
}

// Copy results
function copyResults() {
    if (!currentResults) {
        showError('No results to copy');
        return;
    }

    let text = 'PII DETECTED:\n\n';
    const byType = {};

    currentResults.entities.forEach(entity => {
        const label = entity.label || 'unknown';
        if (!byType[label]) byType[label] = [];
        byType[label].push(entity.text);
    });

    Object.entries(byType).forEach(([label, values]) => {
        text += `${label.toUpperCase()}: ${values.join(', ')}\n`;
    });

    navigator.clipboard.writeText(text).then(() => {
        if (!copyBtn) return;
        const originalText = copyBtn.textContent;
        copyBtn.textContent = '✓ Copied!';
        copyBtn.disabled = true;

        setTimeout(() => {
            copyBtn.textContent = originalText;
            copyBtn.disabled = false;
        }, 2000);
    }).catch(err => {
        showError('Failed to copy');
    });
}

// Escape HTML
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

// UI Helpers
function showResults() {
    if (results) results.classList.add('show');
}

function hideResults() {
    if (results) results.classList.remove('show');
}

function showLoading(show) {
    if (loading) loading.style.display = show ? 'block' : 'none';
}

function showError(message) {
    if (error) {
        error.textContent = message;
        error.classList.add('show');
    }
    console.error('[ERROR]', message);
}

function hideError() {
    if (error) error.classList.remove('show');
}

// Cleanup
window.addEventListener('beforeunload', () => {
    if (connectionCheckTimeout) {
        clearInterval(connectionCheckTimeout);
    }
});

console.log('✓ popup.js loaded successfully');