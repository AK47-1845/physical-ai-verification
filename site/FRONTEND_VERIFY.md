# FRONTEND VERIFY (C22, 2026-10-04) - founder-run, no compiler in sandbox

C22 added a release-brief UI over the new backend route
GET /api/v2/ui/release/{run_id} (Block 8). TypeScript was NOT compiled
here (sandbox has no Node): every line below was hand-checked
(line-by-line record at the bottom), but `tsc` + `next build` on your
machine are the real gate. [Unverified-needs-founder-run]

## Files touched (C22)
- NEW site/src/components/ReleaseSummary.tsx (render-only brief card)
- NEW site/src/app/release/page.tsx (/release?run=&compare= page)
- site/src/components/AppShell.tsx (1 line: chatbot behind a flag)
- site/src/lib/console-endpoints.ts (4 catalog entries + count comment)
- site/src/app/api/play/[...path]/route.ts (comment only: 38 -> 42)

## Behavior changes
- New page /release?run=<run_id>&compare=<run_id> renders the backend
  view-model (verdict banner, headline, reasons, what-would-change,
  chips, delta table, copyable offline-verify command).
- Console (Playground) gains 4 entries: runs-list, ui-release,
  dossiers-list, dossiers-get. Catalog now covers 42/42 routes.
- Chatbot is OFF by default (its intents are stale, Block 8 cut).
  Enable: set NEXT_PUBLIC_CHATBOT=on before starting the site
  (Windows cmd: `set NEXT_PUBLIC_CHATBOT=on && npm run dev`,
  or put `NEXT_PUBLIC_CHATBOT=on` in site/.env.local).

## Run this (from hi bro/meta bro/site)
1. `npx tsc --noEmit`
   Expect: no output, exit 0.
2. `npm run build`
   Expect: compiled successfully, 8+ routes (incl /release,
   /playground), no type errors.
3. `npm run dev` (port 5194) + backend on :8000, then:
   - console: POST runs/evaluate, paste run_id into ui-release -> 200
   - open /release?run=<that id> -> brief renders, chips show
   - offline-verify command copies to clipboard.

## Paste back on failure
The FIRST 40 lines of the tsc or build output, plus which step failed.
Do not paste the whole log.

## Line-by-line hand check (assistant, no compiler)
ReleaseSummary.tsx: 'use client' present; react imports (useEffect,
useState) both used; all 6 type aliases used, no `any`, no custom
generics (useState<T> matches Playground style); isView narrows
unknown->ReleaseView with Array checks on every mapped field;
verdictClass covers all paths; useEffect deps [runId, compareId]
complete with live-flag cleanup; fetch envelope unwrapped as
{up,status,data} exactly like Playground; 404/422/offline branches
all render; clipboard write in try/catch; JSX balanced (div/fragment/
table/ul/pre/button all closed, keys on all maps); classes used
(lab-shell, lab-topbar, lab-results, mono, pass, fail, muted, button
secondary) all exist in Playground/site.css; view-model field names
(run_id, verdict_plain, what_would_change, band_from, offline_verify,
...) verified against tests/golden/viewmodel_clean.json keys.
release/page.tsx: query read from window.location (NOT useSearchParams,
so any Next output mode builds); window guard for SSR; useState lazy
initializer; shown-object && render pattern; all imports used; section/
container/section-header/section-number classes mirror existing pages.
AppShell.tsx: 1-line ternary, Chatbot import still used, env var
comparison is string-safe when unset (undefined === 'on' is false).
console-endpoints.ts: 4 entries match the Endpoint/Preset types;
param-less GET presets mirror pilots-list/governance precedent;
{run_id}/{dossier_id} params mirror runs-get/pilots-get.
route.ts: comment text only, no code change.
Claims lint over site/src: green (test_claims_lint 3/3) AFTER these
files landed, so no banned marketing word ships in the new UI copy.
