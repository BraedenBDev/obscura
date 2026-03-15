// src/core/anonymizer.js
/**
 * Anonymizer - Replaces PII with placeholders
 * Extracted from PII-widget.js for testability
 */
export class Anonymizer {
  constructor() {
    this.counters = {};  // Track counters per PII type
    this.mappings = {};  // placeholder -> original value
  }

  /**
   * Load existing mappings (for session continuity)
   * @param {Object} mappings - Existing placeholder->value map
   */
  loadMappings(mappings) {
    this.mappings = { ...mappings };

    // Extract counters from existing mappings
    for (const placeholder of Object.keys(mappings)) {
      const match = placeholder.match(/\[([A-Z_]+)_(\d+)\]/);
      if (match) {
        const type = match[1];
        const id = parseInt(match[2], 10);
        this.counters[type] = Math.max(this.counters[type] || 0, id);
      }
    }
  }

  /**
   * Generate a placeholder string
   * @param {string} type - PII type (e.g., "EMAIL")
   * @param {number} id - Counter for this type
   * @returns {string} Placeholder like "[EMAIL_1]"
   */
  generatePlaceholder(type, id) {
    return `[${type}_${id}]`;
  }

  /**
   * Get next counter for a PII type
   * @param {string} type - PII type
   * @returns {number} Next available counter
   */
  getNextCounter(type) {
    this.counters[type] = (this.counters[type] || 0) + 1;
    return this.counters[type];
  }

  /**
   * Anonymize text by replacing entities with placeholders
   * @param {string} text - Original text
   * @param {Array} entities - Detected entities with start/end positions
   * @returns {{ text: string, mappings: Object }}
   */
  anonymize(text, entities) {
    if (!text || !entities || entities.length === 0) {
      return { text, mappings: {} };
    }

    // Sort entities by position (descending) to replace from end
    const sorted = [...entities].sort((a, b) => b.start - a.start);

    let result = text;
    const newMappings = {};

    for (const entity of sorted) {
      const counter = this.getNextCounter(entity.type);
      const placeholder = this.generatePlaceholder(entity.type, counter);

      // Replace in text
      result = result.slice(0, entity.start) + placeholder + result.slice(entity.end);

      // Store mapping
      newMappings[placeholder] = entity.value;
      this.mappings[placeholder] = entity.value;
    }

    return {
      text: result,
      mappings: newMappings
    };
  }

  /**
   * Get all current mappings
   * @returns {Object} All placeholder->value mappings
   */
  getMappings() {
    return { ...this.mappings };
  }

  /**
   * Reset state
   */
  reset() {
    this.counters = {};
    this.mappings = {};
  }
}

export default Anonymizer;
