import Link from 'next/link';

export default function NotFound() {
  return (
    <main id="main">
      <section className="page-hero">
        <div className="container">
          <div className="hero-kicker mono">
            404 / NO SUCH EVIDENCE
          </div>
          <h1>
            This address
            <br />
            <span>holds nothing.</span>
          </h1>
          <p>
            The page moved, the link was mistyped, or the run was never
            recorded here. Nothing was measured at this URL, so nothing is
            claimed about it.
          </p>
        </div>
      </section>
      <section className="section">
        <div className="container">
          <div className="lab-shell">
            <div className="lab-topbar">
              <span className="mono">
                RECOVERY
              </span>
              <span className="mono muted">PICK A REAL DESTINATION</span>
            </div>
            <div
              className="lab-results"
              style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}
            >
              <Link className="button primary" href="/">
                Home
              </Link>
              <Link className="button secondary" href="/demo">
                Watch the 90-second demo
              </Link>
              <Link className="button secondary" href="/playground">
                Open the workspace
              </Link>
              <Link className="button secondary" href="/free">
                Try the Free Lab
              </Link>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
