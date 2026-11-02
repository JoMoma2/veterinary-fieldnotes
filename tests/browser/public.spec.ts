import { test, expect } from '@playwright/test';

test('public production pages, privacy boundary, and empty states', async ({ page, request }) => {
  const metadata = await request.get('/build-info.json');
  expect(metadata.ok()).toBe(true);
  const info = await metadata.json();
  expect(info.dataset).toBe('production');
  expect(info.recordCounts).toEqual({
    articles: 0,
    cases: 0,
    shifts: 0,
    discussions: 0,
    questions: 0,
  });
  for (const [url, title] of [
    ['/', 'Your learning, connected.'],
    ['/knowledge/', 'A place for everything you learn'],
    ['/cases/', 'Clinical stories, carefully preserved'],
    ['/shifts/', 'Every shift has a place'],
    ['/study/', 'Your study material will grow with your library'],
  ]) {
    const response = await page.goto(url);
    expect(response?.ok()).toBe(true);
    await expect(page.getByRole('heading', { name: title })).toBeVisible();
    await expect(page.locator('.demo-banner')).toHaveCount(0);
    await expect(page.locator('body')).not.toContainText('Case Amber');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
  }
  for (const path of [
    '/archive/topics.json',
    '/processing-status.json',
    '/jobs.sqlite3',
    '/fixtures/demo/public/topics.json',
  ]) {
    const r = await request.get(path);
    expect([403, 404]).toContain(r.status());
  }
});

test('public Pagefind returns results and handles no matches', async ({ page }) => {
  await page.goto('/search/');
  await page.getByRole('searchbox').fill('library');
  await expect(page.locator('.search-result').first()).toBeVisible();
  await expect(page.locator('#search-status')).not.toContainText('development');
  await page.getByRole('searchbox').fill('grooming');
  await expect(page.locator('#search-status')).toContainText('No matching');
});
