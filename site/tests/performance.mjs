import lighthouse from 'lighthouse';
import { launch } from 'chrome-launcher';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const output = path.resolve(import.meta.dirname, '../../design-intel/performance');
await mkdir(output, { recursive: true });
const chrome = await launch({ chromePath: path.join(process.env['PROGRAMFILES(X86)'], 'Microsoft/Edge/Application/msedge.exe'), chromeFlags: ['--headless=new', '--no-first-run'], logLevel: 'error' });
const summaries = [];
try {
  for (const preset of ['mobile', 'desktop']) {
    const flags = { port: chrome.port, output: 'json', logLevel: 'error', onlyCategories: ['performance', 'accessibility', 'best-practices', 'seo'] };
    if (preset === 'desktop') Object.assign(flags, { formFactor: 'desktop', screenEmulation: { mobile: false, width: 1440, height: 960, deviceScaleFactor: 1, disabled: false }, throttling: { rttMs: 40, throughputKbps: 10240, cpuSlowdownMultiplier: 1, requestLatencyMs: 0, downloadThroughputKbps: 0, uploadThroughputKbps: 0 } });
    const result = await lighthouse(process.env.SITE_URL ?? 'http://127.0.0.1:5191', flags);
    await writeFile(path.join(output, `${preset}.json`), result.report);
    const report = result.lhr;
    const summary = { preset, capturedAt: report.fetchTime, lighthouseVersion: report.lighthouseVersion,
      scores: Object.fromEntries(Object.entries(report.categories).map(([key, value]) => [key, Math.round(value.score * 100)])),
      lcpMs: report.audits['largest-contentful-paint'].numericValue, cls: report.audits['cumulative-layout-shift'].numericValue,
      tbtMs: report.audits['total-blocking-time'].numericValue,
      issues: Object.entries(report.audits).filter(([, audit]) => audit.score !== null && audit.score < .9).map(([id, audit]) => ({ id, score: audit.score, displayValue: audit.displayValue, title: audit.title })).slice(0, 14) };
    summaries.push(summary);
    console.log(JSON.stringify(summary, null, 2));
  }
} finally { await chrome.kill(); }
await writeFile(path.join(output, 'summary.json'), JSON.stringify(summaries, null, 2));