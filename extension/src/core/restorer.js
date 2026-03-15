// src/core/restorer.js
/**
 * Restorer - Converts placeholders back to original values
 * Extracted from PII-widget.js for testability
 */
export class Restorer {
  constructor() {
    this.placeholderPattern = /\[([A-Z_]+)_(\d+)\]/g;
  }

  /**
   * Find all placeholders in text
   * @param {string} text - Text to scan
   * @returns {string[]} Array of placeholder strings
   */
  findPlaceholders(text) {
    if (!text) return [];
    const matches = text.match(this.placeholderPattern) || [];
    return [...new Set(matches)]; // Deduplicate
  }

  /**
   * Restore placeholders to original values
   * @param {string} text - Text with placeholders
   * @param {Object} mappings - placeholder->value map
   * @returns {{ text: string, restored: number, notFound: string[], statistics: Object }}
   */
  restore(text, mappings) {
    if (!text) {
      return {
        text: '',
        restored: 0,
        notFound: [],
        statistics: { total: 0, restored: 0, missing: 0 }
      };
    }

    const placeholders = this.findPlaceholders(text);
    let result = text;
    let restoredCount = 0;
    const notFound = [];

    for (const placeholder of placeholders) {
      if (mappings && mappings[placeholder]) {
        result = result.split(placeholder).join(mappings[placeholder]);
        restoredCount++;
      } else {
        notFound.push(placeholder);
      }
    }

    return {
      text: result,
      restored: restoredCount,
      notFound,
      statistics: {
        total: placeholders.length,
        restored: restoredCount,
        missing: notFound.length
      }
    };
  }
}

export default Restorer;
