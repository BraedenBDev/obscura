// ============================================
// Obscura - Side Panel v4.5 (Debug Logging)
// ============================================

// ============================================
// DEBUG LOGGING SYSTEM
// ============================================

const DEBUG = false;  // Set to true for development

// Simple HTML sanitizer - allows only safe tags (strong, em, b, i)
function sanitizeHTML(str) {
    // First escape all HTML entities
    const escaped = str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    // Then restore allowed tags
    return escaped
        .replace(/&lt;(\/?(strong|em|b|i))&gt;/gi, '<$1>');
}

const LOG_LEVELS = {
    DEBUG: 0,
    INFO: 1,
    WARN: 2,
    ERROR: 3
};

let currentLogLevel = LOG_LEVELS.DEBUG;

function formatTimestamp() {
    const now = new Date();
    return now.toTimeString().split(' ')[0] + '.' + String(now.getMilliseconds()).padStart(3, '0');
}

function log(level, category, message, data = null) {
    if (!DEBUG) return;

    const levelNames = ['DEBUG', 'INFO', 'WARN', 'ERROR'];
    const levelColors = ['#888', '#2196f3', '#ff9800', '#f44336'];

    if (level < currentLogLevel) return;

    const timestamp = formatTimestamp();
    const prefix = `[${timestamp}] [${category}]`;

    const style = `color: ${levelColors[level]}; font-weight: ${level >= 2 ? 'bold' : 'normal'}`;

    if (data !== null) {
        console.log(`%c${prefix} ${levelNames[level]}: ${message}`, style, data);
    } else {
        console.log(`%c${prefix} ${levelNames[level]}: ${message}`, style);
    }
}

function logDebug(category, message, data = null) {
    log(LOG_LEVELS.DEBUG, category, message, data);
}

function logInfo(category, message, data = null) {
    log(LOG_LEVELS.INFO, category, message, data);
}

function logWarn(category, message, data = null) {
    log(LOG_LEVELS.WARN, category, message, data);
}

function logError(category, message, data = null) {
    log(LOG_LEVELS.ERROR, category, message, data);
}

// ============================================
// DOM ELEMENTS
// ============================================

logInfo('INIT', 'Side panel v4.5 starting...');

const textArea = document.getElementById('textArea');
const charCount = document.getElementById('charCount');
const stateLabel = document.getElementById('stateLabel');
const infoBox = document.getElementById('infoBox');
const statsBox = document.getElementById('statsBox');
const anonymizeBtn = document.getElementById('anonymizeBtn');
const restoreBtn = document.getElementById('restoreBtn');
const clearBtn = document.getElementById('clearBtn');
const copyIcon = document.getElementById('copyIcon');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const loading = document.getElementById('loading');

// Log DOM element status
logDebug('DOM', 'Element check:', {
    textArea: !!textArea,
    charCount: !!charCount,
    stateLabel: !!stateLabel,
    infoBox: !!infoBox,
    statsBox: !!statsBox,
    anonymizeBtn: !!anonymizeBtn,
    restoreBtn: !!restoreBtn,
    clearBtn: !!clearBtn,
    copyIcon: !!copyIcon,
    statusDot: !!statusDot,
    statusText: !!statusText,
    loading: !!loading
});

// ============================================
// STATE
// ============================================

let isConnected = false;
let connectionCheckInterval = null;
let connectionAttempts = 0;

let state = {
    mode: 'original',
    originalText: null,
    anonymizedText: null,
    replacementMap: {},
    session_id: null,
    entities: [],
    lastDetectionResults: null
};

logDebug('STATE', 'Initial state:', state);

// ============================================
// INITIALIZATION
// ============================================

document.addEventListener('DOMContentLoaded', init);

function init() {
    logInfo('INIT', 'DOMContentLoaded - initializing...');

    // Setup event listeners
    if (textArea) {
        textArea.addEventListener('input', updateCharCount);
        logDebug('INIT', 'textArea input listener attached');
    }

    if (anonymizeBtn) {
        anonymizeBtn.addEventListener('click', anonymize);
        logDebug('INIT', 'anonymizeBtn click listener attached');
    }

    if (restoreBtn) {
        restoreBtn.addEventListener('click', restore);
        logDebug('INIT', 'restoreBtn click listener attached');
    }

    if (clearBtn) {
        clearBtn.addEventListener('click', clear);
        logDebug('INIT', 'clearBtn click listener attached');
    }

    if (copyIcon) {
        copyIcon.addEventListener('click', copyText);
        logDebug('INIT', 'copyIcon click listener attached');
    }

    // Start connection checking
    logInfo('INIT', 'Starting connection check...');
    checkConnection();
    connectionCheckInterval = setInterval(checkConnection, 5000);
    logDebug('INIT', 'Connection check interval set: 5000ms');

    // Setup message listener
    chrome.runtime.onMessage.addListener(handleMessages);
    logDebug('INIT', 'Chrome runtime message listener attached');

    logInfo('INIT', 'Initialization complete');
}

// ============================================
// MESSAGE HANDLING
// ============================================

function handleMessages(request, sender, sendResponse) {
    logDebug('MESSAGE', 'Received message:', { action: request.action, sender: sender.id });

    if (request.action === 'sendToSidePanel') {
        logInfo('MESSAGE', `Received text from content script: ${request.text.length} chars`);
        if (textArea) {
            textArea.value = request.text;
            updateCharCount();
        }
    }
}

// ============================================
// CONNECTION MANAGEMENT
// ============================================

async function checkConnection() {
    connectionAttempts++;
    logDebug('CONNECTION', `Checking connection (attempt ${connectionAttempts})...`);

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => {
            logWarn('CONNECTION', 'Request timeout after 2000ms');
            controller.abort();
        }, 2000);

        const startTime = performance.now();

        const response = await fetch('http://localhost:5001/api/health', {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' },
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        const elapsed = Math.round(performance.now() - startTime);

        if (response.ok) {
            const data = await response.json();
            logInfo('CONNECTION', `Connected to desktop app (${elapsed}ms)`, data);
            setConnected(true);
        } else {
            logWarn('CONNECTION', `Server responded with status ${response.status}`);
            setConnected(false);
        }
    } catch (error) {
        logWarn('CONNECTION', `Connection failed: ${error.message}`);
        setConnected(false);
    }
}

function setConnected(connected) {
    const wasConnected = isConnected;
    isConnected = connected;

    if (wasConnected !== connected) {
        logInfo('CONNECTION', `Connection state changed: ${connected ? 'CONNECTED' : 'DISCONNECTED'}`);
    }

    if (statusDot) {
        statusDot.classList.toggle('offline', !connected);
    }

    if (statusText) {
        statusText.textContent = connected ? 'Connected to Desktop' : 'Local Mode (Offline)';
    }
}

// ============================================
// CHARACTER COUNT
// ============================================

function updateCharCount() {
    if (!textArea || !charCount) return;

    const length = textArea.value.length;
    const words = textArea.value.trim().split(/\s+/).filter(w => w).length;

    charCount.textContent = `${length} chars • ${words} words`;

    const hasText = length > 2;
    if (anonymizeBtn) {
        anonymizeBtn.disabled = !hasText;
    }

    logDebug('INPUT', `Text updated: ${length} chars, ${words} words`);
}

// ============================================
// LOCAL PII DETECTION (Fallback)
// ============================================

function normalizeLabel(label) {
    return label.toLowerCase().trim().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '');
}

function createRegex(pattern) {
    try {
        return new RegExp(pattern, 'g');
    } catch (e) {
        logError('REGEX', `Invalid pattern: ${pattern}`, e);
        return null;
    }
}

function detectLocalPII(text) {
    logInfo('LOCAL_DETECT', `Starting local PII detection on ${text.length} chars`);

    const entities = [];
    const occupiedRanges = [];

    function isOverlapping(start, end) {
        for (let i = 0; i < occupiedRanges.length; i++) {
            const range = occupiedRanges[i];
            if (start < range[1] && end > range[0]) {
                return true;
            }
        }
        return false;
    }

    function addEntity(match, label, start, score) {
        if (!match || match.length < 3) return;
        if (isOverlapping(start, start + match.length)) {
            logDebug('LOCAL_DETECT', `Skipping overlapping: ${label} "${match}"`);
            return;
        }

        entities.push({
            text: match,
            label: label,
            start: start,
            end: start + match.length,
            score: score
        });
        occupiedRanges.push([start, start + match.length]);
        logDebug('LOCAL_DETECT', `Found: ${label} "${match.substring(0, 20)}..." (score: ${score})`);
    }

    function extract(pattern, label, score) {
        const regex = createRegex(pattern);
        if (!regex) return;

        try {
            let match;
            while ((match = regex.exec(text)) !== null) {
                addEntity(match[0], label, match.index, score);
            }
        } catch (e) {
            logError('LOCAL_DETECT', `Error extracting ${label}:`, e);
        }
    }

    // Run pattern extraction
    logDebug('LOCAL_DETECT', 'Running pattern matching...');

    extract('[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}', 'email', 0.99);
    extract('\\b\\d{3}-\\d{2}-\\d{4}\\b', 'ssn', 0.99);
    extract('[A-Z]{2}\\d{2}\\s[A-Z0-9]{4}\\s[A-Z0-9]{4}\\s[A-Z0-9]{4}\\s[A-Z0-9]{2,4}', 'iban', 0.98);
    extract('\\+1\\s\\d{3}\\s\\d{3}\\s\\d{4}', 'phone', 0.98);
    extract('\\+1-\\d{3}-\\d{3}-\\d{4}', 'phone', 0.98);
    extract('\\+1\\(\\d{3}\\)\\s\\d{3}-\\d{4}', 'phone', 0.98);
    extract('\\(\\d{3}\\)\\s?\\d{3}-\\d{4}', 'phone', 0.95);
    extract('\\d{4}[\\s-]\\d{4}[\\s-]\\d{4}[\\s-]\\d{4}', 'credit_card', 0.97);
    extract('\\b(19|20)\\d{2}-(0[1-9]|1[0-2])-(0[1-9]|[12]\\d|3[01])\\b', 'date', 0.95);
    extract('\\b(0[1-9]|1[0-2])/(0[1-9]|[12]\\d|3[01])/\\d{4}\\b', 'date', 0.95);
    extract('\\b\\d{5}(-\\d{4})?\\b', 'zip_code', 0.90);
    extract('\\b[A-Z]{5}\\d{4}[A-Z]\\b', 'pan', 0.90);
    extract('\\b[A-Z]{4}0[A-Z0-9]{6}\\b', 'ifsc_code', 0.90);
    extract('\\b\\d{4}\\s\\d{4}\\s\\d{4}\\b', 'aadhaar', 0.90);
    extract('\\b[6-9]\\d{9}\\b', 'phone', 0.90);

    entities.sort((a, b) => a.start - b.start);

    logInfo('LOCAL_DETECT', `Detection complete: ${entities.length} entities found`);

    // Log entity summary
    const summary = {};
    entities.forEach(e => {
        summary[e.label] = (summary[e.label] || 0) + 1;
    });
    logDebug('LOCAL_DETECT', 'Entity summary:', summary);

    return {
        status: 'success',
        entities: entities,
        entity_count: entities.length
    };
}

// ============================================
// ANONYMIZATION
// ============================================

function createAnonymizedText(text, entities) {
    logDebug('ANON', `Creating anonymized text from ${entities.length} entities`);

    if (!entities || entities.length === 0) {
        logWarn('ANON', 'No entities to anonymize');
        return { anonymized: text, replacementMap: {} };
    }

    const replacementMap = {};
    const counter = {};

    const replacements = entities.map(entity => {
        const label = normalizeLabel(entity.label);
        counter[label] = (counter[label] || 0) + 1;
        const placeholder = '[' + label.toUpperCase() + '_' + counter[label] + ']';

        replacementMap[placeholder] = entity.text;

        return {
            start: entity.start,
            end: entity.end,
            placeholder: placeholder,
            original: entity.text
        };
    });

    // Sort by position descending for safe replacement
    replacements.sort((a, b) => b.end - a.end);

    let result = text;
    for (let i = 0; i < replacements.length; i++) {
        const rep = replacements[i];
        result = result.substring(0, rep.start) + rep.placeholder + result.substring(rep.end);
        logDebug('ANON', `Replaced: "${rep.original.substring(0, 20)}..." -> ${rep.placeholder}`);
    }

    logInfo('ANON', `Anonymization complete: ${Object.keys(replacementMap).length} replacements`);
    logDebug('ANON', 'Replacement map:', replacementMap);

    return {
        anonymized: result,
        replacementMap: replacementMap
    };
}

async function anonymize() {
    logInfo('ANONYMIZE', '=== Anonymize button clicked ===');

    const text = textArea.value.trim();
    if (!text) {
        logWarn('ANONYMIZE', 'No text to anonymize');
        return;
    }

    state.originalText = text;
    logDebug('ANONYMIZE', `Processing ${text.length} characters`);

    showLoading(true);
    updateInfo('Anonymizing...', false);

    try {
        let data = null;

        // Try API first
        if (isConnected) {
            logInfo('ANONYMIZE', 'Attempting API anonymization...');
            try {
                const startTime = performance.now();

                const response = await fetch('http://localhost:5001/api/detect-pii', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        text: text,
                        action: 'anonymize',
                        create_session: true
                    })
                });

                const elapsed = Math.round(performance.now() - startTime);
                logDebug('ANONYMIZE', `API response received in ${elapsed}ms, status: ${response.status}`);

                if (response.ok) {
                    data = await response.json();
                    logInfo('ANONYMIZE', 'API anonymization successful:', {
                        entity_count: data.entity_count,
                        session_id: data.session_id,
                        has_anonymized_text: !!data.anonymized_text
                    });
                } else {
                    const errorText = await response.text();
                    logWarn('ANONYMIZE', `API error ${response.status}: ${errorText}`);
                }
            } catch (err) {
                logWarn('ANONYMIZE', `API request failed: ${err.message}`);
            }
        } else {
            logInfo('ANONYMIZE', 'Not connected - using local detection');
        }

        // Fallback to local detection
        if (!data || !data.anonymized_text) {
            logInfo('ANONYMIZE', 'Using local PII detection fallback');

            const detectionResult = detectLocalPII(text);
            const anonResult = createAnonymizedText(text, detectionResult.entities);

            data = {
                anonymized_text: anonResult.anonymized,
                replacement_map: anonResult.replacementMap,
                entities: detectionResult.entities,
                entity_count: detectionResult.entities.length,
                session_id: null  // No session for local processing
            };

            logDebug('ANONYMIZE', 'Local processing result:', {
                entity_count: data.entity_count,
                replacement_count: Object.keys(data.replacement_map).length
            });
        }

        // Update state
        state.anonymizedText = data.anonymized_text;
        state.replacementMap = data.replacement_map || {};
        state.session_id = data.session_id || null;
        state.entities = data.entities || [];
        state.mode = 'anonymized';

        logDebug('ANONYMIZE', 'State updated:', {
            mode: state.mode,
            session_id: state.session_id,
            replacement_count: Object.keys(state.replacementMap).length
        });

        // Update UI
        textArea.value = state.anonymizedText;
        textArea.classList.add('anonymized');
        stateLabel.textContent = '🔒 Anonymized';
        stateLabel.classList.add('anonymized');

        restoreBtn.classList.add('show');
        anonymizeBtn.disabled = true;

        const count = Object.keys(state.replacementMap).length;
        updateStats(`Anonymized ${count} placeholders`, true);
        updateInfo('Text anonymized! Copy this to use in ChatGPT/Claude. Click Restore when you paste LLM output.', false);

        logInfo('ANONYMIZE', `=== Anonymization complete: ${count} placeholders ===`);

    } catch (error) {
        logError('ANONYMIZE', 'Anonymization failed:', error);
        updateInfo('Anonymization failed: ' + error.message, true);
    } finally {
        showLoading(false);
    }
}

// ============================================
// RESTORATION
// ============================================

function localRestore(text, replacementMap) {
    logInfo('LOCAL_RESTORE', `Restoring ${Object.keys(replacementMap).length} placeholders`);

    let result = text;
    let restored = 0;
    const total = Object.keys(replacementMap).length;

    const sorted = Object.entries(replacementMap).sort((a, b) => b[0].length - a[0].length);

    for (let i = 0; i < sorted.length; i++) {
        const placeholder = sorted[i][0];
        const original = sorted[i][1];
        const escapedPlaceholder = placeholder.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const regex = new RegExp(escapedPlaceholder, 'gi');

        const matches = result.match(regex) || [];
        if (matches.length > 0) {
            result = result.replace(regex, original);
            restored += matches.length;
            logDebug('LOCAL_RESTORE', `Restored: ${placeholder} -> "${original.substring(0, 20)}..." (${matches.length}x)`);
        } else {
            logDebug('LOCAL_RESTORE', `Not found: ${placeholder}`);
        }
    }

    logInfo('LOCAL_RESTORE', `Restoration complete: ${restored}/${total}`);

    return {
        text: result,
        stats: {
            total: total,
            restored: restored,
            notFound: total - restored
        }
    };
}

async function restore() {
    logInfo('RESTORE', '=== Restore button clicked ===');

    if (!state.replacementMap || Object.keys(state.replacementMap).length === 0) {
        logWarn('RESTORE', 'No replacement map available');
        updateInfo('No replacement map. Please anonymize first.', true);
        return;
    }

    const currentText = textArea.value.trim();
    logDebug('RESTORE', `Restoring text: ${currentText.length} chars`);
    logDebug('RESTORE', `Replacement map has ${Object.keys(state.replacementMap).length} entries`);

    showLoading(true);
    updateInfo('Restoring...', false);

    try {
        let restored = null;
        let stats = null;

        // Try API first
        if (isConnected && state.session_id) {
            logInfo('RESTORE', `Attempting API restoration with session: ${state.session_id}`);
            try {
                const startTime = performance.now();

                const response = await fetch('http://localhost:5001/api/restore-llm', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        session_id: state.session_id,
                        llm_output: currentText
                    })
                });

                const elapsed = Math.round(performance.now() - startTime);
                logDebug('RESTORE', `API response received in ${elapsed}ms, status: ${response.status}`);

                if (response.ok) {
                    const data = await response.json();
                    restored = data.restored_text;
                    stats = data.statistics;
                    logInfo('RESTORE', 'API restoration successful:', stats);
                } else {
                    const errorText = await response.text();
                    logWarn('RESTORE', `API error ${response.status}: ${errorText}`);
                }
            } catch (err) {
                logWarn('RESTORE', `API request failed: ${err.message}`);
            }
        } else {
            logInfo('RESTORE', 'Not connected or no session - using local restoration');
        }

        // Fallback to local restoration
        if (!restored) {
            logInfo('RESTORE', 'Using local restoration fallback');
            const result = localRestore(currentText, state.replacementMap);
            restored = result.text;
            stats = result.stats;
        }

        // Update UI
        textArea.value = restored;
        textArea.classList.remove('anonymized');
        stateLabel.textContent = '📝 Restored';
        stateLabel.classList.remove('anonymized');

        restoreBtn.classList.remove('show');
        anonymizeBtn.disabled = false;

        updateStats(`Restored ${stats.restored}/${stats.total} placeholders`, true);
        updateInfo('Text restored! Original PII values are back.', false);

        state.mode = 'original';
        state.originalText = restored;

        logInfo('RESTORE', `=== Restoration complete: ${stats.restored}/${stats.total} ===`);

    } catch (error) {
        logError('RESTORE', 'Restoration failed:', error);
        updateInfo('Restore failed: ' + error.message, true);
    } finally {
        showLoading(false);
    }
}

// ============================================
// COPY TEXT
// ============================================

async function copyText() {
    logInfo('COPY', 'Copy button clicked');

    const text = textArea.value.trim();
    if (!text) {
        logWarn('COPY', 'Nothing to copy');
        updateInfo('Nothing to copy!', true);
        return;
    }

    try {
        await navigator.clipboard.writeText(text);

        copyIcon.textContent = '✓';
        copyIcon.classList.add('copied');

        setTimeout(() => {
            copyIcon.textContent = '📋';
            copyIcon.classList.remove('copied');
        }, 2000);

        logInfo('COPY', `Copied ${text.length} characters to clipboard`);

    } catch (error) {
        logError('COPY', 'Copy failed:', error);
        updateInfo('Copy failed: ' + error.message, true);
    }
}

// ============================================
// CLEAR
// ============================================

function clear() {
    logInfo('CLEAR', 'Clear button clicked');

    textArea.value = '';
    textArea.classList.remove('anonymized');
    stateLabel.textContent = '📝 Original Text';
    stateLabel.classList.remove('anonymized');
    restoreBtn.classList.remove('show');

    state = {
        mode: 'original',
        originalText: null,
        anonymizedText: null,
        replacementMap: {},
        session_id: null,
        entities: [],
        lastDetectionResults: null
    };

    updateInfo('💡 How it works: Click <strong>Anonymize</strong> to replace PII with placeholders. Click <strong>Restore</strong> to get original values back.', false);
    updateStats('', false);
    updateCharCount();

    logDebug('CLEAR', 'State reset');
}

// ============================================
// UI HELPERS
// ============================================

function showLoading(show) {
    logDebug('UI', `Loading: ${show}`);

    if (loading) {
        loading.classList.toggle('show', show);
    }

    if (anonymizeBtn) anonymizeBtn.disabled = show;
    if (restoreBtn) restoreBtn.disabled = show;
}

function updateInfo(message, isWarning) {
    logDebug('UI', `Info: ${message} (warning: ${isWarning})`);

    if (infoBox) {
        infoBox.innerHTML = sanitizeHTML(message);  // Sanitized HTML for bold text support
        infoBox.classList.toggle('warning', isWarning);
    }
}

function updateStats(message, show) {
    logDebug('UI', `Stats: ${message} (show: ${show})`);

    if (statsBox) {
        statsBox.textContent = message;
        statsBox.classList.toggle('show', show);
    }
}

// ============================================
// CLEANUP
// ============================================

window.addEventListener('unload', () => {
    logInfo('CLEANUP', 'Side panel unloading...');
    if (connectionCheckInterval) {
        clearInterval(connectionCheckInterval);
        logDebug('CLEANUP', 'Connection check interval cleared');
    }
});

// ============================================
// STARTUP COMPLETE
// ============================================

logInfo('INIT', '=== Side panel v4.5 loaded successfully ===');
