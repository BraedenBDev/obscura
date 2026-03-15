// tests/unit/restorer.test.js
import { Restorer } from '../../src/core/restorer.js';

describe('Restorer', () => {
  let restorer;

  beforeEach(() => {
    restorer = new Restorer();
  });

  describe('restore', () => {
    test('restores single placeholder', () => {
      const text = 'Hello [EMAIL_1], welcome!';
      const mappings = { '[EMAIL_1]': 'john@example.com' };

      const result = restorer.restore(text, mappings);

      expect(result.text).toBe('Hello john@example.com, welcome!');
      expect(result.restored).toBe(1);
    });

    test('restores multiple placeholders', () => {
      const text = 'Contact [PERSON_1] at [EMAIL_1]';
      const mappings = {
        '[PERSON_1]': 'John Doe',
        '[EMAIL_1]': 'john@example.com'
      };

      const result = restorer.restore(text, mappings);

      expect(result.text).toBe('Contact John Doe at john@example.com');
      expect(result.restored).toBe(2);
    });

    test('handles missing mappings gracefully', () => {
      const text = 'Hello [EMAIL_1] and [EMAIL_2]';
      const mappings = { '[EMAIL_1]': 'known@example.com' };

      const result = restorer.restore(text, mappings);

      expect(result.text).toBe('Hello known@example.com and [EMAIL_2]');
      expect(result.restored).toBe(1);
      expect(result.notFound).toContain('[EMAIL_2]');
    });

    test('returns unchanged text if no placeholders', () => {
      const text = 'Just regular text';
      const mappings = { '[EMAIL_1]': 'test@test.com' };

      const result = restorer.restore(text, mappings);

      expect(result.text).toBe('Just regular text');
      expect(result.restored).toBe(0);
    });

    test('handles empty mappings', () => {
      const text = 'Hello [EMAIL_1]';
      const mappings = {};

      const result = restorer.restore(text, mappings);

      expect(result.text).toBe('Hello [EMAIL_1]');
      expect(result.restored).toBe(0);
    });
  });

  describe('findPlaceholders', () => {
    test('finds all placeholders in text', () => {
      const text = 'Email: [EMAIL_1], Phone: [PHONE_1], Name: [PERSON_2]';

      const result = restorer.findPlaceholders(text);

      expect(result).toHaveLength(3);
      expect(result).toContain('[EMAIL_1]');
      expect(result).toContain('[PHONE_1]');
      expect(result).toContain('[PERSON_2]');
    });
  });

  describe('statistics', () => {
    test('returns correct statistics', () => {
      const text = '[EMAIL_1] and [PHONE_1] and [SSN_1]';
      const mappings = {
        '[EMAIL_1]': 'test@test.com',
        '[PHONE_1]': '555-1234'
        // SSN_1 missing
      };

      const result = restorer.restore(text, mappings);

      expect(result.statistics.total).toBe(3);
      expect(result.statistics.restored).toBe(2);
      expect(result.statistics.missing).toBe(1);
    });
  });
});
