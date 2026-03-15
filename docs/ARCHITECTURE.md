# Obscura — Architecture & Development History

**For Developers: Understanding What Was Built and Why**

> **Note:** This project was originally developed under the name "PII Shield" and rebranded to "Obscura" for the open-source release. Historical references to the old name may appear in this document.

This document provides an educational walkthrough of all merged pull requests, explaining the problems discovered, solutions implemented, and architectural decisions made.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [PR #1: Testing Infrastructure](#pr-1-testing-infrastructure)
3. [PR #2: PII Detection Pipeline Redesign](#pr-2-pii-detection-pipeline-redesign)
4. [PR #3: Correction UI](#pr-3-correction-ui)
5. [PR #4: Smart Session Management](#pr-4-smart-session-management)
6. [PR #6: Badge State Machine](#pr-6-badge-state-machine)
7. [Architecture Summary](#architecture-summary)
8. [Key Learnings](#key-learnings)

---

## Project Overview

Obscura is a privacy tool that detects and anonymizes Personally Identifiable Information (PII) in text before sending to AI services like ChatGPT. It consists of:

- **Python Backend** (`backend/`) — GLiNER AI model + Flask API
- **Chrome Extension** (`extension/`) — Browser integration

The development followed a systematic approach: establish testing first, then rebuild the detection pipeline, add user feedback mechanisms, and finally bulletproof the UI.

---

## PR #1: Testing Infrastructure

**Merged:** 2026-01-24 | **Files:** 25 | **Lines:** +4,250

### The Problem

The codebase had **zero tests**. This meant:
- No confidence that changes wouldn't break existing functionality
- Refactoring was risky
- No automated quality gates on PRs

### What Was Built

#### 1. Core Module Extraction (TDD Approach)

The monolithic `PII-widget.js` (1,663 lines) mixed UI, events, and business logic. We extracted pure functions into testable modules:

```
src/core/
├── detector.js    # PII detection (placeholders + 6 regex patterns)
├── anonymizer.js  # Text anonymization with placeholder generation
├── restorer.js    # Placeholder → original value restoration
├── session.js     # Session lifecycle with 24-hour expiry
└── index.js       # Convenient exports
```

**Why extract?** You can't unit test code that's tangled with DOM manipulation. Pure functions with clear inputs/outputs are testable in isolation.

#### 2. Test Coverage

| Component | Tests | Coverage |
|-----------|-------|----------|
| detector.test.js | 13 | Placeholder detection, regex patterns |
| anonymizer.test.js | 8 | Placeholder generation, text replacement |
| restorer.test.js | 7 | Restoration, missing mapping handling |
| session.test.js | 9 | CRUD, expiration, cleanup |
| api-client.test.js | 5 | Health check, timeout handling |

**Total: 42 unit tests, 90% line coverage**

#### 3. E2E Tests with Playwright

```javascript
// smoke.spec.js - Verify extension loads
test('extension loads with valid ID', async ({ context }) => {
  const extensionId = await getExtensionId(context);
  expect(extensionId).toBeTruthy();
});

// detection.spec.js - Verify PII detection works
test('detects email in text field', async ({ page }) => {
  await page.fill('textarea', 'Contact john@example.com');
  // Verify PII indicator appears
});
```

#### 4. CI/CD with GitHub Actions

Every push/PR now runs:
1. Unit tests (`bun test`)
2. E2E tests (`bun run test:e2e`)
3. Coverage reporting

### Key Learning

> **"Tests are the foundation for safely improving everything else."**
>
> Without tests, every refactor is a gamble. With tests, you can move fast and break nothing.

---

## PR #2: PII Detection Pipeline Redesign

**Merged:** 2026-01-25 | **Files:** 19 | **Lines:** +10,500

### The Problems Discovered

| Problem | Example | Root Cause |
|---------|---------|------------|
| **False positives** | "Email:" detected as PII | No label filtering |
| **Partial matches** | "123 Main" instead of full address | Boundary detection |
| **Wrong classifications** | Phone labeled as SSN | Overlapping model labels |
| **Format blindness** | Missing IBAN, Aadhaar | Limited regex patterns |
| **No learning** | Same false positive every time | No user feedback loop |

### Architecture Solution

```
┌─────────────────────────────────────────────────────────────┐
│                    PIIDetector                               │
│  (Main orchestrator - detector.py)                          │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│   GLiNER      │    │  Validators   │    │   Context     │
│  Extraction   │───▶│   Layer       │───▶│   Analyzer    │
│               │    │               │    │               │
└───────────────┘    └───────────────┘    └───────────────┘
                              │
                              ▼
                     ┌───────────────┐
                     │  Corrections  │
                     │    Layer      │
                     └───────────────┘
                              │
                              ▼
                     ┌───────────────┐
                     │   SQLite      │
                     │   Database    │
                     └───────────────┘
```

### What Was Built

#### 1. Entity Type Consolidation (`entity_types.py`)

**Before:** 24+ overlapping labels (`email`, `email_address`, `e-mail`, `electronic_mail`)

**After:** 10 canonical types with natural language descriptions:

```python
ENTITY_TYPES = {
    "person_name": "person's full name, first name, or last name",
    "email": "email address",
    "phone": "phone number, mobile number, or telephone",
    "government_id": "SSN, passport number, driver license, national ID",
    "financial_account": "credit card, bank account, routing number, IBAN",
    # ... 5 more
}
```

**Why?** Zero-shot models like GLiNER work better with descriptive labels. "SSN, passport number, driver license" gives more context than just "government_id".

#### 2. Validation Layer (`validators.py`)

**Purpose:** Verify detected entities actually match expected formats.

| Validator | What It Checks | Confidence Adjustment |
|-----------|----------------|----------------------|
| `LuhnValidator` | Credit card checksum | +0.2 if valid |
| `SSNValidator` | Valid SSN structure (no 000, 666, 900+) | +0.15 if valid |
| `AadhaarValidator` | Indian 12-digit Verhoeff checksum | +0.2 if valid |
| `NotLabelValidator` | Reject "Email:", "Phone:" | Reject entirely |
| `MinLengthValidator` | Email < 5 chars, Phone < 7 | Reject entirely |

**The Luhn Algorithm (Credit Card Validation):**

```python
def _luhn_check(self, digits: str) -> bool:
    """
    1. From rightmost digit, double every second digit
    2. If doubling produces > 9, subtract 9
    3. Sum all digits
    4. Valid if sum % 10 == 0

    Example: 4532015112830366
    Double every 2nd: 4,10,3,4,0,2,5,2,1,4,8,6,0,6,6,12
    Subtract 9 from >9: 4,1,3,4,0,2,5,2,1,4,8,6,0,6,6,3
    Sum: 55 → 55 % 10 ≠ 0 → Invalid
    """
```

#### 3. Context Analyzer (`context.py`)

**Purpose:** Adjust confidence based on surrounding text.

```python
# "My SSN is 123-45-6789" → HIGH confidence (boost)
# "Reference: 123-45-6789" → LOWER confidence (penalize)

CONTEXT_SIGNALS = {
    "government_id": {
        "boost": ["ssn", "social security", "tax id"],      # +0.15
        "penalize": ["reference", "order", "invoice"],       # -0.15
    },
}
```

**Key Learning:** Context is a MODIFIER, not a detector. We don't detect PII based on context alone—we adjust confidence of existing detections.

#### 4. SQLite Database (`database.py`)

**Before:** `sessions.json` - unbounded growth, no indexing, no concurrent access

**After:** Proper relational schema:

```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    original_text TEXT NOT NULL,
    anonymized_text TEXT NOT NULL,
    expires_at TIMESTAMP
);

CREATE TABLE mappings (
    session_id TEXT REFERENCES sessions(session_id),
    placeholder TEXT NOT NULL,
    original_value TEXT NOT NULL,
    entity_type TEXT NOT NULL
);

CREATE TABLE user_corrections (
    correction_type TEXT NOT NULL,  -- 'rejection', 'relabel', 'boundary', 'missed_pii'
    original_text TEXT NOT NULL,
    context_hash TEXT,              -- For context-aware matching
    ...
);
```

**Security Note:** Always use parameterized queries:

```python
# WRONG - SQL injection vulnerable
cursor.execute(f"SELECT * FROM sessions WHERE id = '{user_input}'")

# RIGHT - Parameterized query
cursor.execute("SELECT * FROM sessions WHERE id = ?", (user_input,))
```

### Key Learning

> **"Detection is a pipeline, not a single step."**
>
> Raw AI output needs validation, context analysis, and user corrections to be reliable.

---

## PR #3: Correction UI

**Merged:** 2026-01-25 | **Files:** 21 | **Lines:** +7,000

### The Problem

Users saw false positives but couldn't teach the system. The only option was to ignore them or add brittle regex patterns.

### What Was Built

A gear button (⚙️) on the PII indicator badge opens a correction panel:

```
┌─────────────────────────────────────┐
│ Detected Entities          [Close] │
├─────────────────────────────────────┤
│ EMAIL: john@example.com             │
│   [Reject] [Relabel ▼]              │
│                                     │
│ PHONE: 555-1234                     │
│   [Reject] [Relabel ▼]              │
├─────────────────────────────────────┤
│ Missed something? Select text and:  │
│   [Add Selected as PII ▼]           │
└─────────────────────────────────────┘
```

#### Four Correction Types

| Type | Use Case | API Endpoint |
|------|----------|--------------|
| **Rejection** | "john@example.com" is not PII here | `/api/corrections/reject` |
| **Relabel** | Phone was labeled as SSN | `/api/corrections/relabel` |
| **Boundary** | "123 Main" should be "123 Main St" | `/api/corrections/boundary` |
| **Missed PII** | Model missed an employee ID | `/api/corrections/add-missed` |

### Key Learning

> **"Users are the best validators."**
>
> A system that learns from user feedback will always outperform one that doesn't.

---

## PR #4: Smart Session Management

**Merged:** 2026-01-26 | **Files:** 12 | **Lines:** +1,900

### The Problem

1. **Cross-field restore broken:** Anonymize in ChatGPT, paste response to Gmail → Restore button doesn't work
2. **Formatting lost:** Newlines disappeared in contentEditable fields
3. **Re-anonymization loop:** Clicking "Anonymize" twice would detect `[EMAIL_1]` as new PII

### What Was Built

#### 1. Cross-Field Session Matching

```javascript
// Session history stores anonymized text patterns
sessionHistory = [
  { sessionId: "abc", placeholders: ["[EMAIL_1]", "[PHONE_2]"], ... }
];

// When user focuses a field, check if text contains known placeholders
function findMatchingSession(text) {
  const placeholders = extractPlaceholders(text);  // Find [TYPE_N] patterns
  for (const session of sessionHistory) {
    const matchCount = countMatches(placeholders, session.placeholders);
    if (matchCount >= threshold) {
      return session;  // Found matching session!
    }
  }
  return null;
}
```

#### 2. Formatting Preservation

**Problem:** `getText()` used `textContent` which strips formatting.

**Solution:** Use `innerText` which preserves line breaks:

```javascript
function getText(element) {
  if (element.tagName === 'TEXTAREA' || element.tagName === 'INPUT') {
    return element.value;
  }
  // innerText preserves visual line breaks
  return element.innerText;
}
```

#### 3. Placeholder Filtering

```python
def _filter_placeholders(self, text: str, entities: List[Entity]) -> List[Entity]:
    """Remove entities that are actually our placeholders."""
    placeholder_pattern = re.compile(r'\[([A-Z_]+)_\d+\]')
    return [e for e in entities if not placeholder_pattern.match(e.text)]
```

### Key Learning

> **"State must flow with the user, not stay trapped in one context."**
>
> The session ID is just a reference. Placeholders are the actual portable identity.

---

## PR #6: Badge State Machine

**Merged:** 2026-01-28 | **Files:** 14 | **Lines:** +5,100

### The Problem

The PIIIndicator badge disappeared when:
- Clicking out of a text field
- Opening extension options
- Switching tabs
- Any focus change

Root cause: A one-time blur listener that hid the badge and never re-evaluated.

### What Was Built

#### 1. State Machine Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        STATES                                │
├─────────┬─────────────────────────────────────┬─────────────┤
│  IDLE   │ No text or text < 3 chars           │ Badge hidden│
│ SCANNING│ Calling backend                      │ Spinner     │
│ DETECTED│ Fresh PII found                      │ "X PII" btn │
│ MASKED  │ Text contains placeholders           │ "Restore"   │
│ MIXED   │ Both new PII AND placeholders        │ Both btns   │
└─────────┴─────────────────────────────────────┴─────────────┘

TRANSITIONS:
  IDLE → SCANNING      : focus/input on field with text ≥3 chars
  SCANNING → DETECTED  : backend returns PII entities
  SCANNING → MASKED    : no new PII, but placeholders in text
  ANY → IDLE           : field loses focus (badge hides)
  IDLE → DETECTED/MASKED : field regains focus (re-evaluate)
```

**Key Principle:** State is determined by **text content analysis**, not by event history.

#### 2. Unified refreshBadge() Function

```javascript
async function refreshBadge(element) {
  // 1. Validate element
  if (!element || !isEditableElement(element)) {
    PIIIndicator.hide();
    return { state: 'IDLE' };
  }

  // 2. Get text content
  const text = getText(element);
  if (!text || text.length < 3) {
    PIIIndicator.hide();
    return { state: 'IDLE' };
  }

  // 3. Check for placeholders (LOCAL - instant)
  const placeholders = extractPlaceholders(text);
  const registryMatches = await PlaceholderRegistry.lookupPlaceholders(placeholders);

  // 4. Check for fresh PII (BACKEND - async)
  const entities = await detectPIIViaBackend(text);

  // 5. Determine state and show badge
  if (entities.length > 0 && registryMatches.length > 0) {
    return { state: 'MIXED', ... };
  } else if (registryMatches.length > 0) {
    return { state: 'MASKED', ... };
  } else if (entities.length > 0) {
    return { state: 'DETECTED', ... };
  } else {
    return { state: 'IDLE' };
  }
}
```

#### 3. Global Placeholder Registry

```javascript
// Storage schema (chrome.storage.local)
{
  "pii_counter": 47,           // Always incrementing
  "pii_registry": {
    "[EMAIL_1]": { value: "john@example.com", sessionId: "abc123" },
    "[PHONE_2]": { value: "555-1234", sessionId: "abc123" }
  }
}
```

**Cross-tab sync:**

```javascript
chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName === 'local' && changes.pii_registry) {
    // Another tab masked/restored - refresh our badge
    refreshBadge(state.activeElement);
  }
});
```

#### 4. Removed Hacks

- ❌ `showProtectedUntil` - Arbitrary 500ms protection period
- ❌ One-time blur listener - Caused badge to never reappear
- ✅ Document-level `focusout` handler - Properly manages visibility

### Key Learning

> **"Event-driven state is fragile. Content-driven state is robust."**
>
> Don't track "what happened" - analyze "what exists now" on every interaction.

---

## Architecture Summary

### Backend Flow

```
User Text
    │
    ▼
┌─────────────┐
│  GLiNER AI  │ ──▶ Raw entities with confidence scores
└─────────────┘
    │
    ▼
┌─────────────┐
│ Validators  │ ──▶ Filter false positives, adjust confidence
└─────────────┘
    │
    ▼
┌─────────────┐
│  Context    │ ──▶ Boost/penalize based on surrounding text
│  Analyzer   │
└─────────────┘
    │
    ▼
┌─────────────┐
│ Corrections │ ──▶ Apply user feedback (rejections, relabels)
└─────────────┘
    │
    ▼
┌─────────────┐
│  SQLite DB  │ ──▶ Persist sessions, mappings, corrections
└─────────────┘
```

### Chrome Extension Flow

```
User types in text field
    │
    ▼
┌─────────────────┐
│  refreshBadge() │ ──▶ Unified state machine
└─────────────────┘
    │
    ├──▶ Extract placeholders (local, instant)
    │
    ├──▶ Lookup in registry (cross-tab)
    │
    └──▶ Call backend API (async)
    │
    ▼
┌─────────────────┐
│  PIIIndicator   │ ──▶ Show badge with appropriate buttons
└─────────────────┘
    │
    ▼
User clicks Mask/Restore
    │
    ▼
┌─────────────────┐
│ Register/Unregister │ ──▶ Update global placeholder registry
│ Placeholders        │
└─────────────────────┘
```

---

## Key Learnings

### 1. Test First, Refactor Safely

Without tests, you're flying blind. The testing infrastructure (PR #1) enabled all subsequent refactors.

### 2. Detection is a Pipeline

Raw AI output isn't reliable enough. Layer validation, context analysis, and user corrections.

### 3. State Should Be Derived, Not Tracked

Don't maintain complex event histories. Analyze current content to determine state.

### 4. Users Are Part of the System

Build feedback loops. A system that learns from corrections will continuously improve.

### 5. Cross-Context Portability

Data (placeholders) must flow with users across tabs, fields, and sessions. Use global registries with sync listeners.

### 6. Formatting Matters

`textContent` vs `innerText` can break user trust. Preserve what users see.

---

## Files Reference

| Directory | Purpose |
|-----------|---------|
| `backend/obscura/` | Python detection pipeline |
| `backend/tests/` | Backend test suite (249 tests) |
| `extension/src/core/` | Extracted testable modules |
| `extension/content/` | Main widget and UI |
| `extension/tests/` | Frontend test suite (42 tests) |
| `docs/` | Documentation |

---

*Document generated: 2026-01-28*
*Total PRs merged: 5*
*Total lines changed: ~30,000*
