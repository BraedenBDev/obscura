import { chromium } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export async function loadExtension() {
  const extensionPath = path.resolve(__dirname, '../../..');

  const context = await chromium.launchPersistentContext('', {
    headless: false,
    args: [
      `--disable-extensions-except=${extensionPath}`,
      `--load-extension=${extensionPath}`,
      '--no-first-run',
      '--disable-default-apps',
    ],
  });

  // Wait for service worker
  let extensionId;
  const maxAttempts = 10;

  for (let i = 0; i < maxAttempts; i++) {
    const workers = context.serviceWorkers();
    if (workers.length > 0) {
      extensionId = workers[0].url().split('/')[2];
      break;
    }
    await new Promise(r => setTimeout(r, 500));
  }

  if (!extensionId) {
    throw new Error('Extension failed to load');
  }

  return { context, extensionId };
}

export async function closeExtension(context) {
  await context.close();
}
