// ============================================
// Obscura - Session-Based Anonymization v1.0
// Production-Ready with Persistent Mappings
// FIXED: Preserves text structure without paragraph wrapping
// ============================================

console.log('[Widget] Initializing Obscura widget...');

if (window._piiShieldWidgetLoaded) {
    console.log('[Widget] Already loaded, skipping');
} else {
    window._piiShieldWidgetLoaded = true;

    const CONFIG = {
        DETECTION_DELAY: 300,
        BACKEND_URL: 'http://localhost:5001/api'
    };

    // ============================================
    // STATE
    // ============================================

    let state = {
        activeElement: null,
        selectedText: null,
        detectedPII: [],
        isMasked: false,
        detectionTimer: null,
        debounceTimer: null,       // For input debouncing
        statusText: null,
        countBox: null,
        countDisplay: null,
        detailsList: null,
        widgetPanel: null,
        backendConnected: false,
        extensionEnabled: true,  // Controlled by desktop app toggle
        currentSessionId: null,
        mappings: {},
        detectedPlaceholders: [],
        hasDetectedPII: false,
        // Smart session tracking
        lastTextHash: null,        // Hash of last processed text
        lastChangeWasPaste: false, // Track paste vs keystroke
        sessionHistory: {},        // Map of session_id -> {anonymizedText, placeholders: [], mappings: {}}
        // State machine
        currentState: 'IDLE'       // IDLE, SCANNING, DETECTED, MASKED, MIXED
    };

    // ============================================
    // GLOBAL PLACEHOLDER REGISTRY (chrome.storage.local)
    // ============================================

    const PlaceholderRegistry = {
        /**
         * Get the current global counter value
         */
        async getCounter() {
            return new Promise((resolve) => {
                chrome.storage.local.get('pii_counter', (result) => {
                    resolve(result.pii_counter || 0);
                });
            });
        },

        /**
         * Get the next placeholder ID for a type (atomically increments counter)
         * @param {string} type - e.g., "EMAIL", "PHONE"
         * @returns {Promise<string>} - e.g., "[EMAIL_47]"
         */
        async getNextPlaceholderId(type) {
            const counter = await this.getCounter();
            const nextId = counter + 1;
            await new Promise(resolve => {
                chrome.storage.local.set({ pii_counter: nextId }, resolve);
            });
            return `[${type.toUpperCase()}_${nextId}]`;
        },

        /**
         * Get the global placeholder registry
         */
        async getRegistry() {
            return new Promise((resolve) => {
                chrome.storage.local.get('pii_registry', (result) => {
                    resolve(result.pii_registry || {});
                });
            });
        },

        /**
         * Register placeholders in the global registry
         * @param {Object} mappings - { "[EMAIL_1]": "john@example.com", ... }
         * @param {string} sessionId
         */
        async registerPlaceholders(mappings, sessionId) {
            const registry = await this.getRegistry();
            const now = Date.now();

            for (const [placeholder, value] of Object.entries(mappings)) {
                registry[placeholder] = { value, sessionId, created: now };
            }

            return new Promise((resolve) => {
                chrome.storage.local.set({ pii_registry: registry }, () => {
                    console.log('[Registry] Registered', Object.keys(mappings).length, 'placeholders for session', sessionId);
                    resolve();
                });
            });
        },

        /**
         * Unregister all placeholders belonging to a session
         * @param {string} sessionId
         */
        async unregisterPlaceholders(sessionId) {
            const registry = await this.getRegistry();
            const updatedRegistry = {};
            let removedCount = 0;

            for (const [placeholder, data] of Object.entries(registry)) {
                if (data.sessionId !== sessionId) {
                    updatedRegistry[placeholder] = data;
                } else {
                    removedCount++;
                }
            }

            return new Promise((resolve) => {
                chrome.storage.local.set({ pii_registry: updatedRegistry }, () => {
                    console.log('[Registry] Unregistered', removedCount, 'placeholders for session', sessionId);
                    resolve();
                });
            });
        },

        /**
         * Lookup placeholders in the registry
         * @param {string[]} placeholders - Array of placeholders to look up
         * @returns {Promise<Object[]>} - Array of { placeholder, value, sessionId }
         */
        async lookupPlaceholders(placeholders) {
            if (!placeholders || placeholders.length === 0) return [];

            const registry = await this.getRegistry();
            const matches = [];

            for (const placeholder of placeholders) {
                if (registry[placeholder]) {
                    matches.push({
                        placeholder,
                        value: registry[placeholder].value,
                        sessionId: registry[placeholder].sessionId
                    });
                }
            }

            return matches;
        },

        /**
         * Get mappings for restore operation
         * @param {string[]} placeholders
         * @returns {Promise<Object>} - { "[EMAIL_1]": "john@example.com", ... }
         */
        async getMappingsForPlaceholders(placeholders) {
            const matches = await this.lookupPlaceholders(placeholders);
            const mappings = {};
            for (const match of matches) {
                mappings[match.placeholder] = match.value;
            }
            return mappings;
        }
    };

    // Cross-tab sync: refresh badge when another tab modifies the registry
    chrome.storage.onChanged.addListener((changes, areaName) => {
        if (areaName === 'local' && changes.pii_registry && state.activeElement) {
            console.log('[Widget] Registry changed in another tab, refreshing badge');
            refreshBadge(state.activeElement);
        }
    });

    // ============================================
    // SMART SESSION MANAGEMENT
    // ============================================

    // Simple hash for change detection (not cryptographic, just for comparison)
    function quickHash(str) {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            const char = str.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash; // Convert to 32bit integer
        }
        return hash;
    }

    // Extract all placeholders from text
    function extractPlaceholders(text) {
        const regex = /\[([A-Z_]+)_(\d+)\]/g;
        const placeholders = [];
        let match;
        while ((match = regex.exec(text)) !== null) {
            placeholders.push(match[0]); // e.g., "[EMAIL_1]"
        }
        return placeholders;
    }

    // Find a session that matches the current text (by placeholders or exact match)
    function findMatchingSession(text) {
        const placeholders = extractPlaceholders(text);

        // First: Check placeholder-based matching
        if (placeholders.length > 0) {
            for (const [sessionId, sessionData] of Object.entries(state.sessionHistory)) {
                // Check if ALL placeholders in text exist in this session's mappings
                const sessionPlaceholders = Object.keys(sessionData.mappings || {});
                const allMatch = placeholders.every(p => sessionPlaceholders.includes(p));
                if (allMatch && placeholders.length > 0) {
                    console.log('[Widget] Session matched by placeholders:', sessionId, placeholders);
                    return { sessionId, sessionData, matchType: 'placeholders' };
                }
            }
        }

        // Second: Exact text match
        for (const [sessionId, sessionData] of Object.entries(state.sessionHistory)) {
            if (sessionData.anonymizedText === text) {
                console.log('[Widget] Session matched by exact text:', sessionId);
                return { sessionId, sessionData, matchType: 'exact' };
            }
        }

        return null;
    }

    // Store session in history after successful anonymization
    function storeSession(sessionId, anonymizedText, mappings) {
        state.sessionHistory[sessionId] = {
            anonymizedText,
            placeholders: extractPlaceholders(anonymizedText),
            mappings: mappings || {},
            timestamp: Date.now()
        };
        console.log('[Widget] Session stored:', sessionId, 'placeholders:', state.sessionHistory[sessionId].placeholders);

        // Limit history to last 20 sessions to prevent memory bloat
        const sessionIds = Object.keys(state.sessionHistory);
        if (sessionIds.length > 20) {
            const oldest = sessionIds.sort((a, b) =>
                state.sessionHistory[a].timestamp - state.sessionHistory[b].timestamp
            )[0];
            delete state.sessionHistory[oldest];
        }
    }

    // Check if text change is significant (paste) vs minor (keystroke)
    function isSignificantChange(oldHash, newHash, oldLength, newLength) {
        // If hash is same, no change
        if (oldHash === newHash) return false;

        // Large length difference (>20 chars) = likely paste
        if (Math.abs(newLength - oldLength) > 20) return true;

        // Otherwise minor edit
        return false;
    }

    // ============================================
    // STATE MACHINE: refreshBadge()
    // Core function that determines state from text content
    // All events funnel through this function
    // ============================================

    /**
     * Refresh badge based on current text content
     * Determines state: IDLE, DETECTED, MASKED, or MIXED
     * @param {HTMLElement} element - The text input element
     * @param {Object} options - { skipBackend: boolean, forceShow: boolean }
     * @returns {Promise<{state: string, entities?: array, registryMatches?: array}>}
     */
    async function refreshBadge(element, options = {}) {
        const { skipBackend = false, forceShow = false } = options;

        // 1. Validate element
        if (!element || !isEditableElement(element)) {
            state.currentState = 'IDLE';
            PIIIndicator.hide();
            return { state: 'IDLE' };
        }

        // 2. Check if extension is enabled
        if (!state.extensionEnabled) {
            state.currentState = 'IDLE';
            PIIIndicator.hide();
            return { state: 'IDLE', reason: 'extension_disabled' };
        }

        // 3. Get text content
        const text = getText(element);
        if (!text || text.length < 3) {
            state.currentState = 'IDLE';
            state.detectedPII = [];
            state.detectedPlaceholders = [];
            state.hasDetectedPII = false;
            state.hasMaskedText = false;
            PIIIndicator.hide();
            return { state: 'IDLE', reason: 'text_too_short' };
        }

        // 4. Check for placeholders in text (LOCAL - instant)
        const placeholders = extractPlaceholders(text);
        state.detectedPlaceholders = placeholders;

        // 5. Lookup placeholders in global registry (cross-tab)
        const registryMatches = await PlaceholderRegistry.lookupPlaceholders(placeholders);

        // If we found registry matches, load the mappings for restore
        if (registryMatches.length > 0) {
            const mappings = await PlaceholderRegistry.getMappingsForPlaceholders(placeholders);
            state.mappings = mappings;
            state.isMasked = true;
            state.hasMaskedText = true;

            // Try to identify the session
            if (registryMatches.length > 0 && registryMatches[0].sessionId) {
                state.currentSessionId = registryMatches[0].sessionId;
            }
        }

        // 6. Check for fresh PII (BACKEND - async) unless skipped
        let entities = [];
        if (!skipBackend && state.backendConnected) {
            entities = await detectPIIViaBackend(text);
            state.detectedPII = entities;
            state.hasDetectedPII = entities.length > 0;
        } else {
            // Use cached entities if available
            entities = state.detectedPII || [];
        }

        // 7. Determine state and show appropriate badge
        let newState = 'IDLE';

        if (entities.length > 0 && registryMatches.length > 0) {
            newState = 'MIXED';
            PIIIndicator.show(element, entities.length, registryMatches.length);
        } else if (registryMatches.length > 0) {
            newState = 'MASKED';
            PIIIndicator.show(element, 0, registryMatches.length);
        } else if (entities.length > 0) {
            newState = 'DETECTED';
            PIIIndicator.show(element, entities.length, 0);
        } else {
            newState = 'IDLE';
            PIIIndicator.hide();
        }

        state.currentState = newState;
        console.log('[Widget] refreshBadge:', newState, '| PII:', entities.length, '| Placeholders:', registryMatches.length);

        return { state: newState, entities, registryMatches };
    }

    // ============================================
    // LISTEN FOR EXTENSION STATUS CHANGES
    // ============================================

    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
        if (request.action === 'extensionStatusChanged') {
            state.extensionEnabled = request.enabled;
            console.log('[Widget] Extension status changed:', request.enabled ? 'ENABLED' : 'DISABLED');

            if (!request.enabled) {
                // Hide all UI elements when disabled
                PIIIndicator.hide();
                PIIPopup.hide();
                if (state.widgetPanel) {
                    state.widgetPanel.style.display = 'none';
                }
            }
            sendResponse({ received: true });
        }
        return true;
    });

    // ============================================
    // WIDGET UI
    // ============================================

    function createWidget() {
        console.log('[Widget] Creating widget...');

        const container = document.createElement('div');
        container.id = 'pii-shield-widget';
        container.style.cssText = `
            position: fixed;
            bottom: 30px;
            right: 30px;
            z-index: 999999;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        `;



        const panel = document.createElement('div');
        panel.style.cssText = `
            position: absolute;
            bottom: 70px;
            right: 0;
            width: 360px;
            background: #161b22;
            border-radius: 8px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.5);
            border: 1px solid #30363d;
            display: none;
            flex-direction: column;
            overflow: hidden;
            z-index: 999999;
        `;

        const header = document.createElement('div');
        header.style.cssText = `
            background: #21262d;
            color: #e6edf3;
            padding: 12px 16px;
            font-weight: 600;
            font-size: 12px;
            font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: move;
            user-select: none;
            border-bottom: 1px solid #30363d;
        `;
        header.innerHTML = `
            <span style="display: flex; align-items: center; gap: 8px;"><svg width="16" height="16" viewBox="0 0 24 24" fill="#58a6ff"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg> Obscura</span>
            <div style="display: flex; gap: 8px;">
                <button id="pii-close-btn" style="background: transparent; border: none; color: #8b949e; cursor: pointer; font-size: 18px; width: 28px; height: 28px; border-radius: 4px; padding: 0; display: flex; align-items: center; justify-content: center;">×</button>
            </div>
        `;


        const closeBtn = header.querySelector('#pii-close-btn');



        closeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            closePanel();
        });

        makeElementDraggable(header, container);

        const content = document.createElement('div');
        content.style.cssText = `
            padding: 12px;
            max-height: 320px;
            overflow-y: auto;
            flex: 1;
            color: #e6edf3;
        `;

        const status = document.createElement('div');
        status.style.cssText = `
            font-size: 11px;
            font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
            color: #8b949e;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
        `;
        status.innerHTML = `
            <span id="pii-status-dot" style="width: 8px; height: 8px; border-radius: 50%; background: #d29922;"></span>
            <span id="pii-status-text">Waiting for backend...</span>
        `;

        const countBox = document.createElement('div');
        countBox.style.cssText = `
            background: rgba(88,166,255,0.15);
            border: 1px solid rgba(88,166,255,0.3);
            padding: 12px;
            border-radius: 6px;
            text-align: center;
            margin-bottom: 12px;
            display: none;
        `;
        countBox.innerHTML = `<div id="pii-count" style="font-size: 12px; font-weight: 600; color: #58a6ff;"></div>`;

        const sessionBox = document.createElement('div');
        sessionBox.style.cssText = `
            background: rgba(88,166,255,0.1);
            border: 1px solid rgba(88,166,255,0.2);
            padding: 8px 12px;
            border-radius: 6px;
            margin-bottom: 12px;
            display: none;
            font-size: 10px;
            color: #58a6ff;
            font-family: 'JetBrains Mono', monospace;
        `;
        sessionBox.innerHTML = `<strong>Session:</strong> <span id="pii-session-id">-</span>`;

        const detailsList = document.createElement('div');
        detailsList.id = 'pii-details-list';
        detailsList.style.cssText = `
            font-size: 11px;
            color: #8b949e;
            display: none;
        `;

        content.appendChild(status);
        content.appendChild(sessionBox);
        content.appendChild(countBox);
        content.appendChild(detailsList);

        const actions = document.createElement('div');
        actions.style.cssText = `
            display: flex;
            gap: 8px;
            padding: 12px;
            border-top: 1px solid #30363d;
            background: #21262d;
        `;

        const anonBtn = document.createElement('button');
        anonBtn.id = 'pii-anon-btn';
        anonBtn.textContent = 'Mask PII';
        anonBtn.style.cssText = `
            flex: 1;
            padding: 12px;
            background: #58a6ff;
            color: #0d1117;
            border: none;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
            cursor: pointer;
            transition: all 0.15s ease;
            display: none;
        `;
        anonBtn.addEventListener('click', anonymizeText);
        anonBtn.addEventListener('mouseenter', () => {
            anonBtn.style.background = '#79b8ff';
            anonBtn.style.boxShadow = '0 0 12px rgba(88, 166, 255, 0.3)';
        });
        anonBtn.addEventListener('mouseleave', () => {
            anonBtn.style.background = '#58a6ff';
            anonBtn.style.boxShadow = 'none';
        });

        const restoreBtn = document.createElement('button');
        restoreBtn.id = 'pii-restore-btn';
        restoreBtn.textContent = 'Restore';
        restoreBtn.style.cssText = `
            flex: 1;
            padding: 12px;
            background: rgba(35, 134, 54, 0.15);
            color: #238636;
            border: 1px solid rgba(35, 134, 54, 0.3);
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
            cursor: pointer;
            transition: all 0.15s ease;
            display: none;
        `;
        restoreBtn.addEventListener('click', restoreOriginalText);
        restoreBtn.addEventListener('mouseenter', () => {
            restoreBtn.style.background = 'rgba(35, 134, 54, 0.25)';
            restoreBtn.style.borderColor = '#238636';
        });
        restoreBtn.addEventListener('mouseleave', () => {
            restoreBtn.style.background = 'rgba(35, 134, 54, 0.15)';
            restoreBtn.style.borderColor = 'rgba(35, 134, 54, 0.3)';
        });

        actions.appendChild(anonBtn);
        actions.appendChild(restoreBtn);

        panel.appendChild(header);
        panel.appendChild(content);
        panel.appendChild(actions);


        container.appendChild(panel);
        document.body.appendChild(container);

        state.widgetPanel = panel;
        state.statusText = status.querySelector('#pii-status-text');
        state.statusDot = document.getElementById('pii-status-dot');
        state.countBox = countBox;
        state.countDisplay = document.getElementById('pii-count');
        state.detailsList = detailsList;
        state.sessionBox = sessionBox;
        state.widgetContainer = container;

        console.log('[Widget] ✓ Widget created');
    }

    // ============================================
    // DRAG FUNCTIONALITY
    // ============================================

    function makeElementDraggable(dragElement, moveElement) {
        let pos1 = 0, pos2 = 0, pos3 = 0, pos4 = 0;

        dragElement.addEventListener('mousedown', dragMouseDown);

        function dragMouseDown(e) {
            e.preventDefault();
            pos3 = e.clientX;
            pos4 = e.clientY;
            document.addEventListener('mousemove', dragMouseMove);
            document.addEventListener('mouseup', dragMouseUp);
            dragElement.style.cursor = 'grabbing';
        }

        function dragMouseMove(e) {
            e.preventDefault();
            pos1 = pos3 - e.clientX;
            pos2 = pos4 - e.clientY;
            pos3 = e.clientX;
            pos4 = e.clientY;

            const newTop = moveElement.offsetTop - pos2;
            const newLeft = moveElement.offsetLeft - pos1;

            const newTopBounded = Math.max(0, Math.min(newTop, window.innerHeight - moveElement.offsetHeight));
            const newLeftBounded = Math.max(0, Math.min(newLeft, window.innerWidth - moveElement.offsetWidth));

            moveElement.style.top = newTopBounded + 'px';
            moveElement.style.left = newLeftBounded + 'px';
            moveElement.style.bottom = 'auto';
            moveElement.style.right = 'auto';
        }

        function dragMouseUp() {
            document.removeEventListener('mousemove', dragMouseMove);
            document.removeEventListener('mouseup', dragMouseUp);
            dragElement.style.cursor = 'move';
        }
    }

    // ============================================
    // CLOSE ON CLICK OUTSIDE
    // ============================================

    document.addEventListener('click', (e) => {
        if (state.widgetContainer && state.widgetContainer.contains(e.target)) {
            return;
        }

        if (isEditableElement(e.target)) {
            return;
        }

        if (state.widgetPanel && state.widgetPanel.style.display !== 'none') {
            closePanel();
            console.log('[Widget] Panel closed (click outside)');
        }
    }, true);

    function togglePanel() {
        state.widgetPanel.style.display = state.widgetPanel.style.display === 'none' ? 'flex' : 'none';
    }

    function hidePanel() {
        state.widgetPanel.style.display = 'none';
        console.log('[Widget] Panel hidden');
    }

    function closePanel() {
        state.widgetPanel.style.display = 'none';
        state.currentSessionId = null;
        state.mappings = {};
        state.isMasked = false;
        state.selectedText = null;
        state.detectedPII = [];
        updateUI(0);
        console.log('[Widget] Panel closed and reset');
    }

    function openPanel() {
        if (state.widgetPanel) {
            state.widgetPanel.style.display = 'flex';
        }
    }

    // ============================================
    // BACKEND CONNECTION
    // ============================================

    async function checkBackendConnection() {
        try {
            console.log('[Widget] Checking backend connection at:', CONFIG.BACKEND_URL.replace('/api', '/api/health'));

            const response = await fetch(CONFIG.BACKEND_URL.replace('/api', '/api/health'), {
                method: 'GET'
            });
            state.backendConnected = response.ok;

            if (state.statusText) {
                if (state.backendConnected) {
                    state.statusText.textContent = 'Backend connected';
                    if (state.statusDot) state.statusDot.style.background = '#238636';
                    console.log('[Widget] Backend connected');
                } else {
                    state.statusText.textContent = 'Backend unavailable';
                    if (state.statusDot) state.statusDot.style.background = '#d29922';
                    console.log('[Widget] Backend unavailable:', response.status);
                }
            }
        } catch (e) {
            state.backendConnected = false;
            if (state.statusText) state.statusText.textContent = 'Backend not running';
            if (state.statusDot) state.statusDot.style.background = '#da3633';
            console.log('[Widget] Backend error:', e.message);
        }
    }

    setInterval(checkBackendConnection, 10000);
    setTimeout(checkBackendConnection, 500);

    // ============================================
    // PII DETECTION VIA BACKEND
    // ============================================

    async function detectPIIViaBackend(text) {
        if (!state.backendConnected) {
            state.statusText.textContent = '❌ Backend not available';
            state.statusDot.style.background = '#F44336';
            return [];
        }

        try {
            const response = await fetch(CONFIG.BACKEND_URL + '/detect-pii', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text })
            });

            if (!response.ok) return [];

            const data = await response.json();
            return data.entities || [];
        } catch (e) {
            console.log('[Widget] Detection error:', e.message);
            return [];
        }
    }

    // ============================================
    // INPUT MONITORING
    // ============================================

    function isEditableElement(el) {
        if (!el) return false;

        const tagName = el.tagName?.toUpperCase();
        const role = el.getAttribute('role');
        const dataTestId = el.getAttribute('data-testid');
        const contentEditable = el.contentEditable;
        const className = el.className ? el.className.toString() : '';

        if (tagName === 'TEXTAREA') return true;
        if (tagName === 'INPUT' && (el.type === 'text' || el.type === 'email' || !el.type)) return true;

        if (contentEditable === 'true' || contentEditable === 'plaintext-only') return true;

        if (role === 'textbox' || role === 'searchbox') return true;

        if (dataTestId?.includes('chat-input') || dataTestId?.includes('message')) return true;
        if (className.includes('chat-input') || className.includes('message-input')) return true;

        if (className.includes('editor') || className.includes('editable') || className.includes('input')) return true;

        return false;
    }

    // ============================================
    // UNIFIED EVENT HANDLERS (all call refreshBadge)
    // ============================================

    document.addEventListener('focus', (e) => {
        if (isEditableElement(e.target)) {
            state.activeElement = e.target;
            console.log('[Widget] Focused on:', e.target.tagName, e.target.className);
            // Use refreshBadge instead of scanForPII
            refreshBadge(e.target);
        }
    }, true);

    document.addEventListener('input', (e) => {
        if (isEditableElement(e.target)) {
            state.activeElement = e.target;
            console.log('[Widget] ✓ Input event detected on:', e.target.tagName);
            // Debounce input events
            clearTimeout(state.debounceTimer);
            state.debounceTimer = setTimeout(() => {
                console.log('[Widget] ⏰ Debounce timer fired, calling refreshBadge()');
                refreshBadge(e.target);
            }, CONFIG.DETECTION_DELAY);
        }
    }, true);

    // Paste event listener for detecting PII in pasted text
    document.addEventListener('paste', (e) => {
        if (isEditableElement(e.target)) {
            state.activeElement = e.target;
            console.log('[Widget] ✓ Paste event detected on:', e.target.tagName);
            // Delay to allow paste content to be inserted, then refresh
            setTimeout(() => {
                console.log('[Widget] Refreshing badge after paste...');
                refreshBadge(e.target);
            }, 100);
        }
    }, true);

    document.addEventListener('click', (e) => {
        if (isEditableElement(e.target)) {
            state.activeElement = e.target;
            console.log('[Widget] Clicked on:', e.target.tagName);
            // refreshBadge handles everything - detecting PII and showing badge
            refreshBadge(e.target);
        }
    }, true);

    // Handle window/tab switching - rescan when page becomes visible again
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible' && state.activeElement) {
            console.log('[Widget] Page became visible, refreshing badge...');
            refreshBadge(state.activeElement);
        }
    });

    // Also handle window focus for when user Alt+Tabs back
    window.addEventListener('focus', () => {
        if (state.activeElement) {
            console.log('[Widget] Window focused, refreshing badge...');
            refreshBadge(state.activeElement);
        }
    });

    // Document-level focusout handler - hide badge when focus leaves to non-editable element
    document.addEventListener('focusout', (e) => {
        // Delay to let click events on badge buttons register first
        setTimeout(() => {
            const active = document.activeElement;
            const badge = PIIIndicator.badge;

            // Hide only if focus went to non-editable AND not to badge/popup
            if (!isEditableElement(active) &&
                !badge?.contains(active) &&
                !PIIPopup.element?.contains(active) &&
                !CorrectionPanel.element?.contains(active)) {
                console.log('[Widget] Focus left to non-editable, hiding badge');
                PIIIndicator.hide();
            }
        }, 150);
    }, true);

    async function scanForPII() {
        // Check if extension is enabled (controlled by desktop app toggle)
        if (!state.extensionEnabled) {
            console.log('[Widget] Extension disabled, skipping PII scan');
            return;
        }

        if (!state.activeElement || !state.backendConnected) return;

        const text = getText(state.activeElement);
        if (!text || text.length < 3) {
            state.detectedPII = [];
            state.detectedPlaceholders = [];
            state.hasDetectedPII = false;
            state.hasMaskedText = false;
            state.currentSessionId = null;
            state.lastTextHash = null;
            updateUI(0);
            PIIIndicator.hide();
            PIIPopup.hide();
            return;
        }

        // Check if this is a significant change or minor edit
        const currentHash = quickHash(text);
        const lastLength = state.lastTextLength || 0;
        const isSignificant = isSignificantChange(state.lastTextHash, currentHash, lastLength, text.length);

        // Skip re-scanning if minor edit and we already have a session
        if (!isSignificant && state.lastTextHash !== null && state.currentSessionId) {
            console.log('[Widget] Minor edit detected, keeping current session');
            return;
        }

        state.lastTextHash = currentHash;
        state.lastTextLength = text.length;

        console.log('[Widget] Scanning for PII...', { isSignificant, hasSession: !!state.currentSessionId });

        // 1. Detect existing placeholders (FAST LOCAL CHECK)
        // Matches [TYPE_ID] format e.g., [PERSON_1], [EMAIL_2]
        const placeholderPattern = /\[([A-Z_]+)_(\d+)\]/g;
        const potentialPlaceholders = text.match(placeholderPattern) || [];
        state.detectedPlaceholders = potentialPlaceholders;

        // 2. Smart session matching - check if this text matches a known session
        if (potentialPlaceholders.length > 0 || isSignificant) {
            const matchedSession = findMatchingSession(text);
            if (matchedSession) {
                console.log('[Widget] Found matching session:', matchedSession.sessionId, 'via', matchedSession.matchType);
                state.currentSessionId = matchedSession.sessionId;
                state.mappings = matchedSession.sessionData.mappings;
                state.isMasked = true;
            } else if (potentialPlaceholders.length === 0) {
                // No placeholders and no match = fresh text, clear session
                state.currentSessionId = null;
                state.mappings = {};
                state.isMasked = false;
            }
        }

        if (potentialPlaceholders.length > 0) {
            console.log('[Widget] Detected existing placeholders:', potentialPlaceholders);
            state.isMasked = true; // Assume masked if we see placeholders
        }

        // 2. Detect backend PII
        const entities = await detectPIIViaBackend(text);
        state.detectedPII = entities;

        console.log('[Widget] ✓ PII Detection Complete:', {
            piiCount: entities.length,
            placeholderCount: potentialPlaceholders.length,
            entities: entities.map(e => ({ label: e.label, text: e.text.substring(0, 20) }))
        });

        // Update UI with combined count
        updateUI(entities.length + potentialPlaceholders.length);

        // SIMPLE INDICATOR: Border around text field + badge
        try {
            if (entities.length > 0 || potentialPlaceholders.length > 0) {
                console.log('[Widget] Showing PII indicator...');
                PIIIndicator.show(state.activeElement, entities.length, potentialPlaceholders.length);
            } else {
                PIIIndicator.hide();
            }
        } catch (err) {
            console.error('[Widget] Indicator error:', err);
        }

        // CLICK-TO-SHOW: Show underlines, popup on click
        // Store detection state for click handler
        state.hasDetectedPII = entities.length > 0;
        state.hasMaskedText = potentialPlaceholders.length > 0;

        console.log('[Widget] PII state:', { hasDetectedPII: state.hasDetectedPII, count: entities.length });

        // No auto-popup - user must click underline
        if (!state.hasDetectedPII && !state.hasMaskedText) {
            PIIIndicator.hide();
            PIIPopup.hide();
        }
    }

    function updateUI(count) {
        try {
            const anonBtn = document.getElementById('pii-anon-btn');
            const restoreBtn = document.getElementById('pii-restore-btn');

            if (count === 0) {
                if (state.statusText) state.statusText.textContent = '✓ No PII detected';
                if (state.countBox) state.countBox.style.display = 'none';
                if (state.detailsList) state.detailsList.style.display = 'none';
                if (anonBtn) anonBtn.style.display = 'none';
                if (!state.isMasked && restoreBtn) restoreBtn.style.display = 'none';
                return;
            }

            if (state.statusText) {
                if (state.detectedPlaceholders.length > 0) {
                    state.statusText.textContent = `Found ${state.detectedPII.length} PII, ${state.detectedPlaceholders.length} masked`;
                } else {
                    state.statusText.textContent = `Found ${count} PII item${count > 1 ? 's' : ''}`;
                }
            }
            if (state.countDisplay) state.countDisplay.textContent = `🔴 ${count} item${count > 1 ? 's' : ''} detected`;
            if (state.countBox) state.countBox.style.display = 'block';

            let html = '<div style="margin-top: 8px;">';
            state.detectedPII.forEach(e => {
                // Terminal Security color palette for PII types
                const colors = {
                    EMAIL: '#a371f7', PHONE: '#3fb950', SSN: '#f0883e',
                    CREDIT_CARD: '#f85149', DATE: '#79c0ff', AADHAAR: '#a371f7',
                    PAN: '#f0883e', IFSC: '#3fb950', PERSON: '#58a6ff', ADDRESS: '#db61a2'
                };
                const color = colors[e.label?.toUpperCase()] || '#8b949e';
                html += `<div style="margin: 4px 0; padding: 8px 10px; background: #21262d; border-left: 3px solid ${color}; border-radius: 4px; font-family: 'JetBrains Mono', monospace; font-size: 11px;">
                    <span style="color: ${color}; font-weight: 600; text-transform: uppercase; font-size: 10px; letter-spacing: 0.5px;">${e.label}</span><br>
                    <span style="color: #8b949e;">${e.text}</span>
                </div>`;
            });
            html += '</div>';
            if (state.detailsList) state.detailsList.innerHTML = html;
            if (state.detailsList) state.detailsList.style.display = 'block';

            if (anonBtn) anonBtn.style.display = (state.detectedPII.length > 0 && !state.isMasked) ? 'block' : 'none';
            // Show restore if we have active mapping OR if we detected placeholders from a past session
            if (restoreBtn) restoreBtn.style.display = (state.isMasked || state.detectedPlaceholders.length > 0) ? 'block' : 'none';
        } catch (e) {
            console.log('[Widget] updateUI error:', e.message);
        }
    }

    // ============================================
    // ANONYMIZE - Backend API Call
    // ============================================

    // Pattern to detect existing Obscura placeholders
    const PLACEHOLDER_REGEX = /\[([A-Z_]+)_(\d+)\]/g;

    async function anonymizeText() {
        if (!state.detectedPII.length) {
            showNotification('No PII to anonymize', 'warning');
            return;
        }

        if (!state.backendConnected) {
            showNotification('❌ Backend not connected. Start your desktop app on localhost:5001', 'error');
            console.log('[Widget] Backend URL:', CONFIG.BACKEND_URL);
            return;
        }

        let text = state.selectedText || (state.activeElement ? getText(state.activeElement) : null);

        if (!text) {
            showNotification('No text to anonymize', 'warning');
            return;
        }

        // Check if text already contains placeholders (already anonymized)
        const existingPlaceholders = text.match(PLACEHOLDER_REGEX);
        if (existingPlaceholders && existingPlaceholders.length > 0) {
            // If we already have a session for this text, warn and skip
            if (state.currentSessionId) {
                showNotification('Text already anonymized. Use Restore to get original.', 'warning');
                console.log('[Widget] Skipping re-anonymization, found placeholders:', existingPlaceholders);
                return;
            }
        }

        const anonBtn = document.getElementById('pii-anon-btn');
        const restoreBtn = document.getElementById('pii-restore-btn');
        const sessionIdEl = document.getElementById('pii-session-id');

        if (!anonBtn) {
            console.log('[Widget] Buttons not found');
            return;
        }

        try {
            if (state.statusText) state.statusText.textContent = '🔄 Anonymizing...';
            anonBtn.disabled = true;

            console.log('[Widget] Anonymize Request:');
            console.log('  URL:', CONFIG.BACKEND_URL + '/detect-pii');
            console.log('  Text length:', text.length);
            console.log('  PII count:', state.detectedPII.length);

            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 10000);

            const response = await fetch(CONFIG.BACKEND_URL + '/detect-pii', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: text,
                    action: 'anonymize',
                    // Reuse existing session to accumulate mappings, or create new
                    session_id: state.currentSessionId || undefined,
                    create_session: !state.currentSessionId
                }),
                signal: controller.signal
            });

            clearTimeout(timeoutId);

            console.log('[Widget] Response Status:', response.status);

            if (!response.ok) {
                const errorText = await response.text();
                console.log('[Widget] Response Error:', errorText);
                throw new Error(`HTTP ${response.status}: ${errorText}`);
            }

            const data = await response.json();
            console.log('[Widget] Response Success:', { session_id: data.session_id, entity_count: data.entity_count });

            state.currentSessionId = data.session_id;
            state.mappings = data.replacement_map || {};
            state.isMasked = true;

            // Store session in history for cross-field restore
            if (data.session_id && data.anonymized_text) {
                storeSession(data.session_id, data.anonymized_text, data.replacement_map || {});
                // Update hash to match the new anonymized text
                state.lastTextHash = quickHash(data.anonymized_text);
                state.lastTextLength = data.anonymized_text.length;

                // Register placeholders in global registry for cross-tab detection
                if (data.replacement_map) {
                    await PlaceholderRegistry.registerPlaceholders(data.replacement_map, data.session_id);
                    console.log('[Widget] Registered', Object.keys(data.replacement_map).length, 'placeholders in global registry');
                }
            }

            if (state.activeElement && !state.selectedText) {
                // Try in-place replacement first (preserves DOM structure/formatting)
                const tagName = state.activeElement.tagName?.toUpperCase();
                const isContentEditable = state.activeElement.contentEditable === 'true' ||
                                          state.activeElement.contentEditable === 'plaintext-only';

                if (isContentEditable && data.replacement_map) {
                    // Create reverse map: original → placeholder
                    const originalToPlaceholder = {};
                    for (const [placeholder, original] of Object.entries(data.replacement_map)) {
                        originalToPlaceholder[original] = placeholder;
                    }

                    // Use in-place replacement to preserve formatting
                    // This walks through DOM text nodes and replaces text directly
                    const result = applyReplacementsToElement(state.activeElement, originalToPlaceholder);

                    if (result.allReplaced) {
                        console.log('[Widget] In-place replacement complete (all', result.expectedCount, 'items replaced)');
                    } else if (result.replacedCount > 0) {
                        // Partial success - some items replaced, some missed
                        console.log('[Widget] In-place replacement partial:', result.replacedCount, '/', result.expectedCount, 'items');

                        if (result.missing && result.missing.length > 0) {
                            console.log('[Widget] Missed items:', result.missing.map(m => m.substring(0, 25)));

                            // Handle multi-line items that span multiple DOM nodes
                            const multiLineItems = result.missing.filter(item => item.includes('\n'));
                            if (multiLineItems.length > 0) {
                                console.log('[Widget] Attempting multi-line replacement for', multiLineItems.length, 'items');
                                let currentText = getText(state.activeElement);
                                let anyMultiLineReplaced = false;

                                for (const original of multiLineItems) {
                                    const placeholder = originalToPlaceholder[original];
                                    if (currentText.includes(original)) {
                                        currentText = currentText.split(original).join(placeholder);
                                        anyMultiLineReplaced = true;
                                        console.log('[Widget] Multi-line item replaced:', original.substring(0, 30) + '...');
                                    }
                                }

                                if (anyMultiLineReplaced) {
                                    console.log('[Widget] Setting text after multi-line replacements');
                                    setText(state.activeElement, currentText);
                                }
                            }
                        }
                    } else {
                        // No in-place replacements worked - fall back to setText
                        console.log('[Widget] In-place replacement failed, using setText');
                        setText(state.activeElement, data.anonymized_text);
                    }
                } else {
                    setText(state.activeElement, data.anonymized_text);
                }
                showNotification(`✓ Anonymized ${data.entity_count} item${data.entity_count > 1 ? 's' : ''}`, 'success');
            } else if (state.selectedText) {
                try {
                    await navigator.clipboard.writeText(data.anonymized_text);
                    showNotification('✓ Anonymized text copied to clipboard!', 'success');
                } catch (clipErr) {
                    console.log('[Widget] Clipboard copy failed:', clipErr.message);
                    showNotification('✓ Anonymized (paste from notification)', 'success');
                }
            }

            if (sessionIdEl) sessionIdEl.textContent = state.currentSessionId;
            if (state.sessionBox) state.sessionBox.style.display = 'block';

            showMappings(data.replacement_map);

            if (state.statusText) state.statusText.textContent = `✓ Anonymized ${data.entity_count || state.detectedPII.length} item${data.entity_count > 1 ? 's' : ''}`;
            anonBtn.style.display = 'none';
            anonBtn.disabled = false;
            if (restoreBtn) restoreBtn.style.display = 'block';

            console.log('[Widget] ✓ Anonymization complete');

            // Update state for masked text
            state.hasMaskedText = true;
            state.hasDetectedPII = false; // No raw PII anymore, just placeholders
            state.detectedPlaceholders = extractPlaceholders(data.anonymized_text);
            PIIPopup.hide();

            // Explicitly show the indicator with Restore button
            // Use longer delay to ensure DOM is stable after our changes
            setTimeout(() => {
                if (state.activeElement) {
                    console.log('[Widget] Showing indicator with Restore button');
                    PIIIndicator.show(state.activeElement, 0, state.detectedPlaceholders.length);
                }
            }, 200);

        } catch (e) {
            console.error('[Widget] Anonymize Error:', {
                message: e.message,
                name: e.name,
                backend_url: CONFIG.BACKEND_URL
            });

            if (e.name === 'AbortError') {
                if (state.statusText) state.statusText.textContent = '❌ Request timeout (backend slow)';
                showNotification('Request timeout - is backend running?', 'error');
            } else if (e.message.includes('Failed to fetch')) {
                if (state.statusText) state.statusText.textContent = '❌ Cannot reach backend';
                showNotification('Cannot connect to backend at ' + CONFIG.BACKEND_URL, 'error');
                console.log('[Widget] Check: Is desktop app running on localhost:5001?');
            } else {
                if (state.statusText) state.statusText.textContent = '❌ Error: ' + e.message;
                showNotification('Error: ' + e.message, 'error');
            }

            if (anonBtn) anonBtn.disabled = false;
        }
    }

    function showMappings(mappings) {
        let html = '<div style="margin-top: 8px; font-size: 10px; font-family: \'JetBrains Mono\', monospace;"><span style="color: #e6edf3; font-weight: 600;">Mappings:</span>';
        for (const [placeholder, original] of Object.entries(mappings)) {
            html += `<div style="margin: 4px 0; padding: 4px 8px; background: rgba(35,134,54,0.1); border-radius: 4px; color: #238636;"><code style="background: rgba(35,134,54,0.2); padding: 2px 4px; border-radius: 3px;">${placeholder}</code> <span style="color: #6e7681;">=</span> <code style="color: #8b949e;">${original.substr(0, 15)}${original.length > 15 ? '...' : ''}</code></div>`;
        }
        html += '</div>';
        if (state.detailsList) state.detailsList.innerHTML = html;
    }

    // ============================================
    // RESTORE - Backend API Call
    // ============================================

    async function restoreOriginalText() {
        if (!state.activeElement && !state.selectedText) {
            showNotification('No text element found. Focus an input or select text.', 'warning');
            return;
        }

        if (!state.backendConnected) {
            showNotification('❌ Backend not connected. Check if server is running on localhost:5001', 'error');
            return;
        }

        const text = state.selectedText || (state.activeElement ? getText(state.activeElement) : null);
        const restoreBtn = document.getElementById('pii-restore-btn');
        const anonBtn = document.getElementById('pii-anon-btn');

        if (!text) {
            showNotification('No text to restore', 'warning');
            return;
        }

        try {
            if (state.statusText) state.statusText.textContent = '🔄 Restoring...';
            if (restoreBtn) restoreBtn.disabled = true;

            // DECISION: Use Session ID if available, otherwise use Global Restoration
            let endpoint = '/restore-llm';
            let payload = {};

            if (state.currentSessionId) {
                console.log('[Widget] Using Session Restore (Session ID found)');
                payload = {
                    session_id: state.currentSessionId,
                    llm_output: text
                };
            } else {
                console.log('[Widget] Using Global Restore (No Session ID, checking history)');
                endpoint = '/restore-global';
                payload = { text: text };
            }

            console.log(`[Widget] Restore Request to ${endpoint}`);

            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 10000);

            const response = await fetch(CONFIG.BACKEND_URL + endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
                signal: controller.signal
            });

            clearTimeout(timeoutId);

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`HTTP ${response.status}: ${errorText}`);
            }

            const data = await response.json();
            console.log('[Widget] Restore Success:', data);

            // Check if anything was actually restored
            const stats = data.statistics || {};
            if (stats.restored === 0) {
                showNotification('⚠️ No matching original values found in history.', 'warning');
                if (state.statusText) state.statusText.textContent = '⚠️ No match found';
            } else {
                if (state.activeElement && !state.selectedText) {
                    // Try in-place replacement first (preserves DOM structure/formatting)
                    const isContentEditable = state.activeElement.contentEditable === 'true' ||
                                              state.activeElement.contentEditable === 'plaintext-only';

                    if (isContentEditable && state.mappings && Object.keys(state.mappings).length > 0) {
                        // mappings is placeholder → original, use it directly
                        const result = applyReplacementsToElement(state.activeElement, state.mappings);
                        if (result.allReplaced) {
                            console.log('[Widget] In-place restore complete (all', result.expectedCount, 'items)');
                        } else if (result.replacedCount > 0) {
                            // Partial - check for multi-line original values that need restoration
                            console.log('[Widget] In-place restore partial:', result.replacedCount, '/', result.expectedCount);

                            if (result.missing && result.missing.length > 0) {
                                // For restore, check if the ORIGINAL VALUES (not placeholders) contain newlines
                                const multiLineRestores = result.missing.filter(placeholder => {
                                    const original = state.mappings[placeholder];
                                    return original && original.includes('\n');
                                });

                                if (multiLineRestores.length > 0) {
                                    console.log('[Widget] Attempting multi-line restore for', multiLineRestores.length, 'items');
                                    let currentText = getText(state.activeElement);
                                    let anyMultiLineRestored = false;

                                    for (const placeholder of multiLineRestores) {
                                        const original = state.mappings[placeholder];
                                        if (currentText.includes(placeholder)) {
                                            currentText = currentText.split(placeholder).join(original);
                                            anyMultiLineRestored = true;
                                            console.log('[Widget] Multi-line item restored:', placeholder);
                                        }
                                    }

                                    if (anyMultiLineRestored) {
                                        console.log('[Widget] Setting text after multi-line restores');
                                        setText(state.activeElement, currentText);
                                    }
                                }
                            }
                        } else {
                            // Nothing worked - fall back
                            console.log('[Widget] In-place restore failed, using setText');
                            setText(state.activeElement, data.restored_text);
                        }
                    } else {
                        setText(state.activeElement, data.restored_text);
                    }
                    showNotification(`✓ Restored ${stats.restored} item(s)`, 'success');
                } else if (state.selectedText) {
                    try {
                        await navigator.clipboard.writeText(data.restored_text);
                        showNotification('✓ Restored text copied to clipboard!', 'success');
                    } catch (clipErr) {
                        showNotification('✓ Restored (paste from notification)', 'success');
                    }
                }

                state.isMasked = false;
                state.selectedText = null;
                state.detectedPlaceholders = []; // Clear placeholders
                state.hasMaskedText = false;

                // Unregister placeholders from global registry before clearing session
                if (state.currentSessionId) {
                    await PlaceholderRegistry.unregisterPlaceholders(state.currentSessionId);
                    console.log('[Widget] Unregistered placeholders for session:', state.currentSessionId);
                }
                state.currentSessionId = null; // Clear session for fresh start

                if (state.statusText) state.statusText.textContent = '✓ Restored to original';
                if (anonBtn) anonBtn.style.display = 'block'; // Allow starting over
                if (restoreBtn) restoreBtn.style.display = 'none';


                // Refresh badge to update state after restore
                setTimeout(() => {
                    if (state.activeElement) {
                        refreshBadge(state.activeElement);
                    }
                    PIIPopup.hide();
                }, 10);
            }

            if (restoreBtn) restoreBtn.disabled = false;

        } catch (e) {
            console.error('[Widget] Restore Error:', e);
            showNotification('Error: ' + e.message, 'error');
            if (restoreBtn) restoreBtn.disabled = false;
        }
    }

    // ============================================
    // FIXED: getText and setText Functions
    // Prevents paragraph wrapping in contentEditable
    // ============================================

    function getText(el) {
        if (!el) return '';

        const tagName = el.tagName?.toUpperCase();

        // Standard input/textarea
        if (tagName === 'TEXTAREA' || tagName === 'INPUT') {
            return el.value || '';
        }

        // ContentEditable elements - use innerText to preserve line breaks
        // innerText respects <br> tags and rendered whitespace, unlike textContent
        if (el.contentEditable === 'true' || el.contentEditable === 'plaintext-only') {
            // innerText preserves line breaks from <br> tags and block elements
            return el.innerText || '';
        }

        // Fallback - use innerText to preserve formatting
        return el.innerText?.trim() || '';
    }

    // Apply replacements to contentEditable while preserving DOM structure
    // Returns { success: boolean, allReplaced: boolean, replacedCount: number, expectedCount: number, missing: [] }
    function applyReplacementsToElement(el, replacements) {
        if (!el || !replacements || Object.keys(replacements).length === 0) {
            return { success: false, allReplaced: false, replacedCount: 0, expectedCount: 0, missing: [] };
        }

        const expectedCount = Object.keys(replacements).length;
        const replacedSet = new Set(); // Track which replacements were actually made

        // CRITICAL: Sort replacements by length (longest first)
        // This prevents "Braeden" from being replaced before "Braeden James Bihag"
        const sortedReplacements = Object.entries(replacements)
            .sort((a, b) => b[0].length - a[0].length);

        console.log('[Widget] Replacement order (longest first):',
            sortedReplacements.map(([orig, repl]) => `${orig.substring(0, 20)}... → ${repl}`));

        // Walk through all text nodes and apply replacements
        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null, false);
        const textNodes = [];

        // Collect all text nodes first (to avoid modifying while walking)
        let node;
        while ((node = walker.nextNode())) {
            textNodes.push(node);
        }

        let anyReplaced = false;

        // Apply replacements to each text node
        for (const textNode of textNodes) {
            let text = textNode.nodeValue;
            let modified = false;

            // Use sorted replacements (longest first)
            for (const [original, placeholder] of sortedReplacements) {
                if (text.includes(original)) {
                    text = text.split(original).join(placeholder);
                    modified = true;
                    replacedSet.add(original); // Track this replacement was made
                }
            }

            if (modified) {
                textNode.nodeValue = text;
                anyReplaced = true;
            }
        }

        if (anyReplaced) {
            // Trigger events to notify the page
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }

        const allReplaced = replacedSet.size === expectedCount;
        const missing = Object.keys(replacements).filter(k => !replacedSet.has(k));

        console.log('[Widget] In-place replacement result:', {
            expectedCount,
            replacedCount: replacedSet.size,
            allReplaced,
            missing: missing.map(m => m.substring(0, 30) + (m.length > 30 ? '...' : ''))
        });

        return {
            success: anyReplaced,
            allReplaced,
            replacedCount: replacedSet.size,
            expectedCount,
            missing
        };
    }

    function setText(el, text) {
        if (!el) return;

        const tagName = el.tagName?.toUpperCase();

        // ============================================
        // TEXTAREA & INPUT
        // ============================================
        if (tagName === 'TEXTAREA' || tagName === 'INPUT') {
            el.value = text;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            return;
        }

        // ============================================
        // CONTENTEDITABLE - Use innerText (simplest, most reliable)
        // ============================================
        if (el.contentEditable === 'true' || el.contentEditable === 'plaintext-only') {
            console.log('[Widget] Setting text on contentEditable via innerText');

            // innerText is the most reliable for contentEditable
            // It properly handles newlines without extra spacing
            el.innerText = text;
            console.log('[Widget] Set innerText directly');

            // Trigger input/change events (NOT blur - that hides the badge!)
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));

            // Trigger keyboard events for React
            el.dispatchEvent(new KeyboardEvent('keydown', {
                bubbles: true,
                key: 'End',
                code: 'End'
            }));
            el.dispatchEvent(new KeyboardEvent('keyup', {
                bubbles: true,
                key: 'End',
                code: 'End'
            }));

            // Focus and set cursor at end
            try {
                el.focus();
                // Only set selection if element is still in document
                if (document.body.contains(el) && el.lastChild) {
                    const selection = window.getSelection();
                    const range = document.createRange();
                    range.setStartAfter(el.lastChild);
                    range.collapse(true);
                    selection.removeAllRanges();
                    selection.addRange(range);
                }
            } catch (e) {
                // Silently ignore cursor positioning errors
                console.log('[Widget] Cursor position skip:', e.message);
            }

            console.log('[Widget] setText completed successfully');
            return;
        }

        // ============================================
        // FALLBACK
        // ============================================
        el.textContent = text;
        el.dispatchEvent(new Event('input', { bubbles: true }));
    }

    // ============================================
    // NOTIFICATION
    // ============================================

    function showNotification(msg, type = 'info') {
        // Terminal Security notification colors
        const colors = {
            success: { bg: 'rgba(35, 134, 54, 0.15)', border: '#238636', text: '#238636' },
            error: { bg: 'rgba(218, 54, 51, 0.15)', border: '#da3633', text: '#da3633' },
            warning: { bg: 'rgba(210, 153, 34, 0.15)', border: '#d29922', text: '#d29922' },
            info: { bg: 'rgba(88, 166, 255, 0.15)', border: '#58a6ff', text: '#58a6ff' }
        };
        const style = colors[type] || colors.info;

        const notif = document.createElement('div');
        notif.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 16px;
            background: #0d1117;
            border: 1px solid ${style.border};
            border-left: 3px solid ${style.border};
            color: ${style.text};
            border-radius: 6px;
            font-size: 12px;
            font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
            z-index: 9999999;
            box-shadow: 0 8px 24px rgba(0,0,0,0.4);
            animation: slideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            max-width: 300px;
            word-wrap: break-word;
        `;
        notif.textContent = msg;
        document.body.appendChild(notif);

        setTimeout(() => {
            notif.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => notif.remove(), 300);
        }, 4000);
    }

    // ============================================
    // NEW: SIMPLE PII INDICATOR (Badge near text field)
    // ============================================

    const PIIIndicator = {
        badge: null,
        activeElement: null,
        originalBorder: null,
        // REMOVED: showProtectedUntil hack - no longer needed with state machine

        init() {
            if (this.badge) return;

            this.badge = document.createElement('div');
            this.badge.id = 'pii-indicator-badge';
            this.badge.style.cssText = `
                position: fixed;
                z-index: 2147483646;
                background: linear-gradient(135deg, rgba(13, 17, 23, 0.95) 0%, rgba(22, 27, 34, 0.95) 100%);
                backdrop-filter: blur(12px);
                -webkit-backdrop-filter: blur(12px);
                color: #e6edf3;
                padding: 3px;
                border-radius: 10px;
                font-size: 11px;
                font-weight: 600;
                font-family: 'JetBrains Mono', 'SF Mono', 'Fira Code', Consolas, monospace;
                cursor: default;
                box-shadow:
                    0 8px 32px rgba(0,0,0,0.5),
                    0 2px 8px rgba(0,0,0,0.3),
                    inset 0 1px 0 rgba(255,255,255,0.05);
                border: 1px solid rgba(88, 166, 255, 0.2);
                display: none;
                align-items: center;
                gap: 3px;
                user-select: none;
                transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            `;

            this.badge.addEventListener('click', (e) => {
                e.stopPropagation();
                console.log('[PIIIndicator] Badge clicked');
                if (state.activeElement) {
                    PIIPopup.show(state.activeElement, {
                        piiCount: state.detectedPII.length,
                        placeholderCount: state.detectedPlaceholders.length,
                        onAnonymize: () => anonymizeText(),
                        onRestore: () => restoreOriginalText()
                    });
                }
            });

            document.body.appendChild(this.badge);
            console.log('[PIIIndicator] Badge created');

            // Click outside to hide badge and border
            document.addEventListener('click', (e) => {
                // Use setTimeout to let button clicks register first
                setTimeout(() => {
                    if (this.activeElement && this.badge && this.badge.style.display !== 'none') {
                        // Hide if clicking outside the text field and badge
                        if (!this.activeElement.contains(e.target) && !this.badge.contains(e.target)) {
                            this.hide();
                            PIIPopup.hide();
                        }
                    }
                }, 50);
            }, true);
        },

        show(element, piiCount, placeholderCount) {
            this.init();

            // If showing on a different element, hide from previous
            if (this.activeElement && this.activeElement !== element) {
                this.hide();
            }

            this.activeElement = element;

            // Save original border
            if (this.originalBorder === null) {
                this.originalBorder = element.style.border || '';
            }

            // REMOVED: blur listener - now handled by document-level focusout in refreshBadge

            // Add Steel Blue border to text field
            element.style.border = '2px solid #58a6ff';
            element.style.borderRadius = '6px';

            // Position badge near top-right of element
            const rect = element.getBoundingClientRect();
            this.badge.style.top = (rect.top - 15) + 'px';
            this.badge.style.left = (rect.right - 200) + 'px';

            // Set badge with icon + buttons
            // Show BOTH buttons if there's new PII AND existing placeholders
            let html = '';
            const hasMasked = state.isMasked || placeholderCount > 0;
            const hasNewPII = piiCount > 0;

            if (hasNewPII && hasMasked) {
                // Both new PII and existing placeholders - show both buttons
                html = `<span style="
                        display: flex;
                        align-items: center;
                        gap: 6px;
                        padding: 7px 12px;
                        background: linear-gradient(135deg, rgba(88,166,255,0.12) 0%, rgba(88,166,255,0.08) 100%);
                        border-radius: 7px;
                        color: #58a6ff;
                        font-weight: 600;
                        font-size: 11px;
                        letter-spacing: 0.3px;
                    ">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" style="filter: drop-shadow(0 0 4px rgba(88,166,255,0.4));"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                        ${piiCount} PII
                    </span>
                    <button id="pii-badge-anon-btn" style="
                        background: linear-gradient(135deg, #58a6ff 0%, #4d9aef 100%);
                        color: #0d1117;
                        border: none;
                        padding: 7px 14px;
                        border-radius: 7px;
                        font-size: 11px;
                        font-weight: 700;
                        font-family: inherit;
                        cursor: pointer;
                        letter-spacing: 0.3px;
                        transition: all 0.15s ease;
                        box-shadow: 0 2px 8px rgba(88,166,255,0.3);
                    " onmouseover="this.style.background='linear-gradient(135deg, #79b8ff 0%, #58a6ff 100%)'; this.style.boxShadow='0 4px 16px rgba(88,166,255,0.4)';" onmouseout="this.style.background='linear-gradient(135deg, #58a6ff 0%, #4d9aef 100%)'; this.style.boxShadow='0 2px 8px rgba(88,166,255,0.3)';">Mask</button>
                    <button id="pii-badge-restore-btn" style="
                        background: linear-gradient(135deg, #238636 0%, #1e7830 100%);
                        color: #e6edf3;
                        border: none;
                        padding: 7px 14px;
                        border-radius: 7px;
                        font-size: 11px;
                        font-weight: 700;
                        font-family: inherit;
                        cursor: pointer;
                        letter-spacing: 0.3px;
                        transition: all 0.15s ease;
                        box-shadow: 0 2px 8px rgba(35,134,54,0.3);
                    " onmouseover="this.style.background='linear-gradient(135deg, #2ea043 0%, #238636 100%)'; this.style.boxShadow='0 4px 16px rgba(35,134,54,0.4)';" onmouseout="this.style.background='linear-gradient(135deg, #238636 0%, #1e7830 100%)'; this.style.boxShadow='0 2px 8px rgba(35,134,54,0.3)';">Restore</button>
                    <button id="pii-badge-gear-btn" style="
                        background: rgba(110,118,129,0.1);
                        border: none;
                        color: #8b949e;
                        width: 30px;
                        height: 30px;
                        border-radius: 7px;
                        font-size: 14px;
                        cursor: pointer;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        transition: all 0.15s ease;
                    " title="Correction options" aria-label="Correction options" onmouseover="this.style.background='rgba(88,166,255,0.15)'; this.style.color='#58a6ff';" onmouseout="this.style.background='rgba(110,118,129,0.1)'; this.style.color='#8b949e';">
                        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M9.405 1.05c-.413-1.4-2.397-1.4-2.81 0l-.1.34a1.464 1.464 0 01-2.105.872l-.31-.17c-1.283-.698-2.686.705-1.987 1.987l.169.311c.446.82.023 1.841-.872 2.105l-.34.1c-1.4.413-1.4 2.397 0 2.81l.34.1a1.464 1.464 0 01.872 2.105l-.17.31c-.698 1.283.705 2.686 1.987 1.987l.311-.169a1.464 1.464 0 012.105.872l.1.34c.413 1.4 2.397 1.4 2.81 0l.1-.34a1.464 1.464 0 012.105-.872l.31.17c1.283.698 2.686-.705 1.987-1.987l-.169-.311a1.464 1.464 0 01.872-2.105l.34-.1c1.4-.413 1.4-2.397 0-2.81l-.34-.1a1.464 1.464 0 01-.872-2.105l.17-.31c.698-1.283-.705-2.686-1.987-1.987l-.311.169a1.464 1.464 0 01-2.105-.872l-.1-.34zM8 10.93a2.929 2.929 0 110-5.86 2.929 2.929 0 010 5.858z"/></svg>
                    </button>`;
            } else if (hasMasked) {
                // Only placeholders - show Restore
                html = `<span style="
                        display: flex;
                        align-items: center;
                        gap: 6px;
                        padding: 7px 12px;
                        background: linear-gradient(135deg, rgba(35,134,54,0.12) 0%, rgba(35,134,54,0.08) 100%);
                        border-radius: 7px;
                        color: #3fb950;
                        font-weight: 600;
                        font-size: 11px;
                        letter-spacing: 0.3px;
                    ">
                        <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor" style="filter: drop-shadow(0 0 4px rgba(35,134,54,0.4));"><path d="M8 16A8 8 0 108 0a8 8 0 000 16zm3.78-9.72a.75.75 0 00-1.06-1.06L6.75 9.19 5.28 7.72a.75.75 0 00-1.06 1.06l2 2a.75.75 0 001.06 0l4.5-4.5z"/></svg>
                        Masked
                    </span>
                    <button id="pii-badge-restore-btn" style="
                        background: linear-gradient(135deg, #238636 0%, #1e7830 100%);
                        color: #e6edf3;
                        border: none;
                        padding: 7px 14px;
                        border-radius: 7px;
                        font-size: 11px;
                        font-weight: 700;
                        font-family: inherit;
                        cursor: pointer;
                        letter-spacing: 0.3px;
                        transition: all 0.15s ease;
                        box-shadow: 0 2px 8px rgba(35,134,54,0.3);
                    " onmouseover="this.style.background='linear-gradient(135deg, #2ea043 0%, #238636 100%)'; this.style.boxShadow='0 4px 16px rgba(35,134,54,0.4)';" onmouseout="this.style.background='linear-gradient(135deg, #238636 0%, #1e7830 100%)'; this.style.boxShadow='0 2px 8px rgba(35,134,54,0.3)';">Restore</button>
                    <button id="pii-badge-gear-btn" style="
                        background: rgba(110,118,129,0.1);
                        border: none;
                        color: #8b949e;
                        width: 30px;
                        height: 30px;
                        border-radius: 7px;
                        font-size: 14px;
                        cursor: pointer;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        transition: all 0.15s ease;
                    " title="Correction options" aria-label="Correction options" onmouseover="this.style.background='rgba(88,166,255,0.15)'; this.style.color='#58a6ff';" onmouseout="this.style.background='rgba(110,118,129,0.1)'; this.style.color='#8b949e';">
                        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M9.405 1.05c-.413-1.4-2.397-1.4-2.81 0l-.1.34a1.464 1.464 0 01-2.105.872l-.31-.17c-1.283-.698-2.686.705-1.987 1.987l.169.311c.446.82.023 1.841-.872 2.105l-.34.1c-1.4.413-1.4 2.397 0 2.81l.34.1a1.464 1.464 0 01.872 2.105l-.17.31c-.698 1.283.705 2.686 1.987 1.987l.311-.169a1.464 1.464 0 012.105.872l.1.34c.413 1.4 2.397 1.4 2.81 0l.1-.34a1.464 1.464 0 012.105-.872l.31.17c1.283.698 2.686-.705 1.987-1.987l-.169-.311a1.464 1.464 0 01.872-2.105l.34-.1c1.4-.413 1.4-2.397 0-2.81l-.34-.1a1.464 1.464 0 01-.872-2.105l.17-.31c.698-1.283-.705-2.686-1.987-1.987l-.311.169a1.464 1.464 0 01-2.105-.872l-.1-.34zM8 10.93a2.929 2.929 0 110-5.86 2.929 2.929 0 010 5.858z"/></svg>
                    </button>`;
            } else if (hasNewPII) {
                // Only PII - show Mask
                html = `<span style="
                        display: flex;
                        align-items: center;
                        gap: 6px;
                        padding: 7px 12px;
                        background: linear-gradient(135deg, rgba(88,166,255,0.12) 0%, rgba(88,166,255,0.08) 100%);
                        border-radius: 7px;
                        color: #58a6ff;
                        font-weight: 600;
                        font-size: 11px;
                        letter-spacing: 0.3px;
                    ">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" style="filter: drop-shadow(0 0 4px rgba(88,166,255,0.4));"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                        ${piiCount} PII
                    </span>
                    <button id="pii-badge-anon-btn" style="
                        background: linear-gradient(135deg, #58a6ff 0%, #4d9aef 100%);
                        color: #0d1117;
                        border: none;
                        padding: 7px 14px;
                        border-radius: 7px;
                        font-size: 11px;
                        font-weight: 700;
                        font-family: inherit;
                        cursor: pointer;
                        letter-spacing: 0.3px;
                        transition: all 0.15s ease;
                        box-shadow: 0 2px 8px rgba(88,166,255,0.3);
                    " onmouseover="this.style.background='linear-gradient(135deg, #79b8ff 0%, #58a6ff 100%)'; this.style.boxShadow='0 4px 16px rgba(88,166,255,0.4)';" onmouseout="this.style.background='linear-gradient(135deg, #58a6ff 0%, #4d9aef 100%)'; this.style.boxShadow='0 2px 8px rgba(88,166,255,0.3)';">Mask</button>
                    <button id="pii-badge-gear-btn" style="
                        background: rgba(110,118,129,0.1);
                        border: none;
                        color: #8b949e;
                        width: 30px;
                        height: 30px;
                        border-radius: 7px;
                        font-size: 14px;
                        cursor: pointer;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        transition: all 0.15s ease;
                    " title="Correction options" aria-label="Correction options" onmouseover="this.style.background='rgba(88,166,255,0.15)'; this.style.color='#58a6ff';" onmouseout="this.style.background='rgba(110,118,129,0.1)'; this.style.color='#8b949e';">
                        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M9.405 1.05c-.413-1.4-2.397-1.4-2.81 0l-.1.34a1.464 1.464 0 01-2.105.872l-.31-.17c-1.283-.698-2.686.705-1.987 1.987l.169.311c.446.82.023 1.841-.872 2.105l-.34.1c-1.4.413-1.4 2.397 0 2.81l.34.1a1.464 1.464 0 01.872 2.105l-.17.31c-.698 1.283.705 2.686 1.987 1.987l.311-.169a1.464 1.464 0 012.105.872l.1.34c.413 1.4 2.397 1.4 2.81 0l.1-.34a1.464 1.464 0 012.105-.872l.31.17c1.283.698 2.686-.705 1.987-1.987l-.169-.311a1.464 1.464 0 01.872-2.105l.34-.1c1.4-.413 1.4-2.397 0-2.81l-.34-.1a1.464 1.464 0 01-.872-2.105l.17-.31c.698-1.283-.705-2.686-1.987-1.987l-.311.169a1.464 1.464 0 01-2.105-.872l-.1-.34zM8 10.93a2.929 2.929 0 110-5.86 2.929 2.929 0 010 5.858z"/></svg>
                    </button>`;
            }

            this.badge.innerHTML = html;

            // Bind button events
            const anonBtn = this.badge.querySelector('#pii-badge-anon-btn');
            if (anonBtn) {
                anonBtn.onclick = (e) => {
                    e.stopPropagation();
                    anonBtn.textContent = '...';
                    anonBtn.disabled = true;
                    anonymizeText();
                };
            }

            const restoreBtn = this.badge.querySelector('#pii-badge-restore-btn');
            if (restoreBtn) {
                restoreBtn.onclick = (e) => {
                    e.stopPropagation();
                    restoreBtn.textContent = '...';
                    restoreBtn.disabled = true;
                    restoreOriginalText();
                };
            }

            const gearBtn = this.badge.querySelector('#pii-badge-gear-btn');
            if (gearBtn) {
                gearBtn.onclick = (e) => {
                    e.stopPropagation();
                    if (typeof CorrectionPanel !== 'undefined') {
                        CorrectionPanel.toggle(state.activeElement);
                    } else {
                        showNotification('Correction panel loading...', 'info');
                    }
                };
            }

            this.badge.style.display = 'flex';
            // NO BLUR LISTENER - refreshBadge() controls visibility
        },

        hide() {
            if (this.badge) {
                this.badge.style.display = 'none';
            }
            this.clearBorder();
        },

        clearBorder() {
            // Restore original border if element exists
            if (this.activeElement) {
                this.activeElement.style.border = this.originalBorder || '';
                this.activeElement.style.borderRadius = '';
                this.originalBorder = null;
                // Note: Don't null activeElement here - refreshBadge may still need it
            }
        }
    };

    // ============================================
    // OLD: PII HIGHLIGHTER (Overlay) - kept for reference
    // ============================================

    const PIIHighlighter = {
        overlay: null,
        mirror: null,
        activeElement: null,

        init() {
            if (this.overlay) return;

            // Container for the mirror
            this.overlay = document.createElement('div');
            this.overlay.id = 'pii-highlighter-overlay';
            this.overlay.style.cssText = `
                position: absolute;
                top: 0;
                left: 0;
                pointer-events: none;
                z-index: 999900;
                overflow: hidden;
                background: transparent;
                display: none;
            `;//

            // The mirror element that will contain the text
            this.mirror = document.createElement('div');
            this.mirror.id = 'pii-highlighter-mirror';
            this.mirror.style.cssText = `
                position: absolute;
                top: 0;
                left: 0;
                white-space: pre-wrap;
                word-wrap: break-word;
                color: transparent;
                background: transparent;
            `;

            this.overlay.appendChild(this.mirror);
            document.body.appendChild(this.overlay);

            // Click handler on overlay to show popup - only on underline spans
            this.overlay.addEventListener('click', (e) => {
                // Only trigger if clicked on the actual underline span
                if (e.target.classList.contains('pii-underline')) {
                    console.log('[PIIHighlighter] Underline clicked');
                    if (state.activeElement && state.hasDetectedPII) {
                        try {
                            PIIPopup.show(state.activeElement, {
                                piiCount: state.detectedPII.length,
                                placeholderCount: state.detectedPlaceholders.length,
                                onAnonymize: () => anonymizeText(),
                                onRestore: () => restoreOriginalText()
                            });
                        } catch (err) {
                            console.error('[PIIHighlighter] Error showing popup:', err);
                        }
                    }
                }
            });

            // Sync scroll
            document.addEventListener('scroll', () => this.syncScroll(), true);
        },

        highlight(element, entities) {
            if (!element || !isEditableElement(element)) {
                this.hide();
                return;
            }

            this.init();
            this.activeElement = element;



            // 1. Position and Size
            const rect = element.getBoundingClientRect();
            const computedStyle = window.getComputedStyle(element);

            this.overlay.style.width = (rect.width) + 'px';
            this.overlay.style.height = (rect.height) + 'px';
            this.overlay.style.top = (rect.top + window.scrollY) + 'px';
            this.overlay.style.left = (rect.left + window.scrollX) + 'px';
            this.overlay.style.display = 'block';

            // 2. Copy Styles
            const stylesToCopy = [
                'font-family', 'font-size', 'font-weight', 'font-style',
                'line-height', 'letter-spacing', 'text-align',
                'padding-top', 'padding-bottom', 'padding-left', 'padding-right',
                'border-width', 'box-sizing', 'word-spacing', 'text-indent',
                'margin-top', 'margin-bottom', 'margin-left', 'margin-right',
                'white-space', 'overflow-wrap'
            ];

            // Reset mirror styles first
            this.mirror.style.cssText = `
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                white-space: pre-wrap;
                word-wrap: break-word;
                color: transparent; 
                background: transparent;
                overflow: hidden;
                pointer-events: none;
            `;

            stylesToCopy.forEach(prop => {
                this.mirror.style[prop] = computedStyle[prop];
            });

            // Special handling for textarea scroll
            if (element.tagName === 'TEXTAREA') {
                this.mirror.style.width = element.clientWidth + 'px'; // Exclude scrollbar
                this.mirror.style.height = element.clientHeight + 'px';
            }

            // 3. Render Text with Highlights
            const text = getText(element) || '';
            let html = '';
            let lastIndex = 0;

            // Sort entities ASCENDING (Start -> End) to build string linearly
            const sortedEntities = [...entities].sort((a, b) => a.start - b.start);

            sortedEntities.forEach(entity => {
                // Determine cut points (clamp to text length)
                const start = Math.max(0, Math.min(entity.start, text.length));
                const end = Math.max(0, Math.min(entity.end, text.length));

                if (start < lastIndex) return; // Skip overlaps/out-of-order

                // Append text before entity
                const before = text.substring(lastIndex, start);
                html += this.escapeHtml(before);

                // Append entity with highlight
                const match = text.substring(start, end);
                // Steel Blue underline - clickable to show popup
                html += `<span class="pii-underline" style="
                    border-bottom: 2px solid #58a6ff;
                    pointer-events: auto;
                    cursor: pointer;
                ">${this.escapeHtml(match)}</span>`;

                lastIndex = end;
            });

            // Append remaining text
            if (lastIndex < text.length) {
                html += this.escapeHtml(text.substring(lastIndex));
            }

            // Add a zero-width space to ensure last line renders if empty/newline
            this.mirror.innerHTML = html + '&#8203;';

            // 4. Sync Scroll immediately
            this.syncScroll();

            // Add listeners to keep in sync
            // Note: We're adding listeners repeatedly, best to remove first or use named handler
            // For now, simpler to just ensure syncScroll calls
        },

        syncScroll() {
            if (!this.activeElement || !this.mirror) return;

            // Sync scrollTop/scrollLeft
            this.mirror.scrollTop = this.activeElement.scrollTop;
            this.mirror.scrollLeft = this.activeElement.scrollLeft;

            // For overlay position (if window scrolled)
            const rect = this.activeElement.getBoundingClientRect();
            this.overlay.style.top = (rect.top + window.scrollY) + 'px';
            this.overlay.style.left = (rect.left + window.scrollX) + 'px';
        },

        hide() {
            if (this.overlay) this.overlay.style.display = 'none';
            this.activeElement = null;
        },

        escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    };

    // ============================================
    // NEW: CONTEXTUAL POPUP (Small "Anonymize/Restore" bubble)
    // ============================================

    const PIIPopup = {
        element: null,

        init() {
            console.log('[PIIPopup] init() called, element exists:', !!this.element);

            if (this.element) {
                console.log('[PIIPopup] Already initialized, skipping');
                return;
            }

            if (!document.body) {
                console.error('[PIIPopup] ERROR: document.body not available yet!');
                return;
            }

            console.log('[PIIPopup] Creating popup element...');

            try {
                this.element = document.createElement('div');
                this.element.id = 'pii-context-popup';
                this.element.style.cssText = `
                    position: fixed !important;
                    z-index: 2147483647 !important;
                    background: #161b22 !important;
                    padding: 0 !important;
                    border-radius: 8px !important;
                    box-shadow: 0 8px 24px rgba(0,0,0,0.5) !important;
                    display: none !important;
                    flex-direction: column !important;
                    border: 1px solid #30363d !important;
                    font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace !important;
                    animation: slideUp 0.2s cubic-bezier(0.16, 1, 0.3, 1);
                    pointer-events: auto !important;
                    overflow: hidden !important;
                    min-width: 280px !important;
                `;

                // Add animation style
                const style = document.createElement('style');
                style.textContent = `
                    @keyframes slideUp {
                        from { opacity: 0; transform: translateY(10px); }
                        to { opacity: 1; transform: translateY(0); }
                    }
                `;
                document.head.appendChild(style);

                document.body.appendChild(this.element);

                console.log('[PIIPopup] ✓ Popup element created and added to DOM');

                // Click outside to close popup
                document.addEventListener('click', (e) => {
                    if (this.element && this.element.style.display !== 'none') {
                        // Close if clicking outside popup and outside overlay
                        const overlay = document.getElementById('pii-highlighter-overlay');
                        if (!this.element.contains(e.target) && (!overlay || !overlay.contains(e.target))) {
                            this.hide();
                        }
                    }
                }, true);
            } catch (err) {
                console.error('[PIIPopup] ERROR creating popup element:', err);
            }
        },

        show(targetElement, options) {
            console.log('[PIIPopup] show() called with:', {
                element: targetElement?.tagName,
                options
            });

            this.init();

            let piiCount = 0;
            let placeholderCount = 0;
            let onAnonymize = null;
            let onRestore = null;

            if (typeof options === 'object' && options !== null) {
                piiCount = options.piiCount || 0;
                placeholderCount = options.placeholderCount || 0;
                onAnonymize = options.onAnonymize;
                onRestore = options.onRestore;
            } else {
                piiCount = options;
                onAnonymize = arguments[2];
            }

            if (!targetElement || (piiCount === 0 && placeholderCount === 0)) {
                console.log('[PIIPopup] Hiding - no target or no PII');
                this.hide();
                return;
            }

            console.log('[PIIPopup] Building popup HTML...');

            let html = '<span style="font-size: 14px;">🛡️</span>';

            if (piiCount > 0) {
                html += `<span style="font-size: 13px; font-weight: 500; color: #333;">${piiCount} PII Detected</span>`;
            } else if (placeholderCount > 0) {
                html += `<span style="font-size: 13px; font-weight: 500; color: #333;">Masked</span>`;
            }

            if (piiCount > 0 && placeholderCount === 0) {
                html += `<button id="pii-ctx-anon-btn" style="
                    background: #667eea;
                    color: white;
                    border: none;
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: 600;
                    cursor: pointer;
                    margin-left: 4px;
                ">Anonymize</button>`;
            }

            if (placeholderCount > 0 || (state.isMasked && !piiCount)) {
                html += `<button id="pii-ctx-restore-btn" style="
                    background: #4CAF50;
                    color: white;
                    border: none;
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: 600;
                    cursor: pointer;
                    margin-left: 4px;
                ">Restore</button>`;
            }

            html += `<button id="pii-ctx-close-btn" style="
                background: transparent;
                border: none;
                color: #999;
                cursor: pointer;
                font-size: 16px;
                padding: 0 4px;
                margin-left: 4px;
            ">×</button>`;

            this.element.innerHTML = html;

            const anonBtn = this.element.querySelector('#pii-ctx-anon-btn');
            if (anonBtn) {
                anonBtn.onclick = (e) => {
                    e.stopPropagation();
                    if (onAnonymize) {
                        anonBtn.textContent = '...';
                        anonBtn.disabled = true;
                        anonBtn.style.opacity = '0.7';
                        anonBtn.style.cursor = 'wait';
                        onAnonymize();
                    }
                };
            }

            const restoreBtn = this.element.querySelector('#pii-ctx-restore-btn');
            if (restoreBtn) {
                restoreBtn.onclick = (e) => {
                    e.stopPropagation();
                    if (onRestore) {
                        restoreBtn.textContent = '...';
                        restoreBtn.disabled = true;
                        restoreBtn.style.opacity = '0.7';
                        restoreBtn.style.cursor = 'wait';
                        onRestore();
                    }
                };
            }

            const close = this.element.querySelector('#pii-ctx-close-btn');
            if (close) {
                close.onclick = (e) => {
                    e.stopPropagation();
                    this.hide();
                };
            }


            const rect = targetElement.getBoundingClientRect();
            // With position: fixed, we use viewport coordinates directly
            let top = rect.top - 50;
            let left = rect.left;

            // If popup would be above viewport, show it below the element instead
            if (top < 0) {
                top = rect.bottom + 10;
            }

            // Ensure popup stays within viewport width
            if (left + 300 > window.innerWidth) {
                left = window.innerWidth - 310;
            }
            if (left < 0) left = 10;

            this.element.style.top = top + 'px';
            this.element.style.left = left + 'px';
            this.element.style.setProperty('display', 'flex', 'important');

            console.log('[PIIPopup] ✓ Popup displayed at position:', { top, left, rect: { top: rect.top, left: rect.left, bottom: rect.bottom } });
        },

        hide() {
            if (this.element) {
                this.element.style.setProperty('display', 'none', 'important');
                console.log('[PIIPopup] Popup hidden');
            }
        }
    };

    // ============================================
    // CORRECTION PANEL - User feedback for model improvement
    // ============================================

    const ENTITY_LABELS = [
        { value: 'email', label: 'Email' },
        { value: 'phone', label: 'Phone' },
        { value: 'person_name', label: 'Person Name' },
        { value: 'address', label: 'Address' },
        { value: 'government_id', label: 'Government ID' },
        { value: 'financial_account', label: 'Financial Account' },
        { value: 'date_of_birth', label: 'Date of Birth' },
        { value: 'medical_id', label: 'Medical ID' },
        { value: 'digital_id', label: 'Digital ID' },
        { value: 'reference_number', label: 'Reference Number' }
    ];

    const CorrectionPanel = {
        element: null,
        targetElement: null,
        selectionListener: null,
        documentClickListener: null,  // Store reference for cleanup

        init() {
            if (this.element) return;

            this.element = document.createElement('div');
            this.element.id = 'pii-correction-panel';
            this.element.style.cssText = `
                position: fixed;
                z-index: 2147483647;
                background: linear-gradient(180deg, #161b22 0%, #0d1117 100%);
                backdrop-filter: blur(12px);
                -webkit-backdrop-filter: blur(12px);
                width: 340px;
                max-height: 500px;
                border-radius: 12px;
                box-shadow:
                    0 12px 48px rgba(0,0,0,0.5),
                    0 4px 16px rgba(0,0,0,0.3),
                    inset 0 1px 0 rgba(255,255,255,0.05);
                border: 1px solid rgba(88, 166, 255, 0.15);
                display: none;
                flex-direction: column;
                font-family: 'JetBrains Mono', 'SF Mono', 'Fira Code', Consolas, monospace;
                overflow: hidden;
            `;

            // Header
            const header = document.createElement('div');
            header.style.cssText = `
                background: linear-gradient(135deg, rgba(88,166,255,0.15) 0%, rgba(88,166,255,0.05) 100%);
                color: #e6edf3;
                padding: 14px 16px;
                font-weight: 700;
                font-size: 12px;
                letter-spacing: 0.5px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                border-bottom: 1px solid #30363d;
            `;
            header.innerHTML = `
                <span style="display: flex; align-items: center; gap: 8px;">
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="#58a6ff"><path d="M9.405 1.05c-.413-1.4-2.397-1.4-2.81 0l-.1.34a1.464 1.464 0 01-2.105.872l-.31-.17c-1.283-.698-2.686.705-1.987 1.987l.169.311c.446.82.023 1.841-.872 2.105l-.34.1c-1.4.413-1.4 2.397 0 2.81l.34.1a1.464 1.464 0 01.872 2.105l-.17.31c-.698 1.283.705 2.686 1.987 1.987l.311-.169a1.464 1.464 0 012.105.872l.1.34c.413 1.4 2.397 1.4 2.81 0l.1-.34a1.464 1.464 0 012.105-.872l.31.17c1.283.698 2.686-.705 1.987-1.987l-.169-.311a1.464 1.464 0 01.872-2.105l.34-.1c1.4-.413 1.4-2.397 0-2.81l-.34-.1a1.464 1.464 0 01-.872-2.105l.17-.31c.698-1.283-.705-2.686-1.987-1.987l-.311.169a1.464 1.464 0 01-2.105-.872l-.1-.34zM8 10.93a2.929 2.929 0 110-5.86 2.929 2.929 0 010 5.858z"/></svg>
                    Corrections
                </span>
                <button id="pii-correction-close" style="
                    background: rgba(218, 54, 51, 0.1);
                    border: none;
                    color: #da3633;
                    cursor: pointer;
                    font-size: 16px;
                    width: 26px;
                    height: 26px;
                    border-radius: 6px;
                    padding: 0;
                    line-height: 26px;
                    transition: all 0.15s ease;
                " onmouseover="this.style.background='rgba(218, 54, 51, 0.2)'" onmouseout="this.style.background='rgba(218, 54, 51, 0.1)'">×</button>
            `;

            // Content area
            const content = document.createElement('div');
            content.id = 'pii-correction-content';
            content.style.cssText = `
                padding: 14px 16px;
                max-height: 300px;
                overflow-y: auto;
                flex: 1;
                color: #e6edf3;
            `;

            // Add-missed section
            const addMissedSection = document.createElement('div');
            addMissedSection.id = 'pii-add-missed-section';
            addMissedSection.style.cssText = `
                padding: 14px 16px;
                border-top: 1px solid #30363d;
                background: rgba(33, 38, 45, 0.5);
            `;
            addMissedSection.innerHTML = `
                <div style="font-size: 11px; font-weight: 700; color: #58a6ff; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;">
                    Add Missed PII
                </div>
                <div style="font-size: 10px; color: #8b949e; margin-bottom: 10px;">
                    Select text in the input field, then click "Add Selected"
                </div>
                <div style="display: flex; gap: 8px; align-items: center;">
                    <select id="pii-add-missed-type" style="
                        flex: 1;
                        padding: 8px 10px;
                        border: 1px solid #30363d;
                        border-radius: 6px;
                        font-size: 11px;
                        font-family: inherit;
                        background: #21262d;
                        color: #e6edf3;
                        cursor: pointer;
                        transition: all 0.15s ease;
                    " onfocus="this.style.borderColor='#58a6ff'; this.style.boxShadow='0 0 0 2px rgba(88,166,255,0.15)';" onblur="this.style.borderColor='#30363d'; this.style.boxShadow='none';">
                        ${ENTITY_LABELS.map(e => `<option value="${e.value}">${e.label}</option>`).join('')}
                    </select>
                    <button id="pii-add-missed-btn" style="
                        background: linear-gradient(135deg, #58a6ff 0%, #4d9aef 100%);
                        color: #0d1117;
                        border: none;
                        padding: 8px 14px;
                        border-radius: 6px;
                        font-size: 11px;
                        font-weight: 700;
                        font-family: inherit;
                        cursor: pointer;
                        white-space: nowrap;
                        transition: all 0.15s ease;
                        box-shadow: 0 2px 8px rgba(88,166,255,0.3);
                    " onmouseover="this.style.background='linear-gradient(135deg, #79b8ff 0%, #58a6ff 100%)'; this.style.boxShadow='0 4px 16px rgba(88,166,255,0.4)';" onmouseout="this.style.background='linear-gradient(135deg, #58a6ff 0%, #4d9aef 100%)'; this.style.boxShadow='0 2px 8px rgba(88,166,255,0.3)';">Add Selected</button>
                </div>
                <div id="pii-selected-text-preview" style="
                    margin-top: 10px;
                    padding: 8px 10px;
                    background: rgba(210, 153, 34, 0.1);
                    border: 1px solid rgba(210, 153, 34, 0.3);
                    border-radius: 6px;
                    font-size: 10px;
                    color: #d29922;
                    display: none;
                "></div>
            `;

            this.element.appendChild(header);
            this.element.appendChild(content);
            this.element.appendChild(addMissedSection);
            document.body.appendChild(this.element);

            // Bind close button
            const closeBtn = header.querySelector('#pii-correction-close');
            closeBtn.addEventListener('click', () => this.hide());

            // Bind add-missed button
            const addMissedBtn = addMissedSection.querySelector('#pii-add-missed-btn');
            addMissedBtn.addEventListener('click', () => {
                const selectedText = window.getSelection().toString().trim();
                const typeSelect = document.getElementById('pii-add-missed-type');
                if (selectedText && typeSelect) {
                    this.addMissedPII(selectedText, typeSelect.value);
                } else {
                    showNotification('Please select some text first', 'warning');
                }
            });

            // Click outside to close - store reference for cleanup
            this.documentClickListener = (e) => {
                if (this.element && this.element.style.display !== 'none') {
                    if (!this.element.contains(e.target) &&
                        !e.target.closest('#pii-badge-gear-btn')) {
                        this.hide();
                    }
                }
            };
            document.addEventListener('click', this.documentClickListener, true);

            console.log('[CorrectionPanel] Initialized');
        },

        show(targetElement) {
            this.init();
            this.targetElement = targetElement || state.activeElement;

            // Position panel near the target element
            if (this.targetElement) {
                const rect = this.targetElement.getBoundingClientRect();
                let top = rect.top;
                let left = rect.right + 10;

                // If panel would go off screen right, position to the left
                if (left + 350 > window.innerWidth) {
                    left = rect.left - 350;
                    if (left < 0) left = 10;
                }

                // If panel would go off screen bottom, adjust
                if (top + 400 > window.innerHeight) {
                    top = window.innerHeight - 410;
                    if (top < 0) top = 10;
                }

                this.element.style.top = top + 'px';
                this.element.style.left = left + 'px';
            } else {
                // Fallback to center
                this.element.style.top = '100px';
                this.element.style.right = '20px';
                this.element.style.left = 'auto';
            }

            this.renderEntities();
            this.setupSelectionListener();
            this.element.style.display = 'flex';

            console.log('[CorrectionPanel] Shown');
        },

        hide() {
            if (this.element) {
                this.element.style.display = 'none';
            }
            if (this.selectionListener) {
                document.removeEventListener('selectionchange', this.selectionListener);
                this.selectionListener = null;
            }
            console.log('[CorrectionPanel] Hidden');
        },

        toggle(targetElement) {
            if (this.element && this.element.style.display !== 'none') {
                this.hide();
            } else {
                this.show(targetElement);
            }
        },

        renderEntities() {
            const content = document.getElementById('pii-correction-content');
            if (!content) return;

            const entities = state.detectedPII || [];

            if (entities.length === 0) {
                content.innerHTML = `
                    <div style="text-align: center; padding: 24px; color: #8b949e; font-size: 12px;">
                        <div style="font-size: 13px; margin-bottom: 8px; color: #58a6ff;">No PII Detected</div>
                        <div style="font-size: 10px;">Select text and add missed PII below</div>
                    </div>
                `;
                return;
            }

            let html = `
                <div style="font-size: 11px; font-weight: 700; color: #58a6ff; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px;">
                    Detected Entities (${entities.length})
                </div>
            `;

            entities.forEach((entity, index) => {
                const displayText = entity.text.length > 30
                    ? entity.text.substring(0, 30) + '...'
                    : entity.text;
                const escapedText = this.escapeHtml(displayText);
                const entityLabel = entity.label || entity.type || 'unknown';

                html += `
                    <div class="pii-entity-item" style="
                        display: flex;
                        align-items: center;
                        gap: 8px;
                        padding: 10px 12px;
                        margin-bottom: 8px;
                        background: #21262d;
                        border: 1px solid #30363d;
                        border-radius: 8px;
                        font-size: 11px;
                        transition: all 0.15s ease;
                    " data-entity-index="${index}">
                        <div style="flex: 1; overflow: hidden;">
                            <div style="
                                font-weight: 700;
                                color: #58a6ff;
                                text-transform: uppercase;
                                font-size: 9px;
                                letter-spacing: 0.5px;
                                margin-bottom: 3px;
                            ">${this.escapeHtml(entityLabel)}</div>
                            <div style="color: #e6edf3; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                                ${escapedText}
                            </div>
                        </div>
                        <select class="pii-relabel-select" style="
                            padding: 5px 8px;
                            border: 1px solid #30363d;
                            border-radius: 5px;
                            font-size: 10px;
                            font-family: inherit;
                            background: #161b22;
                            color: #8b949e;
                            cursor: pointer;
                            transition: all 0.15s ease;
                        " data-entity-index="${index}" title="Relabel entity type" onfocus="this.style.borderColor='#58a6ff'" onblur="this.style.borderColor='#30363d'">
                            <option value="">Relabel...</option>
                            ${ENTITY_LABELS.map(e => `<option value="${e.value}">${e.label}</option>`).join('')}
                        </select>
                        <button class="pii-reject-btn" style="
                            background: rgba(218, 54, 51, 0.15);
                            color: #da3633;
                            border: 1px solid rgba(218, 54, 51, 0.3);
                            padding: 5px 10px;
                            border-radius: 5px;
                            font-size: 10px;
                            font-weight: 600;
                            font-family: inherit;
                            cursor: pointer;
                            white-space: nowrap;
                            transition: all 0.15s ease;
                        " data-entity-index="${index}" title="Mark as not PII" onmouseover="this.style.background='rgba(218, 54, 51, 0.25)'; this.style.borderColor='#da3633';" onmouseout="this.style.background='rgba(218, 54, 51, 0.15)'; this.style.borderColor='rgba(218, 54, 51, 0.3)';">
                            Reject
                        </button>
                    </div>
                `;
            });

            content.innerHTML = html;

            // Bind reject buttons
            content.querySelectorAll('.pii-reject-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const index = parseInt(e.target.dataset.entityIndex);
                    const entity = entities[index];
                    if (entity) {
                        this.rejectEntity(entity);
                    }
                });
            });

            // Bind relabel selects
            content.querySelectorAll('.pii-relabel-select').forEach(select => {
                select.addEventListener('change', (e) => {
                    const index = parseInt(e.target.dataset.entityIndex);
                    const entity = entities[index];
                    const newType = e.target.value;
                    if (entity && newType) {
                        this.relabelEntity(entity, newType);
                        e.target.value = ''; // Reset select
                    }
                });
            });
        },

        setupSelectionListener() {
            // Remove existing listener
            if (this.selectionListener) {
                document.removeEventListener('selectionchange', this.selectionListener);
            }

            const preview = document.getElementById('pii-selected-text-preview');
            if (!preview) return;

            this.selectionListener = () => {
                const selection = window.getSelection();
                const selectedText = selection.toString().trim();

                if (selectedText && selectedText.length > 0) {
                    const displayText = selectedText.length > 50
                        ? selectedText.substring(0, 50) + '...'
                        : selectedText;
                    preview.textContent = `Selected: "${displayText}"`;
                    preview.style.display = 'block';
                } else {
                    preview.style.display = 'none';
                }
            };

            document.addEventListener('selectionchange', this.selectionListener);
        },

        async rejectEntity(entity) {
            console.log('[CorrectionPanel] Rejecting entity:', entity);

            try {
                const context = this.targetElement ? getText(this.targetElement) : '';

                const response = await fetch(CONFIG.BACKEND_URL + '/corrections/reject', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        text: entity.text,
                        detected_type: entity.label || entity.type,
                        context_before: context.substring(Math.max(0, (entity.start || 0) - 50), entity.start || 0),
                        context_after: context.substring(entity.end || 0, (entity.end || 0) + 50)
                    })
                });

                if (!response.ok) {
                    const errorText = await response.text();
                    throw new Error(`HTTP ${response.status}: ${errorText}`);
                }

                const data = await response.json();
                console.log('[CorrectionPanel] Reject response:', data);

                // Remove entity from local state
                const index = state.detectedPII.findIndex(e =>
                    e.text === entity.text && (e.label || e.type) === (entity.label || entity.type)
                );
                if (index !== -1) {
                    state.detectedPII.splice(index, 1);
                }

                showNotification('Entity marked as not PII', 'success');
                this.renderEntities();

                // Refresh badge to update UI
                setTimeout(() => {
                    if (this.targetElement) {
                        refreshBadge(this.targetElement);
                    }
                }, 100);

            } catch (error) {
                console.error('[CorrectionPanel] Reject error:', error);
                showNotification('Failed to submit rejection: ' + error.message, 'error');
            }
        },

        async relabelEntity(entity, newType) {
            console.log('[CorrectionPanel] Relabeling entity:', entity, 'to', newType);

            try {
                const context = this.targetElement ? getText(this.targetElement) : '';

                const response = await fetch(CONFIG.BACKEND_URL + '/corrections/relabel', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        text: entity.text,
                        original_type: entity.label || entity.type,
                        corrected_type: newType,
                        context_before: context.substring(Math.max(0, (entity.start || 0) - 50), entity.start || 0),
                        context_after: context.substring(entity.end || 0, (entity.end || 0) + 50)
                    })
                });

                if (!response.ok) {
                    const errorText = await response.text();
                    throw new Error(`HTTP ${response.status}: ${errorText}`);
                }

                const data = await response.json();
                console.log('[CorrectionPanel] Relabel response:', data);

                // Update entity in local state
                const index = state.detectedPII.findIndex(e =>
                    e.text === entity.text && (e.label || e.type) === (entity.label || entity.type)
                );
                if (index !== -1) {
                    state.detectedPII[index].label = newType;
                    state.detectedPII[index].type = newType;
                }

                showNotification(`Entity relabeled to ${newType}`, 'success');
                this.renderEntities();

            } catch (error) {
                console.error('[CorrectionPanel] Relabel error:', error);
                showNotification('Failed to submit relabel: ' + error.message, 'error');
            }
        },

        async addMissedPII(text, entityType) {
            console.log('[CorrectionPanel] Adding missed PII:', text, 'as', entityType);

            try {
                const context = this.targetElement ? getText(this.targetElement) : '';

                // Find position of the selected text in context for context extraction
                const textPos = context.indexOf(text);
                const contextBefore = textPos > 0 ? context.substring(Math.max(0, textPos - 50), textPos) : '';
                const contextAfter = textPos >= 0 ? context.substring(textPos + text.length, textPos + text.length + 50) : '';

                const response = await fetch(CONFIG.BACKEND_URL + '/corrections/add-missed', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        text: text,
                        entity_type: entityType,
                        context_before: contextBefore,
                        context_after: contextAfter
                    })
                });

                if (!response.ok) {
                    const errorText = await response.text();
                    throw new Error(`HTTP ${response.status}: ${errorText}`);
                }

                const data = await response.json();
                console.log('[CorrectionPanel] Add-missed response:', data);

                // Add to local state
                state.detectedPII.push({
                    text: text,
                    label: entityType,
                    type: entityType,
                    start: -1, // Unknown position
                    end: -1,
                    confidence: 1.0,
                    source: 'user_correction'
                });

                showNotification(`Added "${text.substring(0, 20)}..." as ${entityType}`, 'success');
                this.renderEntities();

                // Clear selection preview
                const preview = document.getElementById('pii-selected-text-preview');
                if (preview) preview.style.display = 'none';

                // Clear text selection
                window.getSelection().removeAllRanges();

                // Refresh badge to update UI
                setTimeout(() => {
                    if (this.targetElement) {
                        refreshBadge(this.targetElement);
                    }
                }, 100);

            } catch (error) {
                console.error('[CorrectionPanel] Add-missed error:', error);
                showNotification('Failed to add missed PII: ' + error.message, 'error');
            }
        },

        escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        },

        // Full cleanup method for when panel needs to be completely removed
        destroy() {
            this.hide();

            // Remove document click listener
            if (this.documentClickListener) {
                document.removeEventListener('click', this.documentClickListener, true);
                this.documentClickListener = null;
            }

            // Remove element from DOM
            if (this.element && this.element.parentNode) {
                this.element.parentNode.removeChild(this.element);
            }
            this.element = null;
            this.targetElement = null;

            console.log('[CorrectionPanel] Destroyed');
        }
    };

    // ============================================
    // INITIALIZATION
    // ============================================

    function init() {
        if (document.body) {
            createWidget();
        } else {
            document.addEventListener('DOMContentLoaded', createWidget);
        }
    }

    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideIn {
            from { transform: translateX(400px); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        @keyframes slideOut {
            from { transform: translateX(0); opacity: 1; }
            to { transform: translateX(400px); opacity: 0; }
        }
    `;
    document.head.appendChild(style);

    init();
}