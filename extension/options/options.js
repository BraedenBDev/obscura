// ============================================
// FILE: options/options.js
// ============================================

// DOM Elements
const hostInput = document.getElementById('hostInput');
const portInput = document.getElementById('portInput');
const presetSelect = document.getElementById('presetSelect');
const thresholdInput = document.getElementById('thresholdInput');
const hybridModeToggle = document.getElementById('hybridModeToggle');
const enableHighlightToggle = document.getElementById('enableHighlightToggle');
const autoDetectToggle = document.getElementById('autoDetectToggle');
const saveHistoryToggle = document.getElementById('saveHistoryToggle');
const semanticAnalysisToggle = document.getElementById('semanticAnalysisToggle');
const contextAwareToggle = document.getElementById('contextAwareToggle');
const thresholdDisplay = document.getElementById('thresholdDisplay');
const testConnectionBtn = document.getElementById('testConnectionBtn');
const clearDataBtn = document.getElementById('clearDataBtn');
const saveBtn = document.getElementById('saveBtn');
const resetBtn = document.getElementById('resetBtn');
const connectionStatus = document.getElementById('connectionStatus');
const saveStatus = document.getElementById('saveStatus');

// Load settings on page load
document.addEventListener('DOMContentLoaded', loadSettings);

// Load current settings
function loadSettings() {
    chrome.storage.sync.get('settings', (result) => {
        const settings = result.settings || {};
        
        hostInput.value = settings.desktopHost || 'localhost';
        portInput.value = settings.desktopPort || 5001;
        presetSelect.value = settings.defaultPreset || 'all';
        thresholdInput.value = settings.defaultThreshold || 30;
        hybridModeToggle.checked = settings.hybridMode !== false;
        enableHighlightToggle.checked = settings.enableHighlight !== false;
        autoDetectToggle.checked = settings.autoDetect || false;
        saveHistoryToggle.checked = settings.saveHistory !== false;
        semanticAnalysisToggle.checked = settings.semanticAnalysis !== false;
        contextAwareToggle.checked = settings.contextAware !== false;
        
        thresholdDisplay.textContent = thresholdInput.value + '%';
    });
}

// Update threshold display
thresholdInput.addEventListener('input', () => {
    thresholdDisplay.textContent = thresholdInput.value + '%';
});

// Test connection
testConnectionBtn.addEventListener('click', async () => {
    const host = hostInput.value || 'localhost';
    const port = portInput.value || 5001;
    
    connectionStatus.innerHTML = 'Testing...';
    connectionStatus.style.display = 'block';
    
    try {
        const response = await fetch(`http://${host}:${port}/api/health`, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (response.ok) {
            connectionStatus.innerHTML = '✅ Connected successfully!';
            connectionStatus.style.color = '#16a34a';
            connectionStatus.style.background = 'rgba(34, 197, 94, 0.1)';
            connectionStatus.style.borderColor = 'rgba(34, 197, 94, 0.3)';
        } else {
            throw new Error('Server returned error');
        }
    } catch (error) {
        connectionStatus.innerHTML = '❌ Connection failed. Make sure desktop app is running on ' + host + ':' + port;
        connectionStatus.style.color = '#ef4444';
        connectionStatus.style.background = 'rgba(239, 68, 68, 0.1)';
        connectionStatus.style.borderColor = 'rgba(239, 68, 68, 0.3)';
    }
});

// Save settings
saveBtn.addEventListener('click', () => {
    const settings = {
        desktopHost: hostInput.value || 'localhost',
        desktopPort: parseInt(portInput.value) || 5001,
        defaultPreset: presetSelect.value || 'all',
        defaultThreshold: parseInt(thresholdInput.value) || 30,
        hybridMode: hybridModeToggle.checked,
        enableHighlight: enableHighlightToggle.checked,
        autoDetect: autoDetectToggle.checked,
        saveHistory: saveHistoryToggle.checked,
        semanticAnalysis: semanticAnalysisToggle.checked,
        contextAware: contextAwareToggle.checked
    };

    chrome.storage.sync.set({ settings }, () => {
        saveStatus.textContent = '✓ Settings saved successfully';
        saveStatus.style.color = '#16a34a';
        saveStatus.style.display = 'block';
        
        setTimeout(() => {
            saveStatus.textContent = '';
            saveStatus.style.display = 'none';
        }, 3000);
    });
});

// Reset to defaults
resetBtn.addEventListener('click', () => {
    if (confirm('Reset all settings to defaults? This cannot be undone.')) {
        const defaults = {
            desktopHost: 'localhost',
            desktopPort: 5001,
            defaultPreset: 'all',
            defaultThreshold: 30,
            hybridMode: true,
            enableHighlight: true,
            autoDetect: false,
            saveHistory: true,
            semanticAnalysis: true,
            contextAware: true
        };
        
        chrome.storage.sync.set({ settings: defaults }, () => {
            loadSettings();
            saveStatus.textContent = '✓ Settings reset to defaults';
            saveStatus.style.color = '#16a34a';
            saveStatus.style.display = 'block';
            
            setTimeout(() => {
                saveStatus.textContent = '';
                saveStatus.style.display = 'none';
            }, 3000);
        });
    }
});

// Clear all data
clearDataBtn.addEventListener('click', () => {
    if (confirm('Clear all local data including detection history? This cannot be undone.')) {
        chrome.storage.local.clear(() => {
            alert('✓ All local data cleared');
        });
    }
});

console.log('✓ options.js loaded');