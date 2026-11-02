import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests/browser',
  testMatch: process.env.E2E_EMPTY ? 'empty.spec.ts' : 'app.spec.ts',
  fullyParallel: true,
  use: { baseURL: 'http://127.0.0.1:4321', browserName: 'chromium', headless: true },
  webServer: {
    command: 'npm run preview -- --port 4321 --ignore-lock',
    url: 'http://127.0.0.1:4321',
    reuseExistingServer: false,
  },
  reporter: 'list',
});
