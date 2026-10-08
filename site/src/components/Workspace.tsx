'use client';

import { useEffect, useRef, useState } from 'react';
import { Activity, ArrowDownToLine, ArrowRight, Box, Braces, Check, ChevronRight, FileCheck2, Fingerprint, FlaskConical, GitCompareArrows, Layers3, LoaderCircle, Play, Radar, RefreshCw, ShieldCheck, ShieldQuestion, Upload, Workflow } from 'lucide-react';
import { downloadJson } from '@/lib/demo';
import { shortHost } from '@/lib/host';
import { apiError, apiRequest, captureContext, exchangeCount, GATE_INFO, lastExchange, parseTrace, passBoundary, presetRequest, record, resultSummary, SAMPLES, type ApiResult, type Exchange, type PresetContext, type TracePair } from '@/lib/workspace';
import { EvidenceChip, GateInspector, ReadableResult, TracePlot, VerdictBadge } from './EvidenceViews';

type Flow = 'score' | 'hunt' | 'compare' | 'dossier' | 'verify' | 'worksheet' | 'provenance' | 'transfer' | 'bounded';
type HistoryRun = { id: string; name: string; verdict: string; pair?: TracePair; result?: unknown; label: string };
const FLOWS = [
  { id: 'score', name: 'Score a run', icon: Activity, caption: 'Measure the deviation. Locate the evidence.' },
  { id: 'hunt', name: 'Hunt failures', icon: Radar, caption: 'Search a bounded set of disturbances.' },
  { id: 'compare', name: 'Compare releases', icon: GitCompareArrows, caption: 'What changed between two recorded runs?' },
  { id: 'dossier', name: 'Compile a dossier', icon: FileCheck2, caption: 'One scoped record, ready for human review.' },
  { id: 'verify', name: 'Verify a PAR', icon: Fingerprint, caption: 'Check the artifact. Do not take its word for it.' },
  { id: 'worksheet', name: 'Applicability worksheet', icon: ShieldQuestion, caption: 'Record the facts. Leave the legal decision to a person.' },
  { id: 'provenance', name: 'Inspect provenance', icon: Layers3, caption: 'Track the ingredients behind a generated dataset.' },
  { id: 'transfer', name: 'Check transfer', icon: Workflow, caption: 'Same frame first. Invalid comparisons are refused.' },
  { id: 'bounded', name: 'Bounded checks', icon: Box, caption: 'Small, explicit scopes. UNKNOWN is not a pass.' },
] as const;

function ActionButton({ label, busy, onRun, disabled = false }: { label: string; busy: string; onRun: () => void; disabled?: boolean }) {
  return <button className="button primary" disabled={Boolean(busy) || disabled} onClick={onRun}>{busy === label ? <LoaderCircle size={16} className="is-spinning" /> : <Play size={15} />}{busy === label ? 'Working...' : label}</button>;
}

export default function Workspace({ advanced }: { advanced?: React.ReactNode }) {
  const [flow, setFlow] = useState<Flow>('score');
  const [sample, setSample] = useState('drifty');
  const [pair, setPair] = useState<TracePair | null>(SAMPLES[1]);
  const [inputLabel, setInputLabel] = useState('SYNTHETIC');
  const [online, setOnline] = useState<boolean | null>(null);
  const [host, setHost] = useState('Same-origin proxy');
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState('');
  const [sealedExchange, setSealedExchange] = useState<Exchange | null>(null);
  const [waking, setWaking] = useState(0);
  const [result, setResult] = useState<unknown>(null);
  const [runResult, setRunResult] = useState<unknown>(null);
  const [selectedGate, setSelectedGate] = useState('drift_final');
  const [history, setHistory] = useState<HistoryRun[]>([]);
  const [parentId, setParentId] = useState('');
  const [childId, setChildId] = useState('');
  const [trialCap, setTrialCap] = useState(16);
  const [huntPolicy, setHuntPolicy] = useState('clean');
  const [odd, setOdd] = useState('Synthetic 2D reacher in world frame, supervised demonstration');
  const [product, setProduct] = useState('Demo robot');
  const [answers, setAnswers] = useState({ ml_safety_function: true, self_evolving: false, frozen_weight_ota: true });
  const [par, setPar] = useState<unknown>(null);
  const [parName, setParName] = useState('Canonical synthetic PAR');
  const context = useRef<PresetContext>({});
  const inputRevision = useRef(0);
  const uploadRef = useRef<HTMLInputElement>(null);
  const parRef = useRef<HTMLInputElement>(null);
  const summary = resultSummary(runResult);
  const current = FLOWS.find(item => item.id === flow)!;

  async function pingOnce(signal?: AbortSignal): Promise<boolean> {
    const response = await apiRequest('governance', 'GET', undefined, signal);
    if (signal?.aborted) return false;
    if (response.up && response.status === 200) {
      setOnline(true);
      if (response.backendHost) setHost(response.backendHost);
      return true;
    }
    return false;
  }

  async function pingWithBackoff(signal?: AbortSignal): Promise<boolean> {
    if (await pingOnce(signal)) return true;
    if (signal?.aborted) return false;
    setOnline(false);
    for (let attempt = 1; attempt <= 3; attempt += 1) {
      setWaking(attempt);
      await new Promise(resolve => setTimeout(resolve, 2000 * 2 ** (attempt - 1)));
      if (signal?.aborted) { setWaking(0); return false; }
      if (await pingOnce(signal)) { setWaking(0); return true; }
    }
    setWaking(0);
    return false;
  }

  async function checkConnection() {
    setOnline(null);
    await pingWithBackoff();
  }

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      const revision = inputRevision.current;
      const alive = await pingWithBackoff(controller.signal);
      if (!alive) return;
      const requested = new URLSearchParams(window.location.search).get('flow');
      if (FLOWS.some(item => item.id === requested)) setFlow(requested as Flow);
      const preview = await apiRequest('lab/score', 'POST', { sample_id: 'drifty' }, controller.signal);
      if (preview.up && preview.status === 200 && !controller.signal.aborted && inputRevision.current === revision) setRunResult(preview.data);
      const saved = await apiRequest('runs', 'GET', undefined, controller.signal);
      const ids = record(saved.data).run_ids;
      if (Array.isArray(ids)) setHistory(ids.filter((id): id is string => typeof id === 'string').slice(-8).reverse().map(id => ({ id, name: 'Stored run', verdict: 'INSUFFICIENT', label: 'Source in artifact' })));
    })().catch(() => undefined);
    return () => controller.abort();
  }, []);

  function accept(response: ApiResult): unknown {
    setOnline(response.up);
    if (!response.up || response.status >= 400) throw new Error(apiError(response));
    return response.data;
  }

  async function executePreset(id: string, replacement?: unknown) {
    const request = presetRequest(id, context.current);
    const data = accept(await apiRequest(request.path, request.method, replacement ?? request.body));
    context.current = captureContext(id, data, context.current);
    return data;
  }

  async function perform(label: string, action: () => Promise<unknown>) {
    if (busy) return;
    const exchangeBefore = exchangeCount();
    setBusy(label);
    setMessage('');
    setResult(null);
    try { const data = await action(); setResult(data); if (exchangeCount() !== exchangeBefore) setSealedExchange(lastExchange()); return data; }
    catch (error) { setMessage(error instanceof Error ? error.message : 'The request could not complete. Retry with the same input.'); }
    finally { setBusy(''); }
  }

  async function sealCapsule() {
    if (busy || !sealedExchange || online !== true) return;
    const exchange = sealedExchange;
    const done = await perform('Seal replay capsule', async () => {
      const capsule = accept(await apiRequest('eval/capsule/seal', 'POST', {
        request: { path: exchange.path, method: exchange.method, body: exchange.body },
        envelope: { status: exchange.status, data: exchange.data },
        mode: 'live',
        backend_host: exchange.backendHost ?? host,
      }));
      downloadJson('verification-replay-capsule.json', capsule);
      return capsule;
    });
    if (done) setMessage('Replay capsule sealed and downloaded. Verify it any time: POST the file to eval/capsule/verify.');
  }

  async function score() {
    inputRevision.current += 1;
    if (!pair) throw new Error('Select a sample or upload a trace before scoring.');
    const request = record(presetRequest('runs-evaluate').body);
    const data = await executePreset('runs-evaluate', { ...request, intended: pair.intended, observed: pair.observed, policy_id: inputLabel === 'SYNTHETIC' ? `example-${sample}` : 'uploaded-trace', units: pair.units, frame_id: pair.frame_id });
    const scored = resultSummary(data);
    setRunResult(data);
    setSelectedGate(scored.gates.find(gate => gate.status === 'BLOCKED')?.gate ?? scored.gates[0]?.gate ?? 'drift_final');
    if (scored.runId) {
      context.current.RUN_ID = scored.runId;
      const entry = { id: scored.runId, name: pair.name || SAMPLES.find(item => item.id === sample)?.name || 'Uploaded trace', verdict: scored.verdict, pair, result: data, label: inputLabel };
      setHistory(previous => [entry, ...previous.filter(item => item.id !== entry.id)].slice(0, 20));
      setChildId(scored.runId);
      setParentId(previous => previous || scored.runId);
    }
    return data;
  }

  async function loadRun(entry: HistoryRun) {
    inputRevision.current += 1;
    setFlow('score');
    await perform('Loading run', async () => {
      const data = entry.result ?? accept(await apiRequest(`runs/${encodeURIComponent(entry.id)}`));
      const root = record(data);
      const loaded = root.doc ? { ...record(root.doc), run_id: entry.id } : data;
      setRunResult(loaded);
      setPair(entry.pair ?? null);
      setInputLabel(entry.label);
      context.current.RUN_ID = entry.id;
      return loaded;
    });
  }

  function chooseFlow(id: Flow) { setFlow(id); setResult(null); setMessage(''); }

  async function uploadTrace(file?: File) {
    if (!file) return;
    inputRevision.current += 1;
    try {
      const parsed = parseTrace(await file.text());
      setPair({ ...parsed, name: parsed.name || file.name });
      setInputLabel('UPLOADED'); setSample('uploaded'); setRunResult(null); setMessage(''); setResult(null);
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Unable to read that trace.'); }
  }

  async function verifyPar(tamper = false) {
    const original = par ?? record(presetRequest('par-validate').body).envelope;
    const envelope = structuredClone(original);
    if (tamper) {
      const payload = record(record(envelope).par);
      const gates = Array.isArray(payload.gates) ? payload.gates : [];
      if (!gates.length) throw new Error('This PAR has no gate value to change. Choose the synthetic example.');
      record(gates[0]).measurement = Number(record(gates[0]).measurement ?? 0) + 1;
    }
    const response = await apiRequest('par/validate', 'POST', { envelope });
    if (tamper && response.up && (response.status >= 400 || record(response.data).ok === false)) return { integrity: 'Tampering detected', status: 'REFUSED', explanation: apiError(response), authenticity: 'UNSIGNED: this does not identify the author.' };
    return accept(response);
  }

  return <main id="main" className="workspace-page">
    <div className="workspace-heading"><div><h1>Validation workspace</h1><p>One release. Every boundary in view.</p></div><div className={`connection-state ${online === true ? 'connected' : ''}`}><span className="connection-dot" /><span>{online === null ? 'Connecting' : online ? 'Connected' : 'Unavailable'}<small title={host}>{shortHost(host)}</small></span><button className="icon-button" onClick={() => void checkConnection()} aria-label="Retry backend connection" title="Retry backend connection"><RefreshCw size={14} /></button></div></div>
    {online === false && <div className="workspace-offline" role="status"><ShieldQuestion size={20} /><div>{waking > 0 ? <strong>Waking backend, attempt {waking} of 3.</strong> : <strong>The backend is asleep or unreachable.</strong>}<p>No live results are being generated. Retry the connection, or watch the explicitly labeled synthetic replay.</p><code>START-BACKEND.cmd</code></div><a className="button secondary" href="/demo">Open demo <ArrowRight size={15} /></a></div>}
    <div className="workspace-layout"><aside className="workflow-rail" aria-label="Validation workflows"><span className="rail-heading">Workflows</span>{FLOWS.map(item => <button key={item.id} className={flow === item.id ? 'active' : ''} onClick={() => chooseFlow(item.id)} aria-pressed={flow === item.id}><item.icon size={17} /><span>{item.name}</span><ChevronRight size={13} /></button>)}<div className="rail-bottom"><EvidenceChip>DRAFT GATES</EvidenceChip><p>Screening, not certification.</p><a href="/methodology">Measurement methods <ArrowRight size={13} /></a></div></aside>
      <section className="workflow-stage" aria-label={current.name}><div className="workflow-title"><div><h2>{current.name}</h2><p>{current.caption}</p></div><EvidenceChip tone="signal">{flow === 'score' ? inputLabel : 'SCOPED EVIDENCE'}</EvidenceChip></div>
        {flow === 'score' && <>
          <div className="sample-strip" role="group" aria-label="Synthetic trace samples">{SAMPLES.map(item => <button className={sample === item.id ? 'selected' : ''} key={item.id} aria-pressed={sample === item.id} onClick={() => { inputRevision.current += 1; setSample(item.id); setPair(item); setInputLabel('SYNTHETIC'); setRunResult(null); setResult(null); setMessage(''); }}><span>{item.name}</span><small>{item.detail}</small></button>)}</div>
          <div className="score-toolbar"><div className="scope-facts"><span><small>FRAME</small>{pair?.frame_id ?? 'Not included'}</span><span><small>SAMPLES</small>{pair?.intended.length ?? '-'}</span><span><small>UNITS</small>{pair?.units ?? '-'}</span></div><div className="toolbar-actions"><input type="file" ref={uploadRef} accept=".json,application/json" hidden onChange={event => { void uploadTrace(event.target.files?.[0]); event.target.value = ''; }} /><button className="icon-button" title="Upload trace JSON" aria-label="Upload trace JSON" onClick={() => uploadRef.current?.click()}><Upload size={16} /></button><ActionButton label="Score this run" busy={busy} disabled={!pair} onRun={() => void perform('Score this run', score)} /></div></div>
          <div className="score-layout"><div className="score-visual">{pair ? <TracePlot pair={pair} selectedGate={selectedGate} /> : <div className="trace-empty"><Activity size={32} /><strong>Trace not included in this record</strong><p>The scorecard remains inspectable. Reopen its original upload to draw the trajectory.</p></div>}<div className="instrument-caption"><span>{inputLabel} / task-space screening</span><span>Deterministic profile: draft-0</span></div></div>
            <div className="score-findings">{busy === 'Score this run' ? <div className="result-empty" role="status"><LoaderCircle className="is-spinning" size={25} /><h3>Evaluating the trace</h3><p>Measuring gates and recording the evidence.</p></div> : runResult ? <><div className="verdict-heading"><VerdictBadge verdict={summary.verdict} /><h3>{summary.verdict === 'BLOCKED' ? 'Boundary exceeded.' : summary.verdict === 'TRUSTED' ? 'Within these draft gates.' : 'More evidence needed.'}</h3></div><GateInspector gates={summary.gates} selected={selectedGate} onSelect={setSelectedGate} sampleCount={pair?.intended.length} /></> : <div className="result-empty"><ShieldCheck size={30} /><h3>Evidence, not a guess.</h3><p>No verdict yet. The selected trace is ready to evaluate.</p><div className="empty-gates">{Object.entries(GATE_INFO).map(([id, info]) => <span key={id}><span className="gate-dot" />{info.name}<span className="mono">{passBoundary(id)}</span></span>)}</div></div>}</div>
          </div>
          {runResult && <div className="run-actions"><span className="mono">{summary.runId}</span><button className="button secondary" onClick={() => downloadJson('verification-scorecard.json', runResult)}><ArrowDownToLine size={15} />Scorecard</button>{summary.runId && <a className="button secondary" href={`/release?run=${encodeURIComponent(summary.runId)}`}>Release brief <ArrowRight size={15} /></a>}<button className="button secondary" onClick={() => void sealCapsule()} disabled={Boolean(busy) || !sealedExchange || online !== true} title={online === true ? 'Seal this run as a replay capsule' : 'Backend offline: no live evidence to seal'}><Fingerprint size={15} />Seal capsule</button><button className="button secondary" onClick={() => chooseFlow('dossier')}>Compile dossier <FileCheck2 size={15} /></button></div>}
        </>}
        {flow === 'hunt' && <div className="guided-form"><div className="guided-illustration"><Radar size={46} /><div><h3>Find the boundary.</h3><p>A seeded search over fixture-policy noise and bias. Every returned trial is replayable.</p></div><EvidenceChip>SYNTHETIC</EvidenceChip></div><div className="form-row"><label>Fixture policy<select value={huntPolicy} onChange={event => setHuntPolicy(event.target.value)}><option value="clean">Nominal policy</option><option value="drifty">Drifty policy</option><option value="playback">Playback policy</option><option value="synthfed">Synthetic-fed policy</option></select></label><label>Trial budget <span className="mono">{trialCap} / 50</span><input type="range" min="1" max="50" value={trialCap} onChange={event => setTrialCap(Number(event.target.value))} /></label></div><ActionButton label="Hunt failures" busy={busy} onRun={() => void perform('Hunt failures', () => executePreset('hunt-random', { ...record(presetRequest('hunt-random').body), policy: huntPolicy, trial_cap: trialCap }))} /><p className="instrument-footnote">Seed 1. Supervisory screening only. No simulator or hardware is connected.</p></div>}
        {flow === 'compare' && <div className="guided-form"><div className="guided-illustration"><GitCompareArrows size={44} /><div><h3>One release is a snapshot.<br />Two expose the change.</h3><p>Compare per-gate measurements from stored runs. Success cannot offset a blocked gate.</p></div></div><div className="form-row"><label>Earlier run<select value={parentId} onChange={event => setParentId(event.target.value)}><option value="">Select a run</option>{history.map(item => <option key={item.id} value={item.id}>{item.name} / {item.id.slice(-8)}</option>)}</select></label><label>Candidate run<select value={childId} onChange={event => setChildId(event.target.value)}><option value="">Select a run</option>{history.map(item => <option key={item.id} value={item.id}>{item.name} / {item.id.slice(-8)}</option>)}</select></label></div><ActionButton label="Compare runs" busy={busy} disabled={!parentId || !childId} onRun={() => void perform('Compare runs', async () => accept(await apiRequest(`ui/release/${encodeURIComponent(childId)}?compare=${encodeURIComponent(parentId)}`)))} />{(!parentId || !childId) && <p className="instrument-footnote">Score two examples to populate the comparison.</p>}<button className="text-action" onClick={() => void perform('Example regression', () => executePreset('releases-regression'))}>Inspect a synthetic regression example <ArrowRight size={14} /></button></div>}
        {flow === 'dossier' && <div className="guided-form"><div className="guided-illustration"><FileCheck2 size={44} /><div><h3>From a finding<br />to a reviewable record.</h3><p>Scorecard, scope, independence declaration and ledger reference, compiled by the backend.</p></div></div><label>Operating envelope<textarea value={odd} onChange={event => setOdd(event.target.value)} maxLength={2000} rows={3} /></label><div className="artifact-chain"><span><Activity size={17} />Run</span><ChevronRight size={15} /><span><Layers3 size={17} />Ledger</span><ChevronRight size={15} /><span><FileCheck2 size={17} />PAR</span></div><div className="honesty-line"><EvidenceChip>DRAFT</EvidenceChip><EvidenceChip>UNSIGNED</EvidenceChip><EvidenceChip>TAMPER-EVIDENT</EvidenceChip></div><ActionButton label="Compile evidence" busy={busy} disabled={!odd.trim()} onRun={() => void perform('Compile evidence', async () => { if (!context.current.RUN_ID) await score(); const data = await executePreset('dossiers-compile', { ...record(presetRequest('dossiers-compile', context.current).body), odd }); const envelope = record(data).par; if (envelope) { setPar(envelope); setParName('Compiled PAR'); } return data; })} /><p className="instrument-footnote">Human and legal review required. A hash is not an author signature; keep the ledger head outside this system.</p></div>}
        {flow === 'verify' && <div className="guided-form"><div className="guided-illustration"><Fingerprint size={48} /><div><h3>Evidence a stranger<br />can check.</h3><p>Recompute the PAR envelope hash and check its structure. This does not authenticate its author.</p></div></div><input ref={parRef} type="file" hidden accept=".json,application/json" onChange={event => { const file = event.target.files?.[0]; if (file) void file.text().then(source => { if (file.size > 262144) throw new Error('PAR exceeds 256 KB.'); setPar(JSON.parse(source) as unknown); setParName(file.name); setMessage(''); }).catch(() => setMessage('Choose a valid PAR JSON file under 256 KB.')); event.target.value = ''; }} /><button className="artifact-upload" onClick={() => parRef.current?.click()}><Upload size={22} /><span><strong>{parName}</strong><small>Choose a PAR JSON artifact</small></span></button><div className="toolbar-actions"><ActionButton label="Verify integrity" busy={busy} onRun={() => void perform('Verify integrity', () => verifyPar())} /><button className="button secondary" disabled={Boolean(busy)} onClick={() => void perform('Tamper duel', () => verifyPar(true))}><FlaskConical size={16} />Change one value</button></div><p className="instrument-footnote">Tamper Duel / ASTRA-IDEA. A self-consistently rehashed forgery still needs an external anchor or signature to expose it.</p></div>}
        {flow === 'worksheet' && <div className="guided-form"><div className="legal-banner"><ShieldQuestion size={19} /><span>Human and legal review required. This worksheet records answers; it does not decide applicability.</span></div><label>Product or asset<input value={product} onChange={event => setProduct(event.target.value)} maxLength={120} /></label><div className="worksheet-questions">{([{ key: 'ml_safety_function', title: 'ML performs a safety function', note: 'The declared use includes a safety-related function.' }, { key: 'self_evolving', title: 'Behavior evolves after shipment', note: 'Record the actual deployed behavior, not a model category.' }, { key: 'frozen_weight_ota', title: 'Frozen weights receive OTA updates', note: 'Record the update path for separate modification review.' }] as const).map(item => <label className="question-row" key={item.key}><span><strong>{item.title}</strong><small>{item.note}</small></span><input type="checkbox" checked={answers[item.key]} onChange={event => setAnswers(previous => ({ ...previous, [item.key]: event.target.checked }))} /></label>)}</div><ActionButton label="Record worksheet" busy={busy} disabled={!product.trim()} onRun={() => void perform('Record worksheet', () => executePreset('worksheet', { product, analyst: 'Workspace operator', ...answers }))} /></div>}
        {flow === 'provenance' && <div className="guided-form"><div className="guided-illustration"><Layers3 size={46} /><div><h3>The ingredients matter.</h3><p>Compare distribution collapse, inspect generation manifests and detect duplicate rows.</p></div></div><div className="workflow-commands">{[{ id: 'sentinels-collapsed', name: 'Expose collapsed variation', icon: Activity }, { id: 'bridge', name: 'Inspect an Axiom generation', icon: Layers3 }, { id: 'duplicates-near', name: 'Find duplicate samples', icon: Fingerprint }, { id: 'ledger-verify', name: 'Verify the evidence ledger', icon: ShieldCheck }].map(item => <button key={item.id} onClick={() => void perform(item.name, () => executePreset(item.id))} disabled={Boolean(busy)}><item.icon size={20} /><span>{item.name}<small>Synthetic example / live backend calculation</small></span><ArrowRight size={16} /></button>)}</div></div>}
        {flow === 'transfer' && <div className="guided-form"><div className="guided-illustration"><Workflow size={46} /><div><h3>Different robot.<br />Same coordinate contract.</h3><p>Task-space screening is scoped. Joint angles do not transfer across morphologies.</p></div></div><div className="toolbar-actions"><ActionButton label="Compare task-space pair" busy={busy} onRun={() => void perform('Compare task-space pair', () => executePreset('transfer-morph'))} /><button className="button secondary" disabled={Boolean(busy)} onClick={() => void perform('Refusal receipt', async () => { const request = presetRequest('transfer-joint'); const response = await apiRequest(request.path, request.method, request.body); if (response.up && response.status === 422) return { status: 'INSUFFICIENT', decision: 'Comparison refused', reason: apiError(response), label: 'SYNTHETIC', receipt: 'Refusal Receipt / ASTRA-IDEA' }; return accept(response); })}><ShieldQuestion size={16} />Test an invalid frame contract</button></div><p className="instrument-footnote">These cards declare task-space transforms. This is not a robot-wide transfer assessment.</p></div>}
        {flow === 'bounded' && <div className="guided-form"><div className="guided-illustration"><Box size={46} /><div><h3>A small claim.<br />An explicit boundary.</h3><p>Interval and grid checks on toy affine/ReLU policies. Never a full-policy or whole-robot proof.</p></div></div><div className="toolbar-actions"><ActionButton label="Check bounded example" busy={busy} onRun={() => void perform('Check bounded example', () => executePreset('bounded-proven'))} /><button className="button secondary" disabled={Boolean(busy)} onClick={() => void perform('Find bounded violation', () => executePreset('bounded-violated'))}>Find a violation <ArrowRight size={15} /></button><button className="button secondary" disabled={Boolean(busy)} onClick={() => void perform('Check property margin', () => executePreset('property-violates'))}>Check property margin <ArrowRight size={15} /></button></div><p className="instrument-footnote">The bounded verdict covers only the returned model, input box, assumptions and method. The runtime guard is a Python reference, not a hardware safety controller.</p></div>}
        {message && <div className="workspace-error" role="alert"><ShieldQuestion size={20} /><div><strong>Request not completed</strong><p>{message}</p><span>INSUFFICIENT: no passing result was inferred.</span></div></div>}
        {flow === 'bounded' && <button className="button secondary" disabled={Boolean(busy)} onClick={() => void perform('Extended measurement record', async () => accept(await apiRequest('lab/extended-metrics', 'POST', {})))}><Activity size={15} />Time-to-success and impact record</button>}
        {busy && flow !== 'score' && <div className="operation-progress" role="status"><LoaderCircle size={18} className="is-spinning" /><span>{busy}...</span></div>}
        {result !== null && flow !== 'score' && <section className="operation-result" aria-label="Operation result"><div className="instrument-heading"><h3>Returned evidence</h3><span><Check size={14} /> Backend response</span></div><ReadableResult data={result} /><div className="toolbar-actions"><button className="button secondary" onClick={() => downloadJson(`verification-${flow}.json`, result)}><ArrowDownToLine size={15} />Download artifact</button>{flow === 'dossier' && par !== null && <button className="button secondary" onClick={() => downloadJson('verification-par.json', par)}><Fingerprint size={15} />Download PAR</button>}<button className="button secondary" onClick={() => void sealCapsule()} disabled={Boolean(busy) || !sealedExchange || online !== true} title={online === true ? 'Seal this result as a replay capsule' : 'Backend offline: no live evidence to seal'}><Fingerprint size={15} />Seal capsule</button><button className="button secondary" onClick={() => window.print()}>Print review</button></div></section>}
        <details className="artifact-advanced"><summary><Braces size={15} />Advanced: request and returned artifact</summary><pre>{JSON.stringify(result ?? runResult ?? { state: 'No result yet', profile: 'draft-0' }, null, 2)}</pre><button className="text-action" onClick={() => downloadJson('trace-template.json', { intended: SAMPLES[0].intended, observed: SAMPLES[0].observed, units: 'm', frame_id: 'world' })}>Download trace template <ArrowDownToLine size={14} /></button></details>
      </section>
    </div>
    <section className="workspace-history" aria-label="Run history"><div className="instrument-heading"><h2>Run history</h2><span>{history.length} available in this workspace</span></div>{history.length ? <div className="history-table">{history.map(entry => <button key={entry.id} className="history-row" onClick={() => void loadRun(entry)} disabled={Boolean(busy)}><Activity size={15} /><span><strong>{entry.name}</strong><small className="mono">{entry.id}</small></span><EvidenceChip>{entry.label}</EvidenceChip>{entry.result ? <VerdictBadge verdict={entry.verdict} /> : <span className="muted">Open evidence</span>}<ArrowRight size={15} /></button>)}</div> : <div className="history-empty"><FileCheck2 size={20} /><span>No stored runs yet. The first completed score appears here.</span></div>}</section>
    {advanced && <details className="endpoint-advanced"><summary><Braces size={17} /><span>Advanced endpoint explorer</span><span className="mono">Full API catalog</span><ChevronRight size={15} /></summary>{advanced}</details>}
  </main>;
}