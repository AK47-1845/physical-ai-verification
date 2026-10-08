// Full console catalog: all 44 backend routes with working presets.
// Every preset body below was validated against the real handler
// (shapes cross-checked with the test suites + route tests).

export type Preset = { name: string; body?: unknown; params?: Record<string, string> };
export type Endpoint = {
  id: string; group: string; method: 'GET' | 'POST'; path: string;
  desc: string; prereq?: string; presets: Preset[];
};

export const T6A = [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0], [5, 0]];
export const T6B = [[0, 0], [1, 0.1], [2, -0.1], [3, 0.2], [4, 0], [5, 0.1]];
const T6DRIFT = [[0, 0], [1, 0.3], [2, 0.7], [3, 1.2], [4, 1.8], [5, 2.5]];

const ARM = { embodiment_id: 'arm-7dof', space: 'task', position_scale: 1.0, frame_id: 'world' };
const HUMANOID = { embodiment_id: 'humanoid', space: 'task', position_scale: 2.0, frame_id: 'world' };
const JOINT = { embodiment_id: 'arm-7dof', space: 'joint', position_scale: 1.0, frame_id: 'world' };
const TRACE3 = [[0, 0], [1, 0], [1, 1]];

const WEIGHTS = 'sha256:' + 'f'.repeat(64);
const HEX64 = (ch: string) => ch.repeat(64);

const HARDCODED_PAR = {
  par: {
    gates: [{ evidence: 'ev:1', id: 'tracking', measurement: 0.1, verdict: 'PASS' }],
    independence: { builder: 'OEM-X', funder: 'OEM-X', relationship: 'none' },
    ledger_head: HEX64('e'),
    odd: 'console demo cell, 2D reacher, supervised',
    par_version: '0.1',
    policy: { id: 'arm-reach', weights: WEIGHTS },
    release: { delta: 'IN-ODD', parent: WEIGHTS },
  },
  par_hash: '8b5588bc033f529eb582e48021c7baf66e184997228f114dab98731c84cd1126',
};

const CARD = {
  gate_id: 'tracking', gate_version: '1.0', corpus_hash: HEX64('a'), n: 120,
  false_positives: 2, false_negatives: 1, label_counts: { pass: 100, fail: 20 },
  calibration_bins: [{ lo: 0.0, hi: 0.5, predicted: 0.2, observed: 0.22, n: 60 }],
  rollout_types: { 'policy-sampled': 120 }, transfer_error: 0.03, search_hits: 0,
  date: '2026-10-04', analyst: 'qa',
};
const CARD_HASH = '88a3235d56bc59f512f87326ec0c3f7967e356e92b97e1c420f9cf27b500a47a';
const COMMITMENT = '6193506908fb8362c9e1506dc26bab6024775eb632cd3e79a41e6f569d41c15d';

const G_PASS = { gate: 't', measurement: 0.1, status: 'PASS' };
const G_BLOCK = { gate: 't', measurement: 0.9, status: 'BLOCKED' };

const LIBERO_DOC = {
  framework: 'libero', benchmark: 'libero_spatial', task_id: 3, seed: 100,
  env_num: 20, num_success: 14, success_rate: 0.7, loss: 0.42,
};

const SEALED_DEMO_CAPSULE = {
  schema: 'verification.replay-capsule/1', mode: 'live',
  request: { path: 'runs/evaluate', method: 'POST', body: { policy_id: 'demo-clean-v1' } },
  envelope: { status: 200, data: { verdict: 'TRUSTED' } },
  backend_host: 'console',
  track_hash: 'e9cc935af385c13d8cfcbc5b18e4377c303265342bf98354b1de9d8e47aaa22d',
};

const MIN_CATALOGUE = {
  mode: 'grid', seed: 1, trial_cap: 2, exhausted: true,
  trials: [
    { trial: 0, params: { bias: 0.0 }, breaks: true, measurement: 0.9 },
    { trial: 1, params: { bias: 0.5 }, breaks: false, measurement: 0.1 },
  ],
  breaks: [{ trial: 0, params: { bias: 0.0 }, breaks: true, measurement: 0.9 }],
};

export const ENDPOINTS: Endpoint[] = [
  // ---------- SCORE & RUNS ----------
  { id: 'eval-score', group: 'Score & runs', method: 'POST', path: 'eval/score',
    desc: 'Score one trace pair into a pinned scorecard.',
    presets: [
      { name: 'Nominal', body: { intended: T6A, observed: T6B, profile: 'draft-0', seed: 7, threshold: 0.5, evidence_prefix: 'playground' } },
      { name: 'Drifted', body: { intended: T6A, observed: T6DRIFT, profile: 'draft-0', seed: 7, threshold: 0.5, evidence_prefix: 'playground' } },
    ] },
  { id: 'runs-evaluate', group: 'Score & runs', method: 'POST', path: 'runs/evaluate',
    desc: 'Score + persist as a run. Returns run_id for dossiers.',
    presets: [
      { name: 'Demo run', body: { intended: T6A, observed: T6B, policy_id: 'console-demo', seed: 7, threshold: 0.5 } },
    ] },
  { id: 'runs-get', group: 'Score & runs', method: 'GET', path: 'runs/{run_id}',
    desc: 'Fetch one stored run.',
    prereq: 'POST runs/evaluate first, paste its run_id.',
    presets: [{ name: 'By id', params: { run_id: 'PASTE_RUN_ID' } }] },
  { id: 'runs-list', group: 'Score & runs', method: 'GET', path: 'runs',
    desc: 'List stored run ids.',
    presets: [{ name: 'List' }] },
  { id: 'ui-release', group: 'Score & runs', method: 'GET', path: 'ui/release/{run_id}',
    desc: 'Release brief: verdict, reasons, deltas, offline-verify. Compare runs on the /release page.',
    prereq: 'POST runs/evaluate first, paste its run_id.',
    presets: [{ name: 'By id', params: { run_id: 'PASTE_RUN_ID' } }] },
  // ---------- FAILURE MODES & GATES ----------
  { id: 'failure-modes', group: 'Failure modes & gates', method: 'POST', path: 'eval/failure-modes',
    desc: 'FM1 drift + FM2 executability proxy + FM5 sim-real gap. FM3/FM4 stay library-only (need model callables).',
    presets: [
      { name: 'Nominal', body: { intended: T6A, observed: T6B, threshold: 0.5, breach_run: 3, bounds: [-2, 2] } },
      { name: 'Wild', body: { intended: T6A, observed: T6DRIFT, threshold: 0.5, breach_run: 2, bounds: [-1, 1] } },
    ] },
  { id: 'property', group: 'Failure modes & gates', method: 'POST', path: 'eval/property',
    desc: 'G9 signed satisfaction margin with a named predicate.',
    presets: [
      { name: 'Clearance holds', body: { spec: { op: 'always', predicate: 'clearance', name: 'stay-clear' }, trace: [{ clearance: 0.5 }, { clearance: 0.2 }] } },
      { name: 'Speed violates', body: { spec: { op: 'always', predicate: 'speed_cap_2', name: 'speed-cap' }, trace: [{ speed: 1.0 }, { speed: 2.5 }] } },
    ] },
  { id: 'bounded', group: 'Failure modes & gates', method: 'POST', path: 'eval/bounded',
    desc: 'M3 slice-1 bound check: PROVEN / VIOLATED / UNKNOWN.',
    presets: [
      { name: 'Proven', body: { layers: [{ weights: [[0.5]], bias: [0.0] }], input_box: [[0, 1]], output_bounds: [[-0.5, 1]] } },
      { name: 'Violated', body: { layers: [{ weights: [[2.0]], bias: [0.0] }], input_box: [[0, 1]], output_bounds: [[0, 1]], grid_per_dim: 3 } },
    ] },
  { id: 'credibility', group: 'Failure modes & gates', method: 'POST', path: 'eval/credibility',
    desc: 'FR-32 DRAFT-lift gate. No card, no lift.',
    presets: [
      { name: 'Good card', body: { card_envelope: { card: CARD, card_hash: CARD_HASH } } },
    ] },
  { id: 'rank', group: 'Failure modes & gates', method: 'POST', path: 'eval/rank',
    desc: 'FR-6 worst-first policy ranking for triage.',
    presets: [
      { name: 'Three policies', body: { entries: [
        { policy_id: 'p1', verdict: 'TRUSTED', gates: [{ status: 'PASS' }] },
        { policy_id: 'p2', verdict: 'BLOCKED', gates: [{ status: 'BLOCKED' }] },
        { policy_id: 'p3', verdict: 'REVIEW', gates: [{ status: 'REVIEW' }] },
      ] } },
    ] },
  // ---------- HUNTS ----------
  { id: 'hunt', group: 'Hunts', method: 'POST', path: 'eval/hunt',
    desc: 'Seeded M4 falsification hunt over a fixture policy.',
    presets: [
      { name: 'Defaults (breaks)', body: {} },
      { name: 'Random clean', body: { policy: 'clean', method: 'random', space: { noise_scale: [0.5, 2.0], bias: [0.0, 1.0] }, seed: 1, trial_cap: 8 } },
    ] },
  { id: 'redteam', group: 'Hunts', method: 'POST', path: 'eval/redteam',
    desc: 'FR-36 hunt at OUR scorer. Broken must break; sane must not.',
    presets: [
      { name: 'Broken (hits!)', body: { score_fn: 'broken' } },
      { name: 'Sane (silent)', body: { score_fn: 'sane' } },
    ] },
  { id: 'hunt-summarize', group: 'Hunts', method: 'POST', path: 'eval/hunt/summarize',
    desc: 'Summarize + seal a catalogue. Or paste a real one from a hunt above.',
    presets: [{ name: 'Minimal catalogue', body: { catalogue: MIN_CATALOGUE } }] },
  { id: 'envelope', group: 'Hunts', method: 'POST', path: 'eval/envelope',
    desc: 'Marginal break/hold boundary map. Marginal-only, labeled.',
    presets: [
      { name: 'Two params', body: { trials: [
        { breaks: true, params: { noise_scale: 2.0, bias: 0.5 } },
        { breaks: false, params: { noise_scale: 1.0, bias: 0.0 } },
        { breaks: true, params: { noise_scale: 2.0, bias: 0.0 } },
        { breaks: false, params: { noise_scale: 0.5, bias: 0.0 } },
      ], param_names: ['noise_scale', 'bias'] } },
    ] },
  // ---------- TRANSFER & CONTRACTS ----------
  { id: 'transfer', group: 'Transfer & contracts', method: 'POST', path: 'eval/transfer',
    desc: 'Cross-embodiment transfer. Joint-space refuses loudly.',
    presets: [
      { name: 'Arm to arm', body: { card_a: ARM, trace_a: TRACE3, card_b: ARM, trace_b: TRACE3, threshold: 0.1 } },
      { name: 'Arm to humanoid', body: { card_a: ARM, trace_a: TRACE3, card_b: HUMANOID, trace_b: TRACE3, threshold: 0.1 } },
      { name: 'Joint refuses', body: { card_a: JOINT, trace_a: TRACE3, card_b: ARM, trace_b: TRACE3, threshold: 0.1 } },
    ] },
  { id: 'contracts-check', group: 'Transfer & contracts', method: 'POST', path: 'eval/contracts/check',
    desc: 'Preset skill contracts (grasp|release). Custom stays library-only.',
    presets: [
      { name: 'Grasp holds', body: { contract_id: 'grasp', states: [{ gripper_open: true, holding: false }, { gripper_open: true, holding: true }] } },
      { name: 'Grasp violates', body: { contract_id: 'grasp', states: [{ gripper_open: false, holding: false }, { gripper_open: true, holding: true }] } },
    ] },
  { id: 'task-graph', group: 'Transfer & contracts', method: 'POST', path: 'eval/task-graph',
    desc: 'Task DAG order + PAR chain. Cycles refuse.',
    presets: [
      { name: 'Chain', body: { graph: { nodes: [{ id: 'approach', skill_id: 'move' }, { id: 'grasp', skill_id: 'grasp' }, { id: 'lift', skill_id: 'move' }], edges: [['approach', 'grasp'], ['grasp', 'lift']] } } },
      { name: 'Cycle refuses', body: { graph: { nodes: [{ id: 'a' }, { id: 'b' }], edges: [['a', 'b'], ['b', 'a']] } } },
    ] },
  { id: 'briefing', group: 'Transfer & contracts', method: 'POST', path: 'eval/briefing',
    desc: 'Notified-Body briefing view over a PAR.',
    presets: [
      { name: 'PAR only', body: { par_envelope: HARDCODED_PAR } },
      { name: 'PAR + worksheet', body: { par_envelope: HARDCODED_PAR, worksheet: { implied_route: 'PART_A_5_6_NOTIFIED_BODY_ROUTE', banner: 'Human and legal review required.' } } },
    ] },
  // ---------- PROVENANCE ----------
  { id: 'batches', group: 'Provenance', method: 'POST', path: 'provenance/batches',
    desc: 'Stamp a generation-level batch manifest.',
    presets: [
      { name: 'Axiom batch', body: { generator: { name: 'axiom-sim', version: '0.3' }, seed: 11, content_hash: HEX64('c'), n_rows: 500, ingredients: [{ kind: 'real', n_rows: 500 }], batch_seq: 1 } },
    ] },
  { id: 'bridge', group: 'Provenance', method: 'POST', path: 'provenance/bridge',
    desc: 'Axiom generation wrap: manifest + mix batch + datacard.',
    presets: [
      { name: 'Axiom run', body: { generator_name: 'axiom-sim', generator_version: '0.3', seed: 11, n_rows: 500, content_hash: HEX64('d'), real_ingredients: [{ kind: 'real', n_rows: 500 }], axiom_datacard: { split: 'train' } } },
    ] },
  { id: 'sentinels', group: 'Provenance', method: 'POST', path: 'provenance/sentinels',
    desc: 'Collapse sentinels over baseline/current columns.',
    presets: [
      { name: 'Healthy', body: { baseline: { x: [0.1, 0.5, 0.9, 0.3, 0.7] }, current: { x: [0.2, 0.4, 0.8, 0.35, 0.65] } } },
      { name: 'Collapsed', body: { baseline: { x: [0.1, 0.5, 0.9, 0.3, 0.7] }, current: { x: [0.5, 0.5, 0.5, 0.5, 0.5] } } },
    ] },
  { id: 'corpora', group: 'Provenance', method: 'POST', path: 'provenance/corpora',
    desc: 'Open a mix-ledger corpus.',
    presets: [{ name: 'New corpus', body: { corpus_id: 'console-corpus-1' } }] },
  { id: 'generations', group: 'Provenance', method: 'POST', path: 'provenance/corpora/{corpus_id}/generations',
    desc: 'Append one generation (alpha computed, unstamped refused).',
    prereq: 'POST provenance/corpora first, paste its id.',
    presets: [{ name: 'Gen 0', params: { corpus_id: 'console-corpus-1' }, body: { real_rows: 800, synth_batches: [{ manifest_id: 'console-demo-batch', n_rows: 200 }] } }] },
  { id: 'risk', group: 'Provenance', method: 'GET', path: 'provenance/corpora/{corpus_id}/risk',
    desc: 'Accumulate/replace/synthetic-only verdict.',
    prereq: 'Needs a corpus with generations.',
    presets: [{ name: 'Risk', params: { corpus_id: 'console-corpus-1' } }] },
  { id: 'duplicates', group: 'Provenance', method: 'POST', path: 'provenance/duplicates',
    desc: 'Exact or SimHash near-duplicate rate.',
    presets: [
      { name: 'Near', body: { rows: [[1.0], [1.0], [5.0]], mode: 'near' } },
      { name: 'Exact', body: { rows: [[1.0], [1.0], [5.0]], mode: 'exact' } },
    ] },
  // ---------- PAR & DOSSIER ----------
  { id: 'par-build', group: 'PAR & dossier', method: 'POST', path: 'par/build',
    desc: 'Build + hash a Policy Assurance Record.',
    presets: [
      { name: 'Demo PAR', body: { policy: { id: 'arm-reach', weights: WEIGHTS }, release: { parent: WEIGHTS, delta: 'IN-ODD' }, gates: [{ id: 'tracking', verdict: 'PASS', measurement: 0.1, evidence: 'ev:1' }], ledger_head: HEX64('e'), odd: 'console demo cell, 2D reacher, supervised', independence: { builder: 'OEM-X', funder: 'OEM-X', relationship: 'none' } } },
    ] },
  { id: 'par-validate', group: 'PAR & dossier', method: 'POST', path: 'par/validate',
    desc: 'Recompute + structural check of a PAR envelope.',
    presets: [{ name: 'Valid PAR', body: { envelope: HARDCODED_PAR } }] },
  { id: 'par-read', group: 'PAR & dossier', method: 'POST', path: 'par/read',
    desc: 'Offline-reader rendering of a PAR envelope.',
    presets: [{ name: 'Read PAR', body: { envelope: HARDCODED_PAR } }] },
  { id: 'dossiers-compile', group: 'PAR & dossier', method: 'POST', path: 'dossiers/compile',
    desc: 'Compile stored runs into a sealed PAR + ledger seal.',
    prereq: 'POST runs/evaluate first, paste its run_id.',
    presets: [{ name: 'Compile', body: { run_ids: ['PASTE_RUN_ID'], independence: { builder: 'OEM-X', funder: 'OEM-X', relationship: 'none' }, odd: 'console demo cell, 2D reacher, supervised' } }] },
  { id: 'dossiers-list', group: 'PAR & dossier', method: 'GET', path: 'dossiers',
    desc: 'List compiled dossier ids.',
    presets: [{ name: 'List' }] },
  { id: 'dossiers-get', group: 'PAR & dossier', method: 'GET', path: 'dossiers/{dossier_id}',
    desc: 'Fetch one compiled dossier.',
    prereq: 'POST dossiers/compile first, paste its dossier_id.',
    presets: [{ name: 'By id', params: { dossier_id: 'PASTE_DOSSIER_ID' } }] },
  { id: 'ledger-verify', group: 'PAR & dossier', method: 'POST', path: 'ledger/verify',
    desc: 'Re-verify the full hash chain from the store.',
    presets: [{ name: 'Verify', body: {} }] },
  // ---------- PANEL & RELEASES ----------
  { id: 'panel-commit', group: 'Panel & releases', method: 'POST', path: 'panel/commit',
    desc: 'Commit a held-out panel BEFORE scoring.',
    presets: [{ name: 'Commit', body: { seed: 'console-seed-1', case_count: 8 } }] },
  { id: 'panel-reveal', group: 'Panel & releases', method: 'POST', path: 'panel/reveal',
    desc: 'Verify a reveal against its commitment.',
    presets: [
      { name: 'Honest reveal', body: { commitment: COMMITMENT, seed: 'console-seed-1', case_count: 8 } },
      { name: 'Wrong seed fails', body: { commitment: COMMITMENT, seed: 'console-seed-2', case_count: 8 } },
    ] },
  { id: 'releases-compare', group: 'Panel & releases', method: 'POST', path: 'releases/compare',
    desc: 'Parent/child compare with modification flag.',
    presets: [
      { name: 'Identical', body: { parent_gates: [G_PASS], child_gates: [G_PASS], parent_weights_hash: 'h', child_weights_hash: 'h' } },
      { name: 'Regression flags', body: { parent_gates: [G_PASS], child_gates: [G_BLOCK], parent_weights_hash: 'p', child_weights_hash: 'c' } },
    ] },
  // ---------- WORKSHEET & GOVERNANCE ----------
  { id: 'worksheet', group: 'Worksheet & governance', method: 'POST', path: 'worksheet/record',
    desc: 'Applicability worksheet. Routes implied, never decided.',
    presets: [
      { name: 'Notified-body route', body: { product: 'console-arm', analyst: 'qa', ml_safety_function: true, self_evolving: true, frozen_weight_ota: false } },
      { name: 'OTA variant', body: { product: 'console-arm', analyst: 'qa', ml_safety_function: true, self_evolving: false, frozen_weight_ota: true } },
    ] },
  { id: 'governance', group: 'Worksheet & governance', method: 'GET', path: 'governance',
    desc: 'Regulatory clock snapshot. Not legal advice.',
    presets: [{ name: 'Snapshot' }] },
  // ---------- PILOTS ----------
  { id: 'pilots-post', group: 'Pilots', method: 'POST', path: 'pilots',
    desc: 'Intake a pilot. Deterministic id, idempotent re-posts.',
    presets: [
      { name: 'Demo pilot', body: { name: 'Ada Lovelace', org: 'Console Labs', email: 'ada@consolelabs.dev', robot: 'humanoid pilot', failure_mode: 'sim-to-real drift at horizon', notes: 'Sent from the console.' } },
    ] },
  { id: 'pilots-list', group: 'Pilots', method: 'GET', path: 'pilots',
    desc: 'List pilot request ids.',
    presets: [{ name: 'List' }] },
  { id: 'pilots-get', group: 'Pilots', method: 'GET', path: 'pilots/{pilot_id}',
    desc: 'Fetch one pilot envelope.',
    prereq: 'POST pilots first, paste its pilot_id.',
    presets: [{ name: 'By id', params: { pilot_id: 'PASTE_PILOT_ID' } }] },
  // ---------- ADAPTERS ----------
  { id: 'adapters-ingest', group: 'Adapters', method: 'POST', path: 'adapters/ingest',
    desc: 'Parse one external eval doc. STUBs refuse loudly.',
    presets: [
      { name: 'Libero (derived)', body: { harness: 'simpler-libero', document: LIBERO_DOC } },
      { name: 'Halos (refuses)', body: { harness: 'halos', document: {} } },
    ] },
  { id: 'adapters-status', group: 'Adapters', method: 'GET', path: 'adapters/status',
    desc: 'Adapter board: STUB / DERIVED / VERIFIED.',
    presets: [{ name: 'Board' }] },
  // ---------- CAPSULES ----------
  { id: 'capsule-seal', group: 'Capsules', method: 'POST', path: 'eval/capsule/seal',
    desc: 'Seal request+envelope+mode under a track hash. UNSIGNED.',
    presets: [{ name: 'Seal demo run', body: { request: { path: 'runs/evaluate', method: 'POST', body: { policy_id: 'demo-clean-v1' } }, envelope: { status: 200, data: { verdict: 'TRUSTED' } }, mode: 'live', backend_host: 'console' } }] },
  { id: 'capsule-verify', group: 'Capsules', method: 'POST', path: 'eval/capsule/verify',
    desc: 'Recompute a capsule track hash. Fails closed on edits.',
    presets: [
      { name: 'Sealed capsule (verifies)', body: SEALED_DEMO_CAPSULE },
      { name: 'Edited copy (fails closed)', body: { ...SEALED_DEMO_CAPSULE, mode: 'recorded' } },
    ] },
];
