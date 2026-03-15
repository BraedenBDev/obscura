// tests/unit/detector.test.js
import { PIIDetector } from '../../src/core/detector.js';

describe('PIIDetector', () => {
  let detector;

  beforeEach(() => {
    detector = new PIIDetector();
  });

  describe('detectPlaceholders', () => {
    test('detects single placeholder', () => {
      const text = 'Hello [EMAIL_1], how are you?';
      const result = detector.detectPlaceholders(text);

      expect(result).toEqual(['[EMAIL_1]']);
    });

    test('detects multiple placeholders', () => {
      const text = 'Contact [PERSON_1] at [EMAIL_1] or [PHONE_2]';
      const result = detector.detectPlaceholders(text);

      expect(result).toHaveLength(3);
      expect(result).toContain('[PERSON_1]');
      expect(result).toContain('[EMAIL_1]');
      expect(result).toContain('[PHONE_2]');
    });

    test('returns empty array when no placeholders', () => {
      const text = 'Just regular text without placeholders';
      const result = detector.detectPlaceholders(text);

      expect(result).toEqual([]);
    });

    test('handles complex placeholder types', () => {
      const text = '[CREDIT_CARD_1] and [BANK_ACCOUNT_3]';
      const result = detector.detectPlaceholders(text);

      expect(result).toHaveLength(2);
    });
  });

  describe('parsePlaceholder', () => {
    test('extracts type and id from placeholder', () => {
      const result = detector.parsePlaceholder('[EMAIL_1]');

      expect(result).toEqual({ type: 'EMAIL', id: 1 });
    });

    test('handles multi-word types', () => {
      const result = detector.parsePlaceholder('[CREDIT_CARD_5]');

      expect(result).toEqual({ type: 'CREDIT_CARD', id: 5 });
    });

    test('returns null for invalid placeholder', () => {
      const result = detector.parsePlaceholder('not a placeholder');

      expect(result).toBeNull();
    });
  });

  describe('detectWithRegex', () => {
    test('detects email addresses', () => {
      const text = 'Contact me at john.doe@example.com for more info';
      const result = detector.detectWithRegex(text);

      const emails = result.filter(e => e.type === 'EMAIL');
      expect(emails).toHaveLength(1);
      expect(emails[0].value).toBe('john.doe@example.com');
    });

    test('detects SSN', () => {
      const text = 'My SSN is 123-45-6789';
      const result = detector.detectWithRegex(text);

      const ssns = result.filter(e => e.type === 'SSN');
      expect(ssns).toHaveLength(1);
      expect(ssns[0].value).toBe('123-45-6789');
    });

    test('detects phone numbers', () => {
      const text = 'Call me at (555) 123-4567 or 555.123.4567';
      const result = detector.detectWithRegex(text);

      const phones = result.filter(e => e.type === 'PHONE');
      expect(phones.length).toBeGreaterThanOrEqual(1);
    });

    test('detects credit card numbers', () => {
      const text = 'Card: 4111-1111-1111-1111';
      const result = detector.detectWithRegex(text);

      const cards = result.filter(e => e.type === 'CREDIT_CARD');
      expect(cards).toHaveLength(1);
    });

    test('rejects invalid SSN starting with 000', () => {
      const text = 'Invalid SSN: 000-12-3456';
      const result = detector.detectWithRegex(text);

      const ssns = result.filter(e => e.type === 'SSN');
      expect(ssns).toHaveLength(0);
    });

    test('detects multiple PII types', () => {
      const text = 'Email: test@test.com, Phone: 555-123-4567, SSN: 123-45-6789';
      const result = detector.detectWithRegex(text);

      expect(result.length).toBeGreaterThanOrEqual(3);
    });
  });
});
