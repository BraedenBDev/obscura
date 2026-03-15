console.log('[Content] Obscura v1.0 content script loading');

// Only run on top level, not in iframes
if (window.self === window.top) {
    const url = window.location.href;
    
    // Skip special pages
    if (url.startsWith('chrome://') || url.startsWith('about:') || url.startsWith('edge://')) {
        console.log('[Content] Skipping special page:', url);
    } else {
        console.log('[Content] Running on:', url);

        // Initialize on page load
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initializeContent);
        } else {
            initializeContent();
        }
    }
}

// ============================================
// INITIALIZATION (Only sends ready signal)
// ============================================

function initializeContent() {
    console.log('[Content] Page loaded, widget injected via manifest');
    
    // Widget is auto-injected by manifest content_scripts
    // This just notifies background that content script is ready
    
    chrome.runtime.sendMessage({
        action: 'contentScriptReady',
        url: window.location.href,
        title: document.title
    }).catch(error => {
        console.log('[Content] Background not available (normal)');
    });
}

// ============================================
// MESSAGE HANDLING
// ============================================

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    console.log('[Content] Message received:', request.action);
    
    // Don't do anything, widget handles everything
    sendResponse({ status: 'ok' });
    return true;
});

console.log('[Content] ✓ Ready - widget will auto-inject via manifest');