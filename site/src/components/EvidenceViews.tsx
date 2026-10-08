'use client';

import { useId } from 'react';
import { Check, ChevronRight, CircleAlert, FileCheck2, ShieldQuestion } from 'lucide-react';
import { formatValue, GATE_INFO, record, text, traceErrors, type GateResult, type TracePair } from '@/lib/workspace';

export function EvidenceChip({ children, tone = '' }: { children: React.ReactNode; tone?: string }) {
  return <span className={`evidence-chip ${tone}`}>{children}</span>;
}

export function VerdictBadge({ verdict }: { verdict: string }) {
  const status = verdict.toUpperCase();
  const tone = ['TRUSTED', 'PASS'].includes(status) ? 'pass' : ['BLOCKED', 'BLOCK', 'VIOLATED', 'REFUSED'].includes(status) ? 'blocked' : ['REVIEW', 'UNKNOWN'].includes(status) ? 'review' : 'insufficient';
  const Icon = tone === 'pass' ? Check : tone === 'blocked' ? CircleAlert : ShieldQuestion;
  return <span className={`verdict-badge ${tone}`}><Icon size={13} />{status}</span>;
}

export function TracePlot({ pair, selectedGate, compact = false }: { pair: TracePair; selectedGate?: string; compact?: boolean }) {
  const gridId = useId().replaceAll(':', '');
  const points = [...pair.intended, ...pair.observed];
  const lowerX = Math.min(...points.map(point => point[0]));
  const upperX = Math.max(...points.map(point => point[0]));
  const lowerY = Math.min(-0.25, ...points.map(point => point[1]));
  const upperY = Math.max(0.5, ...points.map(point => point[1]));
  const projectX = (value: number) => 44 + (value - lowerX) / Math.max(upperX - lowerX, 0.01) * 552;
  const projectY = (value: number) => 208 - (value - lowerY) / Math.max(upperY - lowerY, 0.01) * 170;
  const line = (trace: number[][]) => trace.map((point, index) => `${index ? 'L' : 'M'}${projectX(point[0])},${projectY(point[1])}`).join(' ');
  const errors = traceErrors(pair.intended, pair.observed);
  const maxError = Math.max(0.8, ...errors) * 1.15;
  const errorX = (index: number) => 44 + index / Math.max(1, errors.length - 1) * 552;
  const errorY = (value: number) => 150 - value / maxError * 126;
  const errorLine = errors.map((value, index) => `${index ? 'L' : 'M'}${errorX(index)},${errorY(value)}`).join(' ');
  const crosses = errors.findIndex(value => value > 0.5);
  return <div className={`trace-instrument ${compact ? 'compact' : ''}`}>
    <div className="trace-legend"><span><i className="reference-line" />Reference</span><span><i className="observed-line" />Observed</span><span className="mono">{pair.frame_id} / {pair.units}{pair.intended[0]?.length === 3 ? ' / XY projection' : ''}</span></div>
    <svg className="trajectory-plot" viewBox="0 0 640 246" role="img" aria-label="Reference and observed task-space trajectories in metres">
      <defs><pattern id={gridId} width="46" height="34" patternUnits="userSpaceOnUse"><path d="M46 0H0V34" fill="none" stroke="currentColor" strokeWidth="0.6" /></pattern></defs>
      <rect x="44" y="22" width="552" height="186" fill={`url(#${gridId})`} className="plot-grid" />
      <path d="M44 22V208H596" className="plot-axis" />
      <path d={line(pair.intended)} className="plot-reference" />
      <path d={line(pair.observed)} className="plot-observed" />
      {pair.observed.map((point, index) => <circle key={index} cx={projectX(point[0])} cy={projectY(point[1])} r={index === pair.observed.length - 1 ? 5 : 3} className={errors[index] > 0.5 ? 'plot-point breached' : 'plot-point'} />)}
      <text x="44" y="232">{formatValue(lowerX)} m</text><text x="596" y="232" textAnchor="end">{formatValue(upperX)} m</text><text x="24" y="30" textAnchor="end">Y</text><text x="616" y="212">X</text>
    </svg>
    {!compact && <><div className="trace-subhead"><span>Tracking error</span><span className="mono">0.5 m screening boundary</span></div>
      <div className="error-field">
        <svg className="error-plot" viewBox="0 0 640 178" preserveAspectRatio="none" role="img" aria-label="Pointwise tracking error by sample with a draft 0.5 metre boundary">
          {crosses >= 0 && <rect x={errorX(crosses)} y="12" width={Math.max(4, 600 - errorX(crosses))} height="138" className="plot-breach-area" />}
          <path d={`M44 ${errorY(0.5)}H596`} className="plot-boundary" vectorEffect="non-scaling-stroke" />
          <path d="M44 12V150H596" className="plot-axis" vectorEffect="non-scaling-stroke" />
          <path d={errorLine} className="plot-error" vectorEffect="non-scaling-stroke" />
        </svg>
        <div className="error-marks" aria-hidden="true">{errors.map((error, index) => <i key={index} className={error > 0.5 ? 'breached' : ''} style={{ left: `${errorX(index) / 640 * 100}%`, top: `${errorY(error) / 178 * 100}%`, width: selectedGate === 'drift_final' && index === errors.length - 1 ? 12 : 6, height: selectedGate === 'drift_final' && index === errors.length - 1 ? 12 : 6 }} />)}</div>
        <span className="error-axis start mono">Sample 0</span><span className="error-axis end mono">Sample {errors.length - 1}</span><span className="error-axis unit mono">m</span>
      </div></>}
  </div>;
}

export function GateInspector({ gates, selected, onSelect, sampleCount }: { gates: GateResult[]; selected: string; onSelect: (gate: string) => void; sampleCount?: number }) {
  const gate = gates.find(item => item.gate === selected) ?? gates[0];
  const info = gate ? GATE_INFO[gate.gate] : undefined;
  return <div className="gate-inspector">
    <div className="instrument-heading"><h3>Evidence gates</h3><EvidenceChip tone="review">DRAFT</EvidenceChip></div>
    <div className="gate-list">{gates.map(item => {
      const bounds = GATE_INFO[item.gate];
      const higher = item.gate === 'coherence';
      const span = bounds ? Math.max(bounds.amber, bounds.green, item.measurement ?? 0) * 1.12 : 0;
      const position = bounds && span > 0 && item.measurement !== null ? Math.min(100, item.measurement / span * 100) : null;
      return <button key={item.gate} className={`gate-item ${gate?.gate === item.gate ? 'selected' : ''}`} onClick={() => onSelect(item.gate)} aria-pressed={gate?.gate === item.gate}>
        <span className="gate-row-top"><span className={`gate-dot ${item.status.toLowerCase()}`} /><span className="gate-row-name"><strong>{bounds?.name ?? item.gate}</strong><small>{item.status}</small></span><b className="mono">{formatValue(item.measurement)}<small> {bounds?.unit}</small></b><ChevronRight size={14} /></span>
        {position !== null && bounds && <span className="gate-scale" aria-hidden="true"><span className="gate-scale-track"><i className="zone-green" style={{ left: higher ? `${bounds.amber / span * 100}%` : 0, width: `${(higher ? span - bounds.amber : bounds.green) / span * 100}%` }} /><i className="zone-amber" style={{ left: higher ? `${bounds.green / span * 100}%` : `${bounds.green / span * 100}%`, width: `${Math.abs(bounds.amber - bounds.green) / span * 100}%` }} /><i className="gate-needle" style={{ left: `${position}%` }} /></span></span>}
      </button>;
    })}</div>
    {gate && <div className="gate-detail" aria-live="polite"><div className="gate-detail-title"><FileCheck2 size={16} /><strong>Evidence Lens</strong></div><p>{info?.description ?? (gate.note || 'Inspect the returned evidence before drawing a conclusion.')}</p>
      <dl><div><dt>Measurement</dt><dd>{formatValue(gate.measurement, 6)} {info?.unit}</dd></div>{info && <><div><dt>{gate.gate === 'coherence' ? 'Review / pass floor' : 'Green / amber boundary'}</dt><dd>{info.green} / {info.amber}</dd></div></>}
        <div><dt>Interval</dt><dd>{sampleCount ? gate.gate === 'drift_final' ? `Final sample ${sampleCount - 1}` : `Aggregate: samples 0-${sampleCount - 1}` : 'Trace not included'}</dd></div><div><dt>Source</dt><dd className="mono">{gate.evidence || 'Not recorded'}</dd></div></dl><span className="instrument-footnote">Screening evidence. Thresholds are not calibrated.</span>
    </div>}
  </div>;
}

export function ReadableResult({ data }: { data: unknown }) {
  const value = record(data);
  const catalogue = record(value.catalogue ?? value);
  const trials = Array.isArray(catalogue.trials) ? catalogue.trials : [];
  const deltas = Array.isArray(value.deltas) ? value.deltas : [];
  const candidate = record(value.certificate ?? value);
  const verdict = text(candidate.verdict) || text(value.status);
  const route = text(value.implied_route) || text(record(value.worksheet).implied_route);
  const measurements = Object.entries(record(value.measurement ?? value.success_time)).filter(([, item]) => typeof item === 'number' || typeof item === 'boolean' || item === null);
  const manifest = record(value.manifest);
  const generator = record(record(manifest.body).generator);
  const lineage = record(record(generator.params).lineage);
  const fall = record(value.fall_impact);
  const rows = Object.entries(value).filter(([key, item]) => !['trials', 'breaks', 'payload', 'doc'].includes(key) && ['string', 'number', 'boolean'].includes(typeof item)).slice(0, 14);
  return <div className="readable-result">
    {verdict && <VerdictBadge verdict={verdict} />}
    {trials.length > 0 && <><div className="result-headline"><strong>{trials.filter(item => record(item).breaks === true).length}</strong><span>breaking trials / {trials.length} evaluated</span></div><div className="trial-grid" aria-label="Completed hunt trial results">{trials.map((item, index) => { const trial = record(item); return <span key={index} className={trial.breaks ? 'broken' : 'held'} title={`Trial ${index + 1}: ${trial.breaks ? 'boundary breached' : 'no break found'}; measurement ${formatValue(trial.measurement)}`}>{String(index + 1).padStart(2, '0')}</span>; })}</div><p className="instrument-footnote">Actual returned trials on a SYNTHETIC fixture policy. No physical robot was tested.</p></>}
    {route && <div className="worksheet-route"><strong>{route.replaceAll('_', ' ').toLowerCase()}</strong><p>Recorded implication only. Human and legal review required.</p></div>}
    {measurements.length > 0 && <dl className="result-facts">{measurements.map(([key, item]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{typeof item === 'boolean' ? item ? 'Yes' : 'No' : formatValue(item, 6)}</dd></div>)}</dl>}
    {Object.keys(fall).length > 0 && <div className="page-ledger-result"><h3>Fall and impact record</h3><VerdictBadge verdict={text(fall.verdict, 'INSUFFICIENT')} /><p>DRAFT placeholder. Supplied metrics are recorded, never judged against an unpublished threshold.</p></div>}
    {Object.keys(manifest).length > 0 && <dl className="result-facts">{Object.entries({ generator: generator.name, version: generator.version, ...lineage, seed: record(manifest.body).seed, rows: record(record(manifest.body).content).n_rows, content_fingerprint: record(record(manifest.body).content).content_hash, manifest_fingerprint: manifest.manifest_id, signature: 'UNSIGNED' }).map(([key, item]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd className={String(item).length > 40 ? 'mono' : ''}>{typeof item === 'string' || typeof item === 'number' ? String(item) : 'Not recorded'}</dd></div>)}</dl>}
    {deltas.length > 0 && <div className="result-table-wrap"><table className="result-table"><thead><tr><th>Gate</th><th>Before</th><th>After</th><th>Delta</th></tr></thead><tbody>{deltas.map((item, index) => { const delta = record(item); return <tr key={index}><td>{text(delta.gate)}</td><td>{text(delta.band_from, '-')}</td><td>{text(delta.band_to, '-')}</td><td className={delta.regression ? 'fail' : ''}>{formatValue(delta.delta)}</td></tr>; })}</tbody></table></div>}
    {rows.length > 0 && <dl className="result-facts">{rows.map(([key, item]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd className={typeof item === 'string' && item.length > 40 ? 'mono' : ''}>{typeof item === 'boolean' ? item ? 'Yes' : 'No' : String(item)}</dd></div>)}</dl>}
    {!rows.length && !trials.length && !deltas.length && !route && <p>Evidence returned. Download the artifact or inspect its full structure under Advanced.</p>}
  </div>;
}