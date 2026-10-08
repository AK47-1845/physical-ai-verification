// Server-only helper: proxy Playground calls to the local V&V backend.
//
// The browser talks same-origin to /api/play/* (these route handlers),
// which forward server-side to the FastAPI backend. No CORS needed,
// and the mirror API's cross-origin-mutation guard never trips (server
// fetch sends no Origin header). Backend stays untouched: D-night-1.

export const BACKEND_URL =
  (process.env.BACKEND_URL ?? process.env.VV_BACKEND_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '');

export const OFFLINE_HINT =
  'Backend is unavailable or waking. Run START-BACKEND.cmd in the working copy, ' +
  'or check the configured cloud backend, then retry.';

export async function backendFetch(path: string, init?: RequestInit) {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    ...init,
    headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
    signal: AbortSignal.timeout(15000),
  });
  const text = await res.text();
  let data: unknown;
  let rawJson: string;
  try {
    data = text ? (JSON.parse(text) as unknown) : null;
    rawJson = text || 'null';
  } catch {
    data = { raw: text };
    rawJson = JSON.stringify(data);
  }
  return { status: res.status, data, rawJson };
}
