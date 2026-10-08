'use client';

import { useEffect, useState } from 'react';
import { ArrowDownToLine, ArrowRight, Fingerprint, ShieldQuestion } from 'lucide-react';
import { apiError, apiRequest, record, resultSummary, text } from '@/lib/workspace';
import { downloadJson } from '@/lib/demo';
import { EvidenceChip, GateInspector, VerdictBadge } from './EvidenceViews';

export default function ShareArtifact() {
  const [data, setData] = useState<unknown>(null);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState('drift_final');
  useEffect(() => {
    const controller = new AbortController();
    const id = new URLSearchParams(window.location.search).get('id');
    void (async () => {
      if (!id || !/^[a-f0-9]{32}$/.test(id)) throw new Error('This link does not contain a valid public artifact identifier.');
      const response = await apiRequest(`lab/shares/${id}`, 'GET', undefined, controller.signal);
      if (!response.up || response.status !== 200) throw new Error(apiError(response));
      if (!controller.signal.aborted) setData(response.data);
    })().catch(failure => { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'Artifact unavailable.'); });
    return () => controller.abort();
  }, []);
  const envelope = record(data);
  const artifact = record(envelope.artifact);
  const summary = resultSummary(artifact);
  return <main id="main" className="shared-artifact"><div className="shared-artifact-head"><Fingerprint size={32} strokeWidth={1.3} /><h1>{artifact.kind === 'duel' ? 'Two traces. One comparison.' : 'Evidence, open to inspection.'}</h1><p>Publicly shared by its submitter. Not an independent endorsement.</p></div>{error ? <div className="workspace-error" role="alert"><ShieldQuestion size={22} /><div><strong>Artifact unavailable</strong><p>{error}</p><span>Demo links expire after seven days and can disappear when ephemeral hosting resets.</span></div></div> : !data ? <div className="shared-loading" role="status">Loading the published evidence...</div> : <><div className="shared-artifact-meta"><EvidenceChip>{text(artifact.label, 'SCOPED COMPARISON')}</EvidenceChip><EvidenceChip>DRAFT</EvidenceChip><EvidenceChip>SUBMITTER-PUBLISHED</EvidenceChip></div>{artifact.kind === 'duel' ? <div className="shared-duel">{['left', 'right'].map(side => { const result = resultSummary(artifact[side]); return <section key={side}><h2>{side === 'left' ? 'Trace A' : 'Trace B'}</h2><VerdictBadge verdict={result.verdict} /><GateInspector gates={result.gates} selected={selected} onSelect={setSelected} /></section>; })}</div> : <><div className="shared-verdict"><VerdictBadge verdict={summary.verdict} /><h2>{text(artifact.name, 'Uploaded trace')}</h2></div><GateInspector gates={summary.gates} selected={selected} onSelect={setSelected} sampleCount={Number(record(artifact.scope).samples)} /></>}<div className="shared-hash"><span className="mono">INPUT FINGERPRINT</span><code>{text(artifact.input_hash)}</code><span>Raw traces are not included in this public artifact.</span></div><div className="toolbar-actions"><button className="button secondary" onClick={() => downloadJson('verification-shared-evidence.json', data)}><ArrowDownToLine size={15} />Download evidence</button><button className="button secondary" onClick={() => window.print()}>Print review</button></div><p className="instrument-footnote">{text(artifact.qualification, 'DRAFT scoped comparison. Human review required.')} Link expiry: {text(envelope.expires)}.</p></>}<a href="/free" className="button primary">Check your own trace <ArrowRight size={15} /></a></main>;
}