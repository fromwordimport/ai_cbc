import { create } from 'zustand'
import type { StudySummary, AnalysisJobStatus } from '@/types/api'

const TERMINAL_STATUSES = new Set(['COMPLETED', 'FAILED', 'CANCELLED', 'TIMED_OUT'])

interface AppState {
  // Selected study & analysis
  selectedStudyId: string | null
  selectedAnalysisId: string | null
  setSelectedStudy: (studyId: string | null) => void
  setSelectedAnalysis: (analysisId: string | null) => void

  // Studies list
  studies: StudySummary[]
  setStudies: (studies: StudySummary[]) => void

  // Running analysis jobs
  runningJobs: AnalysisJobStatus[]
  completedJobs: AnalysisJobStatus[]
  addJob: (job: AnalysisJobStatus) => void
  updateJob: (job: AnalysisJobStatus) => void
  removeJob: (analysisId: string) => void
  clearCompletedJobs: () => void
  setJobs: (jobs: AnalysisJobStatus[]) => void
}

export const useAppStore = create<AppState>((set) => ({
  selectedStudyId: null,
  selectedAnalysisId: null,
  setSelectedStudy: (studyId) => set({ selectedStudyId: studyId }),
  setSelectedAnalysis: (analysisId) => set({ selectedAnalysisId: analysisId }),

  studies: [],
  setStudies: (studies) => set({ studies }),

  runningJobs: [],
  completedJobs: [],
  addJob: (job) =>
    set((state) => {
      if (TERMINAL_STATUSES.has(job.status)) {
        return {
          runningJobs: state.runningJobs.filter((j) => j.analysis_id !== job.analysis_id),
          completedJobs: [job, ...state.completedJobs.filter((j) => j.analysis_id !== job.analysis_id)].slice(0, 10),
        }
      }
      return {
        runningJobs: [...state.runningJobs.filter((j) => j.analysis_id !== job.analysis_id), job],
      }
    }),
  updateJob: (job) =>
    set((state) => {
      if (TERMINAL_STATUSES.has(job.status)) {
        return {
          runningJobs: state.runningJobs.filter((j) => j.analysis_id !== job.analysis_id),
          completedJobs: [job, ...state.completedJobs.filter((j) => j.analysis_id !== job.analysis_id)].slice(0, 10),
        }
      }
      const exists = state.runningJobs.some((j) => j.analysis_id === job.analysis_id)
      if (exists) {
        return {
          runningJobs: state.runningJobs.map((j) =>
            j.analysis_id === job.analysis_id ? job : j,
          ),
        }
      }
      return { runningJobs: [...state.runningJobs, job] }
    }),
  removeJob: (analysisId) =>
    set((state) => ({
      runningJobs: state.runningJobs.filter((j) => j.analysis_id !== analysisId),
      completedJobs: state.completedJobs.filter((j) => j.analysis_id !== analysisId),
    })),
  clearCompletedJobs: () => set({ completedJobs: [] }),
  setJobs: (jobs) =>
    set(() => {
      const running: AnalysisJobStatus[] = []
      const completed: AnalysisJobStatus[] = []
      const seen = new Set<string>()
      for (const job of jobs) {
        if (seen.has(job.analysis_id)) continue
        seen.add(job.analysis_id)
        if (TERMINAL_STATUSES.has(job.status)) {
          completed.push(job)
        } else {
          running.push(job)
        }
      }
      return {
        runningJobs: running,
        completedJobs: completed.slice(-10),
      }
    }),
}))
