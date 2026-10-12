# Physical AI Verification

Independent release verdicts for robot policies and world models. Upload eval results, learn whether a release genuinely improved or just got lucky — with honest intervals, failure hunting, and exportable evidence dossiers.

**Live demo:** https://physical-ai-verification.vercel.app (90-second walkthrough at `/demo`)

## What it does

- **Score a run** — trace deviation against draft evidence gates (mean/final tracking error, path divergence, coherence).
- **Hunt failures** — seeded falsification search over fixture trials; every trial retained and replayable.
- **Compare releases** — baseline vs candidate with Wilson / Clopper-Pearson intervals, rule-of-three at zero failures, and episodes-needed guidance.
- **Compile dossiers** — Policy Assurance Records (PAR) with SHA256 integrity, applicability worksheets, and one-file offline re-verification.
- **Fail closed** — `INSUFFICIENT` beats a false pass. Nothing here says "safe" or "certified". All gates are DRAFT until calibrated.

## Repo layout

- `backend/` — FastAPI engine: eval, hunt, dossiers, ledger, lab endpoints, adapters (LeRobot, LIBERO).
- `packages/engine/` — statistics core (`episodes.py`: intervals, sample-size) and PAR tooling.
- `site/` — Next.js product: marketing pages, validation workspace, 90-sec demo, Free Lab.
- `web/` — Vite operator console (served by the backend for local eval work).
- `tests/` + `backend/tests/` — 800+ test suite.
- `modal_backend.py` — Modal deployment (public demo API).

## Quickstart

```bash
# backend (http://127.0.0.1:8012)
uv sync
uv run uvicorn backend.api:create_app --factory --host 127.0.0.1 --port 8012

# site (http://127.0.0.1:5190)
cd site && npm install && npm run dev

# operator console is served by the backend at / (rebuild with: npm --prefix web run build)
```

## Tests

```bash
uv run pytest tests backend/tests -q
cd site && npx tsc --noEmit && node --test tests/host.test.mjs
```

## Deploy (how the live link runs)

- Backend: `modal deploy modal_backend.py` (app `verification`, secret `verification-env2`).
- Frontend: `vercel deploy ./site --prod` with `BACKEND_URL` set to the Modal URL.
- The site proxies `/api/play/*` to the backend's `/api/v2/*`; browser calls stay same-origin.

## Honesty labels

Everything user-facing is labeled `DRAFT`, `SYNTHETIC`, or `UNSIGNED` where true. The public ledger is ephemeral (resets on backend restart) and the site discloses this. No customer, revenue, or benchmark claim exists in this repo beyond what the test suite proves.

## Sister project

[blind-panel](https://github.com/AK47-1845/blind-panel) — held-out test panels + hash-chained evidence packs with offline verification: the eval-integrity companion to this engine.
