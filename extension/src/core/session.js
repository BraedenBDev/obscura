// src/core/session.js
/**
 * Session Manager - Handles anonymization session lifecycle
 * Extracted from PII-widget.js for testability
 *
 * Storage Schema:
 * - sessions: { sessionId: { sessionId, originalText, anonymizedText, mappings, timestamp } }
 * - pii_counter: number (global incrementing counter for placeholder IDs)
 * - pii_registry: { "[TYPE_N]": { value, sessionId, created } }
 */
export class SessionManager {
  constructor() {
    this.SESSION_EXPIRY_MS = 24 * 60 * 60 * 1000; // 24 hours
  }

  // ============================================
  // GLOBAL PLACEHOLDER REGISTRY
  // ============================================

  /**
   * Get the current placeholder counter value
   * @returns {Promise<number>}
   */
  async getCounter() {
    return new Promise((resolve) => {
      chrome.storage.local.get('pii_counter', (result) => {
        resolve(result.pii_counter || 0);
      });
    });
  }

  /**
   * Set the placeholder counter value
   * @param {number} value
   */
  async setCounter(value) {
    return new Promise((resolve) => {
      chrome.storage.local.set({ pii_counter: value }, resolve);
    });
  }

  /**
   * Get the next placeholder ID for a given type
   * Atomically increments counter and returns formatted placeholder
   * @param {string} type - e.g., "EMAIL", "PHONE", "NAME"
   * @returns {Promise<string>} - e.g., "[EMAIL_47]"
   */
  async getNextPlaceholderId(type) {
    const counter = await this.getCounter();
    const nextId = counter + 1;
    await this.setCounter(nextId);
    return `[${type.toUpperCase()}_${nextId}]`;
  }

  /**
   * Get the global placeholder registry
   * @returns {Promise<Object>}
   */
  async getRegistry() {
    return new Promise((resolve) => {
      chrome.storage.local.get('pii_registry', (result) => {
        resolve(result.pii_registry || {});
      });
    });
  }

  /**
   * Register placeholders in the global registry
   * @param {Object} mappings - { "[EMAIL_1]": "john@example.com", ... }
   * @param {string} sessionId - The session these placeholders belong to
   */
  async registerPlaceholders(mappings, sessionId) {
    const registry = await this.getRegistry();
    const now = Date.now();

    for (const [placeholder, value] of Object.entries(mappings)) {
      registry[placeholder] = {
        value,
        sessionId,
        created: now
      };
    }

    return new Promise((resolve) => {
      chrome.storage.local.set({ pii_registry: registry }, resolve);
    });
  }

  /**
   * Unregister all placeholders belonging to a session
   * Called when user restores original text
   * @param {string} sessionId
   */
  async unregisterPlaceholders(sessionId) {
    const registry = await this.getRegistry();
    const updatedRegistry = {};

    for (const [placeholder, data] of Object.entries(registry)) {
      if (data.sessionId !== sessionId) {
        updatedRegistry[placeholder] = data;
      }
    }

    return new Promise((resolve) => {
      chrome.storage.local.set({ pii_registry: updatedRegistry }, resolve);
    });
  }

  /**
   * Lookup placeholders in the registry
   * @param {string[]} placeholders - Array of placeholders to look up, e.g., ["[EMAIL_1]", "[PHONE_2]"]
   * @returns {Promise<Object[]>} - Array of { placeholder, value, sessionId }
   */
  async lookupPlaceholders(placeholders) {
    if (!placeholders || placeholders.length === 0) {
      return [];
    }

    const registry = await this.getRegistry();
    const matches = [];

    for (const placeholder of placeholders) {
      if (registry[placeholder]) {
        matches.push({
          placeholder,
          value: registry[placeholder].value,
          sessionId: registry[placeholder].sessionId
        });
      }
    }

    return matches;
  }

  /**
   * Get all mappings for placeholders (for restore operation)
   * @param {string[]} placeholders - Array of placeholders
   * @returns {Promise<Object>} - { "[EMAIL_1]": "john@example.com", ... }
   */
  async getMappingsForPlaceholders(placeholders) {
    const matches = await this.lookupPlaceholders(placeholders);
    const mappings = {};

    for (const match of matches) {
      mappings[match.placeholder] = match.value;
    }

    return mappings;
  }

  /**
   * Clean up registry entries from expired sessions
   */
  async cleanupExpiredRegistry() {
    const sessions = await this.getAllSessions();
    const registry = await this.getRegistry();
    const validSessionIds = new Set(Object.keys(sessions));
    const updatedRegistry = {};

    for (const [placeholder, data] of Object.entries(registry)) {
      // Keep if session still exists and isn't expired
      if (validSessionIds.has(data.sessionId)) {
        const session = sessions[data.sessionId];
        if (!this.isSessionExpired(session)) {
          updatedRegistry[placeholder] = data;
        }
      }
    }

    return new Promise((resolve) => {
      chrome.storage.local.set({ pii_registry: updatedRegistry }, resolve);
    });
  }

  // ============================================
  // SESSION MANAGEMENT (existing methods below)
  // ============================================

  /**
   * Generate a UUID-like session ID
   * @returns {string}
   */
  generateSessionId() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = Math.random() * 16 | 0;
      const v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  }

  /**
   * Create a new session object
   * @param {string} originalText
   * @param {string} anonymizedText
   * @param {Object} mappings
   * @returns {Object} Session object
   */
  createSession(originalText, anonymizedText, mappings) {
    return {
      sessionId: this.generateSessionId(),
      originalText,
      anonymizedText,
      mappings,
      timestamp: Date.now(),
      entityCount: Object.keys(mappings).length
    };
  }

  /**
   * Save session to Chrome storage
   * @param {Object} session
   */
  async saveSession(session) {
    return new Promise((resolve) => {
      chrome.storage.local.get('sessions', (result) => {
        const sessions = result.sessions || {};
        sessions[session.sessionId] = session;
        chrome.storage.local.set({ sessions }, resolve);
      });
    });
  }

  /**
   * Get session by ID
   * @param {string} sessionId
   * @returns {Object|null}
   */
  async getSession(sessionId) {
    return new Promise((resolve) => {
      chrome.storage.local.get('sessions', (result) => {
        const sessions = result.sessions || {};
        resolve(sessions[sessionId] || null);
      });
    });
  }

  /**
   * Get all sessions
   * @returns {Object}
   */
  async getAllSessions() {
    return new Promise((resolve) => {
      chrome.storage.local.get('sessions', (result) => {
        resolve(result.sessions || {});
      });
    });
  }

  /**
   * Check if session is expired
   * @param {Object} session
   * @returns {boolean}
   */
  isSessionExpired(session) {
    if (!session || !session.timestamp) return true;
    return (Date.now() - session.timestamp) > this.SESSION_EXPIRY_MS;
  }

  /**
   * Remove expired sessions from storage and clean registry
   */
  async cleanupExpiredSessions() {
    const sessions = await this.getAllSessions();
    const validSessions = {};
    const expiredSessionIds = [];

    for (const [id, session] of Object.entries(sessions)) {
      if (!this.isSessionExpired(session)) {
        validSessions[id] = session;
      } else {
        expiredSessionIds.push(id);
      }
    }

    // Clean up registry entries from expired sessions
    await this.cleanupExpiredRegistry();

    return new Promise((resolve) => {
      chrome.storage.local.set({ sessions: validSessions }, resolve);
    });
  }

  /**
   * Delete a specific session and its placeholders
   * @param {string} sessionId
   */
  async deleteSession(sessionId) {
    // First unregister placeholders
    await this.unregisterPlaceholders(sessionId);

    // Then delete session
    const sessions = await this.getAllSessions();
    delete sessions[sessionId];

    return new Promise((resolve) => {
      chrome.storage.local.set({ sessions }, resolve);
    });
  }
}

export default SessionManager;
