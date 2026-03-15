// src/core/detector.js
/**
 * PII Detector - Handles local PII pattern detection
 * Extracted from PII-widget.js for testability
 */
export class PIIDetector {
  constructor() {
    // Matches [TYPE_ID] format e.g., [PERSON_1], [EMAIL_2], [CREDIT_CARD_3]
    this.placeholderPattern = /\[([A-Z_]+)_(\d+)\]/g;

    // Regex patterns for PII detection
    this.patterns = {
      EMAIL: /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/g,
      SSN: /\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b/g,
      PHONE: /\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b/g,
      CREDIT_CARD: /\b(?:\d{4}[-\s]?){3}\d{4}\b/g,
      IP_ADDRESS: /\b(?:\d{1,3}\.){3}\d{1,3}\b/g,
      DATE: /\b(?:\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2})\b/g,
    };
  }

  /**
   * Detect existing placeholders in text
   * @param {string} text - Text to scan
   * @returns {string[]} Array of placeholder strings found
   */
  detectPlaceholders(text) {
    if (!text) return [];
    const matches = text.match(this.placeholderPattern) || [];
    return matches;
  }

  /**
   * Parse a placeholder string into its components
   * @param {string} placeholder - e.g., "[EMAIL_1]"
   * @returns {{ type: string, id: number } | null}
   */
  parsePlaceholder(placeholder) {
    const match = placeholder.match(/\[([A-Z_]+)_(\d+)\]/);
    if (!match) return null;

    return {
      type: match[1],
      id: parseInt(match[2], 10)
    };
  }

  /**
   * Detect PII using regex patterns (local fallback)
   * @param {string} text - Text to scan
   * @returns {Array<{type: string, value: string, start: number, end: number}>}
   */
  detectWithRegex(text) {
    if (!text) return [];

    const results = [];

    for (const [type, pattern] of Object.entries(this.patterns)) {
      // Reset regex state
      pattern.lastIndex = 0;

      let match;
      while ((match = pattern.exec(text)) !== null) {
        results.push({
          type,
          value: match[0],
          start: match.index,
          end: match.index + match[0].length
        });
      }
    }

    // Sort by position
    results.sort((a, b) => a.start - b.start);

    return results;
  }
}

export default PIIDetector;
