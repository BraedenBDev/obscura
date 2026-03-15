# Obscura

**Real-time PII detection and anonymization for AI-powered workflows.**

Obscura protects your sensitive data by detecting and masking Personally Identifiable Information (PII) before it reaches AI services like ChatGPT or Claude — then restoring original values when the AI responds.

## How It Works

```
You type sensitive text     Obscura detects PII        You send to AI
in any web form        →   and masks it with      →   safely with
                           placeholders                anonymized text

AI responds with            Obscura restores           You see the
placeholders           ←   original values        ←   complete response
```

**Example:**
```
Original:  "Contact John Smith at john@example.com or 555-123-4567"
Masked:    "Contact [PERSON_NAME_1] at [EMAIL_1] or [PHONE_1]"
Restored:  AI response with original values back in place
```

## Features

- **AI-Powered Detection** — Uses [GLiNER](https://github.com/urchade/GLiNER) NER models from Hugging Face for intelligent entity recognition
- **Multi-Layer Pipeline** — GLiNER + regex patterns + format validators (Luhn, SSN, Aadhaar) + context analysis
- **Local Learning** — User corrections improve detection over time, stored locally in SQLite
- **Session Management** — Cross-field, cross-tab restoration via global placeholder registry
- **16 PII Types** — Names, emails, phones, SSNs, credit cards, IBANs, passports, addresses, and more
- **100% Local** — No cloud services. Your data never leaves your machine.

## Architecture

```
┌──────────────────────┐     ┌───────────────────────────┐
│   Chrome Extension   │────▶│     Python Backend         │
│                      │◀────│     (localhost:5001)       │
│  - Floating badge    │     │                           │
│  - Mask / Restore    │     │  GLiNER AI Model          │
│  - Session tracking  │     │       ↓                   │
│  - Cross-tab sync    │     │  Format Validators        │
│  - Correction UI     │     │       ↓                   │
│                      │     │  Context Analyzer         │
└──────────────────────┘     │       ↓                   │
                             │  User Corrections         │
                             │       ↓                   │
                             │  SQLite Persistence       │
                             └───────────────────────────┘
```

## Prerequisites

- **Python 3.12+** with pip
- **Google Chrome** (version 114+)
- **Node.js 18+** (for extension development/testing only)

## Installation

### 1. Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate      # macOS/Linux
# or: venv\Scripts\activate   # Windows

pip install -r requirements.txt
```

The GLiNER model downloads automatically on first run (~100MB from Hugging Face Hub).

### 2. Start the Backend

```bash
cd backend
source venv/bin/activate
python main.py
```

This launches the desktop GUI and API server on `http://localhost:5001`.

**macOS shortcut:** Double-click `backend/Run Obscura.command`

### 3. Install the Chrome Extension

1. Open `chrome://extensions/`
2. Enable **Developer mode** (top right)
3. Click **Load unpacked**
4. Select the `extension/` directory
5. Pin the Obscura icon in your toolbar

## Usage

1. **Keep the backend running** (desktop app or `python main.py`)
2. **Browse normally** — Obscura's badge appears on text fields when PII is detected
3. **Click Mask** — PII is replaced with `[TYPE_N]` placeholders
4. **Paste into AI** — Send the anonymized text to ChatGPT, Claude, etc.
5. **Paste AI response** — Into any text field
6. **Click Restore** — Original values are restored from the session

### Placeholder Format

```
[EMAIL_1], [PERSON_NAME_1], [PHONE_1], [SSN_1], [CREDIT_CARD_1], etc.
```

## API Reference

The backend exposes a REST API on `http://localhost:5001`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/detect-pii` | POST | Detect or anonymize PII in text |
| `/api/restore` | POST | Restore PII from session |
| `/api/restore-llm` | POST | Smart restore for LLM output |
| `/api/restore-global` | POST | Cross-session global restore |
| `/api/corrections/reject` | POST | Mark false positive |
| `/api/corrections/relabel` | POST | Fix entity type |
| `/api/corrections/add-missed` | POST | Add missed PII pattern |
| `/api/stats` | GET | Database statistics |

Full API documentation: [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md)

## Project Structure

```
obscura/
├── backend/                  Python backend
│   ├── obscura/              Core detection pipeline
│   │   ├── detector.py       Main PIIDetector class
│   │   ├── validators.py     Format validators (Luhn, SSN, Aadhaar)
│   │   ├── context.py        Context-based confidence adjustment
│   │   ├── corrections.py    User correction layer
│   │   ├── database.py       SQLite persistence
│   │   └── entity_types.py   PII type definitions
│   ├── api_server.py         Flask REST API
│   ├── main.py               Entry point (GUI + API)
│   ├── gui.py                Desktop GUI (Tkinter)
│   └── tests/                249 Python tests
├── extension/                Chrome Extension (Manifest V3)
│   ├── manifest.json         Extension manifest
│   ├── background/           Service worker
│   ├── content/              Content scripts + widget
│   ├── src/core/             Testable core modules
│   ├── popup/                Browser action popup
│   ├── options/              Extension settings
│   ├── side-panel/           Side panel UI
│   └── tests/                42 JS unit tests + E2E
└── docs/                     Documentation
```

## Testing

### Backend
```bash
cd backend && source venv/bin/activate
python -m pytest tests/ -v
python -m pytest tests/ --cov=obscura --cov-report=term-missing
```

### Extension
```bash
cd extension
bun install && bun test
bun run test:e2e    # End-to-end (requires Chrome)
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## AI Declaration

This project was built with the assistance of generative AI tools. See [AI_DECLARATION.md](AI_DECLARATION.md) for full transparency, including GLiNER model attribution and citations.

### GLiNER Attribution

Obscura uses [GLiNER](https://github.com/urchade/GLiNER) models from [Hugging Face](https://huggingface.co) for PII detection:
- [`urchade/gliner_multi_pii-v1`](https://huggingface.co/urchade/gliner_multi_pii-v1) — PII-specific fine-tune (Apache 2.0)
- [`urchade/gliner_small-v2.1`](https://huggingface.co/urchade/gliner_small-v2.1) — General-purpose fallback (Apache 2.0)

## Authors

- **Braeden** — [github.com/BraedenBDev](https://github.com/BraedenBDev)
- **Vivek Chiliveri** — [github.com/vivekchiliveri](https://github.com/vivekchiliveri)
- **Claude Code (Opus 4.6)** — AI development partner ([Anthropic](https://anthropic.com))

## License

[MIT](LICENSE)
