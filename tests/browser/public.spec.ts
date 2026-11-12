import { test, expect } from '@playwright/test';

test('public production pages preserve the privacy boundary', async ({ page, request }) => {
  const metadata = await request.get('/build-info.json');
  expect(metadata.ok()).toBe(true);
  const info = await metadata.json();
  expect(info.dataset).toBe('production');
  expect(Object.keys(info.recordCounts).sort()).toEqual([
    'articles',
    'cases',
    'discussions',
    'questions',
    'shifts',
  ]);
  for (const count of Object.values(info.recordCounts)) {
    expect(Number.isInteger(count)).toBe(true);
    expect(Number(count)).toBeGreaterThanOrEqual(0);
  }
  for (const [url, title] of [
    ['/', 'Your learning, connected.'],
    ['/knowledge/', 'Knowledge library'],
    ['/cases/', 'Clinical cases'],
    ['/shifts/', 'Shift archive'],
    ['/study/', 'Make the learning stick.'],
  ]) {
    const response = await page.goto(url);
    expect(response?.ok()).toBe(true);
    await expect(page.getByRole('heading', { name: title, exact: true }).first()).toBeVisible();
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
  const query = await page.locator('#search-fallback').evaluate((element) => {
    const records = JSON.parse(element.textContent || '[]') as { title: string }[];
    return records.flatMap((record) => record.title.match(/[A-Za-z]{5,}/g) || [])[0] || null;
  });
  if (query) {
    await page.getByRole('searchbox').fill(query);
    await expect(page.locator('.search-result').first()).toBeVisible();
  }
  await expect(page.locator('#search-status')).not.toContainText('development');
  await page.getByRole('searchbox').fill('zzznomatchingfieldnotesqueryzzz');
  await expect(page.locator('#search-status')).toContainText('No matching');
});
