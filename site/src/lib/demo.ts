export type Failure = 'nominal' | 'sensor' | 'scene' | 'drift';
export type GateState = 'PASS' | 'BLOCK';
export const failures: { id: Failure; name: string; short: string; explanation: string }[] = [
  { id: 'nominal', name: 'Nominal conditions', short: 'Baseline', explanation: 'All supplied observations remain inside the demonstration envelope.' },
  { id: 'sensor', name: 'Sensor dropout', short: 'Sensor dropout', explanation: 'Sensor agreement falls below 80%. The supervisory decision switches to HOLD.' },
  { id: 'scene', name: 'Adversarial scene', short: 'Perception conflict', explanation: 'A confident object detection has no independent corroboration. The perception gate blocks the run.' },
  { id: 'drift', name: 'Distribution shift', short: 'Sim-to-real drift', explanation: 'Tracking error crosses the 50 mm demonstration limit. The divergence is retained in the evidence record.' },
];

export function sampleTrace(index: number, failure: Failure = 'nominal') {
  const progress = Math.max(0, Math.min(1, index / 119));
  const angle = progress * Math.PI * 2;
  const intended: [number, number, number] = [0.5 + 0.3 * Math.sin(angle), 0.68 + 0.15 * Math.sin(angle / 2), 0.22 * Math.cos(angle)];
  const active = index >= 45;
  const drift = failure === 'drift' && active ? (progress - 0.37) * 0.24 : 0.002 + 0.001 * Math.sin(angle) ** 2;
  const observed: [number, number, number] = [intended[0] + drift, intended[1], intended[2]];
  return { index, intended, observed, drift, agreement: failure === 'sensor' && active ? 0.32 : 0.98,
    corroborated: !(failure === 'scene' && active), confidence: 0.96 };
}

export function assessDemo(failure: Failure) {
  const samples = Array.from({ length: 120 }, (_, index) => sampleTrace(index, failure));
  const maxDrift = Math.max(...samples.map(sample => sample.drift));
  const agreement = Math.min(...samples.map(sample => sample.agreement));
  const unsupported = samples.filter(sample => !sample.corroborated).length / samples.length;
  const gates: { id: string; label: string; value: number; display: string; limit: string; state: GateState }[] = [
    { id: 'tracking', label: 'Trajectory divergence', value: maxDrift, display: `${(maxDrift * 1000).toFixed(1)} mm`, limit: '< 50 mm', state: maxDrift > 0.05 ? 'BLOCK' : 'PASS' },
    { id: 'sensor', label: 'Sensor agreement', value: agreement, display: `${Math.round(agreement * 100)}%`, limit: '> 80%', state: agreement < 0.8 ? 'BLOCK' : 'PASS' },
    { id: 'perception', label: 'Unsupported perception', value: unsupported, display: `${Math.round(unsupported * 100)}%`, limit: '< 8%', state: unsupported > 0.08 ? 'BLOCK' : 'PASS' },
    { id: 'workspace', label: 'Workspace containment', value: 1, display: 'In bounds', limit: 'Task envelope', state: 'PASS' },
  ];
  const blocked = gates.some(gate => gate.state === 'BLOCK');
  return { schema: 'verification.marketing-demo/1', evidenceKind: 'synthetic', failure, samples, gates,
    verdict: blocked ? 'BLOCK' as const : 'PASS' as const, decision: blocked ? 'HOLD' : 'CONTINUE',
    passing: gates.filter(gate => gate.state === 'PASS').length, description: failures.find(item => item.id === failure)!.explanation,
    qualification: 'Deterministic browser demonstration. Draft limits. No robot executed. Not a safety certificate.' };
}

export function downloadJson(name: string, value: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}