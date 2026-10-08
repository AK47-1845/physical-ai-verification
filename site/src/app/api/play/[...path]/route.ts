import { NextResponse } from 'next/server';
import { BACKEND_URL, OFFLINE_HINT, backendFetch } from '@/lib/play-server';

// Transparent proxy: /api/play/<anything> -> BACKEND_URL/api/v2/<anything>.
// One handler covers all 44 backend routes (23 original + 15 console + 3 history lists + 1 ui + 2 capsule).
// Same-origin browser calls (no CORS); server fetch sends no Origin
// header so the mirror perimeter guard never trips. Backend untouched.

async function forward(segments: string[], req: Request, method: string) {
  const target = segments[0] === 'lab'
    ? `/api/lab/v1/${segments.slice(1).map(encodeURIComponent).join('/')}`
    : `/api/v2/${segments.map(encodeURIComponent).join('/')}`;
  const query = new URL(req.url).search;
  try {
    const init: RequestInit = { method };
    if (method !== 'GET' && method !== 'HEAD') {
      const text = await req.text();
      init.body = text || undefined;
    }
    const { status, rawJson } = await backendFetch(target + query, init);
    const host = JSON.stringify(new URL(BACKEND_URL).host);
    return new Response(`{"up":true,"status":${status},"data":${rawJson},"backendHost":${host}}`, { headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } });
  } catch {
    return NextResponse.json({ up: false, hint: OFFLINE_HINT, backendHost: new URL(BACKEND_URL).host });
  }
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: Request, ctx: Ctx) {
  const { path } = await ctx.params;
  return forward(path, req, 'GET');
}

export async function POST(req: Request, ctx: Ctx) {
  const { path } = await ctx.params;
  return forward(path, req, 'POST');
}
