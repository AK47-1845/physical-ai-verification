'use client';

// /release?run=<run_id>&compare=<run_id> - release brief page.
// Query string is read from window.location (client-only) so this
// page builds under any Next output mode. Render-only: all text
// comes from the ui/release view-model route.

import { useEffect, useState } from 'react';
import ReleaseSummary from '@/components/ReleaseSummary';

function initialQuery(): { run: string; compare: string } {
  if (typeof window === 'undefined') return { run: '', compare: '' };
  const query = new URLSearchParams(window.location.search);
  return { run: query.get('run') ?? '', compare: query.get('compare') ?? '' };
}

export default function ReleasePage() {
  const [run, setRun] = useState('');
  const [compare, setCompare] = useState('');
  const [shown, setShown] = useState<{ run: string; compare: string | null } | null>(null);
  useEffect(() => {
    const query = initialQuery();
    void Promise.resolve().then(() => { setRun(query.run); setCompare(query.compare); if (query.run) setShown({ run: query.run, compare: query.compare || null }); });
  }, []);

  return <main id="main" className="section release-page"><div className="container">
    <div className="section-header"><div>
      <span className="section-number mono">RELEASE BRIEF</span>
      <h1>Release review</h1>
    </div>
      <p>Review a stored run and its per-gate changes. Missing model identity or operating scope remains explicit.</p>
    </div>
    <div className="lab-shell" style={{ marginBottom: 20 }}>
      <div className="lab-results">
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <label className="mono muted" style={{ fontSize: 10 }}>run_id
            <input value={run} onChange={e => setRun(e.target.value)}
              placeholder="run_..." style={{ display: 'block', marginTop: 4, minWidth: 220 }} />
          </label>
          <label className="mono muted" style={{ fontSize: 10 }}>compare (optional)
            <input value={compare} onChange={e => setCompare(e.target.value)}
              placeholder="run_..." style={{ display: 'block', marginTop: 4, minWidth: 220 }} />
          </label>
        </div>
        <div style={{ marginTop: 12 }}>
          <button className="button primary" disabled={!run.trim()}
            onClick={() => setShown({ run: run.trim(), compare: compare.trim() || null })}>
            Show brief</button>
        </div>
      </div>
    </div>
    {shown && <ReleaseSummary runId={shown.run} compareId={shown.compare} />}
  </div></main>;
}
