import { describe, it, expect, beforeEach } from 'vitest'
import { useAppStore } from '@/stores/appStore'
import type { AnalysisJobStatus } from '@/types/api'

const makeJob = (id: string, status: AnalysisJobStatus['status']): AnalysisJobStatus => ({
  analysis_id: id,
  study_id: 's1',
  status,
  model_type: 'hb',
  queued_at: new Date().toISOString(),
  started_at: null,
  completed_at: null,
  estimated_duration_seconds: 0,
  progress_percent: 0,
})

describe('appStore', () => {
  beforeEach(() => {
    useAppStore.setState(useAppStore.getInitialState())
  })

  it('initial state is empty', () => {
    const state = useAppStore.getState()
    expect(state.studies).toEqual([])
    expect(state.runningJobs).toEqual([])
    expect(state.completedJobs).toEqual([])
    expect(state.selectedStudyId).toBeNull()
  })

  it('setStudies updates studies', () => {
    useAppStore.getState().setStudies([{ study_id: 's1' } as any])
    expect(useAppStore.getState().studies).toHaveLength(1)
  })

  it('addJob puts non-terminal job into runningJobs', () => {
    const job = makeJob('a1', 'RUNNING')
    useAppStore.getState().addJob(job)
    expect(useAppStore.getState().runningJobs).toContainEqual(job)
    expect(useAppStore.getState().completedJobs).toHaveLength(0)
  })

  it('addJob moves terminal job to completedJobs', () => {
    const job = makeJob('a1', 'COMPLETED')
    useAppStore.getState().addJob(job)
    expect(useAppStore.getState().runningJobs).toHaveLength(0)
    expect(useAppStore.getState().completedJobs).toContainEqual(job)
  })

  it('updateJob transitions from running to completed', () => {
    const running = makeJob('a1', 'RUNNING')
    useAppStore.getState().addJob(running)
    const completed = makeJob('a1', 'COMPLETED')
    useAppStore.getState().updateJob(completed)
    expect(useAppStore.getState().runningJobs).toHaveLength(0)
    expect(useAppStore.getState().completedJobs[0].status).toBe('COMPLETED')
  })

  it('updateJob appends unknown running job', () => {
    const running = makeJob('a1', 'RUNNING')
    useAppStore.getState().updateJob(running)
    expect(useAppStore.getState().runningJobs).toContainEqual(running)
  })

  it('completedJobs keeps only latest 10', () => {
    for (let i = 0; i < 12; i++) {
      useAppStore.getState().addJob(makeJob(`a${i}`, 'COMPLETED'))
    }
    expect(useAppStore.getState().completedJobs).toHaveLength(10)
    expect(useAppStore.getState().completedJobs[0].analysis_id).toBe('a11')
  })

  it('removeJob deletes from both lists', () => {
    useAppStore.getState().addJob(makeJob('a1', 'RUNNING'))
    useAppStore.getState().addJob(makeJob('a2', 'COMPLETED'))
    useAppStore.getState().removeJob('a1')
    useAppStore.getState().removeJob('a2')
    expect(useAppStore.getState().runningJobs).toHaveLength(0)
    expect(useAppStore.getState().completedJobs).toHaveLength(0)
  })

  it('clearCompletedJobs empties completed list', () => {
    useAppStore.getState().addJob(makeJob('a1', 'COMPLETED'))
    useAppStore.getState().clearCompletedJobs()
    expect(useAppStore.getState().completedJobs).toHaveLength(0)
  })

  it('updateJob updates existing non-terminal job', () => {
    const running = makeJob('a1', 'RUNNING')
    useAppStore.getState().addJob(running)
    const updated = makeJob('a1', 'QUEUED')
    useAppStore.getState().updateJob(updated)
    expect(useAppStore.getState().runningJobs[0].status).toBe('QUEUED')
    expect(useAppStore.getState().completedJobs).toHaveLength(0)
  })

  it('addJob deduplicates running jobs', () => {
    const running = makeJob('a1', 'RUNNING')
    useAppStore.getState().addJob(running)
    const running2 = makeJob('a1', 'RUNNING')
    useAppStore.getState().addJob(running2)
    expect(useAppStore.getState().runningJobs).toHaveLength(1)
  })

  it('addJob moves previously running job to completed when terminal', () => {
    useAppStore.getState().addJob(makeJob('a1', 'RUNNING'))
    useAppStore.getState().addJob(makeJob('a1', 'COMPLETED'))
    expect(useAppStore.getState().runningJobs).toHaveLength(0)
    expect(useAppStore.getState().completedJobs).toHaveLength(1)
  })

  it('selected study and analysis can be set', () => {
    useAppStore.getState().setSelectedStudy('s1')
    useAppStore.getState().setSelectedAnalysis('a1')
    expect(useAppStore.getState().selectedStudyId).toBe('s1')
    expect(useAppStore.getState().selectedAnalysisId).toBe('a1')
  })
})
