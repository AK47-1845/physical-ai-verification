'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, Send } from 'lucide-react';
import { ENDPOINTS, type Endpoint, type Preset } from '@/lib/console-endpoints';
import { downloadJson } from '@/lib/demo';
import { shortHost } from '@/lib/host';
import Workspace from './Workspace';
import { apiRequest } from '@/lib/workspace';

type PlayResult = { up: boolean; status?: number; data?: unknown; hint?: string; backendHost?: string };

function pathParams(path: string): string[] {
  return Array.from(path.matchAll(/\{(\w+)\}/g)).map(m => m[1]);
}

function fillPath(path: string, params: Record<string, string>): string {
  return path.replace(/\{(\w+)\}/g, (_, key: string) => params[key] ?? `{${key}}`);
}

function ResponseView({ result }: { result: PlayResult }) {
  if (!result.up) {
    return <p className="mono fail" role="alert">{result.hint}</p>;
  }
  const ok = result.status !== undefined && result.status >= 200 && result.status < 300;
  return <>
    <div className="mono" style={{ marginBottom: 8 }}>
      <span className={ok ? 'pass' : 'fail'}>HTTP {result.status}</span>
    </div>
    <pre className="mono" style={{ fontSize: 11, lineHeight: 1.6, maxHeight: 320, overflow: 'auto', background: '#0b0f0e', border: '1px solid var(--line)', borderRadius: 4, padding: 12, margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{JSON.stringify(result.data, null, 2)}</pre>
  </>;
}

function EndpointCard({ endpoint, online, onOffline }: { endpoint: Endpoint; online: boolean | null; onOffline: () => void }) {
  const names = useMemo(() => pathParams(endpoint.path), [endpoint.path]);
  const [presetName, setPresetName] = useState(endpoint.presets[0]?.name ?? '');
  const [bodyText, setBodyText] = useState(() =>
    endpoint.presets[0]?.body !== undefined ? JSON.stringify(endpoint.presets[0].body, null, 2) : '');
  const [params, setParams] = useState<Record<string, string>>(() => endpoint.presets[0]?.params ?? {});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PlayResult | null>(null);
  const [error, setError] = useState('');

  function pickPreset(preset: Preset) {
    setPresetName(preset.name);
    setBodyText(preset.body !== undefined ? JSON.stringify(preset.body, null, 2) : '');
    setParams(preset.params ?? {});
    setResult(null);
    setError('');
  }

  async function send() {
    setBusy(true);
    setResult(null);
    setError('');
    try {
      let payload: string | undefined;
      if (endpoint.method === 'POST') {
        try {
          payload = JSON.stringify(bodyText.trim() ? JSON.parse(bodyText) : {});
        } catch {
          setError('Request body is not valid JSON. Fix it and retry.');
          setBusy(false);
          return;
        }
      }
      const res = await fetch(`/api/play/${fillPath(endpoint.path, params)}`, {
        method: endpoint.method,
        headers: { 'content-type': 'application/json' },
        body: payload,
      });
      const data = (await res.json()) as PlayResult;
      if (!data.up) onOffline();
      setResult(data);
    } catch {
      setError('Request failed. Is the site dev server still running?');
    } finally {
      setBusy(false);
    }
  }

  return <div className="lab-shell" style={{ marginBottom: 20 }} id={`ep-${endpoint.id}`}>
    <div className="lab-topbar">
      <span className="mono"><span className="mono" style={{ border: '1px solid var(--line)', borderRadius: 3, padding: '2px 8px', marginRight: 10 }}>{endpoint.method}</span>/api/v2/{endpoint.path}</span>
      <span className="mono muted">{endpoint.group.toUpperCase()}</span>
    </div>
    <div className="lab-results">
      <p style={{ marginTop: 0 }}>{endpoint.desc}</p>
      {endpoint.prereq && <p className="mono muted" style={{ fontSize: 10 }}>PREREQ: {endpoint.prereq}</p>}
      <div className="failure-controls" style={{ border: 'none', padding: '0 0 12px' }} role="group" aria-label={`${endpoint.id} presets`}>
        {endpoint.presets.map(preset => (
          <button key={preset.name} className={`failure-choice ${presetName === preset.name ? 'selected' : ''}`} onClick={() => pickPreset(preset)} aria-pressed={presetName === preset.name}>{preset.name}</button>
        ))}
      </div>
      {names.length > 0 && <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
        {names.map(name => (
          <label key={name} className="mono muted" style={{ fontSize: 10 }}>{name}
            <input value={params[name] ?? ''} onChange={e => setParams(p => ({ ...p, [name]: e.target.value }))} placeholder={`{${name}}`} style={{ display: 'block', marginTop: 4, minWidth: 220 }} />
          </label>
        ))}
      </div>}
      {endpoint.method === 'POST' && <textarea value={bodyText} onChange={e => setBodyText(e.target.value)} rows={Math.min(14, Math.max(4, bodyText.split('\n').length))} spellCheck={false} className="mono" style={{ width: '100%', fontSize: 11, lineHeight: 1.6, background: '#0b0f0e', color: 'inherit', border: '1px solid var(--line)', borderRadius: 4, padding: 12, resize: 'vertical' }} aria-label={`${endpoint.id} request body`} />}
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 12 }}>
        <button className="button primary" onClick={() => void send()} disabled={busy || online === false}>{busy ? 'Sending...' : <><Send size={14} />Send</>}</button>
        {result?.up === true && <button className="button secondary" onClick={() => downloadJson(`verification-${endpoint.id}.json`, result.data)}>Export response</button>}
      </div>
      {error && <p className="mono fail" role="alert" style={{ marginTop: 12 }}>{error}</p>}
      {result && <div style={{ marginTop: 12 }}><ResponseView result={result} /></div>}
    </div>
  </div>;
}

function EndpointExplorer() {
  const [online, setOnline] = useState<boolean | null>(null);
  const [daysLeft, setDaysLeft] = useState<number | null>(null);
  const [host, setHost] = useState('CHECKING');

  const checkStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/play/governance');
      const data = (await res.json()) as PlayResult & { data?: { days_left?: number } };
      const up = data.up === true && data.status === 200;
      setOnline(up);
      if (typeof data.backendHost === 'string' && data.backendHost) setHost(data.backendHost);
      setDaysLeft(up && typeof data.data?.days_left === 'number' ? data.data.days_left : null);
    } catch {
      setOnline(false);
      setDaysLeft(null);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void apiRequest('governance', 'GET', undefined, controller.signal).then(response => {
      if (controller.signal.aborted) return;
      setOnline(response.up && response.status === 200);
      if (response.backendHost) setHost(response.backendHost);
    }).catch(() => undefined);
    return () => controller.abort();
  }, []);

  const groups = useMemo(() => {
    const order: string[] = [];
    for (const ep of ENDPOINTS) if (!order.includes(ep.group)) order.push(ep.group);
    return order;
  }, []);

  return <>
    <section className="page-hero"><div className="container">
      <div className="hero-kicker mono">CONSOLE</div>
      <h1>Every endpoint.<br /><span>One console.</span></h1>
      <p>All {ENDPOINTS.length} backend routes, tryable with one click: scoring, failure modes, hunts, red-team, provenance, PAR, dossiers, panel, releases, pilots, adapters. Real backend, editable requests, exportable responses.</p>
    </div></section>

    <section className="section" style={{ paddingTop: 0 }}><div className="container">
      <div className="lab-shell"><div className="lab-topbar">
        <span className="mono" title={host}>BACKEND / {shortHost(host)}</span>
        <span className="mono muted">{online === null ? 'CHECKING' : online ? `LIVE${daysLeft !== null ? ` / MACHINERY ${daysLeft}D LEFT` : ''}` : 'OFFLINE'}</span>
        <button className="icon-button" onClick={() => void checkStatus()} aria-label="Recheck backend status" title="Recheck status"><Activity size={16} /></button>
      </div>
      {online === false && <div className="lab-results"><div className="verdict-panel blocked" style={{ marginTop: 0 }}>
        <span className="mono">BACKEND OFFLINE</span><strong>Start it first.</strong>
        <p>Double-click <span className="mono">START-BACKEND.cmd</span> in this working copy, keep that window open, then press recheck. Every panel below refuses to fake results while it is down.</p>
      </div></div>}
      </div>
    </div></section>

    <section className="section" style={{ paddingTop: 0 }}><div className="container">
      <div className="failure-controls" style={{ border: '1px solid var(--line)', borderRadius: 6, marginBottom: 28 }} aria-label="Endpoint groups">
        <span className="mono muted">JUMP</span>
        {groups.map(group => <a key={group} className="failure-choice" style={{ textDecoration: 'none' }} href={`#group-${group.toLowerCase().replace(/[^a-z]+/g, '-')}`}>{group}</a>)}
      </div>
      {groups.map(group => (
        <div key={group} id={`group-${group.toLowerCase().replace(/[^a-z]+/g, '-')}`}>
          <div className="section-header"><div>
            <span className="section-number mono">{group.toUpperCase()}</span>
            <h2>{group}.<br /><span>{ENDPOINTS.filter(ep => ep.group === group).length} routes.</span></h2>
          </div></div>
          {ENDPOINTS.filter(ep => ep.group === group).map(ep => (
            <EndpointCard key={ep.id} endpoint={ep} online={online} onOffline={() => setOnline(false)} />
          ))}
        </div>
      ))}
    </div></section>
  </>;
}

export default function Playground() {
  return <Workspace advanced={<EndpointExplorer />} />;
}
