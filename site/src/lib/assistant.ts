/* Verification guide brain. PUBLIC-SAFE ONLY: pitch content, no confidential data,
   no pricing, no customer names, no proprietary internals.
   LIVE UPDATE PROTOCOL: edit QA and CONTEXT below; the chatbot picks it up on
   the next reload (dev) or rebuild (prod). Bump KNOWLEDGE_VERSION each edit. */

import { productAnswer } from './product-guide';

export type ChatReply = { text: string; source: 'guide' | 'ai' | 'fallback' };

export const KNOWLEDGE_VERSION = '2026-10-05 curated-v3';

const QA: { keys: string[]; answer: string }[] = [
  {
    keys: ['what do you verify', 'what is verification', 'what is verify', 'about'],
    answer: 'An independent verification and validation engine for physical AI. We score robot policies and world models against evidence gates and return red, amber, or green trust scorecards with full traceability.',
  },
  {
    keys: ['scoring work', 'how does', 'score', 'gate', 'method'],
    answer: 'Upload a trajectory rollout and we score it against a versioned gate profile: drift at horizon, sim-to-real distance, action sensitivity, spread, and executability checks. Missing evidence yields INSUFFICIENT, never a pass. Worst gate decides the verdict.',
  },
  {
    keys: ['failure', 'drift', 'collapse', 'hallucinat'],
    answer: 'We test five failure modes: compounding autoregressive drift, the executability gap, perceptual hallucination, action marginalization, and sim-to-real degradation. The Failure Lab on this site demonstrates drift and playback faults live.',
  },
  {
    keys: ['regulation', 'compliance', 'eu ', 'machinery', 'certif', 'iso', 'ce '],
    answer: 'EU Machinery Regulation 2023/1230 applies mandatorily from Jan 20, 2027: ML safety components route via Annex I Part A items 5 and 6, and safety-shifting OTA updates trigger re-assessment. AI Act rows are reference mappings. Our dossiers compile scorecards and ledger evidence into auditor-shaped rows. See the Compliance page. Not legal advice.',
  },
  {
    keys: ['pilot', 'start', 'try', 'demo book', 'contact', 'talk', 'price', 'cost', 'pricing'],
    answer: 'Pilots start with one robot, one hard failure mode, and one evidence package. Click Request pilot anywhere on this site and the team replies with a scoped plan. Pricing is scoped per pilot, no public tiers yet.',
  },
  {
    keys: ['who', 'customer', 'insurer', 'oem', 'tic'],
    answer: 'Built for validation engineers at robot OEMs, insurers pricing physical-AI liability, and auditors compiling technical files. First money flows through insurer-recognised evidence sold to OEMs and operators.',
  },
  {
    keys: ['synthetic', 'data', 'dataset', 'provenance', 'ledger'],
    answer: 'Every dataset gets a machine-readable card: generator version, verifier, pass rate, and real-vs-synthetic counts. Ratio enforcement blocks silent drift toward synthetic-only training, which is how model collapse starts.',
  },
  {
    keys: ['world model', 'vla', 'policy', 'robot', 'humanoid'],
    answer: 'We verify neural policies and world models across embodiments: manipulators, humanoids, and autonomous systems. Same-frame, same-units comparison with explicit coordinate frames on every result.',
  },
  {
    keys: ['use case', 'track', 'tier', 'who is this for', 'page', 'section'],
    answer: 'Three verification tracks: humanoid pilots in fenced deployments, VLA release gates for every OTA update, and insurer-shaped evidence. Start with Tier 2 bounded pilots and earn the fence line. See the Use Cases page.',
  },
  {
    keys: ['par', 'assurance record', 'schema', 'reader', 'dossier'],
    answer: 'The Policy Assurance Record is our unit of trust: policy, release delta, per-gate verdicts, ledger head, and independence register. Open JSON Schema plus an offline reader CLI that recomputes every hash with no network. See the Evidence page.',
  },
  {
    keys: ['taxonomy', 'school', 'renderer', 'jepa', 'failure mode', 'fm1', 'engine map', 'module'],
    answer: 'Method in brief: five failure modes (drift, executability gap, hallucination, action marginalization, sim-to-real Fréchet), three world-model schools scored by causal rung, and seven engine modules M1-M7 from scorer to dossier file. See the Methodology page.',
  },
  {
    keys: ['determinism', 'seed', 'reproduc', 'credibility card', 'held-out'],
    answer: 'Same inputs plus same seed equals the same scorecard on any machine: canonical inputs, f64 math, seeded stochasticity, timestamp-free hashes. Every gate carries a credibility card, and DRAFT never lifts without one. See Evidence and Methodology.',
  },
  {
    keys: ['hello', 'hi', 'hey', 'thanks', 'thank'],
    answer: 'Hello. Ask me about verification, scoring, compliance, or starting a pilot.',
  },
];

export function offlineAnswer(question: string): string | null {
  const q = question.toLowerCase();
  let best: { score: number; answer: string } | null = null;
  for (const entry of QA) {
    let score = 0;
    for (const key of entry.keys) if (q.includes(key)) score += key.length;
    if (score > 0 && (!best || score > best.score)) best = { score, answer: entry.answer };
  }
  return best ? best.answer : null;
}

export async function askAssistant(question: string): Promise<ChatReply> {
  return productAnswer(question);
}
