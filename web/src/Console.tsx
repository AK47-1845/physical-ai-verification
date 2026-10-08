import { lazy, Suspense, useDeferredValue, useState } from 'react'
import type { ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as Tooltip from '@radix-ui/react-tooltip'
import { Activity, ArrowDownToLine, ArrowRight, ArrowUpRight, Beaker, Bell, Box, CheckCheck, ChevronRight, Database, FileCheck2, FlaskConical, GitCompare, LayoutDashboard, LockKeyhole, Menu, Plus, Search, ShieldCheck, Upload, X } from 'lucide-react'
import { ApiError, download, exportEvidence, post, request, setCsrf } from './api'
import type { Auth, Entity, Role, Run, RunSummary, Trace, Workspace } from './types'
import { Badge, Button, ErrorNotice, formatNumber, IconButton, Loading, Modal, ShortHash, timeLabel } from './ui'
import Replay, { DriftChart } from './Replay'
import './console.css'

type View = 'overview' | 'laboratory' | 'experiments' | 'transfer' | 'lineage'
const Workbenches = lazy(() => import('./Workbenches'))
const views = [{ id: 'overview' as const, label: 'Overview', icon: LayoutDashboard }, { id: 'laboratory' as const, label: 'Evaluation lab', icon: FlaskConical }, { id: 'experiments' as const, label: 'Stress experiments', icon: Beaker }, { id: 'transfer' as const, label: 'Cross-embodiment', icon: GitCompare }, { id: 'lineage' as const, label: 'Data & lineage', icon: Database }]

async function bootstrap(): Promise<Auth> {
  const configuration = await request<{ demo: boolean }>('/config')
  try {
    const auth = await request<Auth>('/session')
    setCsrf(auth.csrf_token)
    return auth
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401 || !configuration.demo) throw error
    const auth = await post<Auth>('/auth/demo', { role: 'engineer' })
    setCsrf(auth.csrf_token)
    return auth
  }
}

function SignIn({ onSignedIn }: { onSignedIn: (auth: Auth) => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const signIn = useMutation({ mutationFn: () => post<Auth>('/auth/login', { email, password }), onSuccess: (auth) => { setCsrf(auth.csrf_token); onSignedIn(auth); setPassword('') } })
  return <main className="sign-in"><div className="brand"><span className="brand-symbol"><ShieldCheck /></span><span>verification</span></div><h1>Workspace sign-in</h1><form onSubmit={(event) => { event.preventDefault(); signIn.mutate() }}><label>Email<input required type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} /></label><label>Password<input required type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} /></label><ErrorNotice error={signIn.error} /><Button type="submit" variant="primary" busy={signIn.isPending}>Sign in <ArrowRight size={16} /></Button></form></main>
}

export default function App() {
  const queryClient = useQueryClient()
  const auth = useQuery({ queryKey: ['auth'], queryFn: bootstrap, retry: false, staleTime: Infinity })
  if (auth.isPending) return <Loading label="Opening verification workspace" />
  if (auth.isError) {
    if (auth.error instanceof ApiError && auth.error.status === 401) return <SignIn onSignedIn={(value) => queryClient.setQueryData(['auth'], value)} />
    return <div className="connection-error"><ShieldCheck size={32} /><h1>Workspace unavailable</h1><ErrorNotice error={auth.error} /><Button onClick={() => void auth.refetch()}>Reconnect</Button></div>
  }
  return <Tooltip.Provider delayDuration={250}><Console auth={auth.data} /></Tooltip.Provider>
}

function Console({ auth }: { auth: Auth }) {
  const queryClient = useQueryClient()
  const workspaceQuery = useQuery({ queryKey: ['workspace', auth.user.tenant_id], queryFn: () => request<Workspace>('/workspace') })
  const [view, setView] = useState<View>('overview')
  const [search, setSearch] = useState('')
  const deferredSearch = useDeferredValue(search)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [index, setIndex] = useState(0)
  const [newEvaluation, setNewEvaluation] = useState(false)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [activityOpen, setActivityOpen] = useState(false)
  const [mobileNav, setMobileNav] = useState(false)
  const [notification, setNotification] = useState<string | null>(null)
  const workspace = workspaceQuery.data
  const activeId = selectedId ?? workspace?.runs.find((run) => run.name === 'Thermal drift')?.id ?? workspace?.runs[0]?.id
  const runQuery = useQuery({ queryKey: ['run', activeId], queryFn: () => request<Run>(`/runs/${activeId}`), enabled: Boolean(activeId) })
  const selectedRun = runQuery.data
  const canEngineer = ['engineer', 'admin'].includes(auth.user.role)
  const invalidate = async () => { await queryClient.invalidateQueries({ queryKey: ['workspace'] }) }
  const selectRun = (runId: string, navigate = true) => { setSelectedId(runId); setIndex(0); if (navigate) setView('laboratory') }
  const exportMutation = useMutation({ mutationFn: () => exportEvidence(activeId!), onSuccess: () => { setNotification('Evidence package exported'); void invalidate() } })
  const roleMutation = useMutation({ mutationFn: (role: Role) => post<Auth>('/auth/demo', { role }), onSuccess: (value) => { setCsrf(value.csrf_token); queryClient.setQueryData(['auth'], value); setNotification(`Sandbox identity: ${value.user.role}`) } })
  if (workspaceQuery.isPending) return <Loading label="Loading workspace evidence" />
  if (!workspace) return <div className="connection-error"><ErrorNotice error={workspaceQuery.error} /><Button onClick={() => void workspaceQuery.refetch()}>Reconnect</Button></div>
  return <div className="app-shell">
    {mobileNav ? <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setMobileNav(false)} /> : null}
    <aside className={`sidebar ${mobileNav ? 'is-open' : ''}`} aria-label="Main navigation">
      <a className="brand" href="#overview" onClick={(event) => { event.preventDefault(); setView('overview'); setMobileNav(false) }}><span className="brand-symbol"><ShieldCheck size={21} strokeWidth={1.8} /></span><span>verification</span></a>
      <div className="workspace-identity"><span className="workspace-avatar">V</span><div><strong>Physical AI</strong><span>Validation workspace</span></div><span className="tiny-dot" /></div>
      <div className="nav-section-label">WORKSPACE</div>
      <nav>{views.map((item) => <button key={item.id} className={`nav-item ${view === item.id ? 'active' : ''}`} aria-current={view === item.id ? 'page' : undefined} onClick={() => { setView(item.id); setMobileNav(false) }}><item.icon size={18} strokeWidth={1.7} /><span>{item.label}</span>{item.id === 'laboratory' ? <span className="nav-count">{workspace.runs.length}</span> : null}</button>)}</nav>
      <div className="sidebar-bottom"><div className="environment-state"><span className="status-dot" /><strong>{auth.demo ? 'Local sandbox' : 'Authenticated workspace'}</strong><span>v1.0</span></div><div className="identity"><span className="person-avatar">{auth.user.name.split(' ').map((part) => part[0]).slice(0, 2).join('')}</span><div><strong>{auth.user.name}</strong>{auth.demo ? <select aria-label="Sandbox identity" value={auth.user.role} onChange={(event) => roleMutation.mutate(event.target.value as Role)} disabled={roleMutation.isPending}><option value="engineer">Validation engineer</option><option value="reviewer">Independent reviewer</option><option value="admin">Workspace admin</option><option value="viewer">Read-only observer</option></select> : <span>{auth.user.role}</span>}</div></div></div>
    </aside>
    <div className="app-main"><header className="topbar"><div className="breadcrumb"><IconButton label="Open navigation" className="mobile-menu" onClick={() => setMobileNav(true)}><Menu size={19} /></IconButton><span>Workspace</span><ChevronRight size={13} /><strong>{views.find((item) => item.id === view)?.label}</strong></div><div className="topbar-actions"><label className="global-search"><Search size={15} /><input placeholder="Search evaluations..." aria-label="Search evaluations" value={search} onChange={(event) => setSearch(event.target.value)} /></label><span className="environment-label">{auth.demo ? 'SANDBOX' : 'PRIVATE'}</span><IconButton label="Audit activity" onClick={() => setActivityOpen(true)}><Bell size={18} /><span className="notification-dot" /></IconButton></div></header>
      <main id="main-content" className="main-content"><div className="page-heading"><div><div className="page-context">PHYSICAL AI ASSURANCE</div><h1>{view === 'overview' ? 'Assurance overview' : views.find((item) => item.id === view)?.label}</h1><p>{view === 'overview' ? 'Independent evidence. Explicit boundaries.' : view === 'laboratory' ? 'Task-space replay and layer-by-layer findings.' : view === 'experiments' ? 'Controlled perturbations / reproducible evaluations' : view === 'transfer' ? 'Registered embodiments / scoped geometric comparisons' : 'Dataset provenance / generation-level evidence'}</p></div><div className="heading-actions"><Button onClick={() => setUploadOpen(true)} disabled={!canEngineer}><Upload size={15} />Import trace</Button><Button variant="primary" onClick={() => setNewEvaluation(true)} disabled={!canEngineer}><Plus size={16} />New evaluation</Button></div></div>
        <ErrorNotice error={workspaceQuery.error ?? exportMutation.error ?? roleMutation.error} />
        {notification ? <div className="toast" role="status"><CheckCheck size={16} />{notification}<button aria-label="Dismiss notification" onClick={() => setNotification(null)}><X size={14} /></button></div> : null}
        {view === 'overview' ? <><div className="posture-strip"><div><span className="posture-icon"><ShieldCheck size={19} /></span><strong>Engineering evidence, not release certification</strong><span className="posture-note">Draft gate profiles</span></div><span className="regulation-date">EU 2023/1230 <span>20 Jan 2027</span><ArrowUpRight size={13} /></span></div>
          <div className="metrics-strip"><Metric label="Evaluations" value={workspace.runs.length} detail={workspace.scope} icon={<FlaskConical size={16} />} /><Metric label="Passing profiles" value={workspace.counts.PASS} detail="Within draft test boundaries" icon={<CheckCheck size={16} />} /><Metric label="Blocked evaluations" value={workspace.counts.BLOCK} detail="Require engineering attention" danger icon={<Activity size={16} />} /><Metric label="Registered embodiments" value={workspace.embodiments.length} detail="Hardware qualification pending" icon={<Box size={16} />} /></div>
          <div className="overview-workbench"><section className="replay-section"><div className="section-heading"><h2>Evaluation spotlight</h2><button className="text-button" onClick={() => setView('laboratory')}>Open evaluation <ArrowUpRight size={14} /></button></div><div className="spotlight-meta"><span className="robot-icon"><Box size={16} /></span><strong>{selectedRun?.data.trace.name ?? 'Loading evaluation'}</strong><span className="mono">{selectedRun?.data.trace.embodiment_id}</span></div>{selectedRun ? <Replay trace={selectedRun.data.trace} result={selectedRun.data.result} index={index} onIndex={setIndex} compact /> : <Loading />}</section>
          <section className="layer-section"><div className="section-heading"><h2>Verification layers</h2><span className="muted mono">{selectedRun?.data.result.coverage.observed ?? 0}/{selectedRun?.data.result.coverage.total ?? 0}</span></div><div className="layer-list">{selectedRun?.data.result.gates.slice(0, 8).map((gate, gateIndex) => <button key={gate.metric} className="layer-row" onClick={() => { setView('laboratory'); const event = selectedRun.data.result.events.find((entry) => entry.metric === gate.metric); if (event) setIndex(event.index) }}><span className="layer-number">{String(gateIndex + 1).padStart(2, '0')}</span><div><strong>{gate.label}</strong><span>{formatNumber(gate.value, gate.unit)}</span></div>{gate.status === 'PASS' ? <CheckCheck size={15} className="success-ink" /> : <ChevronRight size={15} />}</button>)}</div><div className="layer-footer"><LockKeyhole size={15} /><span>Unobserved evidence never passes.</span></div></section></div>
          <RunTable runs={workspace.runs} search={deferredSearch} onSelect={selectRun} selectedId={activeId} />
          <div className="overview-footer"><ShieldCheck size={14} />Source-linked results <span />Versioned gates <span />Tamper-evident audit trail<strong>{workspace.datasets.filter((entry) => entry.evidence_kind === 'recorded').length} recorded / {workspace.datasets.filter((entry) => entry.evidence_kind === 'synthetic').length} synthetic datasets</strong></div></> :
          view === 'laboratory' ? <><div className="lab-toolbar"><label>Evaluation<select aria-label="Selected evaluation" value={activeId ?? ''} onChange={(event) => selectRun(event.target.value, false)}>{workspace.runs.map((run) => <option key={run.id} value={run.id}>{run.name} / {run.embodiment_id} / {run.id.slice(-6)}</option>)}</select></label><Button onClick={() => exportMutation.mutate()} busy={exportMutation.isPending} disabled={!activeId}><ArrowDownToLine size={15} />Export evidence</Button></div><ErrorNotice error={runQuery.error} />{selectedRun ? <EvaluationDetail run={selectedRun} index={index} onIndex={setIndex} /> : <Loading />}</> : <Suspense fallback={<Loading />}><Workbenches view={view} workspace={workspace} canEngineer={canEngineer} onSelectRun={selectRun} /></Suspense>}
      </main></div>
    <NewEvaluation open={newEvaluation} onClose={() => setNewEvaluation(false)} workspace={workspace} onCreated={async (run) => { setNewEvaluation(false); selectRun(run.id); setNotification('Evaluation recorded in the audit ledger'); await invalidate() }} />
    <UploadTrace open={uploadOpen} onClose={() => setUploadOpen(false)} onUploaded={async () => { setUploadOpen(false); await invalidate(); setNewEvaluation(true) }} />
    <Modal open={activityOpen} onOpenChange={setActivityOpen} title="Audit activity" description="Latest recorded workspace operations."><div className="audit-list">{workspace.audit.map((entry) => <div key={entry.id}><span className="audit-icon"><FileCheck2 size={17} /></span><div><strong>{entry.action.replaceAll('.', ' / ')}</strong><span>{entry.actor} / {timeLabel(entry.created_at)}</span><ShortHash value={entry.event_hash} /></div><span className="mono muted">#{entry.sequence}</span></div>)}</div></Modal>
  </div>
}

function Metric({ label, value, detail, icon, danger = false }: { label: string; value: number; detail: string; icon: ReactNode; danger?: boolean }) {
  return <div className="metric"><div className="metric-label">{label}{icon}</div><strong className={danger ? 'danger-ink' : ''}>{String(value).padStart(2, '0')}</strong><span>{detail}</span></div>
}

function RunTable({ runs, search, onSelect, selectedId }: { runs: RunSummary[]; search: string; onSelect: (id: string) => void; selectedId?: string }) {
  const [filter, setFilter] = useState('all')
  const filtered = runs.filter((run) => (filter === 'all' || run.verdict === filter) && `${run.name} ${run.embodiment_id} ${run.id} ${run.policy_version}`.toLowerCase().includes(search.toLowerCase()))
  return <section className="runs-section"><div className="section-heading"><h2>Evaluation history <span className="count-label">{filtered.length}</span></h2><div className="segmented" aria-label="Filter evaluations">{[['all', 'All'], ['PASS', 'Passed'], ['BLOCK', 'Blocked'], ['REVIEW', 'Review']].map(([value, label]) => <button key={value} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>)}</div></div><div className="table-scroll"><table className="data-table"><thead><tr><th>Evaluation</th><th>Embodiment</th><th>Result</th><th>Evidence</th><th>Mean error</th><th>Recorded</th><th><span className="sr-only">Open</span></th></tr></thead><tbody>{filtered.slice(0, 8).map((run) => <tr key={run.id} className={run.id === selectedId ? 'selected-row' : ''}><td><button className="run-name" onClick={() => onSelect(run.id)}><span className="table-icon"><FlaskConical size={16} /></span><span><strong>{run.name}</strong><small>{run.policy_version}</small></span></button></td><td><span className="embodiment-label">{run.embodiment_id}</span></td><td><Badge status={run.verdict} /></td><td><span className="evidence-type">{run.evidence_kind}</span><span className="coverage-text">{run.coverage.observed}/{run.coverage.total} gates</span></td><td className="mono">{formatNumber(run.mean_drift, 'm')}</td><td className="muted">{timeLabel(run.created_at)}</td><td><IconButton label={`Open ${run.name}`} onClick={() => onSelect(run.id)}><ArrowUpRight size={16} /></IconButton></td></tr>)}</tbody></table>{filtered.length === 0 ? <div className="empty-state"><Search size={24} /><strong>No matching evaluations</strong><Button onClick={() => setFilter('all')}>Clear status filter</Button></div> : null}</div><div className="table-footer"><span>{Math.min(8, filtered.length)} of {filtered.length} evaluations</span><span className="muted">{runs.filter((run) => run.release_eligible).length} release-qualified</span></div></section>
}

function EvaluationDetail({ run, index, onIndex }: { run: Run; index: number; onIndex: (value: number) => void }) {
  const { trace, result, profile } = run.data
  const [selectedGate, setSelectedGate] = useState<string | null>(null)
  const gate = result.gates.find((entry) => entry.metric === selectedGate)
  return <div className="evaluation-detail"><div className="detail-title"><div><Badge status={result.verdict} /><h2>{trace.name}</h2><span className="mono muted">{run.id.slice(-12)}</span></div><span className="profile-tag">{profile.name} / v{profile.version} / DRAFT</span></div><div className="lab-workbench"><div><Replay trace={trace} result={result} index={index} onIndex={onIndex} /><div className="chart-heading"><h3>Tracking error</h3><span className="mono">mm / sample</span></div><DriftChart result={result} index={index} onSelect={onIndex} /></div><aside className="findings"><div className="section-heading"><h2>Findings</h2><span className="count-label">{result.events.length}</span></div>{result.events.length ? result.events.map((event, eventIndex) => <button key={`${event.metric}-${eventIndex}`} className={`finding-row ${index === event.index ? 'active' : ''}`} onClick={() => { onIndex(event.index); setSelectedGate(event.metric) }}><span className="finding-mark" /><div><strong>{event.label}</strong><span>Sample {event.index} / {formatNumber(result.series.error_m[event.index], 'm')}</span></div><ArrowUpRight size={14} /></button>) : <div className="empty-inline"><CheckCheck size={20} /><span>No trace events recorded</span></div>}<div className="evidence-context"><span className="nav-section-label">EVIDENCE CONTEXT</span><dl><dt>Source</dt><dd>{trace.evidence_kind}</dd><dt>Reference</dt><dd>{trace.reference_kind}</dd><dt>Frame</dt><dd>{trace.coordinate_frame}</dd><dt>Dimensions</dt><dd>{trace.observed[0].length}D</dd><dt>Timing</dt><dd>{trace.timestamps_s ? 'Provided' : 'Unavailable'}</dd><dt>Policy</dt><dd>{trace.policy_version}</dd></dl></div></aside></div>
    <section className="gates-section"><div className="section-heading"><h2>Gate results</h2><span className="muted">{result.coverage.observed} observed / {result.coverage.total} configured</span></div><div className="table-scroll"><table className="data-table gates-table"><thead><tr><th>Verification gate</th><th>Layer</th><th>Measurement</th><th>Pass threshold</th><th>Result</th><th>Evidence</th></tr></thead><tbody>{result.gates.map((entry) => <tr key={entry.metric} className={selectedGate === entry.metric ? 'selected-row' : ''}><td><button className="text-button gate-name" onClick={() => { setSelectedGate(entry.metric); const event = result.events.find((event) => event.metric === entry.metric); if (event) onIndex(event.index) }}>{entry.label}<ArrowUpRight size={13} /></button></td><td className="muted">{entry.layer}</td><td className="mono">{formatNumber(entry.value, entry.unit)}</td><td className="mono muted">{entry.direction === 'upper' ? '<=' : '>='} {formatNumber(entry.pass_limit, entry.unit)}</td><td><Badge status={entry.status} /></td><td>{entry.required ? 'Required' : 'Optional'}</td></tr>)}</tbody></table></div>{gate ? <div className="gate-explanation"><ShieldCheck size={17} /><strong>{gate.label}</strong><span>{gate.limitation}</span><IconButton label="Close gate detail" onClick={() => setSelectedGate(null)}><X size={15} /></IconButton></div> : null}</section>
    <section className="limitations"><h3><LockKeyhole size={16} />Assurance boundaries</h3>{result.limitations.map((limitation) => <p key={limitation}>{limitation}</p>)}<div className="hash-row"><span>Input <ShortHash value={result.input_hash} /></span><span>Profile <ShortHash value={result.profile_hash} /></span><span>Result <ShortHash value={result.result_hash} /></span></div></section></div>
}

function NewEvaluation({ open, onClose, workspace, onCreated }: { open: boolean; onClose: () => void; workspace: Workspace; onCreated: (run: Run) => void }) {
  const [datasetId, setDatasetId] = useState('dataset-nominal')
  const [profileId, setProfileId] = useState('profile-default')
  const mutation = useMutation({ mutationFn: () => post<Run>('/runs', { dataset_id: datasetId, profile_id: profileId }), onSuccess: onCreated })
  const dataset = workspace.datasets.find((entry) => entry.id === datasetId)
  return <Modal open={open} onOpenChange={(value) => { if (!value) onClose() }} title="New evaluation" description="A recorded evaluation against an immutable gate profile."><form onSubmit={(event) => { event.preventDefault(); mutation.mutate() }} className="form-stack"><label>Dataset<select value={datasetId} onChange={(event) => { setDatasetId(event.target.value); const chosen = workspace.datasets.find((entry) => entry.id === event.target.value); const matching = workspace.profiles.find((profile) => profile.coordinate_frame === chosen?.coordinate_frame && profile.dimension === chosen.dimension); if (matching) setProfileId(matching.id) }}>{workspace.datasets.map((entry) => <option key={entry.id} value={entry.id}>{entry.name} / {entry.embodiment_id}</option>)}</select></label><label>Gate profile<select value={profileId} onChange={(event) => setProfileId(event.target.value)}>{workspace.profiles.map((entry) => <option key={entry.id} value={entry.id}>{entry.name} / v{entry.version} / draft</option>)}</select></label>{dataset ? <div className="form-facts"><span>{dataset.samples} samples</span><span>{dataset.dimension}D / {dataset.units}</span><Badge status={dataset.evidence_kind}>{dataset.evidence_kind}</Badge></div> : null}<ErrorNotice error={mutation.error} /><div className="dialog-actions"><Button type="button" onClick={onClose}>Cancel</Button><Button type="submit" variant="primary" busy={mutation.isPending}><FlaskConical size={16} />Run evaluation</Button></div></form></Modal>
}

function UploadTrace({ open, onClose, onUploaded }: { open: boolean; onClose: () => void; onUploaded: () => void }) {
  const [file, setFile] = useState<File | null>(null)
  const mutation = useMutation({ mutationFn: async () => { if (!file) throw new Error('Choose a trace JSON file'); if (file.size > 2 * 1024 * 1024) throw new Error('Trace exceeds the 2 MiB limit'); const payload: unknown = JSON.parse(await file.text()); return post<Entity<{ trace: Trace }>>('/datasets', payload) }, onSuccess: onUploaded })
  const sample = useMutation({ mutationFn: () => request<Entity<{ trace: Trace }>>('/datasets/dataset-nominal'), onSuccess: (value) => download(new Blob([JSON.stringify(value.data.trace, null, 2)], { type: 'application/json' }), 'verification-trace-example.json') })
  return <Modal open={open} onOpenChange={(value) => { if (!value) onClose() }} title="Import trajectory" description="verification.trace/1 JSON / maximum 2 MiB / 512 samples."><form className="form-stack" onSubmit={(event) => { event.preventDefault(); mutation.mutate() }}><label className="file-input"><Upload size={28} /><strong>{file?.name ?? 'Select a trajectory file'}</strong><input type="file" accept=".json,application/json" aria-label="Trajectory JSON file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></label><Button type="button" variant="ghost" onClick={() => sample.mutate()} busy={sample.isPending}><ArrowDownToLine size={15} />Download schema example</Button><ErrorNotice error={mutation.error ?? sample.error} /><div className="dialog-actions"><Button type="button" onClick={onClose}>Cancel</Button><Button type="submit" variant="primary" busy={mutation.isPending} disabled={!file}>Import trace <ArrowRight size={15} /></Button></div></form></Modal>
}