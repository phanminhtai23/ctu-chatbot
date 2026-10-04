import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth'
import RequireAuth from './RequireAuth'

/** Chỉ cho tài khoản role 'admin'. Quyền thật do BE kiểm tra ở mọi endpoint /admin; đây chỉ là chặn giao diện. */
function AdminOnly({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  if (user?.role !== 'admin') return <Navigate to="/chat" replace />
  return children
}

export default function RequireAdmin({ children }: { children: ReactNode }) {
  return (
    <RequireAuth>
      <AdminOnly>{children}</AdminOnly>
    </RequireAuth>
  )
}
