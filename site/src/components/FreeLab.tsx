'use client';

import { useEffect, useRef, useState } from 'react';
import { Activity, ArrowDownToLine, ArrowRight, Braces, Check, ChevronRight, Copy, FileJson2, Flag, FlaskConical, GitCompareArrows, KeyRound, LoaderCircle, Play, Plus, Radar, Share2, ShieldQuestion, Trophy, Upload, X } from 'lucide-react';
import { apiError, apiRequest, formatValue, GATE_INFO, MAX_UPLOAD_BYTES, parseTrace, passBoundary, record, resultSummary, SAMPLES, text, type ApiResult, type TracePair } from '@/lib/workspace';
import { downloadJson } from '@/lib/demo';
import { EvidenceChip, GateInspector, ReadableResult, TracePlot, VerdictBadge } from './EvidenceViews';

type LabView = 'verify' | 'hunt' | 'duel' | 'atlas' | 'board' | 'api';
const VIEWS = [
  { id: 'verify', name: 'Trace check', icon: Activity }, { id: 'hunt', name: 'Weekly hunt', icon: Radar },
  { id: 'duel', name: 'Drift duel', icon: GitCompareArrows }, { id: 'atlas', name: 'Failure atlas', icon: FlaskConical },
  { id: 'board', name: 'Public board', icon: Trophy }, { id: 'api', name: 'API', icon: Braces },
] as const;
const MODES = [
  { id: 'fm1', name: 'Long-horizon drift', question: 'Where does tracking stop holding?', requirement: 'Reference + observed trajectory', label: 'DRAFT' },
  { id: 'fm2', name: 'Executability', question: 'Does the motion violate a declared envelope?', requirement: 'Task-space jerk and bounds only', label: 'PROXY' },
  { id: 'fm3', name: 'Reconstruction residual', question: 'What did the model fail to reconstruct?', requirement: 'Toy encode/decode fixture; custom models are library-only', label: 'SYNTHETIC' },
  { id: 'fm4', name: 'Action sensitivity', question: 'Is the policy listening to its actions?', requirement: 'Toy callable policy; a trace alone cannot establish this', label: 'SYNTHETIC' },
  { id: 'fm5', name: 'Path divergence', question: 'How far apart are comparable paths?', requirement: 'Same-frame, same-unit trajectories', label: 'DRAFT' },
] as const;

async function trophyImage(data: unknown, name: string, label: string, theme: string) {
  const result = resultSummary(data);
  const canvas = document.createElement('canvas');
  canvas.width = 1200; canvas.height = 630;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Image export is unavailable in this browser. Export the JSON artifact instead.');
  await document.fonts.ready;
  const paper = theme === 'paper';
  const ground = paper ? '#eef1ed' : theme === 'blueprint' ? '#122b2a' : '#0c1011';
  const ink = paper ? '#142124' : '#eef1ed';
  const muted = paper ? '#4d6257' : '#a4b9ac';
  const signal = result.verdict === 'BLOCKED' ? paper ? '#a3422b' : '#ffa18b' : paper ? '#38713b' : '#bfdea1';
  context.fillStyle = ground; context.fillRect(0, 0, 1200, 630);
  context.strokeStyle = paper ? '#c5d1c6' : '#2f493c'; context.lineWidth = 1;
  for (let position = 0; position < 1200; position += 48) { context.beginPath(); context.moveTo(position, 0); context.lineTo(position, 630); context.stroke(); }
  for (let position = 0; position < 630; position += 48) { context.beginPath(); context.moveTo(0, position); context.lineTo(1200, position); context.stroke(); }
  context.fillStyle = ground; context.fillRect(40, 35, 1120, 555);
  context.fillStyle = muted; context.font = '17px sans-serif'; context.fillText('VERIFICATION / FREE LAB', 72, 88);
  context.fillStyle = ink; context.font = '36px sans-serif'; context.fillText(name.slice(0, 44), 72, 159, 1050);
  context.fillStyle = signal; context.font = '80px sans-serif'; context.fillText(result.verdict, 66, 267);
  context.fillStyle = muted; context.font = '18px sans-serif'; context.fillText(`${label}  /  DRAFT THRESHOLDS  /  SCREENING ONLY`, 72, 313, 1050);
  result.gates.slice(0, 3).forEach((gate, index) => {
    const offset = 72 + index * 353;
    context.fillStyle = muted; context.font = '15px sans-serif'; context.fillText(GATE_INFO[gate.gate]?.name ?? gate.gate, offset, 393);
    context.fillStyle = ink; context.font = '38px monospace'; context.fillText(formatValue(gate.measurement, 4), offset, 445);
  });
  context.fillStyle = muted; context.font = '15px sans-serif'; context.fillText('A result on declared traces, not a hardware safety assessment.', 72, 510);
  context.fillStyle = ink; context.font = '17px sans-serif'; context.fillText(`${window.location.host}/free`, 72, 554, 1050);
  const blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob(value => value ? resolve(value) : reject(new Error('Image export failed.')), 'image/png'));
  const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = `verification-${theme}-evidence.png`; anchor.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function FreeLab() {
  const [view, setView] = useState<LabView>('verify');
  const [sample, setSample] = useState('clean');
  const [pair, setPair] = useState<TracePair>(SAMPLES[0]);
  const [inputLabel, setInputLabel] = useState('SYNTHETIC');
  const [score, setScore] = useState<unknown>(null);
  const [selectedGate, setSelectedGate] = useState('drift_final');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [online, setOnline] = useState<boolean | null>(null);
  const [shareConsent, setShareConsent] = useState(false);
  const [benchmarkConsent, setBenchmarkConsent] = useState(false);
  const [boardConsent, setBoardConsent] = useState(false);
  const [theme, setTheme] = useState('signal');
  const [shareUrl, setShareUrl] = useState('');
  const [board, setBoard] = useState<unknown[]>([]);
  const [challenge, setChallenge] = useState<unknown>(null);
  const [trialResult, setTrialResult] = useState<unknown>(null);
  const [bias, setBias] = useState(0.25);
  const [noise, setNoise] = useState(0.5);
  const [duelLeft, setDuelLeft] = useState('clean');
  const [duelRight, setDuelRight] = useState('drifty');
  const [customDuel, setCustomDuel] = useState<Partial<Record<'left' | 'right', TracePair>>>({});
  const [duel, setDuel] = useState<unknown>(null);
  const [atlas, setAtlas] = useState('fm1');
  const [atlasResult, setAtlasResult] = useState<unknown>(null);
  const [apiKey, setApiKey] = useState('');
  const [keyInfo, setKeyInfo] = useState<unknown>(null);
  const [recipe, setRecipe] = useState('score');
  const [apiResult, setApiResult] = useState<unknown>(null);
  const [onboarding, setOnboarding] = useState(false);
  const [onboardingStep, setOnboardingStep] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);
  const duelFileRef = useRef<HTMLInputElement>(null);
  const duelSide = useRef<'left' | 'right'>('left');
  const keyRef = useRef('');
  const summary = resultSummary(score);

  useEffect(() => {
    const controller = new AbortController();
    void apiRequest('governance', 'GET', undefined, controller.signal).then(response => {
      if (controller.signal.aborted) return;
      setOnline(response.up && response.status === 200);
      try { const key = sessionStorage.getItem('verification-free-key') ?? ''; keyRef.current = key; setApiKey(key); if (!localStorage.getItem('verification-lab-intro')) setOnboarding(true); } catch { setStatus('Browser storage is unavailable; this session still works in memory.'); }
    }).catch(() => undefined);
    void apiRequest('lab/board', 'GET', undefined, controller.signal).then(response => { const entries = record(response.data).entries; if (Array.isArray(entries) && !controller.signal.aborted) setBoard(entries); }).catch(() => undefined);
    return () => controller.abort();
  }, []);

  function accept(response: ApiResult) { setOnline(response.up); if (!response.up || response.status >= 400) throw new Error(apiError(response)); return response.data; }
  async function operation(name: string, action: () => Promise<void>) {
    if (busy) return;
    setBusy(name); setError(''); setStatus('');
    try { await action(); } catch (failure) { setError(failure instanceof Error ? failure.message : 'The operation did not complete. No result was inferred.'); } finally { setBusy(''); }
  }

  async function labRequest(path: string, method = 'GET', body?: unknown) {
    const request = body === undefined ? undefined : { ...record(body), ...(keyRef.current ? { api_key: keyRef.current } : {}) };
    return accept(await apiRequest(`lab/${path}`, method, request));
  }

  async function ensureKey() {
    if (keyRef.current) return keyRef.current;
    const issued = await labRequest('keys', 'POST', {});
    const token = text(record(issued).key);
    if (!token) throw new Error('The backend did not issue a demo key.');
    keyRef.current = token; setApiKey(token); setKeyInfo(issued);
    try { sessionStorage.setItem('verification-free-key', token); } catch { setStatus('Demo key is available in memory only.'); }
    return token;
  }

  function scoreBody() { return sample === 'uploaded' ? { pair, label: 'USER_SUPPLIED' } : { sample_id: sample }; }

  async function evaluate() {
    const data = await labRequest('score', 'POST', scoreBody());
    setScore(data); setShareUrl(''); setShareConsent(false); setBenchmarkConsent(false); setBoardConsent(false);
    const result = resultSummary(data); setSelectedGate(result.gates.find(gate => gate.status === 'BLOCKED')?.gate ?? 'drift_final');
  }

  async function readUpload(file?: File): Promise<TracePair | null> {
    if (!file) return null;
    if (file.size > MAX_UPLOAD_BYTES) throw new Error('File exceeds 256 KB. Keep the free trace within 512 samples.');
    const source = await file.text();
    if (file.name.toLowerCase().endsWith('.csv')) return record(await labRequest('parse', 'POST', { csv: source })).pair as TracePair;
    return parseTrace(source);
  }

  async function publish() {
    await ensureKey();
    const data = record(await labRequest('share', 'POST', { ...scoreBody(), consent_share: shareConsent, consent_benchmark: benchmarkConsent, consent_board: boardConsent, contributor_terms: benchmarkConsent ? 'v1' : undefined, embodiment: 'task-space', task: 'reach' }));
    const id = text(data.id);
    if (!id) throw new Error('A share link was not returned.');
    const url = `${window.location.origin}/share?id=${encodeURIComponent(id)}`;
    setShareUrl(url); setStatus('Public artifact created. The result is visible to anyone with this link.');
    const response = record(await labRequest('board')); if (Array.isArray(response.entries)) setBoard(response.entries);
  }

  async function loadChallenge() { const data = await labRequest('challenge'); setChallenge(data); }
  async function challengeTrial() { await ensureKey(); const result = await labRequest('challenge/trial', 'POST', { bias, noise_scale: noise }); setTrialResult(result); await loadChallenge(); }
  function selectView(next: LabView) { setView(next); setError(''); setStatus(''); if (next === 'hunt') void operation('challenge', loadChallenge); if (next === 'board') void operation('board', async () => { const result = record(await labRequest('board')); if (Array.isArray(result.entries)) setBoard(result.entries); }); }
  function dismissOnboarding() { setOnboarding(false); try { localStorage.setItem('verification-lab-intro', 'seen'); } catch { setStatus('Introduction preference could not be retained in this browser.'); } }
  const leftPair = customDuel.left ?? SAMPLES.find(item => item.id === duelLeft)!;
  const rightPair = customDuel.right ?? SAMPLES.find(item => item.id === duelRight)!;
  const challengeInfo = record(challenge);
  const challengeState = record(trialResult);
  const currentMode = MODES.find(item => item.id === atlas)!;
  const recipePaths: Record<string, string> = { score: 'score', hunt: 'challenge/trial', ledger: 'ledger', par: 'par', rank: 'board' };
  const recipeBody = recipe === 'score' ? { sample_id: 'clean' } : recipe === 'hunt' ? { bias: 0.5, noise_scale: 1 } : {};
  const curl = `curl -X ${recipe === 'rank' || recipe === 'ledger' ? 'GET' : 'POST'} "$BACKEND_URL/api/lab/v1/${recipePaths[recipe]}" \\\n  -H "Content-Type: application/json" \\\n  -H "Authorization: Bearer $VERIFICATION_FREE_KEY"${recipe === 'rank' || recipe === 'ledger' ? '' : ` \\\n  -d '${JSON.stringify(recipeBody)}'`}`;

  return <main id="main" className="free-lab-page">
    <header className="free-lab-heading"><div><h1>Free Lab<span className="free-lab-mark"><FlaskConical size={21} /></span></h1><p>Bring a trace. Find the failure. Keep the evidence.</p></div><div className="free-lab-limits"><span>Free for individuals. No card.</span><small>512 samples / 256 KB / 50 challenge trials</small><EvidenceChip tone={online ? 'signal' : 'review'}>{online === null ? 'CONNECTING' : online ? 'ENGINE CONNECTED' : 'ENGINE UNAVAILABLE'}</EvidenceChip></div></header>
    <nav className="lab-view-tabs" aria-label="Free Lab views">{VIEWS.map(item => <button key={item.id} aria-pressed={view === item.id} className={view === item.id ? 'active' : ''} onClick={() => selectView(item.id)}><item.icon size={16} />{item.name}</button>)}</nav>
    <div className="free-lab-notice"><ShieldQuestion size={15} /><span>Screening, not certification. DRAFT gates. Nothing uploaded is retained for benchmarks without opt-in.</span></div>
    {error && <div className="workspace-error" role="alert"><ShieldQuestion size={20} /><div><strong>Not completed</strong><p>{error}</p><span>No passing result was inferred.</span></div></div>}
    {status && <p className="lab-status" role="status">{status}</p>}
    {view === 'verify' && <section className="free-verifier" aria-label="Trace verifier"><div className="free-input"><div className="instrument-heading"><h2>Check your trace</h2><span>Anonymous first run</span></div><input type="file" ref={fileRef} hidden accept=".json,.csv,application/json,text/csv" onChange={event => { const file = event.target.files?.[0]; void operation('upload', async () => { const parsed = await readUpload(file); if (parsed) { setPair({ ...parsed, name: file?.name }); setSample('uploaded'); setInputLabel('USER-SUPPLIED'); setScore(null); } }); event.target.value = ''; }} /><button className="trace-dropzone" onClick={() => fileRef.current?.click()} onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); const file = event.dataTransfer.files[0]; void operation('upload', async () => { const parsed = await readUpload(file); if (parsed) { setPair({ ...parsed, name: file.name }); setSample('uploaded'); setInputLabel('USER-SUPPLIED'); setScore(null); } }); }}><Upload size={26} strokeWidth={1.4} /><strong>{sample === 'uploaded' ? pair.name : 'Drop a trace, or choose a file'}</strong><span>JSON or CSV / metres / one shared frame</span></button><div className="free-samples"><span>Or start with a synthetic example</span><div>{SAMPLES.map(item => <button key={item.id} className={sample === item.id ? 'active' : ''} aria-pressed={sample === item.id} onClick={() => { setPair(item); setSample(item.id); setInputLabel('SYNTHETIC'); setScore(null); setShareUrl(''); }}><Activity size={14} />{item.name}</button>)}</div></div><div className="free-input-footer"><span className="mono">{pair.intended.length} samples / {pair.units} / {pair.frame_id}</span><button className="button primary" disabled={Boolean(busy)} onClick={() => void operation('score', evaluate)}>{busy === 'score' ? <LoaderCircle size={16} className="is-spinning" /> : <Play size={15} />}Check trace</button></div><details className="trace-schema"><summary>Trace schema and sample file <ChevronRight size={13} /></summary><code>{'{ "units": "m", "frame_id": "world", "intended": [[0,0],[1,0]], "observed": [[0,0],[1,0.1]] }'}</code><p>CSV columns: ref_x, ref_y, obs_x, obs_y, units, frame_id. Every row declares the same scope. No silent resampling.</p><button className="text-action" onClick={() => downloadJson('verification-trace-template.json', SAMPLES[0])}>Download JSON sample <ArrowDownToLine size={14} /></button></details><div className="free-privacy"><Check size={14} /><span>Scoring is transient. Public sharing is a separate action.</span></div></div>
      <div className="free-output"><div className="free-output-heading"><div><span className="mono">{inputLabel}</span><h2>{score !== null ? summary.verdict === 'BLOCKED' ? 'A boundary worth finding.' : 'Your evidence is ready.' : 'Your trace, under the lens.'}</h2></div>{score !== null && <VerdictBadge verdict={summary.verdict} />}</div><TracePlot pair={pair} compact selectedGate={selectedGate} />{score !== null ? <GateInspector gates={summary.gates} selected={selectedGate} onSelect={setSelectedGate} sampleCount={pair.intended.length} /> : <div className="free-waiting"><span>No verdict yet. These four gates will be measured against profile draft-0.</span><div className="empty-gates">{Object.entries(GATE_INFO).map(([id, info]) => <span key={id}><span className="gate-dot" />{info.name}<span className="mono">{passBoundary(id)}</span></span>)}</div></div>}</div>
      {score !== null && <div className="free-export-area"><div className="free-trophy-options"><h3>Take the evidence with you.</h3><p>Three image styles. The same qualification.</p><div className="trophy-themes" role="group" aria-label="Evidence card style">{['signal', 'paper', 'blueprint'].map(value => <button key={value} aria-label={`${value} card style`} title={`${value} card style`} aria-pressed={theme === value} className={`${value} ${theme === value ? 'selected' : ''}`} onClick={() => setTheme(value)}><span /><Check size={12} /></button>)}</div><div className="toolbar-actions"><button className="button secondary" onClick={() => void operation('trophy', async () => trophyImage(score, pair.name || 'Trace screening', inputLabel, theme))}><ArrowDownToLine size={15} />Evidence PNG</button><button className="button secondary" onClick={() => downloadJson('verification-free-score.json', score)}><FileJson2 size={15} />JSON</button></div></div><div className="free-share-consent"><h3>Share deliberately.</h3><label><input type="checkbox" checked={shareConsent} onChange={event => setShareConsent(event.target.checked)} /><span>Publish the scorecard and declared scope at an unlisted link. No raw trace in the public artifact.</span></label><label><input type="checkbox" checked={boardConsent} disabled={!shareConsent} onChange={event => setBoardConsent(event.target.checked)} /><span>Also show the result on the public board.</span></label><label><input type="checkbox" checked={benchmarkConsent} onChange={event => setBenchmarkConsent(event.target.checked)} /><span>Help public benchmarks: retain my traces under the <a href="/contribute">contributor terms</a>. Optional; off by default.</span></label><button className="button primary" disabled={!shareConsent || Boolean(busy)} onClick={() => void operation('share', publish)}><Share2 size={15} />Create share link</button><small>BETA: anonymous demo key, not a verified email account. Links expire after seven days on this demo store.</small>{shareUrl && <a className="generated-share-link" href={shareUrl}>{shareUrl}<ArrowRight size={14} /></a>}</div></div>}
    </section>}
    {view === 'hunt' && <section className="weekly-hunt"><div className="lab-section-title"><div><h2>This week, find the break.</h2><p>A hidden fixture seed. At most 50 attempts per demo key. Reset Monday, 00:00 UTC.</p></div><EvidenceChip>SYNTHETIC CHALLENGE</EvidenceChip></div><div className="challenge-layout"><div className="challenge-control"><div className="challenge-count"><strong>{typeof challengeState.attempts === 'number' ? challengeState.attempts : 0}</strong><span>/ 50 attempts</span></div><label>Command bias <b className="mono">{bias.toFixed(2)}</b><input type="range" min="0" max="1.5" step="0.05" value={bias} onChange={event => setBias(Number(event.target.value))} /></label><label>Noise scale <b className="mono">{noise.toFixed(2)}</b><input type="range" min="0" max="2" step="0.05" value={noise} onChange={event => setNoise(Number(event.target.value))} /></label><button className="button primary" disabled={Boolean(busy)} onClick={() => void operation('trial', challengeTrial)}>{busy === 'trial' ? <LoaderCircle className="is-spinning" size={16} /> : <Radar size={16} />}Test this disturbance</button><div className="challenge-commit"><span className="mono">COMMITTED BEFORE THE FIRST TRIAL</span><code>{text(challengeInfo.commitment, 'Loading commitment...')}</code><span>Seed stays private until this week closes.</span></div></div><div className="challenge-outcome">{trialResult ? <><VerdictBadge verdict={challengeState.breaks ? 'BLOCKED' : 'REVIEW'} /><h3>{challengeState.breaks ? 'You found a counterexample.' : 'This disturbance held.'}</h3><p>{challengeState.breaks ? 'The measured fixture crossed the screening boundary. Its parameters are retained in your result.' : 'No break in this attempt. That does not establish global safety.'}</p><ReadableResult data={trialResult} /><button className="button secondary" onClick={() => downloadJson('weekly-hunt-trial.json', trialResult)}><ArrowDownToLine size={15} />Trial receipt</button>{challengeState.breaks === true && <button className="button secondary" disabled={Boolean(busy)} onClick={() => void operation('publish-winner', async () => { await labRequest('challenge/publish', 'POST', { consent_public: true }); setStatus('Structured challenge result published. No free text or identity is displayed.'); })}><Flag size={15} />Publish this challenge result</button>}</> : <><Radar size={66} strokeWidth={1} /><h3>Small disturbance.<br />Big question.</h3><p>One seed commitment. Every attempt counted by the server. No seed-peeking endpoint for an open week.</p></>}</div></div><div className="challenge-board"><h3>Week {text(challengeInfo.week, 'loading')}</h3>{Array.isArray(challengeInfo.winners) && challengeInfo.winners.length ? <ReadableResult data={{ published_results: challengeInfo.winners.length }} /> : <p>No public results for this week yet.</p>}<button className="text-action" onClick={() => void operation('reveal', async () => { const result = await labRequest(`challenge/reveal?week=${encodeURIComponent(text(challengeInfo.week))}`); downloadJson('challenge-reveal.json', result); })}>Request reveal receipt <FingerprintIcon /></button></div></section>}
    {view === 'duel' && <section className="drift-duel"><div className="lab-section-title"><div><h2>Same horizon. Two stories.</h2><p>Compare traces without blending success into a safety score.</p></div><button className="button primary" disabled={Boolean(busy)} onClick={() => void operation('duel', async () => { const result = await labRequest('duel', 'POST', { left: { pair: leftPair, label: customDuel.left ? 'USER_SUPPLIED' : 'SYNTHETIC' }, right: { pair: rightPair, label: customDuel.right ? 'USER_SUPPLIED' : 'SYNTHETIC' } }); setDuel(result); })}><Play size={15} />Run duel</button></div><input type="file" accept=".json,application/json" hidden ref={duelFileRef} onChange={event => { const file = event.target.files?.[0]; const side = duelSide.current; void operation('duel-upload', async () => { const parsed = await readUpload(file); if (parsed) { setCustomDuel(previous => ({ ...previous, [side]: parsed })); setDuel(null); } }); event.target.value = ''; }} /><div className="duel-lanes">{(['left', 'right'] as const).map((side, index) => { const currentPair = side === 'left' ? leftPair : rightPair; const scored = record(duel)[side]; return <div className="duel-lane" key={side}><div className="duel-lane-title"><span className="mono">{index === 0 ? 'A' : 'B'}</span><select aria-label={`Duel ${side} trace`} value={customDuel[side] ? 'uploaded' : side === 'left' ? duelLeft : duelRight} onChange={event => { setCustomDuel(previous => ({ ...previous, [side]: undefined })); (side === 'left' ? setDuelLeft : setDuelRight)(event.target.value); setDuel(null); }}>{customDuel[side] && <option value="uploaded">Uploaded trace</option>}{SAMPLES.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select><button className="icon-button" aria-label={`Upload ${side} duel trace`} title={`Upload ${side} trace`} onClick={() => { duelSide.current = side; duelFileRef.current?.click(); }}><Upload size={15} /></button></div><EvidenceChip>{customDuel[side] ? 'USER-SUPPLIED' : 'SYNTHETIC'}</EvidenceChip><TracePlot pair={currentPair} /><div className="duel-outcome">{scored ? <><VerdictBadge verdict={resultSummary(scored).verdict} /><strong>{formatValue(resultSummary(scored).gates.find(gate => gate.gate === 'drift_final')?.measurement)} <small>m final error</small></strong></> : <span>Awaiting evaluation</span>}</div></div>; })}</div>{duel !== null && <div className="duel-caption"><p>{text(record(duel).caption)}</p><button className="button secondary" onClick={() => downloadJson('verification-drift-duel.json', duel)}><ArrowDownToLine size={15} />Duel receipt</button><button className="button secondary" disabled={Boolean(busy)} onClick={() => void operation('share-duel', async () => { await ensureKey(); const result = record(await labRequest('duel/share', 'POST', { left: { pair: leftPair }, right: { pair: rightPair }, consent_share: true })); setShareUrl(`${window.location.origin}/share?id=${encodeURIComponent(text(result.id))}`); })}><Share2 size={15} />Publish result-only link</button>{shareUrl && <a href={shareUrl}>Open result <ArrowRight size={14} /></a>}</div>}</section>}
    {view === 'atlas' && <section className="failure-atlas"><div className="lab-section-title"><div><h2>Five ways behavior can fail.</h2><p>Measurements first. Diagnosis stays within the available evidence.</p></div><EvidenceChip>NO AUTO-FIXES</EvidenceChip></div><div className="atlas-layout"><nav aria-label="Failure modes">{MODES.map((item, index) => <button key={item.id} className={atlas === item.id ? 'active' : ''} onClick={() => { setAtlas(item.id); setAtlasResult(null); }}><span className="mono">FM{index + 1}</span><span>{item.name}</span><ChevronRight size={15} /></button>)}</nav><div className="atlas-detail"><EvidenceChip>{currentMode.label}</EvidenceChip><h3>{currentMode.question}</h3><p>{currentMode.requirement}</p><div className="atlas-actions"><button className="button primary" disabled={Boolean(busy)} onClick={() => void operation('atlas', async () => setAtlasResult(await labRequest('failure-demo', 'POST', { mode: atlas, sample_id: 'drifty' })))}><Play size={15} />Run synthetic example</button><button className="button secondary" disabled={Boolean(busy) || ['fm3', 'fm4'].includes(atlas)} title={['fm3', 'fm4'].includes(atlas) ? 'This measurement requires model callables, not a trace file.' : 'Use the selected trace'} onClick={() => void operation('atlas', async () => setAtlasResult(await labRequest('failure-demo', 'POST', { mode: atlas, pair })))}>Use my selected trace <ArrowRight size={14} /></button></div>{['fm3', 'fm4'].includes(atlas) && <p className="instrument-footnote">Custom model integration is library-only: never upload executable model code to this demo API.</p>}{atlasResult !== null && <><ReadableResult data={atlasResult} /><button className="text-action" onClick={() => downloadJson(`verification-${atlas}.json`, atlasResult)}>Download findings <ArrowDownToLine size={14} /></button></>}<a className="text-action" href={`/methodology#${atlas}`}>Measurement method <ArrowRight size={14} /></a></div></div></section>}
    {view === 'board' && <section className="lab-board"><div className="lab-section-title"><div><h2>A board with provenance.</h2><p>Lower path gap within a declared task-space scope. Synthetic examples are not real-robot rankings.</p></div><EvidenceChip>OPT-IN ONLY</EvidenceChip></div><div className="board-loop"><span>Opt-in pair</span><ChevronRight size={14} /><span>Trace fingerprint</span><ChevronRight size={14} /><span>Reviewer labeling</span><ChevronRight size={14} /><span>Future credibility card</span></div><p className="instrument-footnote">Calibration improvements require human labels and recorded validation. Submission alone never lifts DRAFT.</p><div className="result-table-wrap"><table className="public-board"><thead><tr><th>Entry</th><th>Task / frame</th><th>Source</th><th>Path gap</th><th>Evidence</th></tr></thead><tbody>{board.map((entry, index) => { const row = record(entry); return <tr key={text(row.id, String(index))}><td><span className="mono">{String(index + 1).padStart(2, '0')}</span>{text(row.name, 'Anonymous contribution')}</td><td>{text(row.task, 'reach')}<small>{text(row.frame_id, 'world')}</small></td><td><EvidenceChip>{text(row.label, 'UNVERIFIED')}</EvidenceChip></td><td className="mono">{formatValue(row.gap, 4)} m</td><td>{row.share_id ? <a href={`/share?id=${encodeURIComponent(text(row.share_id))}`}>Open <ArrowRight size={13} /></a> : <span>DRAFT / example</span>}</td></tr>; })}</tbody></table></div>{!board.length && <div className="history-empty"><Trophy size={20} /><span>No board response yet. Retry when the backend is available.</span></div>}<button className="text-action" onClick={() => selectView('verify')}>Add a trace with explicit consent <Plus size={15} /></button></section>}
    {view === 'api' && <section className="free-api"><div className="lab-section-title"><div><h2>Put the engine in your workflow.</h2><p>Five bounded recipes. No card. No production identity claim.</p></div><EvidenceChip>BETA / DEMO KEYS</EvidenceChip></div><div className="api-key-row"><KeyRound size={25} /><div><strong>{apiKey ? 'Demo key issued for this browser session' : 'Start with a short-lived demo key'}</strong><p>Email sign-in is not configured. This anonymous key is not an account or a verified identity.</p></div><button className="button primary" disabled={Boolean(busy)} onClick={() => void operation('key', async () => { await ensureKey(); setStatus('Demo key issued. Stored in this tab session, not in analytics.'); })}>{apiKey ? 'Key ready' : 'Issue demo key'}<KeyRound size={14} /></button>{apiKey && <button className="icon-button" aria-label="Copy demo API key" title="Copy demo API key" onClick={() => void operation('copy-key', async () => { await navigator.clipboard.writeText(apiKey); setStatus('Demo key copied. Keep it private.'); })}><Copy size={15} /></button>}</div><div className="api-usage"><span>Usage / this demo key</span><strong>{typeof record(keyInfo).used === 'number' ? String(record(keyInfo).used) : 'Not loaded'}</strong><button className="text-action" onClick={() => void operation('usage', async () => { await ensureKey(); setKeyInfo(await labRequest('usage', 'POST', {})); })}>Refresh usage <Activity size={14} /></button></div><div className="recipe-tabs" role="group" aria-label="API recipe">{['score', 'hunt', 'ledger', 'par', 'rank'].map(value => <button key={value} className={recipe === value ? 'active' : ''} onClick={() => { setRecipe(value); setApiResult(null); }}>{value}</button>)}</div><pre className="api-code">{curl}</pre><details className="api-python"><summary>Python recipe</summary><pre>{`import os, requests\nresponse = requests.${recipe === 'rank' || recipe === 'ledger' ? 'get' : 'post'}(\n    os.environ["BACKEND_URL"] + "/api/lab/v1/${recipePaths[recipe]}",\n    headers={"Authorization": "Bearer " + os.environ["VERIFICATION_FREE_KEY"]},\n    ${recipe === 'rank' || recipe === 'ledger' ? '' : `json=${JSON.stringify(recipeBody)},\n    `}timeout=20,\n)\nresponse.raise_for_status()\nprint(response.json())`}</pre></details><div className="toolbar-actions"><button className="button primary" disabled={Boolean(busy)} onClick={() => void operation('recipe', async () => { await ensureKey(); setApiResult(await labRequest(recipePaths[recipe], recipe === 'rank' || recipe === 'ledger' ? 'GET' : 'POST', recipeBody)); })}><Play size={15} />Run in browser</button><button className="button secondary" onClick={() => void operation('copy-recipe', async () => { await navigator.clipboard.writeText(curl); setStatus('Recipe copied; key stays in its environment variable.'); })}><Copy size={15} />Copy recipe</button></div>{apiResult !== null && <div className="operation-result"><ReadableResult data={apiResult} /><details className="artifact-advanced"><summary>Returned JSON</summary><pre>{JSON.stringify(apiResult, null, 2)}</pre></details></div>}</section>}
    <footer className="lab-footer"><span><Check size={14} />Explicit limits. Exportable results. No hidden retention.</span><a href="/playground">Full validation workspace <ArrowRight size={15} /></a></footer>
    {onboarding && <aside className="lab-onboarding" aria-label="Free Lab introduction"><button className="icon-button" aria-label="Skip introduction" title="Skip introduction" onClick={dismissOnboarding}><X size={14} /></button><span className="mono">{onboardingStep + 1} / 3</span><h2>{['A trace is enough to start.', 'A verdict needs a scope.', 'Sharing is your decision.'][onboardingStep]}</h2><p>{['Pick a synthetic sample or bring a metre-scaled, same-frame trace.', 'Draft gates screen the data supplied. Missing model evidence stays missing.', 'Scoring is transient. Public links and benchmark retention require a separate opt-in.'][onboardingStep]}</p><button className="text-action" onClick={() => onboardingStep === 2 ? dismissOnboarding() : setOnboardingStep(previous => previous + 1)}>{onboardingStep === 2 ? 'Open the lab' : 'Next'}<ArrowRight size={14} /></button></aside>}
  </main>;
}

function FingerprintIcon() { return <FileJson2 size={14} />; }