import { defineConfig } from '@playwright/test';
import path from 'path';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30000,
  retries: process.env.CI ? 2 : 0,
  workers: 1, // Extensions need sequential execution
  reporter: [
    ['html', { open: 'never' }],
    ['list']
  ],
  use: {
    headless: false, // Extensions require headed mode
    trace: 'on-first-retry',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        browserName: 'chromium',
      },
    },
  ],
});
