# backend/ - Physical AI Verification production backend (built on the night shift)

Everything the night shift built lives here + `packages/engine/`.
Read BACKEND_CHANGELOG.md (meta bro root) for the shift log, then
`docs/OBSERVE.md` for what the internet taught us.

## Layout
- `packages/engine/` - stdlib-only deterministic core: M1 scoring,
  M2 guard, M3 bounded proofs, M4 hunt, M6 ledger, M7 PAR/OTA, FR-32
  credibility, FR-34 release, FR-37 panel, FR-39 worksheet, G9/G10.
  No I/O, no network, no wall clock. Importable anywhere.
- `backend/service_app.py` - FastAPI APIRouter (provenance, PAR, panel,
  release, worksheet, pilots) mounted into the mirror api.py. Flat file:
  backend/service.py already owns that import name.
- `backend/persist/` - open_store factory: MongoDB when MONGO_URL is set,
  file-layout fallback otherwise. Pilot requests + provenance docs land
  here. (Mirror backend/store.py keeps the governance domain.)
- `backend/eval/` - failure-mode harnesses FM1..FM5, cross-embodiment
  transfer (joint-space refused), skill contracts, task graphs, hunt
  backends + FR-36 red-team, NB briefing assembler, policy fixtures.
- `backend/provenance/` - generation-level synthetic-data tracking:
  C2PA-style manifests, mix (alpha) ledgers, collapse sentinels,
  SimHash duplicates, axiom bridge. Wraps `verification axiom` output.
- `backend/adapters/` - ExternalEval protocol + 5 STUB ingestions
  (Isaac/SIMPLER/RoboArena/Halos/LeRobot). Schemas verified on a real
  run before graduation, else refuse.
- `backend/docs/` - OBSERVE.md (recon), ARCHITECTURE.md (this map in
  prose), DECISIONS.md (founder-review log), OPERATE.md, GRADUATION.md,
  INGEST_NOTES.md (adapter formats), GRAPHS.md (have-vs-build index),
  ORCHESTRATION_VERDICT.md (stakeholder asks), DEMO_SCRIPT.md,
  MORNING.md (handoff), TROUBLESHOOT.md (run-queue guide),
  ROUTE_PROPOSAL.md (morning decision 2), RECON_WAVE5-70
  (live web recon), par-schema.json (open v0.1).
- `backend/tests/` - stdlib suites mirroring every module above.
- `backend/requirements-service.txt` - service-only deps. Core stays stdlib.
- `backend/par_cli.py` - offline PAR reader CLI (exit 0/2, no network).
- `backend/demo_client.py` - 10-step morning demo (stdlib urllib).

## Laws (non-negotiable)
1. Determinism: same inputs + profile + seed = byte-identical outputs on the same platform+Python.
2. Fail-closed: missing evidence => INSUFFICIENT/REVIEW, never PASS.
3. Worst gate decides; safety never averages away.
4. No invented customers, certifications, or benchmark wins anywhere.
5. Timestamps are caller-supplied; nothing reads the wall clock in core.
6. No em dashes in product or docs (PRD contract); plain hyphens only.
