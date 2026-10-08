import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const destination = path.join(root, '..', 'design-intel', 'build-shots');
await mkdir(destination, { recursive: true });
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const results = [];
try {
  for (const width of [1440, 390]) {
    const page = await browser.newPage({ viewport: { width, height: width === 390 ? 844 : 960 }, deviceScaleFactor: 1 });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(process.env.SITE_URL ?? 'http://127.0.0.1:5190', { waitUntil: 'networkidle' });
    await page.evaluate(() => document.fonts.ready);
    await page.locator('[data-testid="hero-scene"][data-rendered="true"]').waitFor();
    const before = await page.locator('[data-testid="hero-scene"]').getAttribute('data-frame');
    await page.waitForFunction(previous => document.querySelector('[data-testid="hero-scene"]')?.getAttribute('data-frame') !== previous, before);
    const metrics = await page.evaluate(() => {
      const canvas = document.querySelector('.hero canvas');
      const context = canvas.getContext('webgl2');
      const bytes = context ? new Uint8Array(canvas.width * canvas.height * 4) : canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
      if (context) context.readPixels(0, 0, canvas.width, canvas.height, context.RGBA, context.UNSIGNED_BYTE, bytes);
      let colored = 0;
      let cyan = 0;
      for (let index = 0; index < bytes.length; index += 4) {
        if (bytes[index + 3] > 20) colored++;
        if (bytes[index + 1] > bytes[index] * 1.2 && bytes[index + 2] > 90) cyan++;
      }
      return { colored, cyan, overflow: document.documentElement.scrollWidth > innerWidth, heroHeight: document.querySelector('.hero').getBoundingClientRect().height };
    });
    await page.screenshot({ path: path.join(destination, `hero-${width}.png`), animations: 'disabled' });
    await page.locator('.hero canvas').screenshot({ path: path.join(destination, `scene-${width}.png`) });
    results.push({ width, ...metrics, errors });
    await page.close();
  }
} finally { await browser.close(); }
await writeFile(path.join(destination, 'hero-check.json'), JSON.stringify(results, null, 2));
console.log(JSON.stringify(results, null, 2));
if (results.some(result => result.overflow || result.colored < 500 || result.cyan < 50 || result.errors.length)) process.exitCode = 1;