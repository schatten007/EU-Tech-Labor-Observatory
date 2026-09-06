import data from '../data.json'

export interface InsightEvidence {
  [key: string]: unknown
}

export interface Insight {
  rule: string
  text: string
  evidence: InsightEvidence
}

export interface Demand {
  observed_at: string
  active_postings: number
  source_version: string
  licence_reference: string
  access_method: string
  freshness_status: string
  coverage_status: string
}

export interface Coverage {
  observed_at: string
  expected_rows: number
  observed_rows: number
  freshness_status: string
  coverage_status: string
  freshness_age_hours: number | null
  coverage_limitations: string | null
  freshness_threshold_hours: number | null
}

export interface Breadth {
  regions_with_postings: number
  regions_in_frame: number
}

export interface Frequency {
  complete_sweeps: number
  first_observed_at: string
  last_observed_at: string
  median_interval_hours: number
}

export interface RegionRow {
  label: string
  postings: number
  taxonomy_version: string
}

export interface RequirementRow {
  label: string
  code: string | null
  count: number
}

export interface FlowBucket {
  bucket: string
  openings: number | null
  closures: number | null
  active: number | null
  suppressed: boolean
}

export interface DimensionDenominator {
  postings_total: number
  postings_with_source_value: number
  postings_mapped: number
}

export interface Scope {
  source: string
  scope_id: string
  country: string
  label: string
  demand: Demand
  coverage: Coverage
  breadth: Breadth
  frequency: Frequency
  regions_top: RegionRow[]
  requirements: Record<string, RequirementRow[]>
  mappings: Record<string, Record<string, number>>
  denominators: Record<string, DimensionDenominator>
  flows_series: Record<string, FlowBucket[]>
  insights: Insight[]
}

export interface AppData {
  meta: {
    methodology_version: string
    built: string
    scope_count: number
  }
  scopes: Scope[]
}

export const appData = data as unknown as AppData

export function scopeName(scope: Scope): string {
  if (scope.country === 'DE') return 'Germany'
  if (scope.country === 'SE') return 'Sweden'
  return scope.label
}

export function formatNumber(n: number): string {
  return n.toLocaleString('en-GB')
}

export function formatDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}
