import axios, { type InternalAxiosRequestConfig } from 'axios'
import { message } from 'antd'
import type {
  StudyListResponse,
  StudyDetail,
  StudyUpdateRequest,
  CreateStudyRequest,
  GenerateQuestionnaireResponse,
  QuestionnaireDetail,
  GeneratePersonasRequest,
  GeneratePersonasResponse,
  SimulateResponsesRequest,
  SimulateResponsesResponse,
  RawDatasetExportResponse,
  PersonaDetail,
  PersonaFullDetail,
  AnalysisJobStatus,
  AnalysisResultResponse,
  ImportanceResponse,
  WTPResponse,
  MarketSimRequest,
  MarketSimResponse,
  PersonaListResponse,
  ProductScenario,
  ConverseRequest,
  ConverseResponse,
  SegmentComparisonResponse,
  CostStatus,
  HealthStatus,
  ReadyStatus,
  MetricsResponse,
  DashboardSummaryResponse,
  StudyDesignResponse,
  AttributeDefinition,
  ProhibitedPair,
  PersonaResponseSummary,
  ValidateResponse,
  LayerResponse,
  InterviewRequest,
  InterviewResponse,
  PurchaseDecisionRequest,
  PurchaseDecisionResponse,
  AuditLogListResponse,
  AdminSettings,
} from '@/types/api'

const API_KEY = import.meta.env.VITE_API_KEY || 'dev-key-change-in-prod'
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'
const ROOT_API_BASE_URL = import.meta.env.VITE_ROOT_API_BASE_URL || ''

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 60000,
})

// Root-level endpoints are not prefixed with /api/v1.
const rootApi = axios.create({
  baseURL: ROOT_API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
})

// ---------------------------------------------------------------------------
// Request interceptor: inject API Key
// ---------------------------------------------------------------------------

export const injectApiKey = (config: InternalAxiosRequestConfig) => {
  config.headers.set('X-API-Key', API_KEY)
  return config
}

api.interceptors.request.use(injectApiKey, (error) => Promise.reject(error))
rootApi.interceptors.request.use(injectApiKey, (error) => Promise.reject(error))

// ---------------------------------------------------------------------------
// Response interceptor: unified error handling
// ---------------------------------------------------------------------------

export const handleError = (error: { response?: { status: number; data?: { detail?: string; error?: string } }; request?: unknown; message?: string }) => {
  if (error.response) {
    const status = error.response.status
    const detail = error.response.data?.detail || error.response.data?.error || '未知错误'
    if (status === 401) {
      message.error('认证失败，请检查 API Key')
    } else if (status === 403) {
      message.error('权限不足')
    } else if (status === 404) {
      message.error('资源不存在')
    } else if (status === 400) {
      message.error(`请求错误: ${detail}`)
    } else if (status >= 500) {
      message.error('服务器错误，请稍后重试')
    } else {
      message.error(`请求失败 (${status}): ${detail}`)
    }
  } else if (error.request) {
    message.error('网络连接失败，请检查后端服务是否运行')
  } else {
    message.error(`请求配置错误: ${error.message || '未知'}`)
  }
  return Promise.reject(error)
}

api.interceptors.response.use((response) => response, handleError)
rootApi.interceptors.response.use((response) => response, handleError)

// ---------------------------------------------------------------------------
// Studies
// ---------------------------------------------------------------------------

export const getStudies = async (page = 1, pageSize = 20): Promise<StudyListResponse> => {
  const { data } = await api.get('/studies', { params: { page, page_size: pageSize } })
  return data
}

export const getStudy = async (studyId: string): Promise<StudyDetail> => {
  const { data } = await api.get(`/studies/${studyId}`)
  return data
}

export const createStudy = async (request: CreateStudyRequest): Promise<StudyDetail> => {
  const { data } = await api.post('/studies', request)
  return data
}

export const updateStudy = async (
  studyId: string,
  request: StudyUpdateRequest,
): Promise<StudyDetail> => {
  const { data } = await api.put(`/studies/${studyId}`, request)
  return data
}

export const generateQuestionnaire = async (
  studyId: string,
): Promise<GenerateQuestionnaireResponse> => {
  const { data } = await api.post(`/studies/${studyId}/generate`)
  return data
}

export const getQuestionnaire = async (studyId: string): Promise<QuestionnaireDetail> => {
  const { data } = await api.get(`/studies/${studyId}/questionnaire`)
  return data
}

export const getStudyDesign = async (studyId: string): Promise<StudyDesignResponse> => {
  const { data } = await api.get(`/studies/${studyId}/design`)
  return data
}

export const updateStudyDesign = async (
  studyId: string,
  attributes: AttributeDefinition[],
  prohibitedPairs?: ProhibitedPair[],
): Promise<StudyDesignResponse> => {
  const { data } = await api.put(`/studies/${studyId}/design`, {
    attributes,
    prohibited_pairs: prohibitedPairs,
  })
  return data
}

export const deleteStudy = async (studyId: string): Promise<void> => {
  await api.delete(`/studies/${studyId}`)
}

export const simulateResponses = async (
  studyId: string,
  request: SimulateResponsesRequest,
): Promise<SimulateResponsesResponse> => {
  const { data } = await api.post(`/studies/${studyId}/simulate-responses`, request)
  return data
}

export const listResponses = async (studyId: string): Promise<PersonaResponseSummary[]> => {
  const { data } = await api.get(`/studies/${studyId}/responses`)
  return data
}

export const exportDataset = async (studyId: string): Promise<RawDatasetExportResponse> => {
  const { data } = await api.get(`/studies/${studyId}/responses/export`)
  return data
}

// ---------------------------------------------------------------------------
// Analysis
// ---------------------------------------------------------------------------

export const analyzeStudy = async (
  studyId: string,
  modelType: string = 'hb',
  params?: {
    n_draws?: number
    n_tune?: number
    n_chains?: number
    target_accept?: number
  },
): Promise<AnalysisJobStatus> => {
  const { data } = await api.post(`/studies/${studyId}/analyze`, {
    model_type: modelType,
    n_draws: params?.n_draws ?? 1000,
    n_tune: params?.n_tune ?? 1000,
    n_chains: params?.n_chains ?? 4,
    target_accept: params?.target_accept ?? 0.9,
  })
  return data
}

export const getAnalysisStatus = async (
  studyId: string,
  analysisId: string,
): Promise<AnalysisJobStatus> => {
  const { data } = await api.get(`/studies/${studyId}/analysis/${analysisId}/status`)
  return data
}

export const getAnalysisResult = async (
  studyId: string,
  analysisId: string,
): Promise<AnalysisResultResponse> => {
  const { data } = await api.get(`/studies/${studyId}/analysis/${analysisId}`)
  return data
}

export const listAnalyses = async (studyId: string): Promise<AnalysisJobStatus[]> => {
  const { data } = await api.get(`/studies/${studyId}/analysis`)
  return data
}

export const deleteAnalysis = async (studyId: string, analysisId: string): Promise<void> => {
  await api.delete(`/studies/${studyId}/analysis/${analysisId}`)
}

export const getConvergence = async (
  studyId: string,
  analysisId: string,
): Promise<import('@/types/api').ConvergenceDiagnostics> => {
  const { data } = await api.get(`/studies/${studyId}/analysis/${analysisId}/convergence`)
  return data
}

export const getImportance = async (
  studyId: string,
  analysisId: string,
): Promise<ImportanceResponse> => {
  const { data } = await api.get(`/studies/${studyId}/analysis/${analysisId}/importance`)
  return data
}

export const getWTP = async (studyId: string, analysisId: string): Promise<WTPResponse> => {
  const { data } = await api.get(`/studies/${studyId}/analysis/${analysisId}/wtp`)
  return data
}

// ---------------------------------------------------------------------------
// Market Simulation
// ---------------------------------------------------------------------------

export const simulateMarket = async (
  studyId: string,
  analysisId: string,
  request: MarketSimRequest,
): Promise<MarketSimResponse> => {
  const { data } = await api.post(
    `/studies/${studyId}/analysis/${analysisId}/simulate-market`,
    request,
  )
  return data
}

// ---------------------------------------------------------------------------
// Personas
// ---------------------------------------------------------------------------

export const getPersonas = async (
  page = 1,
  pageSize = 20,
  studyId?: string,
  segment?: string,
): Promise<PersonaListResponse> => {
  const params: Record<string, string | number> = { page, page_size: pageSize }
  if (studyId) params.study_id = studyId
  if (segment) params.segment = segment
  const { data } = await api.get('/personas', { params })
  return data
}

export const getPersona = async (personaId: string): Promise<PersonaDetail> => {
  const { data } = await api.get(`/personas/${personaId}`)
  return data
}

export const getPersonaFullDetail = async (personaId: string): Promise<PersonaFullDetail> => {
  const { data } = await api.get(`/personas/${personaId}`)
  return data
}

export const generatePersonas = async (
  request: GeneratePersonasRequest,
): Promise<GeneratePersonasResponse> => {
  const { data } = await api.post('/personas/generate', request)
  return data
}

export const deletePersona = async (personaId: string): Promise<void> => {
  await api.delete(`/personas/${personaId}`)
}

export const validatePersona = async (personaId: string): Promise<ValidateResponse> => {
  const { data } = await api.post(`/personas/${personaId}/validate`)
  return data
}

export const getPersonaLayer = async (personaId: string, layer: number): Promise<LayerResponse> => {
  const { data } = await api.get(`/personas/${personaId}/layers/${layer}`)
  return data
}

// ---------------------------------------------------------------------------
// Interview Lab
// ---------------------------------------------------------------------------

export const converse = async (
  personaId: string,
  request: ConverseRequest,
): Promise<ConverseResponse> => {
  const { data } = await api.post(`/personas/${personaId}/converse`, request)
  return data
}

export const runInterview = async (
  personaId: string,
  request: InterviewRequest,
): Promise<InterviewResponse> => {
  const { data } = await api.post(`/personas/${personaId}/interview`, request)
  return data
}

export const simulatePurchaseDecision = async (
  personaId: string,
  request: PurchaseDecisionRequest,
): Promise<PurchaseDecisionResponse> => {
  const { data } = await api.post(`/personas/${personaId}/purchase-decision`, request)
  return data
}

// ---------------------------------------------------------------------------
// Segment Comparison
// ---------------------------------------------------------------------------

export const getSegmentComparison = async (
  studyId: string,
  analysisId: string,
  segmentA: string,
  segmentB: string,
): Promise<SegmentComparisonResponse> => {
  const { data } = await api.get(
    `/studies/${studyId}/analysis/${analysisId}/segment-comparison`,
    { params: { segment_a: segmentA, segment_b: segmentB } },
  )
  return data
}

// ---------------------------------------------------------------------------
// Module 7: NL parser, reports, visualisation, latent class
// ---------------------------------------------------------------------------

export const parseScenario = async (
  studyId: string,
  request: import('@/types/api').ParseScenarioRequest,
): Promise<ProductScenario> => {
  const { data } = await api.post(`/studies/${studyId}/parse-scenario`, request)
  return data
}

export const getAnalysisReport = async (
  studyId: string,
  analysisId: string,
  format: 'markdown' | 'html' = 'markdown',
): Promise<string> => {
  const { data } = await api.get(
    `/studies/${studyId}/analysis/${analysisId}/report`,
    { params: { format }, responseType: 'text' },
  )
  return data
}

export const getAnalysisVisualization = async (
  studyId: string,
  analysisId: string,
  chart:
    | 'importance_bar'
    | 'importance_pie'
    | 'utility_distribution'
    | 'market_share'
    | 'wtp'
    | 'dashboard',
  simId?: string,
): Promise<import('@/types/api').EChartsOption> => {
  const params: Record<string, string> = { chart }
  if (simId) params.sim_id = simId
  const { data } = await api.get(
    `/studies/${studyId}/analysis/${analysisId}/visualization`,
    { params },
  )
  return data
}

export const runLatentClassAnalysis = async (
  studyId: string,
  request: import('@/types/api').LatentClassRequest = {},
): Promise<AnalysisJobStatus> => {
  const { data } = await api.post(`/studies/${studyId}/analysis/latent-class`, request)
  return data
}

export const getLatentClassResult = async (
  studyId: string,
  analysisId: string,
): Promise<import('@/types/api').LatentClassResponse> => {
  const { data } = await api.get(`/studies/${studyId}/analysis/${analysisId}/latent-class`)
  return data
}

// ---------------------------------------------------------------------------
// Cost, Health, Metrics, Dashboard (root-level endpoints)
// ---------------------------------------------------------------------------

export const getCostStatus = async (): Promise<CostStatus> => {
  const { data } = await rootApi.get('/cost-status')
  return data
}

export const getHealthCheck = async (): Promise<HealthStatus> => {
  const { data } = await rootApi.get('/health')
  return data
}

export const getReadyCheck = async (): Promise<ReadyStatus> => {
  const { data } = await rootApi.get('/ready')
  return data
}

export const getMetrics = async (): Promise<MetricsResponse> => {
  const { data } = await rootApi.get('/metrics')
  return data
}

export const getDashboardSummary = async (): Promise<DashboardSummaryResponse> => {
  const { data } = await rootApi.get('/dashboard/summary')
  return data
}

// ---------------------------------------------------------------------------
// Admin
// ---------------------------------------------------------------------------

export const getAdminSettings = async (): Promise<AdminSettings> => {
  const { data } = await api.get('/admin/settings')
  return data as AdminSettings
}

export const updateAdminSettings = async (
  payload: Record<string, unknown>,
): Promise<Record<string, unknown>> => {
  const { data } = await api.put('/admin/settings', payload)
  return data
}

export const getAuditLogs = async (
  params?: Record<string, string | number>,
): Promise<AuditLogListResponse> => {
  const { data } = await api.get('/admin/audit-logs', { params })
  return data
}

export default api
