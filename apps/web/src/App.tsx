import { lazy, Suspense } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { Login } from './pages/Login'
import { ChangePassword } from './pages/ChangePassword'
import { RoleGate } from './components/RoleGate'
import { STUDENT_ROLES, TEACHER_ROLES, SCHOOL_ROLES, CITY_ROLES, homePath } from './utils/permissions'
import { StudentDetailPage, SchoolDetailPage } from './pages/ManagementDetails'
import { SchoolWorkbenchPage, ClassAnalysisPage } from './features/education/SchoolWorkbench'
import { ExamResultsPage } from './features/education/ExamResults'
import { RosterTaskPage } from './features/education/RosterWorkbench'
import { ImportWorkbenchPage } from './features/education/ImportWorkbench'
import { PaperWorkbenchPage, PaperSplitPage } from './features/education/PaperWorkbench'
import { QuestionWorkbenchPage } from './features/education/QuestionWorkbench'
import { SourcesWorkbenchPage } from './features/education/EvidenceWorkbench'
import { AnswerWorkbenchPage } from './features/education/AnswerWorkbench'
import { ReportWorkbenchPage } from './features/education/ReportWorkbench'
import { ErrorBoundary } from './components/ErrorDisplay'
import { getUserInfo } from './utils/auth'
import { useAuthScope } from './hooks/useApi'
import {
  StudentDashboardPage,
  StudentDiagnosisPage,
  StudentMistakesPage,
  StudentReviewsPage,
  StudentSupportHistoryPage,
  StudentSupportPage,
  StudentTrendsPage,
} from './pages/StudentPages'
const ProfilePage = lazy(() => import('./pages/Profile').then(module => ({ default: module.ProfilePage })))
import {
  FeedbackPage,
  HandoffPage,
  KnowledgePage,
  ManagementOverviewPage,
  RiskPage,
  SchoolPage,
  StudentRosterPage,
} from './pages/ManagementPages'

function App() {
  const scope = useAuthScope()
  const HomeRedirect = () => {
    const path = homePath(getUserInfo())
    return path === '/' ? <StudentDashboardPage /> : <Navigate to={path} replace />
  }

  return (
    <Router>
      <div className="app-root">
        <ErrorBoundary key={scope}>
          <Suspense fallback={<div className="loading-screen">正在加载页面…</div>}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/change-password" element={<ChangePassword />} />
            <Route path="/" element={<RoleGate><HomeRedirect /></RoleGate>} />
            <Route path="/mini" element={<Navigate to={getUserInfo()?.roles.includes('TEACHER') && !getUserInfo()?.roles.includes('STUDENT') ? '/teacher/chat' : '/chat'} replace />} />
            <Route path="/mini-preview" element={<AnswerWorkbenchPage mode="mini" />} />
            <Route path="/chat" element={<RoleGate allowed={[...STUDENT_ROLES, ...TEACHER_ROLES]}><AnswerWorkbenchPage /></RoleGate>} />
            <Route path="/teacher/chat" element={<RoleGate allowed={TEACHER_ROLES}><AnswerWorkbenchPage /></RoleGate>} />
            <Route path="/admin/prompts" element={<RoleGate allowed={['SCHOOL_ADMIN', 'SUPER_ADMIN']}><AnswerWorkbenchPage mode="admin" /></RoleGate>} />
            <Route path="/profile" element={<RoleGate allowed={STUDENT_ROLES}><ProfilePage /></RoleGate>} />
            <Route path="/trends" element={<RoleGate allowed={STUDENT_ROLES}><StudentTrendsPage /></RoleGate>} />
            <Route path="/exam-results" element={<RoleGate allowed={STUDENT_ROLES}><ExamResultsPage /></RoleGate>} />
            <Route path="/diagnosis" element={<RoleGate allowed={STUDENT_ROLES}><StudentDiagnosisPage /></RoleGate>} />
            <Route path="/mistakes" element={<RoleGate allowed={STUDENT_ROLES}><StudentMistakesPage /></RoleGate>} />
            <Route path="/mistakes/reviews" element={<RoleGate allowed={STUDENT_ROLES}><StudentReviewsPage /></RoleGate>} />
            <Route path="/support/records" element={<RoleGate allowed={STUDENT_ROLES}><StudentSupportHistoryPage /></RoleGate>} />
            <Route path="/support" element={<RoleGate allowed={STUDENT_ROLES}><StudentSupportPage /></RoleGate>} />
            <Route path="/teacher" element={<RoleGate allowed={TEACHER_ROLES}><ManagementOverviewPage /></RoleGate>} />
            <Route path="/teacher/analysis" element={<RoleGate allowed={TEACHER_ROLES}><ClassAnalysisPage /></RoleGate>} />
            <Route path="/teacher/exams" element={<RoleGate allowed={TEACHER_ROLES}><ExamResultsPage /></RoleGate>} />
            <Route path="/teacher/students" element={<RoleGate allowed={TEACHER_ROLES}><StudentRosterPage /></RoleGate>} />
            <Route path="/teacher/students/:studentId" element={<RoleGate allowed={TEACHER_ROLES}><StudentDetailPage /></RoleGate>} />
            <Route path="/teacher/feedback" element={<RoleGate allowed={TEACHER_ROLES}><FeedbackPage /></RoleGate>} />
            <Route path="/teacher/handoffs" element={<RoleGate allowed={TEACHER_ROLES}><HandoffPage /></RoleGate>} />
            <Route path="/teacher/risks" element={<RoleGate allowed={TEACHER_ROLES}><RiskPage /></RoleGate>} />
            <Route path="/admin" element={<RoleGate allowed={SCHOOL_ROLES}><ManagementOverviewPage /></RoleGate>} />
            <Route path="/admin/school" element={<RoleGate allowed={[...SCHOOL_ROLES, 'SUPER_ADMIN', 'EXAM_ADMIN']}><SchoolWorkbenchPage /></RoleGate>} />
            {([
              { path: 'import', view: 'import' },
              { path: 'imports', view: 'history' },
              { path: 'imports/:batchId', view: 'batch' },
              { path: 'deletions', view: 'deletions' },
            ] as const).map(({ path, view }) => <Route key={path} path={`/admin/school/:kind/${path}`} element={<RoleGate allowed={[...SCHOOL_ROLES, 'SUPER_ADMIN']}><RosterTaskPage key={path} view={view} /></RoleGate>} />)}
            <Route path="/admin/imports" element={<RoleGate allowed={[...SCHOOL_ROLES, 'SUPER_ADMIN']}><ImportWorkbenchPage /></RoleGate>} />
            <Route path="/admin/imports/new" element={<RoleGate allowed={[...SCHOOL_ROLES, 'SUPER_ADMIN']}><ImportWorkbenchPage key="create" view="create" /></RoleGate>} />
            <Route path="/admin/imports/:importId" element={<RoleGate allowed={[...SCHOOL_ROLES, 'SUPER_ADMIN']}><ImportWorkbenchPage key="detail" view="detail" /></RoleGate>} />
            <Route path="/admin/papers" element={<RoleGate allowed={[...SCHOOL_ROLES, 'SUPER_ADMIN']}><PaperWorkbenchPage /></RoleGate>} />
            <Route path="/admin/papers/new" element={<RoleGate allowed={[...SCHOOL_ROLES, 'SUPER_ADMIN']}><PaperWorkbenchPage key="create" view="create" /></RoleGate>} />
            <Route path="/admin/papers/:paperId" element={<RoleGate allowed={[...SCHOOL_ROLES, 'SUPER_ADMIN']}><PaperWorkbenchPage key="detail" view="detail" /></RoleGate>} />
            <Route path="/admin/papers/:paperId/split/:versionId" element={<RoleGate allowed={[...SCHOOL_ROLES, 'SUPER_ADMIN']}><PaperSplitPage /></RoleGate>} />
            <Route path="/admin/questions" element={<RoleGate allowed={[...SCHOOL_ROLES, 'SUPER_ADMIN']}><QuestionWorkbenchPage /></RoleGate>} />
            <Route path="/admin/sources" element={<RoleGate allowed={[...SCHOOL_ROLES, 'SUPER_ADMIN']}><SourcesWorkbenchPage /></RoleGate>} />
            <Route path="/admin/sources/new" element={<RoleGate allowed={[...SCHOOL_ROLES, 'SUPER_ADMIN']}><SourcesWorkbenchPage key="create" view="create" /></RoleGate>} />
            <Route path="/admin/sources/:sourceId" element={<RoleGate allowed={[...SCHOOL_ROLES, 'SUPER_ADMIN']}><SourcesWorkbenchPage key="detail" view="detail" /></RoleGate>} />
            <Route path="/admin/reports" element={<RoleGate allowed={['SCHOOL_ADMIN', 'QA', 'SUPER_ADMIN']}><ReportWorkbenchPage /></RoleGate>} />
            <Route path="/admin/reports/new" element={<RoleGate allowed={['SCHOOL_ADMIN', 'QA', 'SUPER_ADMIN']}><ReportWorkbenchPage key="create" view="create" /></RoleGate>} />
            <Route path="/admin/analysis" element={<RoleGate allowed={[...SCHOOL_ROLES, 'SUPER_ADMIN']}><ClassAnalysisPage /></RoleGate>} />
            <Route path="/admin/students" element={<RoleGate allowed={SCHOOL_ROLES}><StudentRosterPage /></RoleGate>} />
            <Route path="/admin/students/:studentId" element={<RoleGate allowed={SCHOOL_ROLES}><StudentDetailPage /></RoleGate>} />
            <Route path="/admin/knowledge" element={<RoleGate allowed={SCHOOL_ROLES}><KnowledgePage /></RoleGate>} />
            <Route path="/admin/feedback" element={<RoleGate allowed={SCHOOL_ROLES}><FeedbackPage /></RoleGate>} />
            <Route path="/admin/risks" element={<RoleGate allowed={SCHOOL_ROLES}><RiskPage /></RoleGate>} />
            <Route path="/admin/handoffs" element={<RoleGate allowed={SCHOOL_ROLES}><HandoffPage /></RoleGate>} />
            <Route path="/ops" element={<RoleGate allowed={CITY_ROLES}><ManagementOverviewPage /></RoleGate>} />
            <Route path="/ops/schools" element={<RoleGate allowed={CITY_ROLES}><SchoolPage /></RoleGate>} />
            <Route path="/ops/schools/:schoolId" element={<RoleGate allowed={CITY_ROLES}><SchoolDetailPage /></RoleGate>} />
            <Route path="/ops/knowledge" element={<RoleGate allowed={CITY_ROLES}><KnowledgePage /></RoleGate>} />
            <Route path="/ops/feedback" element={<RoleGate allowed={CITY_ROLES}><FeedbackPage /></RoleGate>} />
            <Route path="/ops/risks" element={<RoleGate allowed={CITY_ROLES}><RiskPage /></RoleGate>} />
            <Route path="/ops/handoffs" element={<RoleGate allowed={CITY_ROLES}><HandoffPage /></RoleGate>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          </Suspense>
        </ErrorBoundary>
      </div>
    </Router>
  )
}

export default App
