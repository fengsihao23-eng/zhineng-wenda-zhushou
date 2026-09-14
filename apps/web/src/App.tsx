import React, { useEffect, useState } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { ChatContainer } from './components/ChatContainer'
import { Login } from './pages/Login'
import { AUTH_CHANGED_EVENT, isAuthenticated } from './utils/auth'
import { apiError, apiFetch } from './services/api'
import { AppShell, roleOf } from './layouts/AppShell'
import { getUserInfo } from './utils/auth'
import {
  StudentDashboardPage,
  StudentDiagnosisPage,
  StudentMistakesPage,
  StudentSupportPage,
  StudentTrendsPage,
} from './pages/StudentPages'
import {
  FeedbackPage,
  HandoffPage,
  KnowledgePage,
  ManagementOverviewPage,
  RiskPage,
  SchoolPage,
  StudentRosterPage,
} from './pages/ManagementPages'

interface Session {
  id: string;
  title: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

function ChatPage() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [sessions, setSessions] = useState<Session[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const loadSessions = async () => {
      try {
        const response = await apiFetch('/chat/sessions')
        if (!response.ok) throw await apiError(response, '无法加载会话')
        const existing = await response.json() as Session[]
        if (cancelled) return
        if (existing.length > 0) {
          setSessions(existing)
          setSessionId(existing[0].id)
          return
        }

        const created = await createSession()
        if (!cancelled) {
          setSessions([created])
          setSessionId(created.id)
        }
      } catch (err: unknown) {
        if (!cancelled) setError(err instanceof Error ? err.message : '无法加载会话')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void loadSessions()
    return () => { cancelled = true }
  }, [])

  if (error) return <div className="error-banner">{error}</div>
  if (loading || !sessionId) return <div className="loading-screen">正在准备你的学习会话…</div>

  const handleNewSession = async () => {
    try {
      const created = await createSession()
      setSessions(current => [created, ...current])
      setSessionId(created.id)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '无法创建会话')
    }
  }

  const handleArchiveSession = async () => {
    if (!sessionId) return
    try {
      const response = await apiFetch(`/chat/sessions/${sessionId}`, { method: 'DELETE' })
      if (!response.ok) throw await apiError(response, '无法结束会话')
      const remaining = sessions.filter(session => session.id !== sessionId)
      if (remaining.length > 0) {
        setSessions(remaining)
        setSessionId(remaining[0].id)
      } else {
        await handleNewSession()
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '无法结束会话')
    }
  }

  return <AppShell title="智能问答" eyebrow="学生空间 / 智能问答"><div className="chat-page-frame"><ChatContainer sessionId={sessionId} sessions={sessions} onSelectSession={setSessionId} onNewSession={handleNewSession} onArchiveSession={handleArchiveSession} /></div></AppShell>
}

async function createSession(): Promise<Session> {
  const response = await apiFetch('/chat/sessions', {
    method: 'POST',
    body: JSON.stringify({}),
  })
  if (!response.ok) throw await apiError(response, '无法创建会话')
  return response.json() as Promise<Session>
}

function App() {
  const [authenticated, setAuthenticated] = useState(isAuthenticated)

  useEffect(() => {
    const onAuthChanged = () => setAuthenticated(isAuthenticated())
    window.addEventListener(AUTH_CHANGED_EVENT, onAuthChanged)
    return () => window.removeEventListener(AUTH_CHANGED_EVENT, onAuthChanged)
  }, [])

  const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
    return authenticated ? <>{children}</> : <Navigate to="/login" replace />
  }

  const HomeRedirect = () => {
    const role = roleOf(getUserInfo())
    if (role === 'student') return <StudentDashboardPage />
    if (role === 'teacher') return <ManagementOverviewPage />
    if (role === 'school') return <ManagementOverviewPage />
    return <ManagementOverviewPage />
  }

  return (
    <Router>
      <div className="min-h-screen bg-gray-50">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<ProtectedRoute><HomeRedirect /></ProtectedRoute>} />
          <Route path="/chat" element={<ProtectedRoute><ChatPage /></ProtectedRoute>} />
          <Route path="/trends" element={<ProtectedRoute><StudentTrendsPage /></ProtectedRoute>} />
          <Route path="/diagnosis" element={<ProtectedRoute><StudentDiagnosisPage /></ProtectedRoute>} />
          <Route path="/mistakes" element={<ProtectedRoute><StudentMistakesPage /></ProtectedRoute>} />
          <Route path="/support" element={<ProtectedRoute><StudentSupportPage /></ProtectedRoute>} />
          <Route path="/teacher" element={<ProtectedRoute><ManagementOverviewPage /></ProtectedRoute>} />
          <Route path="/teacher/students" element={<ProtectedRoute><StudentRosterPage /></ProtectedRoute>} />
          <Route path="/teacher/handoffs" element={<ProtectedRoute><HandoffPage /></ProtectedRoute>} />
          <Route path="/teacher/risks" element={<ProtectedRoute><RiskPage /></ProtectedRoute>} />
          <Route path="/admin" element={<ProtectedRoute><ManagementOverviewPage /></ProtectedRoute>} />
          <Route path="/admin/students" element={<ProtectedRoute><StudentRosterPage /></ProtectedRoute>} />
          <Route path="/admin/knowledge" element={<ProtectedRoute><KnowledgePage /></ProtectedRoute>} />
          <Route path="/admin/feedback" element={<ProtectedRoute><FeedbackPage /></ProtectedRoute>} />
          <Route path="/admin/risks" element={<ProtectedRoute><RiskPage /></ProtectedRoute>} />
          <Route path="/admin/handoffs" element={<ProtectedRoute><HandoffPage /></ProtectedRoute>} />
          <Route path="/ops" element={<ProtectedRoute><ManagementOverviewPage /></ProtectedRoute>} />
          <Route path="/ops/schools" element={<ProtectedRoute><SchoolPage /></ProtectedRoute>} />
          <Route path="/ops/knowledge" element={<ProtectedRoute><KnowledgePage /></ProtectedRoute>} />
          <Route path="/ops/feedback" element={<ProtectedRoute><FeedbackPage /></ProtectedRoute>} />
          <Route path="/ops/risks" element={<ProtectedRoute><RiskPage /></ProtectedRoute>} />
          <Route path="/ops/handoffs" element={<ProtectedRoute><HandoffPage /></ProtectedRoute>} />
        </Routes>
      </div>
    </Router>
  )
}

export default App
