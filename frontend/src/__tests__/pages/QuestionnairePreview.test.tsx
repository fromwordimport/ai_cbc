import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import QuestionnairePreview from '@/pages/QuestionnairePreview'

const getQuestionnaire = vi.fn()

vi.mock('@/services/api', () => ({
  getQuestionnaire: (...args: any[]) => getQuestionnaire(...args),
}))

describe('QuestionnairePreview', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const renderPage = () =>
    render(
      <MemoryRouter initialEntries={['/studies/s1/questionnaire']}>
        <Routes>
          <Route path="/studies/:studyId/questionnaire" element={<QuestionnairePreview />} />
        </Routes>
      </MemoryRouter>,
    )

  it('renders questionnaire details and choice sets', async () => {
    getQuestionnaire.mockResolvedValue({
      design_params: {
        algorithm: 'd_optimal',
        d_efficiency: 0.85,
        n_choice_sets: 2,
        n_alternatives: 2,
        include_none: false,
      },
      choice_sets: [
        {
          choice_set_id: 'cs1',
          alternatives: [
            { alt_index: 0, attributes: { price: 2999, brand: 'A' } },
            { alt_index: 1, attributes: { price: 3299, brand: 'B' } },
          ],
        },
      ],
    })

    renderPage()
    await waitFor(() => expect(screen.getByText('d_optimal')).toBeInTheDocument())
    expect(screen.getByText('0.850')).toBeInTheDocument()
    expect(screen.getByText('选择集 #cs1')).toBeInTheDocument()
    expect(screen.getByText('选项 A')).toBeInTheDocument()
  })

  it('shows error on fetch failure', async () => {
    getQuestionnaire.mockRejectedValue(new Error('not found'))
    renderPage()
    await waitFor(() => expect(screen.getByText('not found')).toBeInTheDocument())
  })
})
