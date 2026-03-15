// tests/e2e/smoke.spec.js
import { test, expect } from '@playwright/test';
import { loadExtension, closeExtension } from './fixtures/extension.js';

test.describe('Extension Smoke Tests', () => {
  let context;
  let extensionId;

  test.beforeAll(async () => {
    const result = await loadExtension();
    context = result.context;
    extensionId = result.extensionId;
  });

  test.afterAll(async () => {
    if (context) {
      await closeExtension(context);
    }
  });

  test('extension loads successfully', async () => {
    expect(extensionId).toBeDefined();
    expect(extensionId.length).toBeGreaterThan(0);
  });

  test('side panel is accessible', async () => {
    const page = await context.newPage();
    await page.goto(`chrome-extension://${extensionId}/side-panel/side-panel.html`);

    // Check title or key element
    const title = await page.locator('h1, .title, [class*="title"]').first();
    await expect(title).toBeVisible({ timeout: 5000 });

    await page.close();
  });

  test('options page loads', async () => {
    const page = await context.newPage();
    await page.goto(`chrome-extension://${extensionId}/options/options.html`);

    // Check for settings elements
    const settingsElement = await page.locator('input, select, button').first();
    await expect(settingsElement).toBeVisible({ timeout: 5000 });

    await page.close();
  });
});
