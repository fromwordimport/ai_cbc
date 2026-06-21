import { createBrowserRouter, Navigate, Outlet } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { Spin } from 'antd'
import Layout from './components/Layout'
import { isAuthenticated } from './services/token'

const Login = lazy(() => import('./pages/Login'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const ImportanceDashboard = lazy(() => import('./pages/ImportanceDashboard'))
const MarketSimulator = lazy(() => import('./pages/MarketSimulator'))
const StudyCreate = lazy(() => import('./pages/StudyCreate'))
const PersonaManager = lazy(() => import('./pages/PersonaManager'))
const PersonaDetail = lazy(() => import('./pages/PersonaDetail'))
const QuestionnairePreview = lazy(() => import('./pages/QuestionnairePreview'))
const QuestionnaireConfig = lazy(() => import('./pages/QuestionnaireConfig'))
const ResponseSimulator = lazy(() => import('./pages/ResponseSimulator'))
const InterviewLab = lazy(() => import('./pages/InterviewLab'))
const SegmentComparison = lazy(() => import('./pages/SegmentComparison'))
const AnalysisStatus = lazy(() => import('./pages/AnalysisStatus'))
const AttributeDesign = lazy(() => import('./pages/AttributeDesign'))

const Settings = lazy(() => import('./pages/Settings'))

const Loading = (
  <Spin
    size="large"
    style={{
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      height: '100%',
    }}
  />
)

const AuthGuard: React.FC = () => {
  return isAuthenticated() ? <Outlet /> : <Navigate to="/login" replace />
}

export const router = createBrowserRouter([
  {
    path: '/login',
    element: (
      <Suspense fallback={Loading}>
        <Login />
      </Suspense>
    ),
  },
  {
    path: '/',
    element: <AuthGuard />,
    children: [
      {
        path: '/',
        element: <Layout />,
        children: [
          { index: true, element: <Suspense fallback={Loading}><Dashboard /></Suspense> },
          { path: 'importance', element: <Suspense fallback={Loading}><ImportanceDashboard /></Suspense> },
          { path: 'market-simulator', element: <Suspense fallback={Loading}><MarketSimulator /></Suspense> },
          { path: 'studies/new', element: <Suspense fallback={Loading}><StudyCreate /></Suspense> },
          { path: 'studies/:studyId/questionnaire', element: <Suspense fallback={Loading}><QuestionnairePreview /></Suspense> },
          { path: 'studies/:studyId/responses', element: <Suspense fallback={Loading}><ResponseSimulator /></Suspense> },
          { path: 'personas', element: <Suspense fallback={Loading}><PersonaManager /></Suspense> },
          { path: 'personas/:personaId', element: <Suspense fallback={Loading}><PersonaDetail /></Suspense> },
          { path: 'interview', element: <Suspense fallback={Loading}><InterviewLab /></Suspense> },
          { path: 'segment-comparison', element: <Suspense fallback={Loading}><SegmentComparison /></Suspense> },
          { path: 'questionnaires', element: <Suspense fallback={Loading}><QuestionnaireConfig /></Suspense> },
          { path: 'analysis-status', element: <Suspense fallback={Loading}><AnalysisStatus /></Suspense> },
          { path: 'responses', element: <Suspense fallback={Loading}><ResponseSimulator /></Suspense> },
          { path: 'studies/:studyId/design', element: <Suspense fallback={Loading}><AttributeDesign /></Suspense> },
          { path: 'settings', element: <Suspense fallback={Loading}><Settings /></Suspense> },
        ],
      },
    ],
  },
])
