// ---------------------------------------------------------------------------
// Study & Questionnaire
// ---------------------------------------------------------------------------

export interface CreateStudyRequest {
  study_id: string
  product_category: string
  research_goal: string
  target_segments: string[]
  attributes?: AttributeDefinition[]
  design_parameters?: Record<string, unknown>
}

export interface GenerateQuestionnaireResponse {
  study_id: string
  questionnaire_id: string
  algorithm: string
  d_efficiency: number | null
  a_efficiency: number | null
  n_choice_sets: number
  n_alternatives: number
  include_none: boolean
  validation_passed: boolean
  validation_errors: string[]
}

export interface ChoiceAlternative {
  alt_index: number
  attributes: Record<string, string | number>
}

export interface ChoiceSet {
  choice_set_id: number
  alternatives: ChoiceAlternative[]
}

export interface QuestionnaireDetail {
  study_id: string
  choice_sets: ChoiceSet[]
  design_params: {
    algorithm: string
    d_efficiency: number | null
    a_efficiency: number | null
    n_attributes: number
    n_choice_sets: number
    n_alternatives: number
    include_none: boolean
  }
  created_at: string
}

export interface StudySummary {
  study_id: string
  product_category: string
  research_goal: string
  target_segments: string[]
  status: string
  created_at: string
}

export interface StudyDetail {
  study_id: string
  product_category: string
  research_goal: string
  target_segments: string[]
  status: string
  n_attributes: number
  n_choice_sets: number
  n_alternatives: number
  algorithm: string
  include_none: boolean
  attributes?: AttributeDefinition[]
  prohibited_pairs?: ProhibitedPair[]
  created_at: string
}

export interface StudyUpdateRequest {
  product_category?: string
  research_goal?: string
  target_segments?: string[]
  sample_size?: number
  cost_budget_cny?: number
  design_parameters?: Record<string, unknown>
}

export interface ProhibitedCondition {
  attribute_id: string
  level_value: string
}

export interface ProhibitedPair {
  conditions: ProhibitedCondition[]
}

export interface Level {
  value: string
  label: string
  description?: string | null
}

export interface AttributeDefinition {
  id: string
  name: string
  type: 'categorical' | 'ordinal' | 'continuous' | 'price'
  description?: string | null
  levels: Level[]
}

export interface StudyDesignResponse {
  study_id: string
  attributes: AttributeDefinition[]
  prohibited_pairs?: ProhibitedPair[]
}

export interface StudyListResponse {
  total: number
  page: number
  page_size: number
  studies: StudySummary[]
}

// ---------------------------------------------------------------------------
// Simulation & Responses
// ---------------------------------------------------------------------------

export interface SimulateResponsesRequest {
  persona_ids: string[]
  mode?: 'rule' | 'llm'
  deterministic?: boolean
  seed?: number
}

export interface SimulatedResponseSummary {
  persona_id: string
  simulated: boolean
  n_choice_sets_answered: number
  error?: string
}

export interface SimulateResponsesResponse {
  study_id: string
  questionnaire_id: string
  simulated: number
  failed: number
  summaries: SimulatedResponseSummary[]
}

export interface RawDatasetExportResponse {
  study_id: string
  n_respondents: number
  n_choice_sets: number
  n_alternatives: number
  n_total_records: number
  choice_records: Record<string, unknown>[]
}

// ---------------------------------------------------------------------------
// Persona
// ---------------------------------------------------------------------------

export interface PersonaDetail {
  persona_id: string
  segment: string
  layer1_demographics: Record<string, unknown>
  layer2_behavior: Record<string, unknown>
  layer3_psychology: Record<string, unknown>
  layer4_scenarios: Record<string, unknown>
  language_samples: string[]
  dishwasher_context: Record<string, unknown>
  authenticity_score: number | null
  bias_audit_status: string
  generation_metadata: Record<string, unknown>
  created_at: string
}

export interface PersonaSummary {
  persona_id: string
  segment: string
  life_stage: string
  city_tier: string
  income_bracket: string
  authenticity_score: number | null
  bias_audit_status: string
  created_at: string
}

export interface PersonaListResponse {
  total: number
  page: number
  page_size: number
  personas: PersonaSummary[]
}

export interface GeneratePersonasRequest {
  study_id: string
  count: number
}

export interface GeneratePersonasResponse {
  study_id: string
  requested: number
  generated: number
  failed: number
  personas: PersonaSummary[]
  errors: Array<{ index: number; error: string }>
  total_cost_cny: number
  generation_time_seconds: number
}

export interface ValidateResponse {
  persona_id: string
  schema_passed: boolean
  logic_passed: boolean
  logic_score: number
  logic_max_score: number
  schema_errors: string[]
  logic_errors: string[]
  overall_passed: boolean
}

export interface LayerResponse {
  persona_id: string
  layer_number: number
  layer_name: string
  data: Record<string, unknown>
}

export interface PersonaResponseSummary {
  response_id: string
  persona_id: string
  completion_status: string
  n_answers: number
  created_at: string
}

// ---------------------------------------------------------------------------
// Analysis
// ---------------------------------------------------------------------------

export interface AnalysisJobStatus {
  analysis_id: string
  study_id: string
  status: 'PENDING' | 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED' | 'TIMED_OUT'
  model_type: string
  queued_at: string
  started_at: string | null
  completed_at: string | null
  estimated_duration_seconds: number
  progress_percent: number
}

export interface ConvergenceDiagnostics {
  rhat_max: number
  rhat_by_param: Record<string, number>
  ess_bulk_min: number
  ess_tail_min: number
  ess_by_param: Record<string, number>
  converged: boolean
  reliable_ess: boolean
  divergences: number
  tree_depth_max: number
}

export interface ImportanceStats {
  mean: number
  std: number
  median: number
  min: number
  max: number
  q25: number
  q75: number
  ci_95_lower: number
  ci_95_upper: number
}

export interface ImportanceResponse {
  overall: Record<string, ImportanceStats>
  by_segment?: Record<string, Record<string, ImportanceStats>>
  individual?: Record<string, Record<string, number>>
}

export interface WTPComparison {
  from_level: string
  to_level: string
  wtp_mean: number
  wtp_median: number
  wtp_std: number
  ci_95_lower: number
  ci_95_upper: number
  n_valid: number
}

export interface WTPAttribute {
  comparisons: WTPComparison[]
}

export interface PriceCoefficientSummary {
  mean: number
  median: number
  std: number
  negative_rate: number
  n_positive_outliers: number
}

export interface WTPResponse {
  wtp_values: Record<string, WTPAttribute>
  price_coefficient_summary: PriceCoefficientSummary
}

export interface AnalysisResultResponse {
  analysis_id: string
  study_id: string
  status: string
  model_type: string
  convergence: ConvergenceDiagnostics
  population_params: {
    mu: Record<string, number>
    sigma: Record<string, number>
  }
  individual_utilities: Record<string, Record<string, number>>
  importance: Record<string, number>
  wtp: Record<string, unknown>
  processing_time_seconds: number
  completed_at: string | null
}

// ---------------------------------------------------------------------------
// Market Simulation
// ---------------------------------------------------------------------------

export interface ProductScenario {
  name: string
  attributes: Record<string, string | number>
}

export interface ScenarioShare {
  name: string
  predicted_share: number
  share_ci_95_lower: number
  share_ci_95_upper: number
}

export interface MarketSimRequest {
  scenarios: ProductScenario[]
  rule: 'logit' | 'first_choice'
  include_none: boolean
  segment_filter?: string | null
}

export interface MarketSimResponse {
  scenarios: ScenarioShare[]
  by_segment?: Record<string, ScenarioShare[]>
}

// ---------------------------------------------------------------------------
// Interview Lab
// ---------------------------------------------------------------------------

export interface ConverseRequest {
  question: string
  context?: Record<string, unknown>
}

export interface ConverseResponse {
  persona_id: string
  turn_number: number
  researcher_question: string
  consumer_response: string
  emotion_tag: string
  inconsistency_flag: boolean
}

export interface InterviewRequest {
  questions: string[]
  context?: Record<string, unknown>
}

export interface InterviewResponse {
  persona_id: string
  turns: ConverseResponse[]
  total_turns: number
}

export interface PurchaseDecisionRequest {
  product_name: string
  price_cny: number
  core_selling_points: string[]
}

export interface PurchaseDecisionResponse {
  persona_id: string
  product_name: string
  price_cny: number
  final_decision: string
  confidence: number
  stages: Record<string, unknown>[]
  stage_count: number
}

// ---------------------------------------------------------------------------
// Segment Comparison
// ---------------------------------------------------------------------------

export interface SegmentComparisonItem {
  attribute: string
  method: string
  t_statistic: number
  p_value: number
  corrected_p_value: number | null
  significant: boolean
  corrected_significant: boolean | null
  cohens_d: number
  effect_size: string
  mean_a: number
  mean_b: number
}

export interface SegmentComparisonResponse {
  segment_a: string
  segment_b: string
  n_a: number
  n_b: number
  overall_test: {
    method: string
    statistic: number
    p_value: number
    significant: boolean
  }
  per_attribute: SegmentComparisonItem[]
  interpretation: string
}

// ---------------------------------------------------------------------------
// Module 7: NL parser, reports, visualisation, latent class
// ---------------------------------------------------------------------------

export interface ParseScenarioRequest {
  text: string
}

export interface LatentClassRequest {
  n_classes?: number
  n_draws?: number
  n_tune?: number
  n_chains?: number
  target_accept?: number
}

export interface LatentClassResponse {
  analysis_id: string
  study_id: string
  n_classes: number
  converged: boolean
  rhat_max: number
  ess_bulk_min: number
  ess_tail_min: number
  class_probs: Record<string, number>
  class_utilities: Record<string, Record<string, number>>
  individual_class_probs: Record<string, Record<string, number>>
  assigned_class: Record<string, string>
  processing_time_seconds: number
  completed_at: string | null
}

export type EChartsOption = Record<string, unknown>

// ---------------------------------------------------------------------------
// Cost & Health
// ---------------------------------------------------------------------------

export interface CostStatus {
  fuse_status: string
  total_cost_cny: number
  daily_cost_cny: number
  daily_budget_cny: number
  warning: boolean
  details?: Record<string, unknown>
}

export interface HealthStatus {
  status: string
  version: string
  environment: string
  timestamp: string
}

export interface ReadyStatus {
  status: string
  checks: Record<string, { name: string; status: string; latency_ms: number; message?: string }>
  timestamp: string
}

export interface MetricsResponse {
  data: string
}

export interface DashboardSummaryResponse {
  summary: {
    total_studies: number
    total_personas: number
    studies_by_status: Record<string, number>
    recent_studies_last_7d: number
  }
  recent_studies: Array<{
    study_id: string
    product_category: string
    status: string
    created_at: string
  }>
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

export interface ProviderConfig {
  enabled?: boolean
  api_key_set?: boolean
  base_url?: string
  model?: string
  api_key?: string
}

export interface LLMSettings {
  provider: string
  model: string
  temperature: number
  max_tokens: number
  timeout_seconds?: number
  base_url?: string
  api_key?: string
}

export interface SystemSettings {
  llm: LLMSettings
  providers?: Record<string, ProviderConfig>
  cost_budget_daily: number
  cost_budget_monthly: number
  pass_threshold: number
  excellent_threshold: number
  max_score?: number
  study_defaults?: {
    n_choice_sets?: number
    n_alternatives?: number
    sample_size?: number
    d_efficiency_target?: number
  }
}

export interface AdminSettings {
  environment: string
  log_level: string
  llm: {
    provider: string
    model: string
    temperature: number
    max_tokens: number
    timeout_seconds?: number
  }
  providers?: Record<string, ProviderConfig>
  available_models?: Record<string, Record<string, string>>
  cost_fuse: {
    single_study_cny?: number
    daily_cny: number
    monthly_cny: number
  }
  study_defaults?: {
    n_choice_sets?: number
    n_alternatives?: number
    sample_size?: number
    d_efficiency_target?: number
  }
  authenticity: {
    pass_threshold: number
    excellent_threshold: number
    max_score?: number
  }
}

// ---------------------------------------------------------------------------
// Admin / Audit
// ---------------------------------------------------------------------------

export interface AuditLogEntry {
  timestamp: string
  user_id: string
  action: string
  resource: string
  resource_id: string
  result: string
  ip_address: string
  data: Record<string, unknown>
}

export interface AuditLogListResponse {
  total: number
  page: number
  page_size: number
  entries: AuditLogEntry[]
}

// ---------------------------------------------------------------------------
// Authentication
// ---------------------------------------------------------------------------

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  role: 'researcher' | 'admin'
  expires_in_minutes: number
}
