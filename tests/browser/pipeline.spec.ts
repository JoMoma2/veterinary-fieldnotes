import { test, expect } from '@playwright/test';

test('generated test knowledge links to actual discussion and shift anchors', async ({
  page,
  request,
}) => {
  const build = await (await request.get('/build-info.json')).json();
  expect(build.dataset).toBe('pipeline-demo');
  for (const group of ['articles', 'cases', 'discussions', 'questions']) {
    expect(build.recordCounts[group]).toBeGreaterThan(0);
  }
  await page.goto('/knowledge/');
  await page.locator('.article-card h3 a').first().click();
  await page.locator('.source-row').first().click();
  await expect(page).toHaveURL(/\/discussions\//);
  await page.getByRole('link', { name: /View in shift archive/ }).click();
  const anchor = new URL(page.url()).hash;
  expect(anchor).not.toBe('');
  await expect(page.locator(anchor)).toBeVisible();
});

test('generated source-recall cards and search work without inference', async ({ page }) => {
  await page.goto('/study/');
  for (const checkbox of await page.locator('input[name=format]').all()) await checkbox.uncheck();
  await page.locator('input[value="flashcard"]').check();
  await page.getByRole('button', { name: 'Start studying' }).click();
  await expect(page.locator('.study-question')).toBeVisible();
  await page.getByRole('button', { name: 'Reveal model answer' }).click();
  await expect(page.locator('.model-answer')).toBeVisible();
  await expect(page.locator('.feedback a').first()).toBeVisible();
  await page.goto('/search/');
  await page.getByRole('searchbox').fill('grooming');
  await expect(page.locator('#search-results .search-result').first()).toBeVisible();
});
