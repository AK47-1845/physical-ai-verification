"""FR-19 human HTML report: offline-readable evidence export.

Renders a PAR envelope (+ optional pinned scorecard) into ONE
self-contained HTML string: no external assets, no JS, no network.
Every interpolated value is html-escaped. Cross-linked by content
hash (par_hash, scorecard inputs_hash when attached, html_hash of
the finished document). Strict: an invalid PAR raises ReportError;
there is no human report on bad evidence.
"""

import html

from engine import InputError, sha256_hex
from engine.par import validate_par


class ReportError(InputError):
    """Refusals. A report on bad evidence is worse than none."""


_COLORS = {"PASS": "green", "REVIEW": "#b58900", "BLOCKED": "red",
           "INSUFFICIENT": "grey"}


def _esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _scorecard_block(scorecard) -> str:
    if scorecard is None:
        return "<p>Scorecard: not attached.</p>"
    if not isinstance(scorecard, dict):
        raise ReportError("scorecard: pinned envelope dict or None")
    payload = scorecard.get("payload")
    inputs_hash = scorecard.get("inputs_hash")
    if (not isinstance(payload, dict)
            or not isinstance(inputs_hash, str) or not inputs_hash):
        raise ReportError("scorecard: need payload dict + inputs_hash")
    verdict = payload.get("verdict", "?")
    gates = payload.get("gates", [])
    if not isinstance(gates, list):
        raise ReportError("scorecard.payload.gates: list required")
    rows = []
    for gate in gates:
        if not isinstance(gate, dict):
            raise ReportError("scorecard gate: dict required")
        rows.append(
            f"<tr><td>{_esc(gate.get('gate', '?'))}</td>"
            f"<td>{_esc(gate.get('status', '?'))}</td>"
            f"<td>{_esc(gate.get('measurement', 'n/a'))}</td>"
            f"<td>{_esc(gate.get('evidence', ''))}</td></tr>")
    return (f"<p>Scorecard verdict: <b>{_esc(verdict)}</b> "
            f"(inputs {_esc(inputs_hash[:16])}...)</p>"
            f"<table border='1'><tr><th>gate</th><th>status</th>"
            f"<th>measurement</th><th>evidence</th></tr>"
            + "".join(rows) + "</table>")


def render_report_html(par_envelope: dict, *, scorecard=None,
                       title: str = "Physical AI Verification evidence report"
                       ) -> dict:
    """Render a PAR to standalone HTML. Returns html + hashes."""
    if not isinstance(title, str) or not title:
        raise ReportError("title: non-empty string required")
    check = validate_par(par_envelope)
    if not check["ok"]:
        raise ReportError(f"cannot report on invalid PAR: "
                          f"{check['reason']}")
    try:
        body = par_envelope["par"]
        policy = body["policy"]
        release = body["release"]
        gates = body["gates"]
        indep = body["independence"]
        head = body["ledger_head"]
        gate_rows = []
        for gate in gates:
            color = _COLORS.get(gate["verdict"], "black")
            measure = ("n/a" if gate.get("measurement") is None
                       else gate["measurement"])
            gate_rows.append(
                f"<tr><td>{_esc(gate['id'])}</td>"
                f"<td style='color:{color}'><b>{_esc(gate['verdict'])}"
                f"</b></td><td>{_esc(measure)}</td>"
                f"<td>{_esc(gate.get('evidence', ''))}</td></tr>")
        worksheet = body.get("worksheet")
        ws_block = "<p>Worksheet: not attached.</p>"
        if worksheet is not None:
            ws_block = (f"<p>Worksheet route: "
                        f"{_esc(worksheet.get('implied_route', '?'))}<br>"
                        f"{_esc(worksheet.get('banner', ''))}</p>")
        cred = body.get("credibility")
        cred_block = "<p>Credibility cards: not attached.</p>"
        if cred is not None:
            cred_block = (f"<p>Credibility attachments present: "
                          f"{_esc(len(cred) if isinstance(cred, dict) else '?')}"
                          f" field(s).</p>")
    except (KeyError, TypeError, IndexError) as exc:
        raise ReportError(f"PAR body incomplete: {exc}") from exc
    doc = (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>{_esc(title)}</title></head><body>"
        f"<h1>{_esc(title)}</h1>"
        f"<p>Policy: <b>{_esc(policy['id'])}</b><br>"
        f"Weights: {_esc(policy['weights'])}<br>"
        f"Release delta: <b>{_esc(release['delta'])}</b><br>"
        f"Ledger head: {_esc(head)}<br>"
        f"PAR hash: {_esc(par_envelope['par_hash'])}</p>"
        f"<h2>Gates ({check['gates']} scored, {check['blocked']} BLOCKED)"
        f"</h2><table border='1'><tr><th>gate</th><th>verdict</th>"
        f"<th>measurement</th><th>evidence</th></tr>"
        + "".join(gate_rows) + "</table>"
        f"<h2>Independence register</h2><p>Builder: "
        f"{_esc(indep['builder'])}<br>Funder: {_esc(indep['funder'])}"
        f"<br>Relationship: {_esc(indep['relationship'])}</p>"
        f"<h2>Applicability</h2>{ws_block}"
        f"<h2>Credibility</h2>{cred_block}"
        f"<h2>Scorecard</h2>{_scorecard_block(scorecard)}"
        f"<p><i>Standalone export. Verify offline: recompute sha256 of "
        f"this file and compare html_hash below.</i></p>"
        "</body></html>")
    return {"html": doc, "html_hash": sha256_hex(doc),
            "par_hash": par_envelope["par_hash"],
            "gates": check["gates"], "blocked": check["blocked"]}
