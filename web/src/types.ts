export type Verdict = 'PASS' | 'REVIEW' | 'BLOCK' | 'INSUFFICIENT'
export type Role = 'engineer' | 'reviewer' | 'admin' | 'viewer'
export type GateStatus = Verdict | 'MISSING' | 'NOT_OBSERVED'
export interface User { id: string; tenant_id: string; email: string; name: string; role: Role }
export interface Auth { user: User; csrf_token: string; demo: boolean }
export interface Gate {
  metric: string; label: string; layer: string; value: number | null; unit: string;
  status: GateStatus; required: boolean; direction: 'upper' | 'lower';
  pass_limit: number; review_limit: number; limitation: string;
}
export interface Generation { generation: number; real_samples: number; synthetic_samples: number; diversity: number; quality: number }
export interface Trace {
  name: string; task: string; embodiment_id: string; policy_version: string;
  evidence_kind: 'synthetic' | 'recorded' | 'simulator'; reference_kind: string;
  units: string; coordinate_frame: string; reference: number[][]; observed: number[][];
  timestamps_s: number[] | null; probed: number[][] | null;
  lineage: { generations: Generation[]; metric_definition: string; evidence_kind: string } | null;
  provenance: { source: string; license: string; transforms: string[]; source_sha256?: string; attribution: string };
}
export interface Profile {
  id: string; name: string; version: number; calibration: 'draft'; coordinate_frame: string;
  units: string; dimension: number; workspace_lower: number[]; workspace_upper: number[];
  drift_breach_m: number; breach_run: number; rules: Pick<Gate, 'metric' | 'direction' | 'pass_limit' | 'review_limit' | 'required'>[];
  content_hash: string;
}
export interface Assessment {
  verdict: Verdict; engine_version: string; input_hash: string; profile_hash: string; result_hash: string;
  gates: Gate[]; events: { index: number; kind: string; metric: string; label: string }[];
  series: { error_m: number[]; speed_m_s: number[]; jerk_m_s3: number[] };
  coverage: { observed: number; total: number }; release_eligible: boolean;
  release_blockers: string[]; limitations: string[];
}
export interface Entity<T> { id: string; kind: string; data: T; content_hash: string; created_at: string; created_by: string }
export interface Review { run_id: string; decision: string; note: string; revision: number; reviewer: string }
export interface Run extends Entity<{ trace: Trace; profile: Profile; result: Assessment; dataset_id: string | null }> { reviews?: Entity<Review>[] }
export interface RunSummary {
  id: string; name: string; task: string; policy_version: string; embodiment_id: string;
  evidence_kind: string; reference_kind: string; created_at: string; created_by: string;
  verdict: Verdict; coverage: { observed: number; total: number }; content_hash: string;
  profile_name: string; profile_version: number; review_state: string; review_revision: number;
  failed_gates: number; mean_drift: number | null; release_eligible: boolean;
}
export interface Dataset {
  id: string; name: string; task: string; embodiment_id: string; evidence_kind: string; reference_kind: string;
  samples: number; units: string; coordinate_frame: string; dimension: number; timing_available: boolean;
  content_hash: string; source: string; license: string; scenario: string | null;
}
export interface Embodiment { id: string; name: string; family: string; degrees_of_freedom: number; coordinate_frame: string; units: string; dimension: number; hardware_validated: boolean; description: string }
export interface AuditEntry { id: string; sequence: number; actor: string; action: string; created_at: string; resource_id: string; resource_hash: string; previous_hash: string; event_hash: string; details: Record<string, unknown> }
export interface Standard { id: string; framework: string; reference: string; topic: string; status: string; application_date: string | null; metrics: string[]; source: string; reviewed_on: string; gap: string }
export interface Workspace {
  runs: RunSummary[]; datasets: Dataset[]; profiles: Profile[]; embodiments: Embodiment[];
  counts: Record<Verdict, number>; scope: string; audit: AuditEntry[]; standards: Standard[];
  scenarios: { id: string; name: string; description: string }[];
}