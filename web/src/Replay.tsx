import { lazy, Suspense, useEffect, useState } from 'react'
import { Box, Pause, Play, RotateCcw, Scan, SkipBack } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Assessment, Trace } from './types'
import { Badge, formatNumber, IconButton, Loading } from './ui'

const Scene = lazy(() => import('./Scene'))

export function DriftChart({ result, index, onSelect }: { result: Assessment; index: number; onSelect: (value: number) => void }) {
  const rows = result.series.error_m.map((error, sample) => ({ sample, error: error * 1000 }))
  return <div className="drift-chart" data-testid="drift-chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={rows} margin={{ top: 12, right: 12, left: -14, bottom: 0 }} onClick={(event) => { if (event?.activeLabel !== undefined) onSelect(Number(event.activeLabel)) }}>
    <CartesianGrid vertical={false} stroke="#e4e9e6" />
    <XAxis dataKey="sample" tick={{ fill: '#68736d', fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={35} />
    <YAxis tick={{ fill: '#68736d', fontSize: 10 }} axisLine={false} tickLine={false} width={48} />
    <Tooltip contentStyle={{ borderRadius: 4, border: '1px solid #d7e0da', fontSize: 12 }} formatter={(value) => [`${Number(value).toFixed(2)} mm`, 'Tracking error']} labelFormatter={(label) => `Sample ${label}`} />
    <Area type="linear" dataKey="error" stroke="#167251" fill="#dcefe4" strokeWidth={1.6} isAnimationActive={false} />
    <ReferenceLine x={index} stroke="#a04c31" />
  </AreaChart></ResponsiveContainer></div>
}

export default function Replay({ trace, result, index, onIndex, compact = false }: { trace: Trace; result: Assessment; index: number; onIndex: (index: number) => void; compact?: boolean }) {
  const [playing, setPlaying] = useState(false)
  const [top, setTop] = useState(false)
  const [resetKey, setResetKey] = useState(0)
  useEffect(() => {
    if (!playing) return
    const interval = setInterval(() => onIndex((index + 1) % trace.observed.length), 50)
    return () => clearInterval(interval)
  }, [playing, index, onIndex, trace.observed.length])
  const point = trace.observed[index] ?? trace.observed[0]
  return <div className={`replay ${compact ? 'replay-compact' : ''}`}>
    <div className="replay-title"><div className="replay-source"><span className="live-square" />{trace.evidence_kind === 'synthetic' ? 'SYNTHETIC REPLAY' : 'RECORDED REPLAY'}</div><span className="replay-frame">{trace.coordinate_frame} / {trace.units}</span></div>
    <div className="scene-wrap"><Suspense fallback={<Loading label="Loading spatial replay" />}><Scene trace={trace} index={index} top={top} resetKey={resetKey} /></Suspense><div className="scene-legend"><span><i className="legend-reference" />Reference</span><span><i className="legend-observed" />Observed</span></div><div className="scene-tools"><IconButton label="Reset camera" onClick={() => setResetKey(resetKey + 1)}><RotateCcw size={16} /></IconButton><IconButton label={top ? 'Perspective view' : 'Top view'} onClick={() => setTop(!top)}>{top ? <Box size={16} /> : <Scan size={16} />}</IconButton></div><span className="scene-caption">{point.length === 3 ? 'Task-space schematic' : 'XY capture / height unavailable'}</span><div className="scene-coordinates">{point.map((value, axis) => <span key={axis}><b>{['X', 'Y', 'Z'][axis]}</b>{value.toFixed(3)}</span>)}</div></div>
    <div className="replay-controls"><IconButton label="Restart replay" onClick={() => { onIndex(0); setPlaying(false) }}><SkipBack size={15} /></IconButton><IconButton label={playing ? 'Pause replay' : 'Play replay'} onClick={() => setPlaying(!playing)}>{playing ? <Pause size={17} /> : <Play size={17} />}</IconButton><input type="range" aria-label="Replay sample" min={0} max={trace.observed.length - 1} value={index} onChange={(event) => { setPlaying(false); onIndex(Number(event.target.value)) }} /><span className="sample-counter">{String(index + 1).padStart(3, '0')}<span> / {trace.observed.length}</span></span></div>
    <div className="replay-measure"><span>Tracking error <strong>{formatNumber(result.series.error_m[index], 'm')}</strong></span><Badge status={result.verdict} /></div>
  </div>
}