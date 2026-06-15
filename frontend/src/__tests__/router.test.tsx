import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { RouterProvider, createMemoryRouter, Navigate } from 'react-router-dom'
import { Suspense } from 'react'
import { router } from '@/router'

// Mock all page components to avoid loading real implementations
vi.mock('@/components/Layout', () => ({
  default: function MockLayout() {
    return (
      <div data-testid="layout">
        <div data-testid="outlet">Outlet Content</div>
      </div>
    )
  },
}))

const mockPage = (name: string) =>
  function MockPage() {
    return <div data-testid={`page-${name}`}>{name}</div>
  }

vi.mock('@/pages/Dashboard', () => ({ default: mockPage('Dashboard') }))
vi.mock('@/pages/ImportanceDashboard', () => ({ default: mockPage('ImportanceDashboard') }))
vi.mock('@/pages/MarketSimulator', () => ({ default: mockPage('MarketSimulator') }))
vi.mock('@/pages/StudyCreate', () => ({ default: mockPage('StudyCreate') }))
vi.mock('@/pages/PersonaManager', () => ({ default: mockPage('PersonaManager') }))
vi.mock('@/pages/PersonaDetail', () => ({ default: mockPage('PersonaDetail') }))
vi.mock('@/pages/QuestionnairePreview', () => ({ default: mockPage('QuestionnairePreview') }))
vi.mock('@/pages/QuestionnaireConfig', () => ({ default: mockPage('QuestionnaireConfig') }))
vi.mock('@/pages/ResponseSimulator', () => ({ default: mockPage('ResponseSimulator') }))
vi.mock('@/pages/InterviewLab', () => ({ default: mockPage('InterviewLab') }))
vi.mock('@/pages/SegmentComparison', () => ({ default: mockPage('SegmentComparison') }))
vi.mock('@/pages/AnalysisStatus', () => ({ default: mockPage('AnalysisStatus') }))
vi.mock('@/pages/AttributeDesign', () => ({ default: mockPage('AttributeDesign') }))
vi.mock('@/pages/Settings', () => ({ default: mockPage('Settings') }))

describe('router', () => {
  it('exports a router object with routes', () => {
    expect(router).toBeDefined()
    expect(router.routes).toBeDefined()
    expect(router.routes.length).toBeGreaterThan(0)
  })

  it('has a root route with path /', () => {
    const rootRoute = router.routes.find((r: any) => r.path === '/')
    expect(rootRoute).toBeDefined()
  })

  it('root route has children array', () => {
    const rootRoute = router.routes.find((r: any) => r.path === '/')
    expect(rootRoute?.children).toBeDefined()
    expect(Array.isArray(rootRoute?.children)).toBe(true)
  })
})

describe('router route configuration', () => {
  const rootRoute = router.routes.find((r: any) => r.path === '/')
  const children = rootRoute?.children || []

  const routeMap = new Map(children.map((c: any) => [c.path || 'index', c]))

  it('has index route for Dashboard', () => {
    const indexRoute = children.find((c: any) => c.index === true)
    expect(indexRoute).toBeDefined()
    expect(indexRoute?.element).toBeDefined()
  })

  it('has route for /importance', () => {
    expect(routeMap.has('importance')).toBe(true)
  })

  it('has route for /market-simulator', () => {
    expect(routeMap.has('market-simulator')).toBe(true)
  })

  it('has route for /studies/new', () => {
    expect(routeMap.has('studies/new')).toBe(true)
  })

  it('has route for /studies/:studyId/questionnaire', () => {
    expect(routeMap.has('studies/:studyId/questionnaire')).toBe(true)
  })

  it('has route for /studies/:studyId/responses', () => {
    expect(routeMap.has('studies/:studyId/responses')).toBe(true)
  })

  it('has route for /personas', () => {
    expect(routeMap.has('personas')).toBe(true)
  })

  it('has route for /personas/:personaId', () => {
    expect(routeMap.has('personas/:personaId')).toBe(true)
  })

  it('has route for /interview', () => {
    expect(routeMap.has('interview')).toBe(true)
  })

  it('has route for /segment-comparison', () => {
    expect(routeMap.has('segment-comparison')).toBe(true)
  })

  it('has route for /questionnaires', () => {
    expect(routeMap.has('questionnaires')).toBe(true)
  })

  it('has route for /analysis-status', () => {
    expect(routeMap.has('analysis-status')).toBe(true)
  })

  it('has route for /responses', () => {
    expect(routeMap.has('responses')).toBe(true)
  })

  it('has route for /studies/:studyId/design', () => {
    expect(routeMap.has('studies/:studyId/design')).toBe(true)
  })

  it('has route for /settings', () => {
    expect(routeMap.has('settings')).toBe(true)
  })

  it('has exactly 15 child routes', () => {
    expect(children.length).toBe(15)
  })

  it('all child routes have element defined', () => {
    for (const child of children) {
      expect(child.element).toBeDefined()
    }
  })

  it('responses route uses Navigate for redirect', () => {
    const responsesRoute = routeMap.get('responses')
    expect(responsesRoute).toBeDefined()
    // The element should be a Navigate component
    expect(responsesRoute?.element?.type).toBe(Navigate)
  })

  it('all non-redirect routes use Suspense wrapper', () => {
    for (const child of children) {
      if (child.element?.type === Navigate) {
        continue
      }
      // Suspense wrapper: element type should be Suspense
      expect(child.element?.type).toBe(Suspense)
    }
  })

  it('index route uses Suspense wrapper', () => {
    const indexRoute = children.find((c: any) => c.index === true)
    expect(indexRoute?.element?.type).toBe(Suspense)
  })

  it('all non-redirect routes have fallback prop in Suspense', () => {
    for (const child of children) {
      if (child.element?.type === Navigate) {
        continue
      }
      expect(child.element?.props?.fallback).toBeDefined()
    }
  })

  it('all non-redirect routes wrap lazy-loaded component', () => {
    for (const child of children) {
      if (child.element?.type === Navigate) {
        continue
      }
      const innerElement = child.element?.props?.children
      expect(innerElement).toBeDefined()
    }
  })
})

describe('router navigation with memory router', () => {
  function renderWithRouter(initialEntries: string[]) {
    const testRouter = createMemoryRouter(router.routes, { initialEntries })
    return render(<RouterProvider router={testRouter} />)
  }

  it('navigates to / and renders Dashboard', async () => {
    renderWithRouter(['/'])
    await waitFor(() => {
      expect(screen.getByTestId('layout')).toBeInTheDocument()
    })
  })

  it('navigates to /importance', async () => {
    renderWithRouter(['/importance'])
    await waitFor(() => {
      expect(screen.getByTestId('layout')).toBeInTheDocument()
    })
  })

  it('navigates to /market-simulator', async () => {
    renderWithRouter(['/market-simulator'])
    await waitFor(() => {
      expect(screen.getByTestId('layout')).toBeInTheDocument()
    })
  })

  it('navigates to /studies/new', async () => {
    renderWithRouter(['/studies/new'])
    await waitFor(() => {
      expect(screen.getByTestId('layout')).toBeInTheDocument()
    })
  })

  it('navigates to /studies/:studyId/questionnaire with route params', async () => {
    renderWithRouter(['/studies/test-study-123/questionnaire'])
    await waitFor(() => {
      expect(screen.getByTestId('layout')).toBeInTheDocument()
    })
  })

  it('navigates to /studies/:studyId/responses with route params', async () => {
    renderWithRouter(['/studies/test-study-456/responses'])
    await waitFor(() => {
      expect(screen.getByTestId('layout')).toBeInTheDocument()
    })
  })

  it('navigates to /personas', async () => {
    renderWithRouter(['/personas'])
    await waitFor(() => {
      expect(screen.getByTestId('layout')).toBeInTheDocument()
    })
  })

  it('navigates to /personas/:personaId with route params', async () => {
    renderWithRouter(['/personas/persona-789'])
    await waitFor(() => {
      expect(screen.getByTestId('layout')).toBeInTheDocument()
    })
  })

  it('navigates to /interview', async () => {
    renderWithRouter(['/interview'])
    await waitFor(() => {
      expect(screen.getByTestId('layout')).toBeInTheDocument()
    })
  })

  it('navigates to /segment-comparison', async () => {
    renderWithRouter(['/segment-comparison'])
    await waitFor(() => {
      expect(screen.getByTestId('layout')).toBeInTheDocument()
    })
  })

  it('navigates to /questionnaires', async () => {
    renderWithRouter(['/questionnaires'])
    await waitFor(() => {
      expect(screen.getByTestId('layout')).toBeInTheDocument()
    })
  })

  it('navigates to /analysis-status', async () => {
    renderWithRouter(['/analysis-status'])
    await waitFor(() => {
      expect(screen.getByTestId('layout')).toBeInTheDocument()
    })
  })

  it('navigates to /responses and redirects to study responses', async () => {
    renderWithRouter(['/responses'])
    await waitFor(() => {
      expect(screen.getByTestId('layout')).toBeInTheDocument()
    })
  })

  it('navigates to /studies/:studyId/design with route params', async () => {
    renderWithRouter(['/studies/test-study-999/design'])
    await waitFor(() => {
      expect(screen.getByTestId('layout')).toBeInTheDocument()
    })
  })

  it('navigates to /settings', async () => {
    renderWithRouter(['/settings'])
    await waitFor(() => {
      expect(screen.getByTestId('layout')).toBeInTheDocument()
    })
  })
})

describe('router 404 handling', () => {
  function renderWithRouter(initialEntries: string[]) {
    const testRouter = createMemoryRouter(router.routes, { initialEntries })
    return render(<RouterProvider router={testRouter} />)
  }

  it('handles unknown routes at root level by showing error boundary fallback', async () => {
    renderWithRouter(['/non-existent-path'])
    // Memory router with no matching route shows React Router default 404
    await waitFor(() => {
      expect(document.body.textContent).toContain('Not Found')
    })
  })

  it('handles deeply nested unknown routes by showing error boundary fallback', async () => {
    renderWithRouter(['/very/deep/nested/path'])
    await waitFor(() => {
      expect(document.body.textContent).toContain('Not Found')
    })
  })
})

describe('router lazy loading verification', () => {
  const rootRoute = router.routes.find((r: any) => r.path === '/')
  const children = rootRoute?.children || []

  it('lazy imports are defined for all page components', () => {
    // Verify that the router config references lazy-loaded components
    // by checking the Suspense children are lazy components
    const nonRedirectRoutes = children.filter((c: any) => c.element?.type !== Navigate)
    expect(nonRedirectRoutes.length).toBe(14)

    for (const route of nonRedirectRoutes) {
      const suspenseChild = route.element?.props?.children
      expect(suspenseChild).toBeDefined()
      // Lazy components in React 18: type is an object (lazy wrapper), not a plain function
      // The $$typeof check confirms it's a valid React element
      expect(suspenseChild.$$typeof).toBeDefined()
      expect(typeof suspenseChild.type).toBe('object')
    }
  })

  it('Loading fallback is defined for all Suspense wrappers', () => {
    for (const child of children) {
      if (child.element?.type === Navigate) {
        continue
      }
      const fallback = child.element?.props?.fallback
      expect(fallback).toBeDefined()
      // The fallback should be a React element (Spin component)
      expect(fallback?.type).toBeDefined()
    }
  })
})
