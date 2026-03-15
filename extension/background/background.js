console.log('[Background] Obscura v1.0 service worker loading');

// ============================================
// STATE MANAGEMENT
// ============================================

let extensionState = {
    backendConnected: false,
    extensionEnabled: true,  // Controlled by desktop app toggle
    activeTabs: new Map()
};

// ============================================
// INSTALLATION
// ============================================

chrome.runtime.onInstalled.addListener((details) => {
    console.log('[Background] Event:', details.reason);

    if (details.reason === 'install') {
        console.log('[Background] Extension installed successfully');
        // Create context menu on install
        createContextMenu();
    } else if (details.reason === 'update') {
        console.log('[Background] Extension updated');
    }
});

// ============================================
// CONTEXT MENU
// ============================================

function createContextMenu() {
    try {
        chrome.contextMenus.create({
            id: 'pii-shield-info',
            title: 'Obscura Active',
            contexts: ['page'],
            documentUrlPattern: '*://*/*'
        }, () => {
            if (chrome.runtime.lastError) {
                console.log('[Background] Context menu error:', chrome.runtime.lastError.message);
            } else {
                console.log('[Background] ✓ Context menu created');
            }
        });
    } catch (e) {
        console.log('[Background] Context menu not available:', e.message);
    }
}

// ============================================
// MESSAGE HANDLING
// ============================================

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    // Content script ready
    if (request.action === 'contentScriptReady') {
        console.log('[Background] Content script ready on:', sender.tab.title);
        extensionState.activeTabs.set(sender.tab.id, {
            url: request.url,
            title: request.title,
            timestamp: Date.now()
        });
        sendResponse({ status: 'acknowledged' });
    }

    // Check backend
    else if (request.action === 'checkBackend') {
        checkBackendConnection().then(connected => {
            sendResponse({ connected });
        });
        return true;
    }

    // Keep-alive
    else if (request.action === 'keepAlive') {
        sendResponse({ status: 'alive' });
    }

    return true;
});

// ============================================
// BACKEND CONNECTION CHECK
// ============================================

async function checkBackendConnection() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 2000);

        const response = await fetch('http://localhost:5001/api/health', {
            method: 'GET',
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        const connected = response.ok;
        extensionState.backendConnected = connected;

        console.log('[Background] Backend:', connected ? '✓ Connected' : '✗ Disconnected');

        // If connected, also check extension enabled status
        if (connected) {
            await checkExtensionStatus();
        }

        return connected;
    } catch (e) {
        extensionState.backendConnected = false;
        console.log('[Background] Backend check error:', e.message);
        return false;
    }
}

// ============================================
// EXTENSION STATUS CHECK (from desktop app)
// ============================================

async function checkExtensionStatus() {
    try {
        const response = await fetch('http://localhost:5001/api/extension-status', {
            method: 'GET'
        });

        if (response.ok) {
            const data = await response.json();
            const wasEnabled = extensionState.extensionEnabled;
            extensionState.extensionEnabled = data.enabled;

            // Broadcast status change to all tabs
            if (wasEnabled !== data.enabled) {
                console.log('[Background] Extension status changed:', data.enabled ? 'ENABLED' : 'DISABLED');
                broadcastExtensionStatus(data.enabled);
            }
        }
    } catch (e) {
        console.log('[Background] Extension status check error:', e.message);
    }
}

// Broadcast extension status to all content scripts
function broadcastExtensionStatus(enabled) {
    chrome.tabs.query({}, (tabs) => {
        tabs.forEach(tab => {
            chrome.tabs.sendMessage(tab.id, {
                action: 'extensionStatusChanged',
                enabled: enabled
            }).catch(() => {
                // Tab may not have content script loaded
            });
        });
    });
}

// ============================================
// PERIODIC CHECKS
// ============================================

// Check backend and extension status every 10 seconds
setInterval(checkBackendConnection, 10000);
checkBackendConnection();

// Keep service worker alive
setInterval(() => {
    chrome.runtime.sendMessage({
        action: 'keepAlive'
    }).catch(() => {
        // Expected to fail sometimes
    });
}, 4 * 60 * 1000);

// ============================================
// TAB CLEANUP
// ============================================

chrome.tabs.onRemoved.addListener((tabId) => {
    extensionState.activeTabs.delete(tabId);
    console.log('[Background] Tab removed:', tabId);
});

console.log('[Background] ✓ Service worker ready');
console.log('[Background] Obscura backend: http://localhost:5001');