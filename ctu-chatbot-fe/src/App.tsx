import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import RequireAdmin from './components/RequireAdmin'
import RequireAuth from './components/RequireAuth'
import { useAuth } from './auth'
import { useI18n } from './i18n'
import Landing from './pages/Landing'

const Chat = lazy(() => import('./pages/Chat'))
const WelcomeDialog = lazy(() => import('./components/WelcomeDialog'))
const DevGifs = lazy(() => import('./pages/DevGifs'))
const Login = lazy(() => import('./pages/Login'))
const SharedView = lazy(() => import('./pages/SharedView'))
const AdminDashboard = lazy(() => import('./pages/admin/AdminDashboard'))
const AdminDocuments = lazy(() => import('./pages/admin/AdminDocuments'))
const AdminDonate = lazy(() => import('./pages/admin/AdminDonate'))
const AdminFeedback = lazy(() => import('./pages/admin/AdminFeedback'))
const AdminKnowledge = lazy(() => import('./pages/admin/AdminKnowledge'))
const AdminUsers = lazy(() => import('./pages/admin/AdminUsers'))

function App() {
  const { user } = useAuth()
  const { t } = useI18n()
  return (
    <BrowserRouter>
      {user && (
        <Suspense fallback={null}>
          <WelcomeDialog />
        </Suspense>
      )}
      <Suspense fallback={<p role="status" className="m-0 p-6 text-muted">{t('common.loading')}</p>}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          {import.meta.env.DEV && <Route path="/dev/gifs" element={<DevGifs />} />}
          <Route path="/s/:token" element={<SharedView />} />
          <Route
            path="/chat/:conversationId?"
            element={
              <RequireAuth>
                <Chat />
              </RequireAuth>
            }
          />
          <Route path="/profile" element={<Navigate to="/chat" replace />} />
          <Route path="/admin" element={<Navigate to="/admin/dashboard" replace />} />
          <Route
            path="/admin/feedback"
            element={
              <RequireAdmin>
                <AdminFeedback />
              </RequireAdmin>
            }
          />
          <Route
            path="/admin/dashboard"
            element={
              <RequireAdmin>
                <AdminDashboard />
              </RequireAdmin>
            }
          />
          <Route
            path="/admin/users"
            element={
              <RequireAdmin>
                <AdminUsers />
              </RequireAdmin>
            }
          />
          <Route
            path="/admin/documents"
            element={
              <RequireAdmin>
                <AdminDocuments />
              </RequireAdmin>
            }
          />
          <Route
            path="/admin/knowledge"
            element={
              <RequireAdmin>
                <AdminKnowledge />
              </RequireAdmin>
            }
          />
          <Route
            path="/admin/donate"
            element={
              <RequireAdmin>
                <AdminDonate />
              </RequireAdmin>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}

export default App
