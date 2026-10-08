'use client';

import { useEffect, useRef, useState } from 'react';
import { ArrowUpRight, Check, FileCheck2, Fingerprint, ScanLine } from 'lucide-react';

const stages = [
  { label: 'Simulate', heading: 'Make the conditions explicit.', body: 'Start with a trajectory, a task and an embodiment. Preserve the coordinate frame and the source of every observation.', artifact: 'SCENARIO / ARM-REACH-0248', detail: 'Intended trajectory + observed behavior', tag: 'INPUT CONTRACT' },
  { label: 'Verify', heading: 'Find the edge of acceptable.', body: 'Apply versioned constraints to the right layer. A narrow proof, a runtime invariant and a perception check answer different questions.', artifact: 'CONSTRAINTS / PROFILE v1.0', detail: 'Task envelope + behavior limits', tag: 'BOUNDED CLAIMS' },
  { label: 'Validate', heading: 'Close the loop with reality.', body: 'Compare behavior under changed conditions. Surface drift, unsupported perception and missing evidence without averaging the risk away.', artifact: 'ASSESSMENT / 04 GATES', detail: 'Measurements + failure intervals', tag: 'TRACEABLE RESULT' },
  { label: 'Certify', heading: 'Give the assessor the evidence.', body: 'Package the trace, gate profile and review history into a verifiable record. Conformity assessment stays with qualified independent assessors.', artifact: 'DOSSIER / PREPARED FOR REVIEW', detail: 'Evidence package, not certification', tag: 'HUMAN AUTHORITY' },
];

export default function Pipeline() {
  const [active, setActive] = useState(0);
  const section = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!window.matchMedia('(min-width: 900px) and (prefers-reduced-motion: no-preference)').matches) return;
    let stopped = false;
    let cleanup = () => {};
    const observer = new IntersectionObserver(entries => {
      if (!entries[0].isIntersecting) return;
      observer.disconnect();
      Promise.all([import('gsap'), import('gsap/ScrollTrigger')]).then(([{ gsap }, { ScrollTrigger }]) => {
        if (stopped) return;
        gsap.registerPlugin(ScrollTrigger);
        const trigger = ScrollTrigger.create({ trigger: section.current, start: 'top 90px', end: 'bottom bottom', onUpdate: self => setActive(Math.min(3, Math.floor(self.progress * 4))) });
        cleanup = () => trigger.kill();
      });
    }, { rootMargin: '200px' });
    if (section.current) observer.observe(section.current);
    return () => { stopped = true; observer.disconnect(); cleanup(); };
  }, []);
  const stage = stages[active];
  return <section className="pipeline-section" id="pipeline" ref={section}><div className="pipeline-sticky container"><div className="section-header"><div><span className="section-number mono">02 / THE EVIDENCE PIPELINE</span><h2>One system.<br /><span>A chain of accountable decisions.</span></h2></div><p>From the first scenario to the final review. Every claim has a source. Every handoff preserves the context.</p></div><div className="pipeline-tabs" role="tablist" aria-label="Evidence pipeline stages">{stages.map((item, index) => <button key={item.label} role="tab" id={`stage-${index}`} aria-controls="pipeline-panel" aria-selected={active === index} onClick={() => setActive(index)} className={active === index ? 'active' : ''}><span className="mono">0{index + 1}</span>{item.label}<ArrowUpRight size={16} /></button>)}</div><div className={`pipeline-content stage-${active}`} id="pipeline-panel" role="tabpanel" aria-labelledby={`stage-${active}`}><div className="pipeline-copy"><span className="mono signal">{stage.tag}</span><h3>{stage.heading}</h3><p>{stage.body}</p><div className="pipeline-checks">{stages.slice(0, active + 1).map(item => <span key={item.label}><Check size={13} />{item.label === 'Certify' ? 'Assessor package' : item.label}</span>)}</div></div><div className="pipeline-instrument"><div className="instrument-top mono"><ScanLine size={15} />{stage.artifact}<Fingerprint size={15} /></div><div className="pipeline-art"><svg viewBox="0 0 560 245" role="img" aria-label={`${stage.label}: the same trajectory progressively gains constraints, measurements and evidence.`}><defs><pattern id="instrument-grid" width="28" height="28" patternUnits="userSpaceOnUse"><path d="M 28 0 L 0 0 0 28" fill="none" stroke="#253633" strokeWidth=".7" /></pattern></defs><rect x="0" y="0" width="560" height="245" fill="url(#instrument-grid)" /><path d="M 42 186 C 100 170 108 56 191 54 S 254 183 328 177 S 426 42 508 66" fill="none" stroke="#83ece4" strokeWidth="2.3" /><path d="M 42 189 C 106 172 110 66 191 59 S 269 206 341 183 S 441 62 508 82" fill="none" stroke="#d3e9dc" strokeWidth="1" opacity=".55" />{active >= 1 ? <><rect x="75" y="31" width="403" height="177" rx="2" fill="none" stroke="#8bc4b7" strokeWidth="1" /><text x="86" y="23" fill="#a4c8bc" fontSize="10">BOUNDED TASK ENVELOPE</text></> : null}{active >= 2 ? <><line x1="335" y1="182" x2="390" y2="215" stroke="#d9bfa3" /><circle cx="335" cy="182" r="5" fill="#ffa18b" /><text x="395" y="221" fill="#d9bfa3" fontSize="10">ERROR / 14.8 mm</text></> : null}</svg>{active === 3 ? <div className="pipeline-report"><FileCheck2 size={32} /><span className="mono">EVIDENCE PACKAGE</span><strong>Ready for<br />independent review.</strong><span className="mono muted">TRACE / GATES / LINEAGE / REVIEW</span><span className="unsigned mono">NOT A CERTIFICATE</span></div> : null}</div><div className="instrument-bottom mono"><span>{stage.detail}</span><span>EXAMPLE / v1</span></div></div></div></div></section>;
}