// tests/unit/anonymizer.test.js
import { Anonymizer } from '../../src/core/anonymizer.js';

describe('Anonymizer', () => {
  let anonymizer;

  beforeEach(() => {
    anonymizer = new Anonymizer();
  });

  describe('generatePlaceholder', () => {
    test('generates placeholder with type and counter', () => {
      const result = anonymizer.generatePlaceholder('EMAIL', 1);
      expect(result).toBe('[EMAIL_1]');
    });

    test('handles multi-word types', () => {
      const result = anonymizer.generatePlaceholder('CREDIT_CARD', 3);
      expect(result).toBe('[CREDIT_CARD_3]');
    });
  });

  describe('anonymize', () => {
    test('replaces single entity', () => {
      const text = 'Contact john@example.com for help';
      const entities = [{ type: 'EMAIL', value: 'john@example.com', start: 8, end: 24 }];

      const result = anonymizer.anonymize(text, entities);

      expect(result.text).toBe('Contact [EMAIL_1] for help');
      expect(result.mappings['[EMAIL_1]']).toBe('john@example.com');
    });

    test('replaces multiple entities', () => {
      const text = 'Email: a@b.com, Phone: 555-123-4567';
      const entities = [
        { type: 'EMAIL', value: 'a@b.com', start: 7, end: 14 },
        { type: 'PHONE', value: '555-123-4567', start: 23, end: 35 }
      ];

      const result = anonymizer.anonymize(text, entities);

      expect(result.text).toContain('[EMAIL_1]');
      expect(result.text).toContain('[PHONE_1]');
      expect(Object.keys(result.mappings)).toHaveLength(2);
    });

    test('increments counter for same type', () => {
      const text = 'Emails: a@b.com and c@d.com';
      const entities = [
        { type: 'EMAIL', value: 'a@b.com', start: 8, end: 15 },
        { type: 'EMAIL', value: 'c@d.com', start: 20, end: 27 }
      ];

      const result = anonymizer.anonymize(text, entities);

      expect(result.text).toContain('[EMAIL_1]');
      expect(result.text).toContain('[EMAIL_2]');
    });

    test('handles overlapping replacements correctly', () => {
      const text = '123-45-6789';
      const entities = [{ type: 'SSN', value: '123-45-6789', start: 0, end: 11 }];

      const result = anonymizer.anonymize(text, entities);

      expect(result.text).toBe('[SSN_1]');
    });

    test('preserves surrounding text', () => {
      const text = 'Before john@test.com after';
      const entities = [{ type: 'EMAIL', value: 'john@test.com', start: 7, end: 20 }];

      const result = anonymizer.anonymize(text, entities);

      expect(result.text).toBe('Before [EMAIL_1] after');
    });
  });

  describe('with existing session mappings', () => {
    test('continues counter from existing mappings', () => {
      const existingMappings = {
        '[EMAIL_1]': 'old@email.com',
        '[EMAIL_2]': 'another@email.com'
      };
      anonymizer.loadMappings(existingMappings);

      const text = 'New email: new@email.com';
      const entities = [{ type: 'EMAIL', value: 'new@email.com', start: 11, end: 24 }];

      const result = anonymizer.anonymize(text, entities);

      expect(result.text).toContain('[EMAIL_3]');
    });
  });
});
