import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';

const shots = path.resolve(import.meta.dirname, '../../design-intel/build-shots');

for (const width of [390, 768, 1024, 1440, 1920]) {
  test(`responsive layout and complete page at ${width}`, async ({ page }) => {
    await mkdir(shots, { recursive: true });
    await page.setViewportSize({ width, height: width < 768 ? 844 : 960 });
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('/');
    await page.evaluate(() => document.fonts.ready);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Physical AIV&V Engine');
    await expect(page.locator('[data-testid="hero-scene"][data-rendered="true"]')).toBeVisible();
    const overflow = await page.evaluate(() => ({ page: document.documentElement.scrollWidth - innerWidth,
      bad: [...document.querySelectorAll('h1,h2,h3,button,input,select')].filter(element => {
        const bounds = element.getBoundingClientRect();
        return bounds.width > 0 && (bounds.right > innerWidth + 2 || bounds.left < -2);
      }).map(element => element.textContent?.slice(0, 60)) }));
    expect(overflow).toEqual({ page: 0, bad: [] });
    await page.screenshot({ path: path.join(shots, `hero-${width}.png`), animations: 'disabled' });
    await page.locator('#failure-lab').scrollIntoViewIfNeeded();
    await expect(page.locator('[data-testid="demo-scene"][data-rendered="true"]')).toBeVisible();
    await page.getByRole('button', { name: 'Distribution shift', exact: true }).click();
    await expect(page.locator('.verdict-panel strong')).toHaveText('HOLD');
    await expect(page.locator('.demo-gate').filter({ hasText: 'Trajectory divergence' })).toContainText('151.2 mm');
    await page.locator('#failure-lab').screenshot({ path: path.join(shots, `demo-${width}.png`), animations: 'disabled' });
    await page.locator('#evidence').scrollIntoViewIfNeeded();
    await page.getByRole('button', { name: /EV-0249 Sensor dropout/ }).click();
    await expect(page.locator('.report-status')).toHaveText('BLOCK');
    await page.locator('#evidence').screenshot({ path: path.join(shots, `evidence-${width}.png`), animations: 'disabled' });
    await page.screenshot({ path: path.join(shots, `full-${width}.png`), fullPage: true, animations: 'disabled' });
    expect(errors).toEqual([]);
  });
}

test('failure modes, reset and evidence export', async ({ page }) => {
  await page.goto('/');
  await page.locator('#failure-lab').scrollIntoViewIfNeeded();
  for (const name of ['Sensor dropout', 'Adversarial scene', 'Distribution shift']) {
    await page.getByRole('button', { name, exact: true }).click();
    await expect(page.locator('.verdict-panel strong')).toHaveText('HOLD');
    await expect(page.locator('.result-heading')).toContainText('3 / 4');
  }
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export example evidence' }).click();
  expect((await download).suggestedFilename()).toBe('verification-drift-evidence.json');
  await page.getByRole('button', { name: 'Reset failure experiment' }).click();
  await expect(page.locator('.verdict-panel strong')).toHaveText('CONTINUE');
});

test('pilot dialog keyboard flow is an honest local draft', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Request pilot' }).first().click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await dialog.getByLabel('Name', { exact: true }).fill('Test Engineer');
  await dialog.getByLabel('Work email').fill('engineer@example.invalid');
  await dialog.getByLabel('Validation challenge').fill('Validate a synthetic local acceptance fixture.');
  await expect(dialog).toContainText('nothing is submitted');
  const download = page.waitForEvent('download');
  await dialog.getByRole('button', { name: 'Download pilot brief' }).click();
  expect((await download).suggestedFilename()).toBe('verification-pilot-request.json');
  await page.keyboard.press('Escape');
  await expect(dialog).not.toBeVisible();
});

test('reduced motion, pipeline and accessibility', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await page.evaluate(() => document.fonts.ready);
  await page.getByRole('tab', { name: /Certify/ }).click();
  await expect(page.getByRole('tabpanel')).toContainText('Give the assessor the evidence.');
  await expect(page.getByRole('tabpanel')).toContainText('NOT A CERTIFICATE');
  const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(result.violations.map(item => ({ id: item.id, nodes: item.nodes.map(node => node.target) }))).toEqual([]);
});

test('internal destinations and launch metadata exist', async ({ page, request }) => {
  await page.goto('/');
  const missing = await page.evaluate(() => [...document.querySelectorAll<HTMLAnchorElement>('a[href^="#"]')].map(anchor => anchor.getAttribute('href')!).filter(href => href.length > 1 && !document.getElementById(href.slice(1))));
  expect(missing).toEqual([]);
  expect((await request.get('/privacy')).status()).toBe(200);
  expect((await request.get('/opengraph-image')).status()).toBe(200);
  expect((await request.get('/icon')).status()).toBe(200);
  expect((await request.get('/sitemap.xml')).status()).toBe(200);
  expect((await request.get('/robots.txt')).status()).toBe(200);
  const gone = await request.get('/no-such-page-xyz');
  expect(gone.status()).toBe(404);
  await page.goto('/no-such-page-xyz');
  await expect(page.locator('main')).toContainText('holds nothing');
  await expect(page.locator('meta[property="og:title"]')).toHaveAttribute('content', 'Verification');
});

test('WebGL unavailable uses the real local poster', async ({ page }) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, type: string, ...parameters: unknown[]) {
      if (type === 'webgl' || type === 'webgl2' || type === 'experimental-webgl') return null;
      return Reflect.apply(original, this, [type, ...parameters]);
    } as typeof original;
  });
  await page.goto('/');
  const poster = page.getByAltText('Static verification trace of a robotic arm. WebGL unavailable.');
  await expect(poster).toBeVisible();
  await expect.poll(() => poster.evaluate((image: HTMLImageElement) => image.complete && image.naturalWidth === 1280)).toBe(true);
  await page.screenshot({ path: path.join(shots, 'hero-webgl-fallback.png'), animations: 'disabled' });
});

test('short desktop viewport retains next-section glimpse and text separation', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 768 });
  await page.goto('/');
  const geometry = await page.evaluate(() => ({ nextTop: document.querySelector('.context-strip')!.getBoundingClientRect().top,
    copyBottom: document.querySelector('.hero-content')!.getBoundingClientRect().bottom,
    statsTop: document.querySelector('.hero-stats')!.getBoundingClientRect().top }));
  expect(geometry.nextTop).toBeLessThan(750);
  expect(geometry.copyBottom).toBeLessThan(geometry.statsTop);
});