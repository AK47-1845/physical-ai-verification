'use client';

import dynamic from 'next/dynamic';
import { Activity, ArrowDownToLine, Check, CircleAlert, EyeOff, Focus, RotateCcw, ScanLine } from 'lucide-react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { useEffect, useRef, useState } from 'react';
import { assessDemo, downloadJson, failures, type Failure } from '@/lib/demo';

const RobotScene = dynamic(() => import('./RobotScene'), { ssr: false });
const icons = { nominal: ScanLine, sensor: EyeOff, scene: Focus, drift: Activity };

export default function FailureLab() {
  const [selected, setSelected] = useState<Failure>('nominal');
  const [applied, setApplied] = useState<Failure>('nominal');
  const [busy, setBusy] = useState(false);
  const [visible, setVisible] = useState(false);
  const [digest, setDigest] = useState('');
  const root = useRef<HTMLElement>(null);
  const reduced = useReducedMotion();
  const result = assessDemo(applied);
  useEffect(() => {
    if (!root.current) return;
    const observer = new IntersectionObserver(entries => { if (entries[0].isIntersecting) { setVisible(true); observer.disconnect(); } }, { rootMargin: '200px' });
    observer.observe(root.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!busy) return;
    const timer = setTimeout(() => { setApplied(selected); setBusy(false); }, reduced ? 0 : 750);
    return () => clearTimeout(timer);
  }, [selected, busy, reduced]);
  useEffect(() => {
    let live = true;
    crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(assessDemo(applied)))).then(buffer => {
      if (live) setDigest(Array.from(new Uint8Array(buffer), value => value.toString(16).padStart(2, '0')).join(''));
    });
    return () => { live = false; };
  }, [applied]);
  function inject(failure: Failure) { setSelected(failure); setBusy(true); }
  const chartPath = result.samples.map((sample, index) => `${index === 0 ? 'M' : 'L'}${16 + index / 119 * 568},${133 - sample.drift * 1000 / 160 * 110}`).join(' ');
  return <section id="failure-lab" className="section failure-section" ref={root}><div className="container"><div className="section-header"><div><span className="section-number mono">01 / FAILURE LAB</span><h2>Don&apos;t trust the demo.<br /><span>Try to break it.</span></h2></div><p>A small change in the world can become a big change in behavior. The evidence should make that impossible to miss.</p></div><div className="lab-shell"><div className="lab-topbar"><span className="mono">ARM-REACH / POLICY v1.0</span><span className="mono muted">SYNTHETIC SANDBOX</span><button className="icon-button" onClick={() => inject('nominal')} aria-label="Reset failure experiment" title="Reset experiment"><RotateCcw /></button></div><div className="failure-controls" role="group" aria-label="Failure injection"><span className="mono muted">INJECT A CONDITION</span>{failures.slice(1).map(failure => { const Icon = icons[failure.id]; return <button key={failure.id} className={`failure-choice ${selected === failure.id ? 'selected' : ''}`} onClick={() => inject(failure.id)} aria-pressed={selected === failure.id}><Icon size={16} />{failure.name}</button>; })}</div><div className="lab-main"><div className="lab-visual"><div className="lab-visual-label mono"><span className={result.verdict === 'BLOCK' ? 'fail' : 'signal'}>{busy ? 'PERTURBATION IN PROGRESS' : result.verdict === 'BLOCK' ? 'FAILURE BOUNDARY DETECTED' : 'REFERENCE BEHAVIOR'}</span><span>120 SAMPLES / 6s</span></div><div className="lab-robot">{visible ? <RobotScene failure={applied} /> : null}</div><div className="plot"><div className="plot-heading mono"><span>TRACKING ERROR</span><span className="muted">mm / time</span></div><svg viewBox="0 0 600 154" role="img" aria-label={`Tracking error chart. Peak ${result.gates[0].display}. Demonstration threshold 50 millimeters.`}><line x1="16" x2="584" y1="133" y2="133" stroke="#35413e" /><line x1="16" x2="584" y1="64" y2="64" stroke="#202d2a" /><line x1="16" x2="584" y1="98.6" y2="98.6" stroke="#9b7564" strokeWidth="1" /><text x="16" y="91" fill="#cfae9b" fontSize="10">50 mm limit</text><path d={chartPath} fill="none" stroke={applied === 'drift' ? '#ffa18b' : '#83ece4'} strokeWidth="2.4" /><text x="16" y="150" fill="#8da29a" fontSize="9">0s</text><text x="555" y="150" fill="#8da29a" fontSize="9">6s</text></svg></div></div><div className="lab-results"><div className="result-heading"><span className="mono muted">GATE EVALUATION</span><span className="mono">{result.passing} / 4</span></div><div className="gate-list">{result.gates.map(gate => <div className="demo-gate" key={gate.id}><span className={gate.state === 'PASS' ? 'pass' : 'fail'}>{gate.state === 'PASS' ? <Check size={15} /> : <CircleAlert size={15} />}</span><div><strong>{gate.label}</strong><span className="mono muted">{gate.limit}</span></div><span className={`mono ${gate.state === 'BLOCK' ? 'fail' : ''}`}>{gate.display}</span></div>)}</div><AnimatePresence mode="wait"><motion.div key={applied + busy} initial={{ opacity: 0, y: reduced ? 0 : 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: .18 }} className={`verdict-panel ${result.verdict === 'BLOCK' ? 'blocked' : ''}`} aria-live="polite"><span className="mono">SUPERVISORY DECISION</span><strong>{busy ? 'Evaluating...' : result.decision}</strong><p>{busy ? 'Replaying the perturbed trace against the same gate profile.' : result.description}</p></motion.div></AnimatePresence><div className="event-record"><span className="mono muted">EVIDENCE RECORD</span><div className="mono"><span>trace</span><span>ev-{applied}-0248</span></div><div className="mono"><span>integrity</span><span>{digest ? `${digest.slice(0, 8)}...${digest.slice(-4)}` : 'computing'}</span></div><div className="mono"><span>origin</span><span>SYNTHETIC</span></div></div><button className="button secondary evidence-download" disabled={busy || !digest} onClick={() => downloadJson(`verification-${applied}-evidence.json`, { ...result, integrity: { algorithm: 'SHA-256', digest, signed: false } })}><ArrowDownToLine size={15} />Export example evidence</button></div></div></div><div className="section-footer mono"><span>DETERMINISTIC BROWSER DEMONSTRATION. NO ROBOT EXECUTED.</span><span>DRAFT GATES / NOT A SAFETY CERTIFICATE</span></div></div></section>;
}