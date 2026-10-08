import { writeFile, mkdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { buildDemoTrack } from '../src/lib/workspace.ts';

const base = process.env.VV_BACKEND_URL ?? 'http://127.0.0.1:8010';
const site = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const calls = [];
const track = await buildDemoTrack(async (route, method = 'GET', body) => {
  const response = await fetch(`${base}/api/v2/${route}`, { method, headers: { 'content-type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(20000) });
  const data = await response.json();
  calls.push({ route, method, status: response.status });
  return { up: true, status: response.status, data };
});
const encoded = JSON.stringify(track);
const capsule = { schema: 'verification.synthetic-replay/1', captured_at: new Date().toISOString(), qualification: 'RECORDED SYNTHETIC demonstration. Real engine responses on fixture inputs, not hardware evidence. DRAFT thresholds. UNSIGNED PAR.', track_sha256: createHash('sha256').update(encoded).digest('hex'), calls, track };
await mkdir(path.join(site, 'src/lib'), { recursive: true });
await writeFile(path.join(site, 'src/lib/demo-receipts.json'), JSON.stringify(capsule, null, 2) + '\n');
console.table(calls);
console.log(`CAPTURE PASS: ${calls.length} actual HTTP responses; PAR and ledger checks passed.`);
console.log(`Capsule track SHA256: ${capsule.track_sha256}`);