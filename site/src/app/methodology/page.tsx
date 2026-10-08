import type { Metadata } from "next";
import { Boxes, FlaskConical, GitBranch, Timer } from 'lucide-react';
import { PilotButton } from '@/components/Actions';
import RobotScene from '@/components/RobotScene';
import { FailureProbe, RatioExperiment } from '@/components/PageWorkbench';

export const metadata: Metadata = {
  title: "Methodology | Verification",
  description: "Five failure modes, layered gates, deterministic evidence. How verification works.",
};

const MODES = [
  { index: 'FM1', icon: FlaskConical, title: 'Compounding autoregressive drift', body: 'Latent errors accumulate over horizon T until the world model leaves the real state space: interpenetration, boundary breach, phantom contact.', chip: 'E[T] ~ O(T·ε)' },
  { index: 'FM2', icon: FlaskConical, title: 'The executability gap', body: 'Perceptual similarity (LPIPS, SSIM) says the motion looks right while commanded forces exceed torque, contact, or acceleration limits.', chip: 'F_contact = μ·F_N' },
  { index: 'FM3', icon: FlaskConical, title: 'Perceptual hallucination', body: 'Out-of-distribution inputs collapse to the nearest latent codebook vector. The reconstruction residual trips the gate before control executes.', chip: 'ALERT IF E_recon > τ' },
  { index: 'FM4', icon: FlaskConical, title: 'Action marginalization', body: 'The model plays back plausible motion while ignoring the action stream. Shuffled actions yielding identical predictions proves it.', chip: 'SHUFFLE TEST ≈ 0' },
  { index: 'FM5', icon: FlaskConical, title: 'Sim-to-real degradation', body: 'Positional divergence between simulated and physical trajectories in identical reference frames, measured as discrete Fréchet distance.', chip: 'FRÉCHET(P_sim, P_real)' },
];

const SCHOOLS = [
  { row: 'RENDERER SCHOOL', title: 'Pixel-space video models', body: 'Visual plausibility is not contact-dynamics evidence. Verify timing, action conditioning and physical constraints for the specific model and task.', badge: 'PIXELS' },
  { row: 'LATENT / JEPA SCHOOL', title: 'Latent prediction and planning', body: 'Latent rollouts can support planning. Inference speed, uncertainty and safety properties need model-specific measurements.', badge: 'LATENT STATE' },
  { row: 'SPATIAL / ENGINEERED SCHOOL', title: 'Voxels + PINN constraints', body: 'Metric geometry with conservation-law penalties. The verifiable structure behind industrial digital twins and audits.', badge: 'RUNG II' },
];

const MODULES = [
  { row: 'M1', title: 'Degradation Scorer', body: 'Sim-to-real divergence, horizon drift, action sensitivity → scorecard JSON.', badge: 'CORE' },
  { row: 'M2', title: 'Executability Guard', body: 'Action-chunk physics validation → supervisory HALT within one chunk of latency.', badge: 'CORE' },
  { row: 'M3', title: 'Bounded Verifier', body: 'Exact queries over sub-policies → PROVEN / VIOLATED / UNKNOWN certificates.', badge: 'PROOF' },
  { row: 'M4', title: 'Adversarial Engine', body: 'Seeded friction / mass / noise search → edge-case catalogue with replay refs.', badge: 'HUNT' },
  { row: 'M5', title: 'Embodiment Benchmark', body: 'Cross-robot transfer with frame checks → centered-Fréchet transfer score.', badge: 'BENCH' },
  { row: 'M6', title: 'Provenance Ledger', body: 'Run seals, dataset cards, reviews → append-only SHA-256 hash chain.', badge: 'CHAIN' },
  { row: 'M7', title: 'Compliance Mapping', body: 'Scorecards + ledger heads → regulation-mapped dossier packs + OTA vault.', badge: 'FILE' },
];

const DETERMINISM = [
  { icon: Timer, title: 'Canonical inputs', body: 'Schema validation, key sorting, unit conversion, and reference-frame pinning before anything scores.' },
  { icon: Timer, title: 'Double precision', body: 'Measurements use unrounded floating-point values. Display rounding does not change gate decisions; cross-platform reproduction requires the golden check.' },
  { icon: Timer, title: 'Seeded stochasticity', body: 'Every random operation takes an explicit, recorded seed. Same seed, same scorecard.' },
  { icon: Timer, title: 'Timestamp-free hashes', body: 'Canonical bodies exclude wall-clock time, so independent re-runs on the same platform hash byte-identically.' },
];

export default function MethodologyPage() {
  return <main id="main">
    <section className="page-hero"><div className="container"><div className="hero-kicker mono">METHOD</div><h1>How verification<br /><span>works.</span></h1><p>Layered gates on measured behavior. Bounded claims, published uncertainty, missing evidence first.</p></div></section>
    <section className="section" style={{ paddingTop: 0 }}><div className="container"><div className="method-visual"><RobotScene /><span className="mono muted">SYNTHETIC REPLAY / SAME SCENE FAMILY AS THE FAILURE LAB</span></div></div></section>
    <section className="section"><div className="container"><FailureProbe /></div></section>
    <section className="section"><div className="container"><div className="section-header"><div><span className="section-number mono">01 / FAILURE MODES</span><h2>Five ways physics<br /><span>breaks the demo.</span></h2></div><p>Every gate traces to a named failure mode with a measurement, never a vibe.</p></div>
      <div className="track-rows">{MODES.map(mode => { const Icon = mode.icon; return <article className="track-row" id={mode.index.toLowerCase()} key={mode.index}><span className="mono muted">{mode.index}</span><span className="track-icon"><Icon size={22} /></span><div><h3>{mode.title}</h3><p>{mode.body}</p></div><span className="ledger-badge">{mode.chip}</span></article>; })}</div>
    </div></section>
    <section className="section"><div className="container"><div className="section-header"><div><h2>Match the model to the measurement</h2></div><p>An architecture name does not establish causal understanding or physical validity. Record the model, task, observation and action contract.</p></div>
      <div className="evidence-ledger"><div className="ledger-heading"><Boxes size={18} /><h3>Three schools</h3><span className="mono">ARCHITECTURE / CAUSAL RUNG</span></div><div className="ledger-columns mono"><span>SCHOOL</span><span>RUNG</span></div>
        {SCHOOLS.map(school => <div className="ledger-row" key={school.row}><span><span className="mono">{school.row}</span><strong>{school.title}</strong><span className="ledger-body">{school.body}</span></span><span className="ledger-badge">{school.badge}</span></div>)}
      </div>
    </div></section>
    <section className="section"><div className="container"><div className="section-header"><div><span className="section-number mono">03 / SYNTHETIC GOVERNANCE</span><h2>Accumulate,<br /><span>then filter.</span></h2></div><p>Recursive training on uncurated synthetic data collapses variance and erases the tail events where safety lives. The fix is a law, not a hope.</p></div>
      <div className="formula-band"><GitBranch size={20} /><code className="mono">D(n+1) = α·D_real + (1−α)·&#123;x ∈ G : Verifier(x)&#125;</code><span className="mono muted">REAL RATIO α PRESERVED / EVERY SYNTHETIC SAMPLE VERIFIED</span></div>
      <RatioExperiment />
    </div></section>
    <section className="section"><div className="container"><div className="section-header"><div><span className="section-number mono">04 / ENGINE MAP</span><h2>Seven modules.<br /><span>One chain of custody.</span></h2></div><p>Local-first and air-gap-compatible: one service, one data directory, complete backup by archiving the folder.</p></div>
      <div className="evidence-ledger"><div className="ledger-heading"><FlaskConical size={18} /><h3>Module responsibilities</h3><span className="mono">M1–M7 / TYPED CORE</span></div><div className="ledger-columns mono"><span>MODULE</span><span>OUTPUT</span></div>
        {MODULES.map(module => <div className="ledger-row" key={module.row}><span><span className="mono">{module.row}</span><strong>{module.title}</strong><span className="ledger-body">{module.body}</span></span><span className="ledger-badge">{module.badge}</span></div>)}
      </div>
    </div></section>
    <section className="section"><div className="container"><div className="section-header"><div><h2>Reproducibility, with a recorded scope</h2></div><p>Inputs, profile, code version and seed are pinned. Same-platform determinism is tested; verify a second platform with the supplied golden-check tool.</p></div>
      <div className="capability-list">{DETERMINISM.map(item => { const Icon = item.icon; return <div className="capability" key={item.title}><h3><Icon size={16} style={{ verticalAlign: -3, marginRight: 8 }} />{item.title}</h3><p>{item.body}</p></div>; })}</div>
      <div className="honesty-banner mono">TASK-SPACE TRANSFER ONLY / JOINT-SPACE CROSS-EMBODIMENT REFUSED LOUDLY / RATE RESAMPLING OPEN (M5b)</div>
      <div className="honesty-banner mono">DRAFT = UNCALIBRATED / PROXY = APPROXIMATION / SYNTHETIC = GENERATED / TAMPER-EVIDENT = HASH-CHAINED</div>
      <div className="page-cta" style={{ marginTop: 40 }}><div><h2>Verify the method<br /><span>on your hardest case.</span></h2></div><div className="page-cta-actions"><PilotButton /><span className="mono muted">ONE ROBOT / ONE FAILURE MODE</span></div></div>
    </div></section>
  </main>;
}
