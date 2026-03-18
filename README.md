<div align="center">

<p align="center">
  <img src="docs/images/logo-horizontal.svg" alt="Obscura logo" width="360" />
</p>

<br />
<br />

**Real-time PII detection and anonymization for AI-powered workflows.**

Detect and mask sensitive data before it reaches AI services like ChatGPT or Claude — then restore original values when the AI responds. 100% local. Nothing leaves your machine.

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![Chrome Extension](https://img.shields.io/badge/Chrome-Manifest%20V3-4285F4?style=flat&logo=googlechrome&logoColor=white)](https://developer.chrome.com/docs/extensions/mv3/)
[![GLiNER](https://img.shields.io/badge/GLiNER-NER%20Model-FF6F00?style=flat&logo=huggingface&logoColor=white)](https://github.com/urchade/GLiNER)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat)](LICENSE)
[![Tests: 331](https://img.shields.io/badge/Tests-331%20passing-brightgreen?style=flat)](#testing)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat)](CONTRIBUTING.md)

[How It Works](#how-it-works) · [Installation](#installation) · [API Reference](#api-reference) · [Contributing](CONTRIBUTING.md)

</div>

---

## The Problem

Every time you paste client names, email addresses, or phone numbers into an AI chat, that data is sent to a third-party server. Obscura sits between you and the AI — masking PII on the way out, restoring it on the way back — so you get the full power of AI without the data exposure.

```
Original:  "Contact John Smith at john@example.com or 555-123-4567"
Masked:    "Contact [PERSON_NAME_1] at [EMAIL_1] or [PHONE_1]"
Restored:  AI response with original values seamlessly back in place
```

## How It Works

```
  ┌─────────────────────┐        ┌───────────────────────────────┐
  │   Chrome Extension  │        │       Python Backend           │
  │                     │  HTTP  │       (localhost:5001)         │
  │   Text field with   │───────▶│                               │
  │   PII detected      │        │   ┌───────────────────────┐   │
  │                     │◀───────│   │  1. GLiNER AI Model   │   │
  │   ● Floating badge  │        │   │  2. Regex Patterns    │   │
  │   ● Mask / Restore  │        │   │  3. Format Validators │   │
  │   ● Cross-tab sync  │        │   │  4. Context Analyzer  │   │
  │   ● Correction UI   │        │   │  5. User Corrections  │   │
  └─────────────────────┘        │   └───────────────────────┘   │
                                 │              ↓                 │
                                 │       SQLite (local)           │
                                 └───────────────────────────────┘
```

1. You type or paste text into any web form
2. The Chrome extension sends it to the local backend for PII detection
3. A multi-layer pipeline (AI model → regex → validators → context) identifies sensitive entities
4. Detected PII is replaced with typed placeholders like `[EMAIL_1]`, `[PHONE_1]`
5. You send the safe text to your AI service
6. When the AI responds with placeholders, hit Restore — original values are swapped back in

## Features

| | Feature | Detail |
|---|---------|--------|
| 🧠 | **AI-powered detection** | [GLiNER](https://github.com/urchade/GLiNER) NER models from Hugging Face for intelligent entity recognition |
| 🔗 | **Multi-layer pipeline** | GLiNER + regex patterns + format validators (Luhn, SSN, Aadhaar) + context analysis |
| 📚 | **Local learning** | Your corrections improve detection over time, stored locally in SQLite |
| 🔄 | **Session management** | Cross-field, cross-tab restoration via a global placeholder registry |
| 🏷️ | **16 PII types** | Names, emails, phones, SSNs, credit cards, IBANs, passports, addresses, and more |
| 🔒 | **100% local** | No cloud services. No telemetry. Your data never leaves your machine |

## Installation

### Prerequisites

- **Python 3.12+** with pip
- **Google Chrome** 114+
- **Node.js 18+** (extension development only)

### 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate      # macOS/Linux
# or: venv\Scripts\activate   # Windows

pip install -r requirements.txt
```

The GLiNER model downloads automatically on first run (~100MB from Hugging Face Hub).

### 2. Start the backend

```bash
cd backend
source venv/bin/activate
python main.py
```

This launches the desktop GUI and API server on `http://localhost:5001`.

**macOS shortcut:** double-click `backend/Run Obscura.command`

### 3. Chrome extension

1. Open `chrome://extensions/`
2. Enable **Developer mode** (top right)
3. Click **Load unpacked** → select the `extension/` directory
4. Pin the Obscura icon in your toolbar

## Usage

1. **Keep the backend running** — desktop app or `python main.py`
2. **Browse normally** — Obscura's badge appears on text fields when PII is detected
3. **Click Mask** — PII is replaced with `[TYPE_N]` placeholders
4. **Paste into AI** — send the anonymized text to ChatGPT, Claude, etc.
5. **Paste AI response** — into any text field
6. **Click Restore** — original values are swapped back in from the session

### Placeholder format

```
[EMAIL_1]  [PERSON_NAME_1]  [PHONE_1]  [SSN_1]  [CREDIT_CARD_1]  ...
```

## API Reference

The backend exposes a REST API on `localhost:5001`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/detect-pii` | POST | Detect and anonymize PII in text |
| `/api/restore` | POST | Restore PII from session |
| `/api/restore-llm` | POST | Smart restore for LLM output |
| `/api/restore-global` | POST | Cross-session global restore |
| `/api/corrections/reject` | POST | Mark false positive |
| `/api/corrections/relabel` | POST | Fix entity type |
| `/api/corrections/add-missed` | POST | Add missed PII pattern |
| `/api/stats` | GET | Database statistics |

Full documentation: [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md)

## Project Structure

```
obscura/
├── backend/                  # Python backend
│   ├── obscura/              # Core detection pipeline
│   │   ├── detector.py       #   Main PIIDetector class
│   │   ├── validators.py     #   Format validators (Luhn, SSN, Aadhaar)
│   │   ├── context.py        #   Context-based confidence adjustment
│   │   ├── corrections.py    #   User correction layer
│   │   ├── database.py       #   SQLite persistence
│   │   └── entity_types.py   #   PII type definitions
│   ├── api_server.py         # Flask REST API
│   ├── main.py               # Entry point (GUI + API)
│   ├── gui.py                # Desktop GUI (Tkinter)
│   └── tests/                # 289 Python tests
├── extension/                # Chrome Extension (Manifest V3)
│   ├── manifest.json         #   Extension manifest
│   ├── background/           #   Service worker
│   ├── content/              #   Content scripts + widget
│   ├── src/core/             #   Testable core modules
│   ├── popup/                #   Browser action popup
│   ├── options/              #   Extension settings
│   ├── side-panel/           #   Side panel UI
│   └── tests/                #   42 JS unit + E2E tests
└── docs/                     # Documentation
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Detection | GLiNER (Hugging Face), regex, Luhn/SSN/Aadhaar validators |
| Backend | Python 3.12, Flask, SQLite |
| Extension | Chrome Manifest V3, vanilla JS |
| Desktop | Tkinter GUI |
| Testing | pytest (289 tests), Bun test + E2E (42 tests) |

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

## Roadmap

- [x] Multi-layer PII detection pipeline (GLiNER + regex + validators + context)
- [x] Chrome extension with floating badge UI
- [x] Cross-tab session management and global restore
- [x] User correction learning system
- [x] Desktop GUI with system tray
- [x] 331 tests across backend and extension
- [ ] Firefox extension
- [ ] VS Code extension
- [ ] Configurable entity type allowlists
- [ ] Batch file processing mode

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and PR guidelines.

## AI Declaration

This project was built with the assistance of generative AI tools. See [AI_DECLARATION.md](AI_DECLARATION.md) for full transparency.

### GLiNER Attribution

Obscura uses [GLiNER](https://github.com/urchade/GLiNER) models from [Hugging Face](https://huggingface.co) for PII detection:

- [`urchade/gliner_multi_pii-v1`](https://huggingface.co/urchade/gliner_multi_pii-v1) — PII-specific fine-tune (Apache 2.0)
- [`urchade/gliner_small-v2.1`](https://huggingface.co/urchade/gliner_small-v2.1) — General-purpose fallback (Apache 2.0)

## Authors

- **Braeden** — [github.com/BraedenBDev](https://github.com/BraedenBDev)
- **Vivek Chiliveri** — [github.com/vivekchiliveri](https://github.com/vivekchiliveri)
- **Claude Code (Opus 4.6)** — AI development partner ([Anthropic](https://anthropic.com))

## License

MIT — see [LICENSE](LICENSE) for details.
