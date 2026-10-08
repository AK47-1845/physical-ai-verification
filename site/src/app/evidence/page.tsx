import type { Metadata } from "next";
import { PilotButton } from '@/components/Actions';
import { CopyCommand, EvidenceWorkbench } from '@/components/PageWorkbench';

export const metadata: Metadata = {
  title: "Evidence | Verification",
  description: "Scorecards, provenance ledgers, and dossiers. Every verdict traceable.",
};

const CARD_FIELDS = [
  { title: 'Independent rollouts', body: 'Rollout count per condition, by type: teleop, scripted, policy-sampled, generated. Below minimum n the gate reports INSUFFICIENT.' },
  { title: 'Error rates by type', body: 'False-positive and false-negative counts with label totals. Fixtures ship labeled; field corpora need a labelling pass.' },
  { title: 'Human agreement', body: 'Agreement with human labels plus inter-annotator spread. A gate no human ever checked cannot lift DRAFT.' },
  { title: 'Calibration', body: 'Score-vs-outcome bins. Conformal thresholds only with an explicit exchangeability statement: void if a policy trained against us.' },
  { title: 'Transfer error', body: 'Cross-embodiment error measured on real-vs-sim pairs. Claims travel only as far as the pairs do.' },
  { title: 'Search hits', body: 'Times our own adversarial hunt proved this gate wrongly TRUSTED. Hits become sev-1 regression tests the same day.' },
];

export default function EvidencePage() {
  return <main id="main">
    <section className="page-hero"><div className="container"><h1>Evidence review</h1><p>Inspect the measurement behind a verdict. Export the record and check its integrity independently.</p></div></section>
    <section className="section"><div className="container"><EvidenceWorkbench /></div></section>
    <section className="section"><div className="container"><div className="section-header"><div><span className="section-number mono">02 / POLICY ASSURANCE RECORD</span><h2>One record.<br /><span>Open schema, offline reader.</span></h2></div><p>The PAR is the unit of trust: policy, release delta, per-gate verdicts, ledger head, and independence register. The schema is open; the reader recomputes every hash with no network.</p></div>
      <CopyCommand command="python backend/par_cli.py par.json" />
      <div className="capability-list" style={{ marginTop: 28 }}><div className="capability"><h3>Portable schema</h3><p>The versioned JSON schema and offline reader ship with the source. No proprietary viewer is needed for the integrity check.</p></div><div className="capability"><h3>Offline integrity check</h3><p>Recomputes the artifact hash and validates structure without a network connection. It does not authenticate the author.</p></div><div className="capability"><h3>Declared relationships</h3><p>Builder, funder and relationship travel with the PAR. A declaration is not independent validation of that relationship.</p></div></div>
    </div></section>
    <section className="section"><div className="container"><div className="section-header"><div><h2>Verifier credibility</h2></div><p>Current thresholds remain DRAFT. A credibility record must describe the labeled corpus, measurement method, analyst and known error rates before a gate can graduate.</p></div>
      <div className="capability-list">{CARD_FIELDS.map(field => <div className="capability" key={field.title}><h3>{field.title}</h3><p>{field.body}</p></div>)}</div>
      <div className="page-cta" style={{ marginTop: 44 }}><div><h2>Scope evidence<br /><span>for your pilot.</span></h2></div><div className="page-cta-actions"><PilotButton /><span className="mono muted">READER + SCHEMA SHIP WITH EVERY PACK</span></div></div>
    </div></section>
  </main>;
}
