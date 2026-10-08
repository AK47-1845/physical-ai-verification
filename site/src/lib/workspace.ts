import sourcePresets from './presets.json' with { type: 'json' };

export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };
export type RecordValue = Record<string, unknown>;
export type PresetContext = Record<string, unknown>;
export type ApiResult = { up: boolean; status: number; data: unknown; backendHost?: string; hint?: string };
export type GateResult = { gate: string; status: string; band: string; measurement: number | null; evidence: string; note: string };
export type TracePair = { intended: number[][]; observed: number[][]; units: 'm'; frame_id: string; name?: string };
export type Sample = TracePair & { id: string; name: string; detail: string; label: 'SYNTHETIC' };
type PresetCall = { id: string; method: string; path: string; expect: number; body?: unknown; save?: Partial<Record<string, string>> };

export const MAX_TRACE_POINTS = 512;
export const MAX_UPLOAD_BYTES = 256 * 1024;
export const PRESET_CALLS: readonly PresetCall[] = sourcePresets.calls;

export function record(value: unknown): RecordValue {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as RecordValue : {};
}

export function text(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function resolve(value: unknown, context: PresetContext, depth = 0): unknown {
  if (depth > 20) throw new Error('Preset references exceed the nesting limit.');
  if (typeof value === 'string') {
    const entire = /^\$([A-Za-z_][A-Za-z0-9_]*)$/.exec(value);
    if (entire) {
      if (!Object.hasOwn(context, entire[1])) throw new Error(`${entire[1]} is required. Complete its preceding workflow first.`);
      return resolve(context[entire[1]], context, depth + 1);
    }
    return value.replace(/\$([A-Za-z_][A-Za-z0-9_]*)/g, (_, key: string) => {
      if (!Object.hasOwn(context, key)) throw new Error(`${key} is required. Complete its preceding workflow first.`);
      const resolved = resolve(context[key], context, depth + 1);
      if (typeof resolved !== 'string' && typeof resolved !== 'number') throw new Error(`${key} must be a scalar in a path.`);
      return String(resolved);
    });
  }
  if (Array.isArray(value)) return value.map(item => resolve(item, context, depth + 1));
  if (value !== null && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, resolve(item, context, depth + 1)]));
  return value;
}

export function presetRequest(id: string, context: PresetContext = {}) {
  const preset = PRESET_CALLS.find(item => item.id === id);
  if (!preset) throw new Error(`Unknown preset: ${id}`);
  for (const [key, value] of Object.entries(context)) {
    if (key.endsWith('_ID') && (typeof value !== 'string' || !/^[a-zA-Z0-9_-]{1,128}$/.test(value))) throw new Error(`${key}: invalid identifier.`);
  }
  const merged = { ...sourcePresets.constants, ...context };
  return { ...preset, path: resolve(preset.path, merged) as string, body: resolve(preset.body, merged) };
}

export function captureContext(id: string, data: unknown, context: PresetContext): PresetContext {
  const call = PRESET_CALLS.find(item => item.id === id);
  const next = { ...context };
  for (const [key, pointer] of Object.entries(call?.save ?? {})) {
    if (pointer === undefined) continue;
    let value = data;
    if (pointer) for (const part of pointer.split('.')) value = record(value)[part];
    if (value !== undefined) next[key] = value;
  }
  return next;
}

export type Exchange = { path: string; method: string; body: unknown; status: number; data: unknown; backendHost?: string };
let exchangeSeq = 0;
let lastExchangeValue: Exchange | null = null;

export function exchangeCount(): number {
  return exchangeSeq;
}

export function lastExchange(): Exchange | null {
  return lastExchangeValue;
}

function noteExchange(entry: Exchange): void {
  exchangeSeq += 1;
  lastExchangeValue = entry;
}

export async function apiRequest(path: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<ApiResult> {
  const direct = process.env.NEXT_PUBLIC_BACKEND_URL?.replace(/\/$/, '');
  const target = direct ? `${direct}${path.startsWith('lab/') ? `/api/lab/v1/${path.slice(4)}` : `/api/v2/${path}`}` : `/api/play/${path}`;
  const timeout = AbortSignal.timeout(20000);
  try {
    const response = await fetch(target, {
      method,
      headers: { 'content-type': 'application/json' },
      body: body === undefined || method === 'GET' ? undefined : JSON.stringify(body),
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
      cache: 'no-store',
    });
    const data: unknown = await response.json();
    if (direct) {
      const host = new URL(direct).host;
      noteExchange({ path, method, body, status: response.status, data, backendHost: host });
      return { up: true, status: response.status, data, backendHost: host };
    }
    const wrapped = record(data);
    const status = typeof wrapped.status === 'number' ? wrapped.status : response.status;
    noteExchange({ path, method, body, status, data: wrapped.data, backendHost: text(wrapped.backendHost) });
    return { up: wrapped.up === true, status, data: wrapped.data, backendHost: text(wrapped.backendHost), hint: text(wrapped.hint) };
  } catch (error) {
    if (signal?.aborted) throw error;
    return { up: false, status: 0, data: null, hint: 'The backend did not respond. Retry the connection or open the labeled synthetic demo.' };
  }
}

export function apiError(result: ApiResult): string {
  const value = record(result.data);
  const detail = record(value.detail);
  return text(detail.message) || text(value.message) || text(value.reason) || text(value.detail) || result.hint || `The request was refused (${result.status}). Check the input and retry.`;
}

export function formatValue(value: unknown, digits = 3): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString('en-US', { maximumFractionDigits: digits }) : 'Not measured';
}

export function resultSummary(value: unknown): { verdict: string; gates: GateResult[]; hash: string; runId: string; profile: string } {
  const root = record(value);
  const card = record(root.scorecard ?? root);
  const payload = record(card.payload);
  const rawGates = Array.isArray(payload.gates) ? payload.gates : [];
  const gates = rawGates.map(item => {
    const gate = record(item);
    const measured = typeof gate.measurement === 'number' && Number.isFinite(gate.measurement);
    return { gate: text(gate.gate, 'unrecorded'), status: measured ? text(gate.status, 'INSUFFICIENT') : 'INSUFFICIENT', band: text(gate.band, 'grey'), measurement: measured ? gate.measurement as number : null, evidence: text(gate.evidence), note: text(gate.note) };
  });
  const declared = text(payload.verdict, 'INSUFFICIENT');
  const verdict = !gates.length || gates.some(gate => gate.measurement === null) ? 'INSUFFICIENT' : declared;
  return { verdict, gates, hash: text(card.hash) || text(card.payload_hash) || text(card.scorecard_hash), runId: text(root.run_id), profile: text(card.profile_version, 'draft-0') };
}

function validatePoints(value: unknown, name: string): number[][] {
  if (!Array.isArray(value) || value.length < 2 || value.length > MAX_TRACE_POINTS) throw new Error(`${name}: provide 2 to ${MAX_TRACE_POINTS} points.`);
  let dimension = 0;
  for (const [index, point] of value.entries()) {
    if (!Array.isArray(point) || ![2, 3].includes(point.length)) throw new Error(`${name}[${index}]: each point needs 2 or 3 coordinates.`);
    if (!dimension) dimension = point.length;
    if (point.length !== dimension) throw new Error(`${name}[${index}]: coordinate dimensions must match.`);
    if (!point.every(coordinate => typeof coordinate === 'number' && Number.isFinite(coordinate))) throw new Error(`${name}[${index}]: coordinates must be finite numbers, not text or booleans.`);
  }
  return value as number[][];
}

export function parseTrace(source: string): TracePair {
  if (new TextEncoder().encode(source).length > MAX_UPLOAD_BYTES) throw new Error('File exceeds the 256 KB free-upload limit.');
  let parsed: unknown;
  try { parsed = JSON.parse(source); } catch { throw new Error('This file is not valid JSON. Use the downloadable trace template.'); }
  const value = record(parsed);
  if (value.units !== 'm') throw new Error('Declare units: "m". Convert coordinates to metres before upload.');
  if (typeof value.frame_id !== 'string' || !/^[a-zA-Z0-9_.-]{1,80}$/.test(value.frame_id)) throw new Error('Declare one frame_id shared by both traces. Cross-frame comparisons are refused.');
  const intended = validatePoints(value.intended, 'intended');
  if (Array.isArray(value.observed) && intended.length !== value.observed.length) throw new Error('Both traces must contain the same number of points. No silent alignment is applied.');
  const observed = validatePoints(value.observed, 'observed');
  if (intended[0].length !== observed[0].length) throw new Error('Both traces must have the same coordinate dimension.');
  return { intended, observed, units: 'm', frame_id: value.frame_id, name: text(value.name).slice(0, 80) };
}

export function traceErrors(intended: number[][], observed: number[][]): number[] {
  if (intended.length !== observed.length) throw new Error('Both traces must contain the same number of points.');
  return intended.map((point, index) => Math.hypot(...point.map((coordinate, axis) => coordinate - observed[index][axis])));
}

const intended = sourcePresets.constants.T6A;
export const SAMPLES: readonly Sample[] = [
  { id: 'clean', name: 'Nominal reach', detail: 'Small tracking error', intended, observed: sourcePresets.constants.T6B, units: 'm', frame_id: 'world', label: 'SYNTHETIC' },
  { id: 'drifty', name: 'Drifting reach', detail: 'Accumulating deviation', intended, observed: sourcePresets.constants.T6DRIFT, units: 'm', frame_id: 'world', label: 'SYNTHETIC' },
  { id: 'playback', name: 'Stalled playback', detail: 'Position does not advance', intended, observed: intended.map(() => [0, 0]), units: 'm', frame_id: 'world', label: 'SYNTHETIC' },
  { id: 'spike', name: 'Sensor spike', detail: 'One final-step outlier', intended, observed: intended.map((point, index) => [point[0], index === intended.length - 1 ? 1.4 : 0.02]), units: 'm', frame_id: 'world', label: 'SYNTHETIC' },
];

export const GATE_INFO: Record<string, { name: string; green: number; amber: number; unit: string; description: string }> = {
  drift_mean: { name: 'Mean tracking error', green: 0.15, amber: 0.5, unit: 'm', description: 'Average pointwise distance over this trace. Profile draft-0.' },
  drift_final: { name: 'Final tracking error', green: 0.2, amber: 0.6, unit: 'm', description: 'Distance between the two final positions. Profile draft-0.' },
  frechet_gap: { name: 'Path divergence', green: 0.3, amber: 0.8, unit: 'm', description: 'Discrete Frechet distance between paths in the declared frame. Profile draft-0.' },
  coherence: { name: 'Coherent horizon', green: 0.5, amber: 0.8, unit: 'ratio', description: 'Trace fraction before a three-step breach of the 0.5 m screening boundary. Higher is better.' },
};

export type DemoTrack = {
  clean: unknown; drifty: unknown; hunt: unknown; dossier: unknown; verification: unknown; ledger: unknown;
  inputs: { clean: TracePair; drifty: TracePair };
};

export function passBoundary(gate: string): string {
  const info = GATE_INFO[gate];
  if (!info) return 'Not recorded';
  return `${gate === 'coherence' ? '>' : '<'} ${gate === 'coherence' ? info.amber : info.green} ${info.unit}`;
}

export async function buildDemoTrack(send: (path: string, method?: string, body?: unknown) => Promise<ApiResult> = apiRequest): Promise<DemoTrack> {
  let context: PresetContext = {};
  async function step(id: string, override?: unknown) {
    const request = presetRequest(id, context);
    const response = await send(request.path, request.method, override ?? request.body);
    if (!response.up || response.status !== request.expect) throw new Error(apiError(response));
    context = captureContext(id, response.data, context);
    return response.data;
  }
  const base = record(presetRequest('runs-evaluate').body);
  const clean = await step('runs-evaluate', { ...base, intended: SAMPLES[0].intended, observed: SAMPLES[0].observed, policy_id: 'demo-clean-v1' });
  const drifty = await step('runs-evaluate', { ...base, intended: SAMPLES[1].intended, observed: SAMPLES[1].observed, policy_id: 'demo-drifty-v1' });
  const hunt = await step('hunt-random', { ...record(presetRequest('hunt-random').body), trial_cap: 16 });
  const dossier = await step('dossiers-compile', { ...record(presetRequest('dossiers-compile', context).body), odd: 'SYNTHETIC 2D reacher, world frame, no hardware execution', independence: { builder: 'Synthetic fixture', funder: 'Internal demonstration', relationship: 'No external assessment' } });
  const envelope = record(dossier).par;
  const verification = await step('par-validate', { envelope });
  if (record(verification).ok !== true) throw new Error('Captured PAR did not pass the integrity check.');
  const ledger = await step('ledger-verify');
  if (record(ledger).ok !== true) throw new Error('Captured ledger did not pass verification.');
  return { clean, drifty, hunt, dossier, verification, ledger, inputs: { clean: SAMPLES[0], drifty: SAMPLES[1] } };
}