import type { ButtonHTMLAttributes, ReactNode } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import * as Tooltip from '@radix-ui/react-tooltip'
import { AlertTriangle, Check, LoaderCircle, X } from 'lucide-react'

const labels: Record<string, string> = { PASS: 'Passed', BLOCK: 'Blocked', REVIEW: 'Review', INSUFFICIENT: 'Incomplete', MISSING: 'Missing', NOT_OBSERVED: 'Not observed', ALLOW: 'Allow', HOLD: 'Hold', VERIFIED_BOX: 'Verified box', COUNTEREXAMPLE: 'Counterexample', INCONCLUSIVE: 'Inconclusive' }

export function Badge({ status, children }: { status: string; children?: ReactNode }) {
  return <span className={`badge badge-${status.toLowerCase()}`}><span className="status-dot" />{children ?? labels[status] ?? status.replaceAll('_', ' ')}</span>
}

export function Button({ children, variant = 'secondary', busy, className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'ghost' | 'danger'; busy?: boolean }) {
  return <button {...props} disabled={props.disabled || busy} className={`button button-${variant} ${className}`}>{busy ? <LoaderCircle size={16} className="spinning" /> : null}{children}</button>
}

export function IconButton({ label, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return <Tooltip.Root><Tooltip.Trigger asChild><button {...props} className={`icon-button ${props.className ?? ''}`} aria-label={label}>{children}</button></Tooltip.Trigger><Tooltip.Portal><Tooltip.Content className="tooltip" sideOffset={6}>{label}<Tooltip.Arrow /></Tooltip.Content></Tooltip.Portal></Tooltip.Root>
}

export function Modal({ open, onOpenChange, title, description, children, wide = false }: { open: boolean; onOpenChange: (open: boolean) => void; title: string; description: string; children: ReactNode; wide?: boolean }) {
  return <Dialog.Root open={open} onOpenChange={onOpenChange}><Dialog.Portal><Dialog.Overlay className="dialog-overlay" /><Dialog.Content className={`dialog-content ${wide ? 'dialog-wide' : ''}`}><div className="dialog-heading"><div><Dialog.Title>{title}</Dialog.Title><Dialog.Description>{description}</Dialog.Description></div><Dialog.Close asChild><button className="icon-button" aria-label="Close dialog"><X size={18} /></button></Dialog.Close></div>{children}</Dialog.Content></Dialog.Portal></Dialog.Root>
}

export function ErrorNotice({ error }: { error: unknown }) {
  if (!error) return null
  return <div className="error-notice" role="alert"><AlertTriangle size={17} /><span>{error instanceof Error ? error.message : String(error)}</span></div>
}

export function SuccessNotice({ children }: { children: ReactNode }) {
  return <div className="success-notice" role="status"><Check size={17} />{children}</div>
}

export function Loading({ label = 'Loading evidence' }: { label?: string }) {
  return <div className="loading-state" role="status"><LoaderCircle size={24} className="spinning" /><span>{label}</span><div className="skeleton" /><div className="skeleton short" /></div>
}

export function formatNumber(value: number | null | undefined, unit = '') {
  if (value === null || value === undefined) return 'Not observed'
  if (unit === 'fraction') return `${(value * 100).toFixed(1)}%`
  if (unit === 'm') return `${(value * 1000).toFixed(1)} mm`
  const number = value === 0 ? '0' : Math.abs(value) < 0.001 ? value.toExponential(2) : value.toLocaleString('en-US', { maximumFractionDigits: 4 })
  return `${number}${unit && unit !== 'ratio' ? ` ${unit}` : ''}`
}

export function timeLabel(value: string) {
  return new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: 'short' }).format(new Date(value))
}

export function ShortHash({ value }: { value: string }) { return <code className="hash" title={value}>{value.slice(0, 12)}</code> }