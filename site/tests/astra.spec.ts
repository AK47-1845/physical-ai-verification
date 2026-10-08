import { test, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';

const evidence = path.resolve('../design-intel/astra/workspace-first');

test('guided workspace scores, exposes evidence, and compiles a verifiable artifact', async ({ page }) => {
  test.setTimeout(90000);
  await page.setViewportSize({ width: 1440, height: 960 });
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/playground');
  await expect(page.locator('.connection-state')).toContainText('Backend connected');
  await page.getByRole('button', { name: 'Score this run', exact: true }).click();
  await expect(page.locator('.score-findings')).toContainText('BLOCKED');
  await page.getByRole('button', { name: /Final tracking error/ }).click();
  await expect(page.locator('.gate-detail')).toContainText('Final sample 5');
  await expect(page.locator('.gate-detail')).toContainText('2.5');
  await expect(page.locator('.workspace-history')).toContainText('Drifting reach');
  const [download] = await Promise.all([page.waitForEvent('download'), page.locator('.run-actions').getByRole('button', { name: 'Scorecard', exact: true }).click()]);
  expect(download.suggestedFilename()).toBe('verification-scorecard.json');
  await mkdir(evidence, { recursive: true });
  await page.evaluate(() => { window.scrollTo(0, 0); if (document.activeElement instanceof HTMLElement) document.activeElement.blur(); });
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
  await page.screenshot({ path: path.join(evidence, 'playground-1440.png'), animations: 'disabled', fullPage: true });
  await page.locator('.workflow-rail').getByRole('button', { name: 'Compile a dossier', exact: true }).click();
  await page.getByRole('button', { name: 'Compile evidence', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Operation result' })).toContainText('dossier id');
  await page.locator('.workflow-rail').getByRole('button', { name: 'Verify a PAR', exact: true }).click();
  await page.getByRole('button', { name: 'Verify integrity', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Operation result' })).toBeVisible();
  await page.getByRole('button', { name: 'Change one value', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Operation result' })).toContainText('Tampering detected');
  expect(errors).toEqual([]);
});

test('guided hunt, refusal receipt and worksheet use the live backend', async ({ page }) => {
  await page.goto('/playground');
  await expect(page.locator('.connection-state')).toContainText('Backend connected');
  await page.locator('.workflow-rail').getByRole('button', { name: 'Hunt failures', exact: true }).click();
  await page.locator('.workflow-stage').getByRole('button', { name: 'Hunt failures', exact: true }).click();
  await expect(page.locator('.trial-grid>span')).toHaveCount(16);
  await page.locator('.workflow-rail').getByRole('button', { name: 'Check transfer', exact: true }).click();
  await page.getByRole('button', { name: 'Test an invalid frame contract', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Operation result' })).toContainText('INSUFFICIENT');
  await expect(page.getByRole('region', { name: 'Operation result' })).toContainText('Comparison refused');
  await page.locator('.workflow-rail').getByRole('button', { name: 'Applicability worksheet', exact: true }).click();
  await page.getByRole('button', { name: 'Record worksheet', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Operation result' })).toContainText('Human and legal review required');
});

test('workspace mobile retains complete scoring controls without overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/playground');
  await expect(page.locator('.connection-state')).toContainText('Backend connected');
  await page.getByRole('button', { name: 'Score this run', exact: true }).click();
  await expect(page.locator('.score-findings')).toContainText('BLOCKED');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await mkdir(evidence, { recursive: true });
  await page.evaluate(() => { window.scrollTo(0, 0); if (document.activeElement instanceof HTMLElement) document.activeElement.blur(); });
  await page.screenshot({ path: path.join(evidence, 'playground-390.png'), animations: 'disabled', fullPage: true });
});

test('workspace connection failure does not present synthetic results as live', async ({ page }) => {
  await page.route('**/api/play/**', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ up: false, hint: 'Test backend unavailable' }) }));
  await page.goto('/playground');
  await expect(page.locator('.workspace-offline')).toBeVisible();
  await page.getByRole('button', { name: 'Score this run', exact: true }).click();
  await expect(page.locator('.workflow-stage').getByRole('alert')).toContainText('INSUFFICIENT');
  await expect(page.locator('.score-findings .verdict-badge')).toHaveCount(0);
});

for (const mode of ['live', 'recorded'] as const) {
  for (let iteration = 1; iteration <= 10; iteration++) {
    test(`90-second demo ${mode} rehearsal ${iteration}`, async ({ page }) => {
      await page.setViewportSize({ width: 1440, height: 960 });
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.clock.install();
      if (mode === 'recorded') await page.route('**/api/play/**', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ up: false }) }));
      await page.goto('/demo');
      const demo = page.getByTestId('demo-experience');
      await expect(demo).toHaveAttribute('data-mode', mode);
      await page.getByRole('button', { name: 'Chapter 3: The boundary', exact: true }).click();
      await page.clock.fastForward(12500);
      await expect(page.locator('.demo-score-paper')).toContainText('BLOCKED');
      await page.clock.resume();
      await page.getByRole('button', { name: 'Chapter 5: The record', exact: true }).click();
      await expect(page.locator('.demo-record')).toContainText('Hash and structure checked');
      await page.clock.fastForward(36000);
      await expect(demo).toHaveAttribute('data-elapsed', '90');
      await expect(demo).toHaveAttribute('data-chapter', '6');
      await expect(page.getByRole('button', { name: 'Replay demo', exact: true })).toBeVisible();
      await expect(page.locator('.demo-mode')).toContainText(mode === 'live' ? 'LIVE ENGINE / SYNTHETIC INPUTS' : 'RECORDED SYNTHETIC / REPLAY');
    });
  }
}

test('demo hero entry, pause, keyboard dismissal and mid-flight fallback', async ({ page }) => {
  await page.clock.install();
  await page.goto('/');
  await page.getByRole('button', { name: 'Watch 90-sec demo', exact: true }).click();
  const demo = page.getByTestId('demo-experience');
  await expect(demo).toHaveAttribute('data-mode', 'live');
  await page.getByRole('button', { name: 'Pause demo', exact: true }).click();
  const paused = await demo.getAttribute('data-elapsed');
  await page.clock.fastForward(5000);
  await expect(demo).toHaveAttribute('data-elapsed', paused!);
  await page.clock.resume();
  await page.route('**/api/play/**', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ up: false }) }));
  await page.getByRole('button', { name: 'Next chapter', exact: true }).click();
  await expect(demo).toHaveAttribute('data-mode', 'recorded');
  await page.keyboard.press('Escape');
  await expect(demo).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Watch 90-sec demo', exact: true })).toBeFocused();
});

test('demo desktop and mobile have visible moving canvas and bounded controls', async ({ browser }) => {
  const destination = path.resolve('../design-intel/astra/demo-first');
  await mkdir(destination, { recursive: true });
  for (const width of [1440, 390]) {
    const page = await browser.newPage({ viewport: { width, height: width === 390 ? 844 : 960 }, deviceScaleFactor: 1 });
    await page.goto(`${process.env.SITE_URL ?? 'http://127.0.0.1:5190'}/demo`);
    const canvas = page.locator('.demo-world canvas');
    await expect(canvas).toBeVisible();
    const scene = page.locator('.demo-world [data-testid="hero-scene"]');
    await expect(scene).toHaveAttribute('data-rendered', 'true');
    const previous = await scene.getAttribute('data-frame');
    await expect.poll(() => scene.getAttribute('data-frame')).not.toBe(previous);
    const pixels = await canvas.evaluate(element => {
      const source = element as HTMLCanvasElement;
      const context = source.getContext('webgl2')!;
      const bytes = new Uint8Array(source.width * source.height * 4);
      context.readPixels(0, 0, source.width, source.height, context.RGBA, context.UNSIGNED_BYTE, bytes);
      let colored = 0;
      for (let index = 0; index < bytes.length; index += 4) if (bytes[index + 3] > 20) colored++;
      return colored;
    });
    expect(pixels).toBeGreaterThan(500);
    await page.getByRole('button', { name: 'Pause demo', exact: true }).click();
    await expect(page.locator('.demo-story-line').first()).toHaveCSS('opacity', '1');
    await page.screenshot({ path: path.join(destination, `opening-${width}.png`), animations: 'disabled' });
    await page.getByRole('button', { name: 'Chapter 3: The boundary', exact: true }).click();
    await expect(page.locator('.demo-focus')).toHaveCSS('opacity', '1');
    await expect(page.locator('.demo-story-line').last()).toHaveCSS('opacity', '1');
    await page.screenshot({ path: path.join(destination, `score-${width}.png`), animations: 'disabled' });
    await page.getByRole('button', { name: 'Chapter 5: The record', exact: true }).click();
    await expect(page.locator('.demo-focus')).toHaveCSS('opacity', '1');
    await expect(page.locator('.demo-story-line').last()).toHaveCSS('opacity', '1');
    await page.screenshot({ path: path.join(destination, `record-${width}.png`), animations: 'disabled' });
    const geometry = await page.locator('.demo-controls').evaluate(element => { const bounds = element.getBoundingClientRect(); return { inside: bounds.bottom <= innerHeight + 1 && bounds.left >= 0 && bounds.right <= innerWidth, overflow: document.documentElement.scrollWidth > innerWidth }; });
    expect(geometry).toEqual({ inside: true, overflow: false });
    await page.close();
  }
});

test('demo pilot CTA opens above the player and returns to it', async ({ page }) => {
  await page.goto('/demo');
  await page.getByRole('button', { name: 'Chapter 7: Your next trace', exact: true }).click();
  await page.getByRole('button', { name: 'Request pilot', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Start with one real failure.', exact: true })).toBeVisible();
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill('Demo reviewer');
  await page.getByRole('button', { name: 'Close pilot request', exact: true }).click();
  await expect(page.getByTestId('demo-experience')).toBeVisible();
});

test('Free Lab completes anonymous scoring, trophy exports, consent sharing and live experiments', async ({ page, browser }) => {
  test.setTimeout(120000);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.goto('/free');
  await expect(page.locator('.free-lab-limits')).toContainText('ENGINE CONNECTED');
  await page.getByRole('button', { name: 'Skip introduction', exact: true }).click();
  await page.getByRole('button', { name: 'Drifting reach', exact: true }).click();
  await page.getByRole('button', { name: 'Check trace', exact: true }).click();
  await expect(page.locator('.free-output .verdict-badge')).toHaveText('BLOCKED');
  await expect(page.getByRole('checkbox', { name: /Help public benchmarks/ })).not.toBeChecked();
  await expect(page.getByRole('button', { name: 'Create share link', exact: true })).toBeDisabled();
  for (const style of ['signal', 'paper', 'blueprint']) {
    await page.getByRole('button', { name: `${style} card style`, exact: true }).click();
    const downloaded = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Evidence PNG', exact: true }).click();
    expect((await downloaded).suggestedFilename()).toBe(`verification-${style}-evidence.png`);
  }
  await page.getByRole('checkbox', { name: /Publish the scorecard and declared scope/ }).check();
  await page.getByRole('button', { name: 'Create share link', exact: true }).click();
  const link = page.locator('.generated-share-link');
  await expect(link).toBeVisible();
  const cold = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await cold.goto((await link.getAttribute('href'))!);
  await expect(cold.locator('.shared-verdict')).toContainText('BLOCKED');
  await expect(cold.locator('.shared-hash')).toContainText('Raw traces are not included');
  expect(await cold.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await cold.close();
  await page.getByRole('button', { name: 'Weekly hunt', exact: true }).click();
  await expect(page.locator('.challenge-commit code')).toHaveText(/[a-f0-9]{64}/);
  await page.getByRole('button', { name: 'Test this disturbance', exact: true }).click();
  await expect(page.locator('.challenge-count')).toContainText('1');
  await page.getByRole('button', { name: /Request reveal receipt/ }).click();
  await expect(page.locator('.workspace-error')).toContainText('reveal refused');
  await page.getByRole('button', { name: 'Drift duel', exact: true }).click();
  await page.getByRole('button', { name: 'Run duel', exact: true }).click();
  await expect(page.locator('.duel-outcome .verdict-badge')).toHaveCount(2);
  await page.getByRole('button', { name: 'Failure atlas', exact: true }).click();
  for (const mode of ['FM1', 'FM2', 'FM3', 'FM4', 'FM5']) {
    await page.getByRole('navigation', { name: 'Failure modes', exact: true }).getByRole('button', { name: new RegExp(mode) }).click();
    await page.getByRole('button', { name: 'Run synthetic example', exact: true }).click();
    await expect(page.locator('.atlas-detail .readable-result')).toContainText(mode.toLowerCase());
  }
  await page.getByRole('button', { name: 'Public board', exact: true }).click();
  await expect(page.locator('.public-board tbody tr')).toHaveCount(10);
  await page.getByRole('button', { name: 'API', exact: true }).click();
  await page.getByRole('button', { name: 'Refresh usage', exact: true }).click();
  await expect(page.locator('.api-usage strong')).not.toHaveText('Not loaded');
  await page.getByRole('button', { name: 'Run in browser', exact: true }).click();
  await expect(page.locator('.free-api .operation-result')).toBeVisible();
  expect(errors).toEqual([]);
});

test('Free Lab mobile scores a declared CSV and refuses missing scope', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => localStorage.setItem('verification-lab-intro', 'seen'));
  await page.goto('/free');
  const csv = 'ref_x,ref_y,obs_x,obs_y,units,frame_id\n0,0,0,0,m,world\n1,0,1,0.1,m,world\n';
  await page.locator('.free-input input[type=file]').setInputFiles({ name: 'trace.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) });
  await expect(page.locator('.trace-dropzone')).toContainText('trace.csv');
  await page.getByRole('button', { name: 'Check trace', exact: true }).click();
  await expect(page.locator('.free-output .verdict-badge')).toBeVisible();
  await page.locator('.free-input input[type=file]').setInputFiles({ name: 'invalid.json', mimeType: 'application/json', buffer: Buffer.from('{"intended":[[0,0],[1,0]],"observed":[[0,0],[1,0]]}') });
  await expect(page.locator('.workspace-error')).toContainText('units');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('a scored run opens an actionable release brief without invented model identity', async ({ page }) => {
  await page.goto('/playground');
  await expect(page.locator('.connection-state')).toContainText('Backend connected');
  await page.getByRole('button', { name: 'Score this run', exact: true }).click();
  await expect(page.locator('.run-actions a')).toContainText('Release brief');
  await page.locator('.run-actions a').click();
  await expect(page.locator('.release-summary')).toContainText('BLOCKED');
  await expect(page.locator('.release-summary')).toContainText('UNSIGNED');
  await expect(page.locator('.release-summary')).toContainText('Review requirements');
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download brief', exact: true }).click();
  expect((await download).suggestedFilename()).toBe('release-brief.json');
});

test('supporting pages perform real measurements and preserve legal review', async ({ page }) => {
  await page.goto('/evidence');
  await page.getByRole('button', { name: 'Score example', exact: true }).click();
  await expect(page.locator('.page-paper .verdict-badge')).toContainText('BLOCKED');
  await page.getByRole('button', { name: 'Append example and verify chain', exact: true }).click();
  await expect(page.locator('.page-ledger-result')).toContainText('entries');
  await page.goto('/compliance');
  await expect(page.locator('.regulation-clock')).toContainText('calendar days');
  await page.getByRole('button', { name: 'Record answers', exact: true }).click();
  await expect(page.locator('.worksheet-route')).toContainText('Human and legal review required');
  await page.goto('/methodology');
  await page.getByRole('button', { name: /FM4.*Action sensitivity/ }).click();
  await page.getByRole('button', { name: 'Run measurement', exact: true }).click();
  await expect(page.locator('.page-workbench .readable-result')).toContainText('raw');
  await page.goto('/use-cases');
  await page.getByRole('button', { name: 'Measure this trace', exact: true }).click();
  await expect(page.locator('.drift-experiment-result .verdict-badge')).toBeVisible();
});
test('playground console names its live backend host', async ({ page }) => {
  await page.goto('/playground');
  await page.locator('.endpoint-advanced > summary').click();
  const topbar = page.locator('.lab-topbar').first();
  await expect(topbar).toBeVisible({ timeout: 15000 });
  await expect(topbar).toContainText(/BACKEND \/ \S+:\d+/);
});


test('workspace seals a replay capsule that verifies', async ({ page, request }) => {
  await page.goto('/playground');
  await page.getByRole('button', { name: 'Score this run', exact: true }).click();
  await expect(page.locator('.verdict-badge').first()).toBeVisible({ timeout: 20000 });
  const downloadPromise = page.waitForEvent('download', { timeout: 20000 });
  await page.getByRole('button', { name: 'Seal capsule', exact: true }).first().click();
  const download = await downloadPromise;
  const path = await download.path();
  if (!path) throw new Error('capsule download produced no file');
  const capsule = JSON.parse((await import('node:fs')).readFileSync(path, 'utf-8'));
  if (capsule.schema !== 'verification.replay-capsule/1') throw new Error('bad capsule schema');
  if (capsule.mode !== 'live') throw new Error('capsule mode is not live');
  if (typeof capsule.track_hash !== 'string' || capsule.track_hash.length !== 64) throw new Error('capsule hash malformed');
  const verify = await request.post('/api/play/eval/capsule/verify', { data: capsule });
  if (!verify.ok()) throw new Error('verify route failed');
  const verdict = await verify.json();
  if (verdict.up !== true || verdict.data.ok !== true) throw new Error('sealed capsule did not verify');
});


test('workspace wakes a cold backend with backoff retries', async ({ page }) => {
  let calls = 0;
  await page.route('**/api/play/governance', async route => {
    calls += 1;
    if (calls < 3) { await route.abort('failed'); return; }
    await route.continue();
  });
  await page.goto('/playground');
  await expect(page.locator('.connection-state')).toContainText('Backend connected', { timeout: 30000 });
  if (calls < 3) throw new Error('backoff never retried, calls=' + calls);
});

