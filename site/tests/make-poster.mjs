import { chromium } from '@playwright/test';
import sharp from 'sharp';
import path from 'node:path';

const browser = await chromium.launch({ channel: 'msedge', headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1024, height: 960 }, reducedMotion: 'reduce' });
  await page.goto('http://127.0.0.1:5190');
  await page.locator('#failure-lab').scrollIntoViewIfNeeded();
  await page.locator('[data-testid="demo-scene"][data-rendered="true"]').waitFor();
  const image = await page.locator('[data-testid="demo-scene"] canvas').screenshot();
  const output = path.resolve(import.meta.dirname, '../public/robot-poster.webp');
  await sharp(image).resize({ width: 1280 }).webp({ quality: 88 }).toFile(output);
  await sharp(image).resize({ width: 640 }).webp({ quality: 78 }).toFile(path.resolve(import.meta.dirname, '../public/robot-poster-mobile.webp'));
  const metadata = await sharp(output).metadata();
  if (metadata.width !== 1280 || metadata.height < 200) throw new Error('Invalid poster geometry');
  console.log({ poster: output, width: metadata.width, height: metadata.height, bytes: metadata.size });
} finally { await browser.close(); }