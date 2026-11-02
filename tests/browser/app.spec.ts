import { test, expect } from '@playwright/test';
test('desktop navigation and topic filtering', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Your learning, connected.' })).toBeVisible();
  await page.getByRole('link', { name: 'Knowledge library', exact: true }).click();
  await expect(page.locator('.article-card')).toHaveCount(6);
  await page.getByRole('button', { name: 'Equipment & techniques' }).click();
  await expect(page.locator('.article-card:visible')).toHaveCount(2);
  await page.getByRole('button', { name: 'All topics' }).click();
  await expect(page.locator('.article-card:visible')).toHaveCount(6);
});
test('source links connect article, discussion, and shift anchor', async ({ page }) => {
  await page.goto('/knowledge/a-fip-reasoning/');
  await page.locator('.source-row').first().click();
  await expect(page).toHaveURL(/\/discussions\/d-fip-first\//);
  await page.getByRole('link', { name: /View in shift archive/ }).click();
  await expect(page).toHaveURL(/\/shifts\/s-2026-10-22\/#d-fip-first/);
  await expect(page.locator('#d-fip-first')).toBeVisible();
  await page.locator('#d-fip-first .connected a').first().click();
  await expect(page).toHaveURL(/a-fip-reasoning/);
});
test('Pagefind full text search returns source-linked results', async ({ page }) => {
  await page.goto('/search/');
  await page.getByRole('searchbox').fill('grooming');
  await expect(page.locator('#search-results .search-result').first()).toBeVisible();
  await expect(page.locator('#search-status')).not.toContainText('development');
  await expect(page.locator('#search-results')).toContainText(/grooming|urinary|litter/i);
});
test('unknown case facts are explicit', async ({ page }) => {
  await page.goto('/cases/c-amber/');
  await expect(page.locator('.case-status')).toContainText('Unknown');
  await expect(page.locator('.facts')).toContainText('Owner reported');
  await expect(page.locator('.facts')).toContainText('Clinical suspicion');
});
test('topic select all/deselect all and empty selection feedback', async ({ page }) => {
  await page.goto('/study/');
  await page.getByRole('button', { name: 'Deselect all' }).click();
  await expect(page.locator('input[name=topic]:checked')).toHaveCount(0);
  await page.getByRole('button', { name: 'Start studying' }).click();
  await expect(page.getByRole('heading', { name: 'No matching questions' })).toBeVisible();
  await page.getByRole('button', { name: 'Select all', exact: true }).click();
  await expect(page.locator('input[name=topic]:checked')).toHaveCount(6);
});
for (const format of ['multiple-choice', 'multiple-select', 'flashcard', 'open-ended', 'scenario'])
  test(`${format} provides immediate stored feedback`, async ({ page }) => {
    await page.goto('/study/');
    for (const checkbox of await page.locator('input[name=format]').all()) await checkbox.uncheck();
    await page.locator(`input[value="${format}"]`).check();
    await page.getByRole('button', { name: 'Start studying' }).click();
    await expect(page.locator('.study-question')).toBeVisible();
    if (format.startsWith('multiple')) {
      await page.locator('input[name=answer]').first().check();
      await page.getByRole('button', { name: 'Check answer' }).click();
      await expect(page.locator('.feedback')).toContainText('Correct answer');
      await expect(page.locator('.answer-option.correct')).not.toHaveCount(0);
    } else {
      await page.getByRole('button', { name: 'Reveal model answer' }).click();
      await expect(page.locator('.model-answer')).toBeVisible();
    }
    await expect(page.locator('.feedback a').first()).toBeVisible();
  });
test('mobile navigation is usable without horizontal page overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  for (const path of [
    '/',
    '/knowledge/',
    '/cases/c-amber/',
    '/shifts/s-2026-10-22/',
    '/study/',
    '/search/',
  ]) {
    await page.goto(path);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
  }
  await page.getByRole('link', { name: 'Clinical cases', exact: true }).click();
  await expect(page).toHaveURL(/\/cases\//);
});
test('study does not persist progress or request inference', async ({ page }) => {
  const requests: string[] = [];
  page.on('request', (r) => requests.push(r.url()));
  await page.goto('/study/');
  await page.getByRole('button', { name: 'Start studying' }).click();
  expect(
    await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length })),
  ).toEqual({ local: 0, session: 0 });
  expect(requests.every((url) => url.startsWith('http://127.0.0.1:4321/'))).toBe(true);
});
