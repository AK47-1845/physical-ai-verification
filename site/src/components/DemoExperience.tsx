'use client';

import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import dynamic from 'next/dynamic';
import localFont from 'next/font/local';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import * as Dialog from '@radix-ui/react-dialog';
import { ArrowDownToLine, ArrowRight, Check, ChevronLeft, ChevronRight, Copy, Fingerprint, Pause, Play, RotateCcw, ShieldCheck, X } from 'lucide-react';
import { gsap } from 'gsap';
import { PilotButton } from './Actions';
import { EvidenceChip, TracePlot, VerdictBadge } from './EvidenceViews';
import { downloadJson } from '@/lib/demo';
import { apiRequest, buildDemoTrack, formatValue, parseTrace, record, resultSummary, text, type DemoTrack } from '@/lib/workspace';
import { chapterAt, DEMO_CHAPTERS, DEMO_DURATION, demoTime } from '@/lib/demo-timeline';
import receipt from '@/lib/demo-receipts.json';

const RobotScene = dynamic(() => import('./RobotScene'), { ssr: false });
const reducedQuery = '(prefers-reduced-motion: reduce)';
const subscribeMotion = (listener: () => void) => { const query = window.matchMedia(reducedQuery); query.addEventListener('change', listener); return () => query.removeEventListener('change', listener); };
const motionSnapshot = () => window.matchMedia(reducedQuery).matches;
const motionServerSnapshot = () => true;
const RECORDED_TRACK: DemoTrack = { ...receipt.track, inputs: { clean: parseTrace(JSON.stringify(receipt.track.inputs.clean)), drifty: parseTrace(JSON.stringify(receipt.track.inputs.drifty)) } };
const demoSans = localFont({ src: '../../node_modules/@fontsource-variable/sora/files/sora-latin-wght-normal.woff2', variable: '--font-demo-sans', display: 'swap' });
const demoMono = localFont({ src: [{ path: '../../node_modules/@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-400-normal.woff2', weight: '400', style: 'normal' }, { path: '../../node_modules/@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-500-normal.woff2', weight: '500', style: 'normal' }, { path: '../../node_modules/@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-600-normal.woff2', weight: '600', style: 'normal' }], variable: '--font-demo-mono', display: 'swap' });

export default function DemoExperience({ onClose }: { onClose?: () => void }) {
  const router = useRouter();
  const [elapsed, setElapsed] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [mode, setMode] = useState<'recorded' | 'live'>('recorded');
  const [track, setTrack] = useState<DemoTrack>(RECORDED_TRACK);
  const [copyStatus, setCopyStatus] = useState('');
  const elapsedRef = useRef(0);
  const contentRef = useRef<HTMLDivElement>(null);
  const reduced = useSyncExternalStore(subscribeMotion, motionSnapshot, motionServerSnapshot);
  const chapter = chapterAt(elapsed);
  const scene = DEMO_CHAPTERS[chapter];
  const candidateVisible = elapsed >= 28;
  const scored = resultSummary(candidateVisible ? track.drifty : track.clean);
  const catalogue = record(record(track.hunt).catalogue ?? track.hunt);
  const trials = Array.isArray(catalogue.trials) ? catalogue.trials : [];
  const revealed = Math.min(trials.length, Math.max(1, Math.floor((elapsed - 38) / 17 * trials.length) + 1));
  const activeTrial = record(trials[revealed - 1]);
  const parEnvelope = record(record(track.dossier).par);
  const parPayload = record(parEnvelope.par);
  const finalError = scored.gates.find(gate => gate.gate === 'drift_final')?.measurement;
  const finalNumber = typeof finalError === 'number' && Number.isFinite(finalError) ? finalError : 0;
  const scoreProgress = reduced ? 1 : Math.max(0, Math.min(1, (elapsed - (candidateVisible ? 28 : 20)) / 1.6));
  const easedScore = finalNumber * (1 - Math.pow(1 - scoreProgress, 3));
  const integrity = record(track.verification).ok === true;
  const narration = chapter === 2 && !candidateVisible
    ? 'Reference run first: the nominal trace holds inside every draft gate.'
    : scene.caption;

  useEffect(() => {
    const controller = new AbortController();
    void buildDemoTrack((path, method, body) => apiRequest(path, method, body, controller.signal)).then(live => {
      if (!controller.signal.aborted) { setTrack(live); setMode('live'); }
    }).catch(() => undefined);
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (mode !== 'live') return;
    const controller = new AbortController();
    let settled = false;
    const check = (attempt: number): void => {
      void apiRequest('governance', 'GET', undefined, controller.signal).then(response => {
        if (controller.signal.aborted || settled) return;
        if (!response.up || response.status !== 200) {
          if (attempt === 0) { check(1); return; }
          settled = true;
          setMode('recorded'); setTrack(RECORDED_TRACK);
        }
      }).catch(() => undefined);
    };
    check(0);
    return () => controller.abort();
  }, [chapter, mode]);

  useEffect(() => {
    if (!playing) return;
    let previous = performance.now();
    const timer = window.setInterval(() => {
      const current = performance.now();
      const next = Math.min(DEMO_DURATION, elapsedRef.current + (current - previous) / 1000);
      previous = current;
      elapsedRef.current = next;
      setElapsed(next);
      if (next === DEMO_DURATION) setPlaying(false);
    }, 100);
    return () => window.clearInterval(timer);
  }, [playing]);

  useEffect(() => {
    if (reduced || !contentRef.current) return;
    const context = gsap.context(() => {
      gsap.fromTo('.demo-story-line', { x: -18, y: 14, opacity: 0 }, { x: 0, y: 0, opacity: 1, stagger: 0.09, duration: 0.8, ease: 'power3.out' });
      gsap.fromTo('.demo-focus', { y: 18, opacity: 0, scale: 0.988 }, { y: 0, opacity: 1, scale: 1, duration: 0.8, delay: 0.12, ease: 'power3.out' });
    }, contentRef);
    return () => context.revert();
  }, [chapter, reduced]);

  function seek(seconds: number) {
    const next = Math.max(0, Math.min(DEMO_DURATION, seconds));
    elapsedRef.current = next; setElapsed(next);
    contentRef.current?.scrollTo({ top: 0 });
    if (next === DEMO_DURATION) setPlaying(false);
  }

  async function copyLink() {
    try { await navigator.clipboard.writeText(`${window.location.origin}/demo`); setCopyStatus('Demo link copied'); }
    catch { setCopyStatus(`${window.location.origin}/demo`); }
  }

  async function exportCapsule() {
    const bytes = new TextEncoder().encode(JSON.stringify(track));
    const digest = await crypto.subtle.digest('SHA-256', bytes);
    const hash = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
    downloadJson('verification-evidence-replay.json', { schema: receipt.schema, mode: mode === 'live' ? 'LIVE_ENGINE_SYNTHETIC_INPUTS' : 'RECORDED_SYNTHETIC', qualification: receipt.qualification, serialization: 'UTF-8 JSON.stringify(track)', track_sha256: hash, track });
  }

  return <div className={`demo-experience chapter-${chapter} ${reduced ? 'reduced' : ''} ${demoSans.variable} ${demoMono.variable}`} data-testid="demo-experience" data-mode={mode} data-chapter={chapter} data-elapsed={Math.round(elapsed)}>
    <div className="demo-world" aria-hidden="true" style={reduced ? undefined : { transform: `scale(${(1 + (elapsed / 90) * 0.07).toFixed(4)})`, transformOrigin: '62% 55%' }}><div className="demo-poster" /><RobotScene hero failure={(chapter === 2 && candidateVisible) || (chapter === 3 && Boolean(activeTrial.breaks)) ? 'drift' : 'nominal'} paused={reduced || !playing} /> <div className="demo-shade" /></div><div className="demo-film-progress" aria-hidden="true"><span style={{ width: `${(elapsed / 90 * 100).toFixed(2)}%` }} /></div>
    <header className="demo-header"><Link href="/" className="demo-brand">Verification</Link><div className="demo-mode"><span className={mode === 'live' ? 'live-indicator' : 'recorded-indicator'} /><span>{mode === 'live' ? 'LIVE ENGINE / SYNTHETIC INPUTS' : 'RECORDED SYNTHETIC / REPLAY'}<small>{mode === 'live' ? 'Returned backend evidence' : `Captured ${receipt.captured_at.slice(0, 10)}; used while backend is unavailable`}</small></span></div><button className="demo-icon-button" aria-label="Close demo" title="Close demo" onClick={() => onClose ? onClose() : router.push('/')}><X size={20} /></button></header>
    <div className="demo-content" ref={contentRef}>
      <article className="demo-story"><div className="demo-chapter-index mono">{String(chapter + 1).padStart(2, '0')} / 07 <span className="demo-chapter-rule" aria-hidden="true" /><span>{scene.name}</span></div><h1>{scene.title.map((line, index) => <span className="demo-story-line" key={`${chapter}-${index}`}>{line}</span>)}</h1><p className="demo-story-line">{scene.lead}</p>{chapter === 0 && <div className="demo-story-line demo-opening-note"><span className="demo-tiny-rule" />90 seconds. A trace becomes a record.</div>}{chapter === 6 && <div className="demo-end-actions demo-story-line"><PilotButton /><a href="/free" className="button secondary">Try the Free Lab <ArrowRight size={16} /></a><button onClick={() => void exportCapsule()} className="demo-export"><ArrowDownToLine size={16} />Take the evidence apart</button></div>}</article>
      <div className="demo-focus" aria-live="off">
        {chapter === 1 && <div className="demo-release-pair"><div className="demo-paper-head"><span>RELEASE SCOPE</span><EvidenceChip>SYNTHETIC</EvidenceChip></div><div className="demo-scope-row demo-row-in"><span className="mono">REFERENCE</span><strong>Evidence has a scope.</strong><span className="mono demo-run-id">{text(record(track.clean).run_id)}</span></div><div className="demo-scope-row candidate demo-row-in" style={{ animationDelay: '90ms' }}><span className="mono">CANDIDATE</span><strong>A new trace enters.</strong><span className="mono demo-run-id">{text(record(track.drifty).run_id)}</span></div><p>Scripted release illustration. No weights were trained or changed.</p></div>}
        {chapter === 2 && <div className={`demo-score-paper ${candidateVisible ? 'candidate' : ''}`}><div className="demo-paper-head"><span>{candidateVisible ? 'CANDIDATE / DRIFTING REACH' : 'REFERENCE / NOMINAL REACH'}</span><EvidenceChip>DRAFT</EvidenceChip></div><div className="demo-score-reading"><span key={scored.verdict} className="demo-verdict-pop"><VerdictBadge verdict={scored.verdict} /></span><div><strong>{formatValue(reduced ? finalError : easedScore, 2)}</strong><span>m final tracking error</span></div></div><div key={candidateVisible ? 'plot-cand' : 'plot-ref'} className="demo-plot-draw"><TracePlot pair={candidateVisible ? track.inputs.drifty : track.inputs.clean} compact /></div><div className="demo-gate-strip" key={candidateVisible ? 'gates-cand' : 'gates-ref'}>{scored.gates.map((gate, index) => <div key={gate.gate} className={`gate-${gate.status.toLowerCase()}`} style={{ animationDelay: `${index * 70}ms` }}><span className="gate-name">{gate.gate.replaceAll('_', ' ')}</span><em className="gate-status">{gate.status}</em><b>{formatValue(gate.measurement)}</b></div>)}</div><p>Exact returned measurements on a six-point synthetic trace.</p></div>}
        {chapter === 3 && <div className="demo-hunt"><div className="demo-paper-head"><span>SEEDED FIXTURE SEARCH</span><EvidenceChip>SYNTHETIC</EvidenceChip></div><div className="demo-hunt-count"><strong key={revealed} className="demo-count-tick">{String(revealed).padStart(2, '0')}</strong><span>/ {trials.length}<small>completed trials revealed</small></span></div><div className="demo-trials" key={`trials-${revealed}`}>{trials.map((item, index) => { const trial = record(item); return <span key={index} style={{ animationDelay: `${index * 30}ms` }} className={`cell-in ${index < revealed ? 'shown' : ''} ${trial.breaks ? 'breaks' : 'holds'} ${index === revealed - 1 ? 'current' : ''}`}>{index < revealed ? trial.breaks ? <X size={14} /> : <Check size={14} /> : <span className="mono">{String(index + 1).padStart(2, '0')}</span>}</span>; })}</div><div className="demo-trial-detail" key={`detail-${revealed}`}><span className="mono">TRIAL {revealed}</span><strong>{activeTrial.breaks ? 'Boundary breached.' : 'No break in this trial.'}</strong><div>{Object.entries(record(activeTrial.params)).map(([key, value]) => <span key={key}>{key.replaceAll('_', ' ')} <b className="mono">{formatValue(value)}</b></span>)}</div></div><p>Search can find a counterexample. It cannot establish the absence of every failure.</p></div>}
        {chapter === 4 && <div className="demo-record"><div className="demo-paper-head"><span>POLICY ASSURANCE RECORD</span><Fingerprint size={19} /></div><h2>Inspectable.<br />Exportable.<br /><span>Still unsigned.</span></h2><div className="demo-record-rows"><span className="demo-row-in"><Check size={15} />Run and gates linked</span><span className="demo-row-in" style={{ animationDelay: '80ms' }}><Check size={15} />Operating envelope recorded</span><span className="demo-row-in" style={{ animationDelay: '160ms' }}><Check size={15} />{integrity ? 'Hash and structure checked' : 'Integrity needs review'}</span><span className="demo-row-in" style={{ animationDelay: '240ms' }}><ShieldCheck size={15} />External ledger anchor required</span></div><div className="demo-hash"><span className="mono">PAR SHA256</span><code>{text(parEnvelope.par_hash, 'Not recorded')}</code></div><div className="demo-law-rows"><span>Machinery: Part A 5 / 6</span><EvidenceChip>REFERENCE MAPPING</EvidenceChip><span>Applicability and OTA review</span><EvidenceChip>HUMAN REVIEW</EvidenceChip></div><p>Not legal advice. An unsigned hash does not authenticate the author.</p></div>}
        {chapter === 5 && <div className="demo-independence"><div className="demo-independence-rule demo-row-in"><span>01</span><strong>No policy training.</strong></div><div className="demo-independence-rule demo-row-in" style={{ animationDelay: '90ms' }}><span>02</span><strong>No automatic remediation.</strong></div><div className="demo-independence-rule demo-row-in" style={{ animationDelay: '180ms' }}><span>03</span><strong>Relationships declared.</strong></div><div className="demo-declaration demo-row-in" style={{ animationDelay: '270ms' }}><span className="mono">THIS DEMONSTRATION</span><p>{text(record(parPayload.independence).builder)} / {text(record(parPayload.independence).funder)}</p><EvidenceChip>NOT AN EXTERNAL ASSESSMENT</EvidenceChip></div></div>}
        {chapter === 6 && <div className="demo-final-artifact"><Fingerprint size={64} strokeWidth={1} /><span className="mono">A RECORD, NOT A PROMISE.</span><strong>{text(parEnvelope.par_hash).slice(0, 16)}</strong><div className="honesty-line"><EvidenceChip>DRAFT</EvidenceChip><EvidenceChip>SYNTHETIC</EvidenceChip><EvidenceChip>UNSIGNED</EvidenceChip></div><a href="/playground">Open the live workspace <ArrowRight size={16} /></a></div>}
      </div>
    </div>
    <footer className="demo-controls"><div className="demo-caption-track" aria-live="polite"><span className="mono">{mode === 'live' ? 'LIVE ENGINE' : 'RECORDED REPLAY'}</span><p key={`${chapter}-${candidateVisible ? 'c' : 'r'}`}>{narration}</p></div><div className="demo-timeline"><input type="range" min="0" max={DEMO_DURATION} step="1" value={Math.floor(elapsed)} onChange={event => seek(Number(event.target.value))} aria-label="Demo timeline" style={{ background: `linear-gradient(90deg,var(--signal) ${(elapsed / DEMO_DURATION * 100).toFixed(2)}%,#2c3f34 ${(elapsed / DEMO_DURATION * 100).toFixed(2)}%)` }} /><div className="demo-chapters">{DEMO_CHAPTERS.map((item, index) => { const fill = Math.max(0, Math.min(1, (elapsed - item.start) / (item.end - item.start))); return <button key={item.start} className={chapter === index ? 'active' : chapter > index ? 'reached' : ''} aria-label={`Chapter ${index + 1}: ${item.name}`} aria-current={chapter === index ? 'step' : undefined} onClick={() => seek(item.start)}><span className="rail" aria-hidden="true"><span className="fill" style={{ width: `${Math.round(fill * 100)}%` }} /></span><span className="rail-name">{item.name}</span></button>; })}</div></div><div className="demo-control-row"><div className="demo-transport"><button className="demo-icon-button" aria-label={playing ? 'Pause demo' : elapsed === DEMO_DURATION ? 'Replay demo' : 'Play demo'} title={playing ? 'Pause' : 'Play'} onClick={() => { if (elapsed === DEMO_DURATION) seek(0); setPlaying(previous => !previous); }}>{playing ? <Pause size={19} /> : <Play size={19} />}</button><button className="demo-icon-button" aria-label="Previous chapter" title="Previous chapter" onClick={() => seek(DEMO_CHAPTERS[Math.max(0, chapter - 1)].start)}><ChevronLeft size={18} /></button><button className="demo-icon-button" aria-label="Next chapter" title="Next chapter" onClick={() => seek(chapter === DEMO_CHAPTERS.length - 1 ? DEMO_DURATION : DEMO_CHAPTERS[chapter + 1].start)}><ChevronRight size={18} /></button><span className="mono demo-time" role="timer">{demoTime(elapsed)} <span>/ 1:30</span></span></div><div className="demo-control-right"><span className="demo-caption-note">{reduced ? 'REDUCED MOTION' : 'CAPTIONED / SILENT'}</span><button className="demo-icon-button" title="Restart demo" aria-label="Restart demo" onClick={() => { seek(0); setPlaying(true); }}><RotateCcw size={17} /></button><button className="demo-icon-button" title="Copy demo link" aria-label="Copy demo link" onClick={() => void copyLink()}><Copy size={17} /></button></div></div><span className="demo-copy-status" role="status">{copyStatus}</span></footer>
  </div>;
}

export function DemoRoute() {
  const router = useRouter();
  return <main id="main"><Dialog.Root defaultOpen onOpenChange={open => { if (!open) router.push('/'); }}><Dialog.Portal><Dialog.Overlay className="demo-overlay" /><Dialog.Content className="demo-dialog"><Dialog.Title className="demo-sr-only">The 90-second evidence walkthrough</Dialog.Title><Dialog.Description className="demo-sr-only">A captioned synthetic demonstration of scoring, failure hunting and evidence verification.</Dialog.Description><DemoExperience /></Dialog.Content></Dialog.Portal></Dialog.Root></main>;
}