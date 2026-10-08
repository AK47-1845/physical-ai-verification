'use client';

import { useEffect, useState } from 'react';
import { Activity, ArrowDownToLine, ArrowRight, Check, Copy, Fingerprint, LoaderCircle, Play } from 'lucide-react';
import { apiError, apiRequest, formatValue, presetRequest, record, resultSummary, SAMPLES, type ApiResult } from '@/lib/workspace';
import { downloadJson } from '@/lib/demo';
import { EvidenceChip, GateInspector, ReadableResult, TracePlot, VerdictBadge } from './EvidenceViews';

function checked(response: ApiResult) {
  if (!response.up || response.status >= 400) throw new Error(apiError(response));
  return response.data;
}

export function EvidenceWorkbench() {
  const [sample, setSample] = useState('drifty');
  const [data, setData] = useState<unknown>(null);
  const [ledger, setLedger] = useState<unknown>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [gate, setGate] = useState('drift_final');
  const selected = SAMPLES.find(item => item.id === sample)!;
  const summary = resultSummary(data);
  async function score() {
    setBusy(true); setError('');
    try { setData(checked(await apiRequest('lab/score', 'POST', { sample_id: sample }))); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Scoring did not complete.'); }
    finally { setBusy(false); }
  }
  async function sealAndVerify() {
    setBusy(true); setError('');
    try {
      const run = record(checked(await apiRequest('runs/evaluate', 'POST', { intended: selected.intended, observed: selected.observed, policy_id: `evidence-example-${sample}`, seed: 7 })));
      checked(await apiRequest('dossiers/compile', 'POST', { ...record(presetRequest('dossiers-compile', { RUN_ID: run.run_id }).body), odd: 'Synthetic example, two-dimensional world frame, no hardware execution' }));
      setLedger(checked(await apiRequest('ledger/verify', 'POST', {})));
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Ledger verification did not complete.'); }
    finally { setBusy(false); }
  }
  return <div className="page-workbench"><div className="page-workbench-bar"><div><h2>Inspect a returned scorecard</h2><p>Actual engine results on a declared synthetic trace.</p></div><EvidenceChip>SYNTHETIC / DRAFT</EvidenceChip></div><div className="page-workbench-actions"><select aria-label="Evidence sample" value={sample} onChange={event => { setSample(event.target.value); setData(null); }}>{SAMPLES.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select><button className="button primary" disabled={busy} onClick={() => void score()}>{busy ? <LoaderCircle size={15} className="is-spinning" /> : <Play size={15} />}Score example</button><a className="text-action" href="/playground">Full workspace <ArrowRight size={14} /></a></div><div className="page-evidence-grid"><TracePlot pair={selected} selectedGate={gate} /><div className="page-paper">{data ? <><VerdictBadge verdict={summary.verdict} /><GateInspector gates={summary.gates} selected={gate} onSelect={setGate} sampleCount={selected.intended.length} /></> : <div className="page-empty"><Fingerprint size={28} /><h3>A finding, with its evidence.</h3><p>Run the example to inspect a measurement, draft boundary and source pointer together.</p></div>}</div></div>{error && <p className="page-error" role="alert">{error}</p>}<div className="page-workbench-actions">{data !== null && <button className="button secondary" onClick={() => downloadJson('evidence-scorecard.json', data)}><ArrowDownToLine size={14} />Scorecard</button>}<button className="button secondary" disabled={busy} onClick={() => void sealAndVerify()}><Fingerprint size={15} />Append example and verify chain</button></div>{ledger !== null && <div className="page-ledger-result"><ReadableResult data={ledger} /><p>Internal verification does not identify the author. Retain the head outside this deployment to detect truncation or wholesale rewriting.</p><button className="text-action" onClick={() => downloadJson('ledger-verification.json', ledger)}>Export verification <ArrowDownToLine size={14} /></button></div>}</div>;
}

export function WorksheetForm() {
  const [answers, setAnswers] = useState({ ml_safety_function: true, self_evolving: false, frozen_weight_ota: true });
  const [product, setProduct] = useState('Review asset');
  const [result, setResult] = useState<unknown>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit() {
    setBusy(true); setError('');
    try { setResult(checked(await apiRequest('worksheet/record', 'POST', { ...answers, product, analyst: 'Site reviewer' }))); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Worksheet unavailable.'); }
    finally { setBusy(false); }
  }
  return <div className="page-workbench worksheet-workbench"><div className="page-workbench-bar"><div><h2>Applicability worksheet</h2><p>Record the inputs. A qualified reviewer determines applicability.</p></div><EvidenceChip>NOT LEGAL ADVICE</EvidenceChip></div><label className="page-field">Product or asset<input value={product} maxLength={120} onChange={event => setProduct(event.target.value)} /></label><div className="worksheet-questions">{([{ key: 'ml_safety_function', name: 'ML performs a safety function', detail: 'The function is safety-related in its intended application.' }, { key: 'self_evolving', name: 'Behavior evolves after shipment', detail: 'Record actual deployed learning behavior, not a model label.' }, { key: 'frozen_weight_ota', name: 'Frozen weights receive OTA updates', detail: 'A separate modification review may be needed.' }] as const).map(item => <label className="question-row" key={item.key}><span><strong>{item.name}</strong><small>{item.detail}</small></span><input type="checkbox" checked={answers[item.key]} onChange={event => setAnswers(previous => ({ ...previous, [item.key]: event.target.checked }))} /></label>)}</div><div className="page-workbench-actions"><button className="button primary" onClick={() => void submit()} disabled={busy || !product.trim()}><Check size={15} />Record answers</button><span>Human and legal review required.</span></div>{error && <p className="page-error" role="alert">{error}</p>}{result !== null && <div className="page-ledger-result"><ReadableResult data={result} /><button className="text-action" onClick={() => downloadJson('applicability-worksheet.json', result)}>Download worksheet <ArrowDownToLine size={14} /></button></div>}</div>;
}

export function RegulationClock() {
  const [days, setDays] = useState<number | null>(null);
  useEffect(() => {
    function update() { setDays(Math.max(0, Math.ceil((Date.UTC(2027, 0, 20) - Date.now()) / 86400000))); }
    const initial = window.setTimeout(update, 0);
    const interval = window.setInterval(update, 60000);
    return () => { window.clearTimeout(initial); window.clearInterval(interval); };
  }, []);
  return <div className="regulation-clock"><div><strong>20 January 2027</strong><span>EU Machinery Regulation application date</span></div><div><strong>{days ?? 'TBD'}</strong><span>calendar days / calculated now</span></div><a href="https://eur-lex.europa.eu/eli/reg/2023/1230/oj" target="_blank" rel="noreferrer">Primary legal text <ArrowRight size={14} /></a></div>;
}

export function FailureProbe() {
  const [mode, setMode] = useState('fm1');
  const [value, setValue] = useState<unknown>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const names = ['Drift', 'Executability', 'Reconstruction', 'Action sensitivity', 'Path gap'];
  async function run() {
    setBusy(true); setError('');
    try { setValue(checked(await apiRequest('lab/failure-demo', 'POST', { mode, sample_id: 'drifty' }))); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Measurement unavailable.'); }
    finally { setBusy(false); }
  }
  const measures = record(record(value).measurement);
  return <div className="page-workbench"><div className="page-workbench-bar"><div><h2>Measure the failure mode</h2><p>Trace probes where possible; explicitly toy callables where required.</p></div><EvidenceChip>SYNTHETIC</EvidenceChip></div><div className="probe-tabs" role="group" aria-label="Failure mode probe">{names.map((name, index) => <button key={name} aria-pressed={mode === `fm${index + 1}`} onClick={() => { setMode(`fm${index + 1}`); setValue(null); }}>FM{index + 1}<span>{name}</span></button>)}</div><div className="page-workbench-actions"><button className="button primary" disabled={busy} onClick={() => void run()}><Play size={15} />Run measurement</button><span>{mode === 'fm3' || mode === 'fm4' ? 'Custom models require the library callable protocol.' : 'Same-frame fixture traces; draft boundaries.'}</span></div>{error && <p className="page-error" role="alert">{error}</p>}{value !== null && <><ReadableResult data={{ ...record(value), ...Object.fromEntries(Object.entries(measures).filter(([, item]) => typeof item === 'number' || typeof item === 'boolean')) }} /><button className="text-action" onClick={() => downloadJson(`${mode}-measurements.json`, value)}>Export full measurement <ArrowDownToLine size={14} /></button></>}</div>;
}

export function DriftExperiment() {
  const [drift, setDrift] = useState(0.4);
  const [value, setValue] = useState<unknown>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const pair = { ...SAMPLES[0], observed: SAMPLES[0].intended.map((point, index, points) => [point[0], drift * index / (points.length - 1)]) };
  async function evaluate() {
    setBusy(true); setError('');
    try { setValue(checked(await apiRequest('lab/score', 'POST', { pair }))); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Scoring unavailable.'); }
    finally { setBusy(false); }
  }
  return <div className="page-workbench"><div className="page-workbench-bar"><div><h2>Move the boundary question</h2><p>A synthetic drift ramp, measured by the live engine.</p></div><EvidenceChip>SYNTHETIC / DRAFT</EvidenceChip></div><div className="drift-experiment"><div><label className="page-field">Final deviation <strong>{formatValue(drift, 2)} m</strong><input type="range" min="0" max="1.5" step="0.05" value={drift} onChange={event => { setDrift(Number(event.target.value)); setValue(null); }} /></label><button className="button primary" disabled={busy} onClick={() => void evaluate()}><Activity size={15} />Measure this trace</button>{value !== null && <div className="drift-experiment-result"><VerdictBadge verdict={resultSummary(value).verdict} /><span>Returned by profile draft-0</span></div>}{error && <p className="page-error" role="alert">{error}</p>}</div><TracePlot pair={pair} compact /></div></div>;
}

export function RatioExperiment() {
  const [realPercent, setRealPercent] = useState(50);
  const synthetic = 1 - realPercent / 100;
  const decision = synthetic <= 0.5 ? 'GOVERNED' : synthetic <= 0.8 ? 'REVIEW' : 'BLOCKED';
  return <div className="page-workbench ratio-experiment"><div className="page-workbench-bar"><div><h2>Declare the data mixture</h2><p>Real fraction alpha is separate from the synthetic-fraction gate.</p></div><EvidenceChip>ILLUSTRATION</EvidenceChip></div><label className="page-field">Real fraction: {realPercent}%<input type="range" min="0" max="100" step="5" value={realPercent} onChange={event => setRealPercent(Number(event.target.value))} /></label><div className="mixture-bar" aria-label={`${realPercent}% real, ${100 - realPercent}% synthetic`}><span style={{ width: `${realPercent}%` }} /><span style={{ width: `${100 - realPercent}%` }} /></div><div className="mixture-readout"><span>Real <strong>{realPercent}%</strong></span><span>Synthetic <strong>{100 - realPercent}%</strong></span><EvidenceChip>{decision}</EvidenceChip></div><p>This ratio illustration is not a prediction of model collapse. A retained real anchor, verifier quality and labeled validation remain necessary.</p><a className="text-action" href="/playground?flow=provenance">Run the provenance checks <ArrowRight size={14} /></a></div>;
}

export function CopyCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  return <div className="copy-command"><code>{command}</code><button className="icon-button" aria-label="Copy offline verification command" title="Copy command" onClick={() => void navigator.clipboard.writeText(command).then(() => setCopied(true)).catch(() => setCopied(false))}>{copied ? <Check size={15} /> : <Copy size={15} />}</button><span role="status">{copied ? 'Copied' : ''}</span></div>;
}