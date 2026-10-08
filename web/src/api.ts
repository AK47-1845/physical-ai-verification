let csrfToken = ''

export function setCsrf(value: string) { csrfToken = value }

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) { super(message); this.status = status }
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    credentials: 'same-origin', cache: 'no-store', ...options,
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken, ...options.headers },
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: `Request failed (${response.status})` }))
    const detail = Array.isArray(payload.detail)
      ? payload.detail.map((entry: { location: string[]; message: string }) => `${entry.location.join('.')}: ${entry.message}`).join('; ')
      : payload.detail
    throw new ApiError(typeof detail === 'string' ? detail : 'The request could not be completed', response.status)
  }
  return response.json() as Promise<T>
}

export function post<T>(path: string, body: unknown) {
  return request<T>(path, { method: 'POST', body: JSON.stringify(body) })
}

export async function exportEvidence(runId: string) {
  const response = await fetch(`/api/runs/${runId}/export`, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRF-Token': csrfToken } })
  if (!response.ok) throw new ApiError('Evidence export failed. Check your session and audit integrity.', response.status)
  download(await response.blob(), `verification-${runId}.zip`)
}

export function download(blob: Blob, filename: string) {
  const address = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = address
  anchor.download = filename
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(address), 5000)
}

export async function verifyEvidence(file: File) {
  const response = await fetch('/api/evidence/verify', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/zip', 'X-CSRF-Token': csrfToken }, body: file })
  if (!response.ok) throw new ApiError('Bundle could not be verified', response.status)
  return response.json() as Promise<{ valid: boolean; origin_verified: boolean; files_checked?: number; reason?: string; qualification?: string }>
}