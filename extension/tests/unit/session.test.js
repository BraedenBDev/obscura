// tests/unit/session.test.js
import { SessionManager } from '../../src/core/session.js';

describe('SessionManager', () => {
  let sessionManager;

  beforeEach(() => {
    sessionManager = new SessionManager();
    // Reset chrome storage mock
    chrome.storage.local.get.mockClear();
    chrome.storage.local.set.mockClear();
  });

  describe('generateSessionId', () => {
    test('generates UUID-like string', () => {
      const id = sessionManager.generateSessionId();

      expect(id).toMatch(/^[a-f0-9-]{36}$/);
    });

    test('generates unique IDs', () => {
      const id1 = sessionManager.generateSessionId();
      const id2 = sessionManager.generateSessionId();

      expect(id1).not.toBe(id2);
    });
  });

  describe('createSession', () => {
    test('creates session with required fields', () => {
      const session = sessionManager.createSession('original text', 'anonymized text', {
        '[EMAIL_1]': 'test@test.com'
      });

      expect(session.sessionId).toBeDefined();
      expect(session.originalText).toBe('original text');
      expect(session.anonymizedText).toBe('anonymized text');
      expect(session.mappings).toEqual({ '[EMAIL_1]': 'test@test.com' });
      expect(session.timestamp).toBeDefined();
    });
  });

  describe('saveSession', () => {
    test('saves session to chrome storage', async () => {
      chrome.storage.local.get.mockImplementation((keys, cb) => {
        cb({ sessions: {} });
      });

      const session = sessionManager.createSession('orig', 'anon', {});
      await sessionManager.saveSession(session);

      expect(chrome.storage.local.set).toHaveBeenCalled();
    });
  });

  describe('getSession', () => {
    test('retrieves session by ID', async () => {
      const mockSession = {
        sessionId: 'test-123',
        mappings: { '[EMAIL_1]': 'test@test.com' }
      };

      chrome.storage.local.get.mockImplementation((keys, cb) => {
        cb({ sessions: { 'test-123': mockSession } });
      });

      const result = await sessionManager.getSession('test-123');

      expect(result).toEqual(mockSession);
    });

    test('returns null for non-existent session', async () => {
      chrome.storage.local.get.mockImplementation((keys, cb) => {
        cb({ sessions: {} });
      });

      const result = await sessionManager.getSession('non-existent');

      expect(result).toBeNull();
    });
  });

  describe('isSessionExpired', () => {
    test('returns false for recent session', () => {
      const session = {
        timestamp: Date.now() - (1000 * 60 * 60) // 1 hour ago
      };

      const result = sessionManager.isSessionExpired(session);

      expect(result).toBe(false);
    });

    test('returns true for old session (>24h)', () => {
      const session = {
        timestamp: Date.now() - (1000 * 60 * 60 * 25) // 25 hours ago
      };

      const result = sessionManager.isSessionExpired(session);

      expect(result).toBe(true);
    });
  });

  describe('cleanupExpiredSessions', () => {
    test('removes expired sessions', async () => {
      const oldTimestamp = Date.now() - (1000 * 60 * 60 * 25);
      const newTimestamp = Date.now();

      chrome.storage.local.get.mockImplementation((keys, cb) => {
        cb({
          sessions: {
            'old-session': { sessionId: 'old-session', timestamp: oldTimestamp },
            'new-session': { sessionId: 'new-session', timestamp: newTimestamp }
          }
        });
      });

      await sessionManager.cleanupExpiredSessions();

      expect(chrome.storage.local.set).toHaveBeenCalled();
      const savedData = chrome.storage.local.set.mock.calls[0][0];
      expect(savedData.sessions['old-session']).toBeUndefined();
      expect(savedData.sessions['new-session']).toBeDefined();
    });
  });
});
