import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { ChatContainer } from './components/ChatContainer'
import { Login } from './pages/Login'
import { RoleGate } from './components/RoleGate'
import { STUDENT_ROLES, TEACHER_ROLES, SCHOOL_ROLES, CITY_ROLES, homePath } from './utils/permissions'
import { StudentDetailPage, SchoolDetailPage } from './pages/ManagementDetails'
import { SchoolWorkbenchPage, ClassAnalysisPage } from './features/education/SchoolWorkbench'
import { ImportWorkbenchPage } from './features/education/ImportWorkbench'
import { PaperWorkbenchPage, PaperSplitPage } from './features/education/PaperWorkbench'
import { QuestionWorkbenchPage } from './features/education/QuestionWorkbench'
import { ReportWorkbenchPage, SourcesWorkbenchPage } from './features/education/EvidenceWorkbench'
import { ErrorBoundary, ErrorDisplay } from './components/ErrorDisplay'
import { AppShell } from './layouts/AppShell'
import { getUserInfo } from './utils/auth'
import { useAuthScope, useChatSessions, useCreateChatSession, useDeleteChatSession } from './hooks/useApi'
import {
  StudentDashboardPage,
  StudentDiagnosisPage,
  StudentMistakesPage,
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

function ChatPage() {
  const { data: sessions, isLoading, error, refetch } = useChatSessions()
  const createSession = useCreateChatSession()
  const deleteSession = useDeleteChatSession()
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const creatingRef = useRef(false)
  const createSessionMutation = createSession.mutate

  // 没有会话时自动创建一个，保证聊天窗口可用。
  useEffect(() => {
    if (!sessions || sessions.length > 0 || sessionId || actionError || creatingRef.current) return
    creatingRef.current = true
    createSessionMutation({}, {
      onSuccess: created => { creatingRef.current = false; setSessionId(created.id) },
      onError: err => { creatingRef.current = false; setActionError(err.message || '无法创建会话') },
    })
  }, [sessions, sessionId, actionError, createSessionMutation])

  const activeSessionId = sessionId || sessions?.[0]?.id || null

  const handleNewSession = () => {
    setActionError(null)
    createSession.mutate({}, {
      onSuccess: created => setSessionId(created.id),
      onError: err => setActionError(err.message || '无法创建会话'),
    })
  }

  const handleArchiveSession = () => {
    if (!activeSessionId) return
    setActionError(null)
    deleteSession.mutate(activeSessionId, {
      onSuccess: () => {
        const remaining = (sessions || []).filter(session => session.id !== activeSessionId)
        setSessionId(remaining[0]?.id ?? null)
      },
      onError: err => setActionError(err.message || '无法结束会话'),
    })
  }

  if (isLoading) return <div className="loading-screen">正在准备你的学习会话…</div>

  if (error) {
    return <div className="chat-error-screen"><ErrorDisplay error={error} title="无法加载会话" onRetry={() => { void refetch() }} /></div>
  }

  if (!activeSessionId) return <AppShell bleed title="智能问答" eyebrow="学生空间 / 智能问答">
    {actionError ? <ErrorDisplay error={actionError} title="无法创建会话" onRetry={handleNewSession} /> : <div className="loading-screen">正在准备你的学习会话…</div>}
  </AppShell>

  return (
    <AppShell bleed title="智能问答" eyebrow="学生空间 / 智能问答">
      <div className="chat-page-frame">
        {actionError && <ErrorDisplay error={actionError} title="操作失败" onDismiss={() => setActionError(null)} variant="banner" />}
        <ChatContainer
          key={activeSessionId}
          sessionId={activeSessionId}
          sessions={sessions || []}
          onSelectSession={setSessionId}
          onNewSession={handleNewSession}
          onArchiveSession={handleArchiveSession}
        />
      </div>
    </AppShell>
  )
}

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
            <Route path="/" element={<RoleGate><HomeRedirect /></RoleGate>} />
            <Route path="/chat" element={<RoleGate allowed={STUDENT_ROLES}><ChatPage /></RoleGate>} />
            <Route path="/profile" element={<RoleGate allowed={STUDENT_ROLES}><ProfilePage /></RoleGate>} />
            <Route path="/trends" element={<RoleGate allowed={STUDENT_ROLES}><StudentTrendsPage /></RoleGate>} />
            <Route path="/diagnosis" element={<RoleGate allowed={STUDENT_ROLES}><StudentDiagnosisPage /></RoleGate>} />
            <Route path="/mistakes" element={<RoleGate allowed={STUDENT_ROLES}><StudentMistakesPage /></RoleGate>} />
            <Route path="/support" element={<RoleGate allowed={STUDENT_ROLES}><StudentSupportPage /></RoleGate>} />
            <Route path="/teacher" element={<RoleGate allowed={TEACHER_ROLES}><ManagementOverviewPage /></RoleGate>} />
            <Route path="/teacher/analysis" element={<RoleGate allowed={TEACHER_ROLES}><ClassAnalysisPage /></RoleGate>} />
            <Route path="/teacher/students" element={<RoleGate allowed={TEACHER_ROLES}><StudentRosterPage /></RoleGate>} />
            <Route path="/teacher/students/:studentId" element={<RoleGate allowed={TEACHER_ROLES}><StudentDetailPage /></RoleGate>} />
            <Route path="/teacher/feedback" element={<RoleGate allowed={TEACHER_ROLES}><FeedbackPage /></RoleGate>} />
            <Route path="/teacher/handoffs" element={<RoleGate allowed={TEACHER_ROLES}><HandoffPage /></RoleGate>} />
            <Route path="/teacher/risks" element={<RoleGate allowed={TEACHER_ROLES}><RiskPage /></RoleGate>} />
            <Route path="/admin" element={<RoleGate allowed={SCHOOL_ROLES}><ManagementOverviewPage /></RoleGate>} />
            <Route path="/admin/school" element={<RoleGate allowed={[...SCHOOL_ROLES, 'SUPER_ADMIN']}><SchoolWorkbenchPage /></RoleGate>} />
            <Route path="/admin/imports" element={<RoleGate allowed={[...SCHOOL_ROLES, 'SUPER_ADMIN']}><ImportWorkbenchPage /></RoleGate>} />
            <Route path="/admin/papers" element={<RoleGate allowed={[...SCHOOL_ROLES, 'SUPER_ADMIN']}><PaperWorkbenchPage /></RoleGate>} />
            <Route path="/admin/papers/:paperId/split/:versionId" element={<RoleGate allowed={[...SCHOOL_ROLES, 'SUPER_ADMIN']}><PaperSplitPage /></RoleGate>} />
            <Route path="/admin/questions" element={<RoleGate allowed={[...SCHOOL_ROLES, 'SUPER_ADMIN']}><QuestionWorkbenchPage /></RoleGate>} />
            <Route path="/admin/sources" element={<RoleGate allowed={[...SCHOOL_ROLES, 'SUPER_ADMIN']}><SourcesWorkbenchPage /></RoleGate>} />
            <Route path="/admin/reports" element={<RoleGate allowed={[...SCHOOL_ROLES, 'SUPER_ADMIN']}><ReportWorkbenchPage /></RoleGate>} />
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
