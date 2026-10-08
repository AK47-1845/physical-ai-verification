import { ArrowUpRight, Bot, CircuitBoard, Workflow, Route, ShieldCheck, Fingerprint, Layers } from 'lucide-react';
import Hero from './Hero';
import { PilotButton } from './Actions';
import FailureLab from './FailureLab';
import Pipeline from './Pipeline';
import Evidence from './Evidence';
import SmoothMotion from './SmoothMotion';
import ContextSections from './ContextSections';

export default function Pitch() {
  return <>
    <SmoothMotion />
    <main id="main">
      <Hero />
      <div className="context-strip"><div className="container context-inner"><p>For the teams putting intelligence<br />into the physical world.</p><div className="domain-list"><span><Bot />Robotics</span><span><Workflow />Autonomous systems</span><span><CircuitBoard />Embodied models</span></div><a className="text-link" href="#platform">One evidence layer<ArrowUpRight size={14} /></a></div></div>
      <section id="platform" className="section"><div className="container"><div className="section-header"><h2>A capable model.<br /><span>Is it a dependable system?</span></h2><p>Between a successful demonstration and a defensible deployment lies the evidence that matters.</p></div><div className="capability-list">
        {[{ icon: Route, title: 'Reality, compared.', body: 'Quantify trajectory divergence. Preserve the units, frames and conditions behind every result.' },{ icon: ShieldCheck, title: 'Behavior, bounded.', body: 'Scope the proof. Guard the runtime. Keep missing evidence from becoming a silent pass.' },{ icon: Layers, title: 'Intelligence, monitored.', body: 'Inspect perception conflicts, distribution shift and recursive-data degradation separately.' },{ icon: Fingerprint, title: 'Evidence, preserved.', body: 'Trace each decision to its inputs, policy version and reviewer. Export a verifiable record.' }].map(item => <article className="capability" key={item.title}><item.icon /><h3>{item.title}</h3><p>{item.body}</p></article>)}
      </div></div></section>
      <FailureLab />
      <Pipeline />
      <Evidence />
      <ContextSections />
      <section className="closing"><div className="container closing-grid"><div><h2>The next deployment<br /><span>deserves better evidence.</span></h2><p>One robot. One hard failure mode. One evidence package worth putting in front of an assessor.</p></div><PilotButton /></div></section>
    </main>
    <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify({ '@context': 'https://schema.org', '@type': 'SoftwareApplication', name: 'Verification', applicationCategory: 'DeveloperApplication', operatingSystem: 'Web', description: 'Evidence-first verification and governance for physical AI. Demonstration site; hardware qualification and independent assessment remain required.' }) }} />
  </>;
}
