import type { Metadata } from "next";
import { Bot, Check, Factory, Fingerprint, HeartPulse } from 'lucide-react';
import { PilotButton } from '@/components/Actions';
import { DriftExperiment } from '@/components/PageWorkbench';

export const metadata: Metadata = {
  title: "Use Cases | Verification",
  description: "Verification tracks for humanoid pilots, VLA release gates, and insurer evidence.",
};

const TRACKS = [
  {
    index: '01', icon: Bot, title: 'Humanoid pilots',
    body: 'Bounded, fenced deployments scored per release: drift curves at horizon, executability envelopes, and a Policy Assurance Record an outsider can re-check. Start with one robot and one hard failure mode.',
    measures: ['DRIFT @ HORIZON', 'EXECUTABILITY', 'PER-RELEASE PAR'],
  },
  {
    index: '02', icon: Factory, title: 'VLA release gates',
    body: 'Compare stored parent and candidate measurements under the same profile. The current review view reports gate deltas, not confidence intervals for uploaded single traces. Human review determines the significance of an update.',
    measures: ['PER-GATE DELTAS', 'PINNED PROFILES', 'HUMAN REVIEW'],
  },
  {
    index: '03', icon: HeartPulse, title: 'Insurer evidence',
    body: 'Review scoped measurements, declared provenance and repeatable integrity checks. Insurer recognition is a validation goal, not an existing endorsement or commercial relationship.',
    measures: ['UNDERWRITING ROWS', 'RELIABILITY INPUTS', 'FORMAT v0.1'],
  },
  {
    index: '04', icon: Fingerprint, title: 'Synthetic-data provenance',
    body: 'Generation-level batch manifests, corpus mix ledgers, and collapse sentinels. Accumulation needs attribution; know your alpha per generation or stop training.',
    measures: ['BATCH MANIFESTS', 'ALPHA LEDGER', 'COLLAPSE SENTINELS'],
  },
];

const TIERS = [
  { title: 'Tier 1 / Simulation & inspection', body: 'Cash-flowing infrastructure: simulators, inspection stacks, and validation tooling running inside enterprise environments today.' },
  { title: 'Tier 2 / Bounded industrial pilots', body: 'Strictly fenced deployments with a human authority line. This is where scored evidence earns its keep, and where we start with you.' },
  { title: 'Tier 3 / Unconstrained labs', body: 'Research environments where behavior is still being mapped. We score generalization here so Tier 2 claims stay honest.' },
];

export default function UseCasesPage() {
  return <main id="main">
    <section className="page-hero"><div className="container"><div className="hero-kicker mono">USE CASES</div><h1>Tested where<br /><span>it matters.</span></h1><p>Verification tracks for the teams shipping physical intelligence. Each track ends in evidence an outsider can re-check.</p></div></section>
    <section className="section"><div className="container"><div className="section-header"><div><span className="section-number mono">01 / TRACKS</span><h2>Four ways in.<br /><span>One evidence standard.</span></h2></div><p>Every track produces the same artifact: a Policy Assurance Record with measurements, thresholds, and lineage.</p></div>
      <div className="track-rows">{TRACKS.map((track, index) => { const Icon = track.icon; return <article className="track-row" key={track.title}><span className="track-icon"><Icon size={22} /></span><div><h3>{track.title}</h3><p>{track.body}</p><div className="track-measures">{track.measures.map(measure => <span key={measure}><Check size={12} />{measure.toLowerCase()}</span>)}</div><a className="text-action" href={`/playground?flow=${['score', 'compare', 'dossier', 'provenance'][index]}`}>Open workflow</a></div></article>; })}</div>
      <DriftExperiment />
    </div></section>
    <section className="section"><div className="container"><div className="section-header"><div><h2>Define the operating envelope</h2></div><p>Reliability is specific to the machine, duty cycle and deployment. This product does not infer a fleet MTBF from synthetic trace tests.</p></div>
      <div className="capability-list">{TIERS.map(tier => <div className="capability" key={tier.title}><h3>{tier.title}</h3><p>{tier.body}</p></div>)}</div>
      <div className="verdict-panel blocked" style={{ marginTop: 36 }}><span className="mono">WHY BOUNDED FIRST</span><strong>Unproven range claims stay fenced.</strong><p>Any behavior outside the measured envelope ships as INSUFFICIENT, never as a pass. The fence moves only when the evidence does.</p></div>
    </div></section>
    <section className="section"><div className="container page-cta"><div><span className="section-number mono">03 / START</span><h2>One robot. One failure mode.<br /><span>One evidence package.</span></h2></div><div className="page-cta-actions"><PilotButton /><span className="mono muted">SCOPED PER PILOT / NO PUBLIC TIERS</span></div></div></section>
  </main>;
}
