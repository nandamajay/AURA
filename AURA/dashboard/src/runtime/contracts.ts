export type RuntimeArtifactType =
  | 'runtime_equivalence_report'
  | 'hardware_truth_graph'
  | 'replay_consistency_report'
  | 'runtime_governance_decision'
  | 'transformation_confidence_report'

export interface ContractIssue {
  code: string
  message: string
  severity: 'error' | 'warning'
}

export interface ContractValidation {
  valid: boolean
  issues: ContractIssue[]
}

export interface RuntimeArtifactMetadata {
  artifact_type: RuntimeArtifactType
  artifact_file: string
  artifact_path: string
  exists: boolean
  size_bytes: number
  modified_at: string
  report_name: string
  schema_version: string
  target_id: string
  classification: string
  lineage_id: string
  session_id: string
  created_at: string
  advisory_only_behavior: boolean
  runtime_truth_precedence: boolean
  deterministic_fingerprint: string
  replay_fingerprint: string
  evidence_references: string[]
}

export interface RuntimeArtifactIndexItem {
  metadata: RuntimeArtifactMetadata
  validation: ContractValidation
}

export interface RuntimeArtifactPagination {
  page: number
  limit: number
  total: number
}

export interface RuntimeArtifactsIndexResponse {
  artifacts: RuntimeArtifactIndexItem[]
  pagination: RuntimeArtifactPagination
  generated_at: string
}

export interface RuntimeArtifactReadResponse<TContract = unknown> {
  metadata: RuntimeArtifactMetadata
  validation: ContractValidation
  contract: TContract | null
}

export interface RuntimeGovernanceSummaryResponse {
  available: boolean
  generated_at: string
  classification: string
  promotion_eligible: boolean
  confidence_score: number
  confidence_threshold: number
  critical_divergence_count: number
  runtime_sensitive_impact_count: number
  deterministic_replay_ready: boolean
  fail_closed_reasons: string[]
  lineage_consistency: ContractValidation
  replay_consistency: Record<string, unknown>
  metadata: RuntimeArtifactMetadata | null
  references: Record<string, string>
}

export interface RuntimeTopologyEvent {
  timestamp_ms?: number | null
  message?: string
  [key: string]: unknown
}

export interface RuntimeTopologyResponse {
  available: boolean
  generated_at: string
  section: string
  sections: string[]
  events: RuntimeTopologyEvent[]
  summary: Record<string, unknown>
  integrity: ContractValidation
  metadata: RuntimeArtifactMetadata | null
  pagination: RuntimeArtifactPagination
}

export interface RuntimeEquivalenceDimension {
  dimension: string
  classification: string
  critical: boolean
  difference_count: number
  drift_ratio: number
  baseline_count: number
  transformed_count: number
  weight: number
  added_items: string[]
  missing_items: string[]
}

export interface RuntimeEquivalenceSummary {
  confidence_score: number
  critical_divergence_count: number
  total_differences: number
}

export interface RuntimeEquivalenceResponse {
  available: boolean
  generated_at: string
  dimensions: RuntimeEquivalenceDimension[]
  summary: RuntimeEquivalenceSummary
  unsafe_regions: string[]
  validation: ContractValidation
  metadata: RuntimeArtifactMetadata | null
  pagination: RuntimeArtifactPagination
}

export interface RuntimeConfidenceResponse {
  available: boolean
  generated_at: string
  classification: string
  runtime_confidence: number
  confidence_threshold: number
  confidence_delta_from_threshold: number
  governance_blocked: boolean
  stale_state: boolean
  stale_reason: string
  drivers: Record<string, unknown>
  validation: ContractValidation
  metadata: RuntimeArtifactMetadata | null
  references: Record<string, string>
}
