import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import RequireAdmin from './components/RequireAdmin'
import RequireAuth from './components/RequireAuth'
import WelcomeDialog from './components/WelcomeDialog'
import Chat from './pages/Chat'
import Landing from './pages/Landing'
import DevGifs from './pages/DevGifs'
import Login from './pages/Login'
import SharedView from './pages/SharedView'
import AdminDashboard from './pages/admin/AdminDashboard'
import AdminDocuments from './pages/admin/AdminDocuments'
import AdminDonate from './pages/admin/AdminDonate'
import AdminFeedback from './pages/admin/AdminFeedback'
import AdminUsers from './pages/admin/AdminUsers'

function App() {
  return (
    <BrowserRouter>
      <WelcomeDialog />
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
          path="/admin/donate"
          element={
            <RequireAdmin>
              <AdminDonate />
            </RequireAdmin>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
