import { test, expect } from '@playwright/test';
test('empty production sections are usable and contain no demonstration records', async ({
  page,
}) => {
  for (const [path, text] of [
    ['/knowledge/', 'A place for everything you learn'],
    ['/cases/', 'Clinical stories, carefully preserved'],
    ['/shifts/', 'Every shift has a place'],
    ['/study/', 'Your study material will grow with your library'],
  ]) {
    await page.goto(path);
    await expect(page.getByRole('heading', { name: text })).toBeVisible();
    await expect(page.locator('body')).not.toContainText('AMBER-TRAINING');
    await expect(page.locator('.demo-banner')).toHaveCount(0);
  }
  await page.goto('/search/');
  await page.getByRole('searchbox').fill('grooming');
  await expect(page.locator('#search-status')).toContainText('No matching');
});
