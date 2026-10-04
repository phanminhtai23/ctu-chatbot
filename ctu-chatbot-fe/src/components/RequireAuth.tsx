import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth'
import { useI18n } from '../i18n'

export default function RequireAuth({ children }: { children: ReactNode }) {
  const { user, status, loggedOut } = useAuth()
  const { t } = useI18n()
  const location = useLocation()

  if (status === 'loading') {
    return (
      <div role="status" className="grid min-h-screen place-items-center bg-surface">
        {t('common.loading')}
      </div>
    )
  }
  // Phiên hết hạn / chưa đăng nhập: nhớ trang đang vào để quay lại. Tự bấm đăng xuất thì không nhớ.
  if (!user) return <Navigate to="/login" replace state={loggedOut ? null : { from: location.pathname }} />
  return children
}
