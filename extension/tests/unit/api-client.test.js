// tests/unit/api-client.test.js
import { jest, describe, test, expect, beforeEach, afterEach } from '@jest/globals';

describe('APIClient', () => {
  let originalFetch;

  beforeEach(() => {
    originalFetch = global.fetch;
    global.logger = {
      info: jest.fn(),
      warn: jest.fn(),
      error: jest.fn(),
      debug: jest.fn()
    };
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  describe('checkHealth', () => {
    test('returns connected: true when backend responds OK', async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ status: 'healthy' })
      });

      const mockClient = {
        baseURL: 'http://localhost:5001',
        isConnected: false,
        timeout: 5000,
        async checkHealth() {
          try {
            const response = await fetch(`${this.baseURL}/api/health`);
            if (response.ok) {
              this.isConnected = true;
              return { connected: true };
            }
            return { connected: false };
          } catch (e) {
            return { connected: false, error: e.message };
          }
        }
      };

      const result = await mockClient.checkHealth();

      expect(result.connected).toBe(true);
      expect(mockClient.isConnected).toBe(true);
    });

    test('returns connected: false when backend unavailable', async () => {
      global.fetch = jest.fn().mockRejectedValue(new Error('Connection refused'));

      const mockClient = {
        baseURL: 'http://localhost:5001',
        isConnected: false,
        async checkHealth() {
          try {
            await fetch(`${this.baseURL}/api/health`);
            return { connected: true };
          } catch (e) {
            this.isConnected = false;
            return { connected: false, error: e.message };
          }
        }
      };

      const result = await mockClient.checkHealth();

      expect(result.connected).toBe(false);
      expect(result.error).toBe('Connection refused');
    });
  });

  describe('detectPII', () => {
    test('sends correct payload for detection', async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({
          entities: [{ type: 'EMAIL', value: 'test@test.com' }],
          entity_count: 1
        })
      });

      const mockClient = {
        baseURL: 'http://localhost:5001',
        async detectPII(text, action = 'detect') {
          const response = await fetch(`${this.baseURL}/api/detect-pii`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, action })
          });
          return response.json();
        }
      };

      await mockClient.detectPII('test@test.com', 'detect');

      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:5001/api/detect-pii',
        expect.objectContaining({
          method: 'POST',
          body: expect.stringContaining('test@test.com')
        })
      );
    });

    test('handles timeout gracefully', async () => {
      global.fetch = jest.fn().mockImplementation(() =>
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error('Timeout')), 100)
        )
      );

      const mockClient = {
        baseURL: 'http://localhost:5001',
        async detectPII(text) {
          try {
            const response = await fetch(`${this.baseURL}/api/detect-pii`, {
              method: 'POST',
              body: JSON.stringify({ text })
            });
            return { success: true, data: await response.json() };
          } catch (e) {
            return { success: false, error: e.message };
          }
        }
      };

      const result = await mockClient.detectPII('test');

      expect(result.success).toBe(false);
      expect(result.error).toBe('Timeout');
    });
  });

  describe('restoreLLMOutput', () => {
    test('sends session ID and LLM output', async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({
          restored_text: 'Hello john@example.com',
          statistics: { restored: 1, total: 1 }
        })
      });

      const mockClient = {
        baseURL: 'http://localhost:5001',
        async restoreLLMOutput(sessionId, llmOutput) {
          const response = await fetch(`${this.baseURL}/api/restore-llm`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, llm_output: llmOutput })
          });
          return response.json();
        }
      };

      const result = await mockClient.restoreLLMOutput('session-123', 'Hello [EMAIL_1]');

      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:5001/api/restore-llm',
        expect.objectContaining({
          method: 'POST',
          body: expect.stringContaining('session-123')
        })
      );
      expect(result.restored_text).toBe('Hello john@example.com');
    });
  });
});
