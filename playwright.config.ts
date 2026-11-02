import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests/browser',
  testMatch: process.env.E2E_PUBLIC
    ? 'public.spec.ts'
    : process.env.E2E_EMPTY
      ? 'empty.spec.ts'
      : process.env.E2E_PIPELINE
        ? 'pipeline.spec.ts'
        : 'app.spec.ts',
  projects:
    process.env.E2E_PUBLIC || process.env.E2E_PIPELINE
      ? [
          { name: 'desktop', use: { viewport: { width: 1440, height: 1000 } } },
          {
            name: 'mobile',
            use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true },
          },
        ]
      : undefined,
  fullyParallel: true,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:4321',
    browserName: 'chromium',
    headless: true,
  },
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: 'npm run preview -- --port 4321 --ignore-lock',
        url: 'http://127.0.0.1:4321',
        reuseExistingServer: false,
      },
  reporter: 'list',
});
