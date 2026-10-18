import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import RequireAdmin from './components/RequireAdmin'
import RequireAuth from './components/RequireAuth'
import Chat from './pages/Chat'
import Landing from './pages/Landing'
import Login from './pages/Login'
import AdminDocuments from './pages/admin/AdminDocuments'
import AdminFeedback from './pages/admin/AdminFeedback'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route
          path="/chat/:conversationId?"
          element={
            <RequireAuth>
              <Chat />
            </RequireAuth>
          }
        />
        <Route path="/profile" element={<Navigate to="/chat" replace />} />
        <Route path="/admin" element={<Navigate to="/admin/feedback" replace />} />
        <Route
          path="/admin/feedback"
          element={
            <RequireAdmin>
              <AdminFeedback />
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
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
