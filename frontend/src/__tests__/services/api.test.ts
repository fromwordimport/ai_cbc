import { describe, it, expect, vi, beforeEach } from 'vitest'
import axios, { type InternalAxiosRequestConfig } from 'axios'

const messageError = vi.fn()

vi.mock('antd', () => ({
  message: {
    error: messageError,
    success: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}))

const mockInstance = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
  interceptors: {
    request: { use: vi.fn() },
    response: { use: vi.fn() },
  },
}))

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => mockInstance),
    defaults: {},
    AxiosHeaders: class AxiosHeaders {
      private _headers: Record<string, string> = {}
      set(name: string, value: string) { this._headers[name] = value }
      get(name: string) { return this._headers[name] }
    },
  },
}))

let api: typeof import('@/services/api')

describe('API service wrappers', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    api = await import('@/services/api')
  })

  it('getStudies returns list response', async () => {
    const payload = { studies: [], total: 0, page: 1, page_size: 20 }
    mockInstance.get.mockResolvedValueOnce({ data: payload })
    const res = await api.getStudies()
    expect(mockInstance.get).toHaveBeenCalledWith('/studies', { params: { page: 1, page_size: 20 } })
    expect(res).toEqual(payload)
  })

  it('createStudy posts request', async () => {
    const request = { product_category: '洗碗机', research_goal: 'test' }
    mockInstance.post.mockResolvedValueOnce({ data: { study_id: 's1', ...request } })
    const res = await api.createStudy(request as any)
    expect(mockInstance.post).toHaveBeenCalledWith('/studies', request)
    expect(res.study_id).toBe('s1')
  })

  it('updateStudy puts request', async () => {
    mockInstance.put.mockResolvedValueOnce({ data: { study_id: 's1' } })
    const res = await api.updateStudy('s1', { product_category: 'x' } as any)
    expect(mockInstance.put).toHaveBeenCalledWith('/studies/s1', { product_category: 'x' })
    expect(res.study_id).toBe('s1')
  })

  it('getStudy fetches detail', async () => {
    mockInstance.get.mockResolvedValueOnce({ data: { study_id: 's1' } })
    const res = await api.getStudy('s1')
    expect(mockInstance.get).toHaveBeenCalledWith('/studies/s1')
    expect(res.study_id).toBe('s1')
  })

  it('deleteStudy calls delete', async () => {
    mockInstance.delete.mockResolvedValueOnce({ data: {} })
    await api.deleteStudy('s1')
    expect(mockInstance.delete).toHaveBeenCalledWith('/studies/s1')
  })

  it('generateQuestionnaire posts', async () => {
    mockInstance.post.mockResolvedValueOnce({ data: { questionnaire_id: 'q1' } })
    const res = await api.generateQuestionnaire('s1')
    expect(mockInstance.post).toHaveBeenCalledWith('/studies/s1/generate')
    expect(res.questionnaire_id).toBe('q1')
  })

  it('getQuestionnaire fetches', async () => {
    mockInstance.get.mockResolvedValueOnce({ data: { choice_sets: [], design_params: { algorithm: 'doe', d_efficiency: null, a_efficiency: null, n_attributes: 0, n_choice_sets: 0, n_alternatives: 0, include_none: false }, created_at: '' } })
    const res = await api.getQuestionnaire('s1')
    expect(mockInstance.get).toHaveBeenCalledWith('/studies/s1/questionnaire')
    expect(res.choice_sets).toEqual([])
  })

  it('getStudyDesign fetches', async () => {
    mockInstance.get.mockResolvedValueOnce({ data: { attributes: [] } })
    const res = await api.getStudyDesign('s1')
    expect(mockInstance.get).toHaveBeenCalledWith('/studies/s1/design')
    expect(res.attributes).toEqual([])
  })

  it('updateStudyDesign puts', async () => {
    mockInstance.put.mockResolvedValueOnce({ data: { attributes: [] } })
    const res = await api.updateStudyDesign('s1', [])
    expect(mockInstance.put).toHaveBeenCalledWith('/studies/s1/design', { attributes: [], prohibited_pairs: undefined })
    expect(res.attributes).toEqual([])
  })

  it('simulateResponses posts', async () => {
    mockInstance.post.mockResolvedValueOnce({ data: { study_id: 's1', questionnaire_id: 'q1', simulated: 10, failed: 0, summaries: [] } })
    const res = await api.simulateResponses('s1', { persona_ids: [], mode: 'rule' })
    expect(mockInstance.post).toHaveBeenCalledWith('/studies/s1/simulate-responses', { persona_ids: [], mode: 'rule' })
    expect(res.simulated).toBe(10)
  })

  it('listResponses fetches', async () => {
    mockInstance.get.mockResolvedValueOnce({ data: [] })
    const res = await api.listResponses('s1')
    expect(mockInstance.get).toHaveBeenCalledWith('/studies/s1/responses')
    expect(res).toEqual([])
  })

  it('exportDataset fetches', async () => {
    mockInstance.get.mockResolvedValueOnce({ data: { study_id: 's1', n_respondents: 1, n_choice_sets: 1, n_alternatives: 2, n_total_records: 2, choice_records: [] } })
    const res = await api.exportDataset('s1')
    expect(mockInstance.get).toHaveBeenCalledWith('/studies/s1/responses/export')
    expect(res.n_respondents).toBe(1)
  })

  it('analyzeStudy posts with defaults', async () => {
    mockInstance.post.mockResolvedValueOnce({ data: { analysis_id: 'a1' } })
    const res = await api.analyzeStudy('s1', 'hb')
    expect(mockInstance.post).toHaveBeenCalledWith('/studies/s1/analyze', {
      model_type: 'hb',
      n_draws: 1000,
      n_tune: 1000,
      n_chains: 4,
      target_accept: 0.9,
    })
    expect(res.analysis_id).toBe('a1')
  })

  it('getAnalysisStatus fetches', async () => {
    mockInstance.get.mockResolvedValueOnce({ data: { analysis_id: 'a1', status: 'COMPLETED' } })
    const res = await api.getAnalysisStatus('s1', 'a1')
    expect(mockInstance.get).toHaveBeenCalledWith('/studies/s1/analysis/a1/status')
    expect(res.status).toBe('COMPLETED')
  })

  it('getAnalysisResult fetches', async () => {
    mockInstance.get.mockResolvedValueOnce({ data: { analysis_id: 'a1' } })
    const res = await api.getAnalysisResult('s1', 'a1')
    expect(mockInstance.get).toHaveBeenCalledWith('/studies/s1/analysis/a1')
    expect(res.analysis_id).toBe('a1')
  })

  it('listAnalyses fetches', async () => {
    mockInstance.get.mockResolvedValueOnce({ data: [] })
    const res = await api.listAnalyses('s1')
    expect(mockInstance.get).toHaveBeenCalledWith('/studies/s1/analysis')
    expect(res).toEqual([])
  })

  it('deleteAnalysis calls delete', async () => {
    mockInstance.delete.mockResolvedValueOnce({ data: {} })
    await api.deleteAnalysis('s1', 'a1')
    expect(mockInstance.delete).toHaveBeenCalledWith('/studies/s1/analysis/a1')
  })

  it('getConvergence fetches', async () => {
    mockInstance.get.mockResolvedValueOnce({ data: { converged: true } })
    const res = await api.getConvergence('s1', 'a1')
    expect(mockInstance.get).toHaveBeenCalledWith('/studies/s1/analysis/a1/convergence')
    expect(res.converged).toBe(true)
  })

  it('getImportance fetches', async () => {
    mockInstance.get.mockResolvedValueOnce({ data: { overall: {} } })
    const res = await api.getImportance('s1', 'a1')
    expect(mockInstance.get).toHaveBeenCalledWith('/studies/s1/analysis/a1/importance')
    expect(res.overall).toEqual({})
  })

  it('getWTP fetches', async () => {
    mockInstance.get.mockResolvedValueOnce({ data: { wtp_values: {}, price_coefficient_summary: { mean: 0, median: 0, std: 0, negative_rate: 1, n_positive_outliers: 0 } } })
    const res = await api.getWTP('s1', 'a1')
    expect(mockInstance.get).toHaveBeenCalledWith('/studies/s1/analysis/a1/wtp')
    expect(res.wtp_values).toEqual({})
  })

  it('simulateMarket posts', async () => {
    mockInstance.post.mockResolvedValueOnce({ data: { scenarios: [] } })
    const res = await api.simulateMarket('s1', 'a1', { scenarios: [], rule: 'logit', include_none: false })
    expect(mockInstance.post).toHaveBeenCalledWith('/studies/s1/analysis/a1/simulate-market', { scenarios: [], rule: 'logit', include_none: false })
    expect(res.scenarios).toEqual([])
  })

  it('getPersonas fetches with params', async () => {
    mockInstance.get.mockResolvedValueOnce({ data: { personas: [] } })
    const res = await api.getPersonas(1, 20, 's1', 'seg')
    expect(mockInstance.get).toHaveBeenCalledWith('/personas', { params: { page: 1, page_size: 20, study_id: 's1', segment: 'seg' } })
    expect(res.personas).toEqual([])
  })

  it('getPersona fetches', async () => {
    mockInstance.get.mockResolvedValueOnce({ data: { persona_id: 'p1' } })
    const res = await api.getPersona('p1')
    expect(mockInstance.get).toHaveBeenCalledWith('/personas/p1')
    expect(res.persona_id).toBe('p1')
  })

  it('getPersonaFullDetail fetches', async () => {
    mockInstance.get.mockResolvedValueOnce({ data: { persona_id: 'p1' } })
    const res = await api.getPersonaFullDetail('p1')
    expect(mockInstance.get).toHaveBeenCalledWith('/personas/p1')
    expect(res.persona_id).toBe('p1')
  })

  it('generatePersonas posts', async () => {
    mockInstance.post.mockResolvedValueOnce({ data: { personas: [] } })
    const request = { study_id: 's1', n_personas: 10 }
    const res = await api.generatePersonas(request as any)
    expect(mockInstance.post).toHaveBeenCalledWith('/personas/generate', request)
    expect(res.personas).toEqual([])
  })

  it('deletePersona calls delete', async () => {
    mockInstance.delete.mockResolvedValueOnce({ data: {} })
    await api.deletePersona('p1')
    expect(mockInstance.delete).toHaveBeenCalledWith('/personas/p1')
  })

  it('validatePersona posts', async () => {
    mockInstance.post.mockResolvedValueOnce({ data: { persona_id: 'p1', schema_passed: true, logic_passed: true, logic_score: 1, logic_max_score: 1, schema_errors: [], logic_errors: [], overall_passed: true } })
    const res = await api.validatePersona('p1')
    expect(mockInstance.post).toHaveBeenCalledWith('/personas/p1/validate')
    expect(res.overall_passed).toBe(true)
  })

  it('getPersonaLayer fetches', async () => {
    mockInstance.get.mockResolvedValueOnce({ data: { persona_id: 'p1', layer_number: 1, layer_name: 'demographics', data: {} } })
    const res = await api.getPersonaLayer('p1', 1)
    expect(mockInstance.get).toHaveBeenCalledWith('/personas/p1/layers/1')
    expect(res.layer_number).toBe(1)
  })

  it('converse posts', async () => {
    mockInstance.post.mockResolvedValueOnce({ data: { persona_id: 'p1', turn_number: 1, researcher_question: 'hello', consumer_response: 'hi', emotion_tag: 'neutral', inconsistency_flag: false } })
    const res = await api.converse('p1', { question: 'hello' })
    expect(mockInstance.post).toHaveBeenCalledWith('/personas/p1/converse', { question: 'hello' })
    expect(res.consumer_response).toBe('hi')
  })

  it('runInterview posts', async () => {
    mockInstance.post.mockResolvedValueOnce({ data: { persona_id: 'p1', turns: [], total_turns: 0 } })
    const res = await api.runInterview('p1', { questions: ['q'] })
    expect(mockInstance.post).toHaveBeenCalledWith('/personas/p1/interview', { questions: ['q'] })
    expect(res.turns).toEqual([])
  })

  it('simulatePurchaseDecision posts', async () => {
    mockInstance.post.mockResolvedValueOnce({ data: { persona_id: 'p1', product_name: 'x', price_cny: 1, final_decision: 'buy', confidence: 0.9, stages: [], stage_count: 0 } })
    const res = await api.simulatePurchaseDecision('p1', { product_name: 'x', price_cny: 1, core_selling_points: [] })
    expect(mockInstance.post).toHaveBeenCalledWith('/personas/p1/purchase-decision', { product_name: 'x', price_cny: 1, core_selling_points: [] })
    expect(res.final_decision).toBe('buy')
  })

  it('getSegmentComparison fetches', async () => {
    mockInstance.get.mockResolvedValueOnce({ data: { segment_a: 'A', segment_b: 'B', n_a: 1, n_b: 1, overall_test: { method: 't', statistic: 0, p_value: 1, significant: false }, per_attribute: [], interpretation: '' } })
    const res = await api.getSegmentComparison('s1', 'a1', 'A', 'B')
    expect(mockInstance.get).toHaveBeenCalledWith(
      '/studies/s1/analysis/a1/segment-comparison',
      { params: { segment_a: 'A', segment_b: 'B' } },
    )
    expect(res.per_attribute).toEqual([])
  })

  it('parseScenario posts', async () => {
    mockInstance.post.mockResolvedValueOnce({ data: { name: 'x', attributes: {} } })
    const res = await api.parseScenario('s1', { text: 'desc' })
    expect(mockInstance.post).toHaveBeenCalledWith('/studies/s1/parse-scenario', { text: 'desc' })
    expect(res.name).toBe('x')
  })

  it('getAnalysisReport fetches text', async () => {
    mockInstance.get.mockResolvedValueOnce({ data: '# report' })
    const res = await api.getAnalysisReport('s1', 'a1', 'markdown')
    expect(mockInstance.get).toHaveBeenCalledWith('/studies/s1/analysis/a1/report', { params: { format: 'markdown' }, responseType: 'text' })
    expect(res).toBe('# report')
  })

  it('getAnalysisVisualization fetches option', async () => {
    mockInstance.get.mockResolvedValueOnce({ data: { option: {} } })
    const res = await api.getAnalysisVisualization('s1', 'a1', 'dashboard')
    expect(mockInstance.get).toHaveBeenCalledWith('/studies/s1/analysis/a1/visualization', { params: { chart: 'dashboard' } })
    expect(res.option).toEqual({})
  })

  it('getAnalysisVisualization passes sim_id', async () => {
    mockInstance.get.mockResolvedValueOnce({ data: { option: {} } })
    await api.getAnalysisVisualization('s1', 'a1', 'market_share', 'sim1')
    expect(mockInstance.get).toHaveBeenCalledWith('/studies/s1/analysis/a1/visualization', { params: { chart: 'market_share', sim_id: 'sim1' } })
  })

  it('runLatentClassAnalysis posts', async () => {
    mockInstance.post.mockResolvedValueOnce({ data: { analysis_id: 'a2' } })
    const res = await api.runLatentClassAnalysis('s1', { n_classes: 3 })
    expect(mockInstance.post).toHaveBeenCalledWith('/studies/s1/analysis/latent-class', { n_classes: 3 })
    expect(res.analysis_id).toBe('a2')
  })

  it('getLatentClassResult fetches', async () => {
    mockInstance.get.mockResolvedValueOnce({ data: { n_classes: 3 } })
    const res = await api.getLatentClassResult('s1', 'a1')
    expect(mockInstance.get).toHaveBeenCalledWith('/studies/s1/analysis/a1/latent-class')
    expect(res.n_classes).toBe(3)
  })

  it('root-level endpoints use rootApi', async () => {
    mockInstance.get.mockResolvedValue({ data: {} })
    await api.getCostStatus()
    expect(mockInstance.get).toHaveBeenCalledWith('/cost-status')
    await api.getHealthCheck()
    expect(mockInstance.get).toHaveBeenCalledWith('/health')
    await api.getReadyCheck()
    expect(mockInstance.get).toHaveBeenCalledWith('/ready')
    await api.getMetrics()
    expect(mockInstance.get).toHaveBeenCalledWith('/metrics')
    await api.getDashboardSummary()
    expect(mockInstance.get).toHaveBeenCalledWith('/dashboard/summary')
  })

  it('admin endpoints call correct paths', async () => {
    mockInstance.get.mockResolvedValueOnce({ data: { settings: {} } })
    await api.getAdminSettings()
    expect(mockInstance.get).toHaveBeenCalledWith('/admin/settings')

    mockInstance.put.mockResolvedValueOnce({ data: { updated: true } })
    await api.updateAdminSettings({ pass_threshold: 0.8 })
    expect(mockInstance.put).toHaveBeenCalledWith('/admin/settings', { pass_threshold: 0.8 })

    mockInstance.get.mockResolvedValueOnce({ data: { entries: [], total: 0 } })
    await api.getAuditLogs({ action: 'DELETE' })
    expect(mockInstance.get).toHaveBeenCalledWith('/admin/audit-logs', { params: { action: 'DELETE' } })
  })

  describe('interceptors', () => {
    it('request interceptor injects Authorization header when token exists', () => {
      localStorage.setItem('aicbc_token', 'test-token')
      const headers = new axios.AxiosHeaders()
      const config = { headers } as InternalAxiosRequestConfig
      const result = api.injectAuthToken(config)
      expect(result.headers.get('Authorization')).toBe('Bearer test-token')
      localStorage.removeItem('aicbc_token')
    })

    it('request interceptor omits Authorization when no token', () => {
      localStorage.removeItem('aicbc_token')
      const headers = new axios.AxiosHeaders()
      const config = { headers } as InternalAxiosRequestConfig
      const result = api.injectAuthToken(config)
      expect(result.headers.get('Authorization')).toBeUndefined()
    })

    it('handleError handles 401', async () => {
      const error = { response: { status: 401, data: {} } }
      await expect(api.handleError(error)).rejects.toBe(error)
      expect(messageError).toHaveBeenCalledWith('登录已过期，请重新登录')
    })

    it('handleError handles 403', async () => {
      const error = { response: { status: 403, data: {} } }
      await expect(api.handleError(error)).rejects.toBe(error)
      expect(messageError).toHaveBeenCalledWith('权限不足')
    })

    it('handleError handles 404', async () => {
      const error = { response: { status: 404, data: {} } }
      await expect(api.handleError(error)).rejects.toBe(error)
      expect(messageError).toHaveBeenCalledWith('资源不存在')
    })

    it('handleError handles 400 with detail', async () => {
      const error = { response: { status: 400, data: { detail: 'missing field' } } }
      await expect(api.handleError(error)).rejects.toBe(error)
      expect(messageError).toHaveBeenCalledWith('请求错误: missing field')
    })

    it('handleError handles 500', async () => {
      const error = { response: { status: 500, data: {} } }
      await expect(api.handleError(error)).rejects.toBe(error)
      expect(messageError).toHaveBeenCalledWith('服务器错误，请稍后重试')
    })

    it('handleError handles unknown status', async () => {
      const error = { response: { status: 418, data: { error: 'teapot' } } }
      await expect(api.handleError(error)).rejects.toBe(error)
      expect(messageError).toHaveBeenCalledWith('请求失败 (418): teapot')
    })

    it('handleError handles network error', async () => {
      const error = { request: {} }
      await expect(api.handleError(error)).rejects.toBe(error)
      expect(messageError).toHaveBeenCalledWith('网络连接失败，请检查后端服务是否运行')
    })

    it('handleError handles config error', async () => {
      const error = new Error('boom')
      await expect(api.handleError(error)).rejects.toBe(error)
      expect(messageError).toHaveBeenCalledWith('请求配置错误: boom')
    })
  })
})
