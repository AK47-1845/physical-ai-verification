export const DEMO_DURATION = 90;
export const DEMO_CHAPTERS = [
  { start: 0, end: 8, name: 'The question', title: ['Every release', 'needs evidence.'], lead: 'A neural policy is not a safety case. Start with behavior you can measure.', caption: 'Nothing has been measured yet. The run opens with a declared reference path and a draft gate profile.' },
  { start: 8, end: 20, name: 'The release', title: ['An update changes', 'the question.'], lead: 'A previous result covers a previous scope. Compare behavior again before a deployment decision.', caption: 'Two stored runs, each carrying its own identifier: one reference, one candidate.' },
  { start: 20, end: 38, name: 'The boundary', title: ['Find the boundary.', 'Keep the trace.'], lead: 'Two synthetic traces. The same draft profile. One remains within its gates; one crosses the boundary.', caption: 'The candidate crosses the 0.5 m draft screening boundary. Its scorecard reads BLOCKED on final tracking error.' },
  { start: 38, end: 55, name: 'The hunt', title: ['Look for the break.', 'Keep every trial.'], lead: 'Sixteen seeded trials on a fixture policy. A completed search, replayed here with both breaks and holds.', caption: 'Every trial is retained and replayable. A search can find a counterexample; it cannot prove none remain.' },
  { start: 55, end: 72, name: 'The record', title: ['Make the evidence', 'checkable.'], lead: 'A Policy Assurance Record links findings, scope and declared relationships. Recompute its hashes independently.', caption: 'The record carries its own SHA256. A hash establishes integrity, not authorship: these records stay UNSIGNED.' },
  { start: 72, end: 82, name: 'The boundary of our role', title: ['Diagnose.', 'Never auto-fix.'], lead: 'The engine does not train or tune the submitted policy. It exposes findings. A human retains the decision.', caption: 'Builder, funder and relationship are declared on the record itself, beside the measurements.' },
  { start: 82, end: 90, name: 'Your next trace', title: ['Physical AI.', 'Physical evidence.'], lead: 'One trace. One explainable result. An evidence trail you can take apart.', caption: 'Screening on declared traces, under draft thresholds. Human review is still required.' },
] as const;

export function chapterAt(seconds: number): number {
  if (!Number.isFinite(seconds)) return 0;
  const bounded = Math.max(0, Math.min(DEMO_DURATION, seconds));
  return DEMO_CHAPTERS.findIndex(chapter => bounded < chapter.end) < 0 ? DEMO_CHAPTERS.length - 1 : DEMO_CHAPTERS.findIndex(chapter => bounded < chapter.end);
}

export function demoTime(seconds: number): string {
  const bounded = Math.floor(Math.max(0, Math.min(DEMO_DURATION, seconds)));
  return `${Math.floor(bounded / 60)}:${String(bounded % 60).padStart(2, '0')}`;
}