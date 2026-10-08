import type { Metadata } from "next";
import { ClipboardCheck, FileCheck2 } from 'lucide-react';
import { PilotButton } from '@/components/Actions';
import { RegulationClock, WorksheetForm } from '@/components/PageWorkbench';

export const metadata: Metadata = {
  title: "Compliance | Verification",
  description: "Regulation rows mapped to evidence: Machinery Regulation, AI Act reference map, OTA vault.",
};

const ROWS = [
  { row: 'EU 2023/1230 / ANNEX I PART A 5-6', title: 'ML safety-function scoping', body: 'Record the safety function and deployed learning behavior. Applicability and assessment route need product-specific human and legal review.', badge: 'DRAFT MAPPING', blocked: false },
  { row: 'EU 2023/1230 / ART 3(16) + 18', title: 'Modification review', body: 'A behavior-changing update may require a substantial-modification review. Parent and candidate evidence support that review; a score does not decide the law.', badge: 'DRAFT MAPPING', blocked: false },
  { row: 'EU 2023/1230 / EHSR 1.1.9 + 1.2.1', title: 'Control-system evidence', body: 'Parameter histories, integrity records and bounded measurements can organize a technical file. They do not establish conformity.', badge: 'UNVERIFIED-CLAUSE', blocked: true },
  { row: 'EU 2024/1689 / REFERENCE ONLY', title: 'AI Act reference map', body: 'Data lineage, logging, oversight and robustness are reference categories. Effective dates and sector interactions require a current legal review.', badge: 'REFERENCE', blocked: false },
  { row: 'ISO 10218:2025 / 5.3.5', title: 'Parameter records', body: 'Checksums and parameter logs support update review. A checksum is not a signature. Clause wording has not been independently verified in this product.', badge: 'UNVERIFIED-CLAUSE', blocked: true },
  { row: 'ISO/CD 25785-1', title: 'Humanoid safety (draft standard)', body: 'Standard unpublished: placeholder only, no clause text cited. Fall and balance behavior tracked as research rows until publication.', badge: 'DRAFT', blocked: true },
];

export default function CompliancePage() {
  return <main id="main">
    <section className="page-hero"><div className="container"><div className="hero-kicker mono">COMPLIANCE</div><h1>Regulation, mapped<br /><span>to evidence.</span></h1><p>Every regulation row points at measured evidence, not marketing. Draft mappings, human review required.</p></div></section>
    <section className="section"><div className="container">
      <RegulationClock />
    </div></section>
    <section className="section"><div className="container"><div className="section-header"><div><span className="section-number mono">01 / REGULATION ROWS</span><h2>Six rows.<br /><span>Each with an artifact.</span></h2></div><p>A row without a pointer is a wish. DRAFT rows stay visibly draft until a credibility card lands.</p></div>
      <div className="evidence-ledger"><div className="ledger-heading"><ClipboardCheck size={18} /><h3>Mapping table</h3><span className="mono">DRAFT / HUMAN REVIEW REQUIRED</span></div><div className="ledger-columns mono"><span>REGULATION ROW</span><span>MAPPING</span></div>
        {ROWS.map(row => <div className="ledger-row" key={row.row}><span><span className="mono">{row.row}</span><strong>{row.title}</strong><span className="ledger-body">{row.body}</span></span><span className={`ledger-badge ${row.blocked ? 'block' : ''}`}>{row.badge}</span></div>)}
      </div>
    </div></section>
    <section className="section"><div className="container"><div className="section-header"><div><span className="section-number mono">02 / APPLICABILITY WORKSHEET</span><h2>Three questions.<br /><span>Recorded, not decided.</span></h2></div><p>The worksheet captures your answers and the implied route. It states no legal conclusion, ever.</p></div>
      <WorksheetForm />
      <div className="honesty-banner mono"><FileCheck2 size={16} />HUMAN + LEGAL REVIEW REQUIRED / THIS PAGE IS NOT LEGAL ADVICE</div>
      <div className="page-cta" style={{ marginTop: 40 }}><div><h2>Map your route.<br /><span>Before the clock does.</span></h2></div><div className="page-cta-actions"><PilotButton /><span className="mono muted">WORKSHEET INCLUDED IN EVERY PILOT</span></div></div>
    </div></section>
  </main>;
}
