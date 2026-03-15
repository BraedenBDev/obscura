# Setup Guide

## Prerequisites

- Python 3.12+ with pip
- Google Chrome (version 114+)
- Node.js 18+ / Bun (for development/testing only)

## Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate      # macOS/Linux
# or: venv\Scripts\activate   # Windows
pip install -r requirements.txt
python main.py
```

The GLiNER model downloads automatically on first run (~100MB from Hugging Face Hub).

### macOS Shortcut

Double-click `backend/Run Obscura.command` to launch with virtual environment activation.

## Chrome Extension Setup

1. Open `chrome://extensions/`
2. Enable **Developer mode** (toggle in top right)
3. Click **Load unpacked**
4. Select the `extension/` directory
5. Pin the Obscura icon in your toolbar

## Configure Settings

1. Right-click the Obscura extension icon
2. Click **Options**
3. Verify the backend port is set to `5001`
4. Click **Test Connection** to verify

## Test Detection

1. Ensure the backend is running
2. Open any web page with a text field
3. Type or paste text containing PII (email, phone number, name, etc.)
4. The Obscura badge should appear showing the count of detected entities
5. Click **Mask** to anonymize, **Restore** to bring back original values
