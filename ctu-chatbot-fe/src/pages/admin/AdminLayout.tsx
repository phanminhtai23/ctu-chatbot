import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../auth'
import Icon from '../../components/Icon'
import PrefToggles from '../../components/PrefToggles'
import Sidebar, { labelClass, useSidebarCollapsed } from '../../components/Sidebar'
import { useI18n } from '../../i18n'
import { FEEDBACK_CHANGED_EVENT, getUnreadFeedbackCount } from '../../lib/adminFeedback'

type Props = {
  title: string
  subtitle?: string
  children: ReactNode
}

// Được bọc bởi <RequireAdmin> ở App.tsx.
export default function AdminLayout({ title, subtitle, children }: Props) {
  const { t } = useI18n()
  const { logout } = useAuth()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [collapsed, toggleSidebar] = useSidebarCollapsed('ctu-admin-sidebar')
  const [unread, setUnread] = useState(0)

  const refreshUnread = useCallback(() => {
    getUnreadFeedbackCount()
      .then(setUnread)
      .catch(() => {})
  }, [])

  useEffect(() => {
    refreshUnread()
    const timer = window.setInterval(() => {
      if (!document.hidden) refreshUnread()
    }, 30000)
    window.addEventListener(FEEDBACK_CHANGED_EVENT, refreshUnread)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener(FEEDBACK_CHANGED_EVENT, refreshUnread)
    }
  }, [refreshUnread])

  return (
    <div className="flex min-h-screen flex-col bg-surface md:flex-row">
      <Sidebar
        collapsed={collapsed}
        onToggle={toggleSidebar}
        title={t('admin.title')}
        subtitle={t('brand.app')}
        switchTo={{ to: '/chat', label: t('admin.nav.chat'), icon: 'chat' }}
        footer={
          <button
            type="button"
            onClick={() => {
              logout()
              navigate('/login', { replace: true })
            }}
            aria-label={t('admin.logout')}
            title={t('admin.logout')}
            className={`flex min-h-11 w-full cursor-pointer items-center gap-3 rounded-lg border-0 bg-transparent px-3 py-2.5 font-sans text-sm text-white hover:bg-white/10 ${
              collapsed ? 'md:justify-center' : ''
            }`}
          >
            <Icon name="logout" />
            <span className={labelClass(collapsed)}>{t('admin.logout')}</span>
          </button>
        }
      >
        <nav aria-label={t('admin.nav')} className="flex flex-col gap-1">
          {(
            [
              ['/admin/dashboard', 'chart', 'admin.nav.dashboard'],
              ['/admin/users', 'users', 'admin.nav.users'],
              ['/admin/feedback', 'inbox', 'admin.nav.feedback'],
              ['/admin/documents', 'doc', 'admin.nav.documents'],
              ['/admin/knowledge', 'book', 'admin.nav.knowledge'],
              ['/admin/donate', 'heart', 'admin.nav.donate'],
            ] as const
          ).map(([to, icon, label]) => {
            const current = pathname === to
            const badge = to === '/admin/feedback' ? unread : 0
            return (
              <Link
                key={to}
                to={to}
                aria-current={current ? 'page' : undefined}
                title={t(label)}
                className={`flex min-h-11 items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-white no-underline hover:bg-white/10 ${
                  current ? 'bg-white/15 font-normal' : ''
                } ${collapsed ? 'md:justify-center' : ''}`}
              >
                <span className="relative flex">
                  <Icon name={icon} />
                  {badge > 0 && (
                    <span
                      aria-hidden="true"
                      className={`absolute -right-1.5 -top-1.5 size-2.5 rounded-full bg-red-500 ring-2 ring-ctu-navy-dark ${
                        collapsed ? 'md:block' : 'md:hidden'
                      }`}
                    />
                  )}
                </span>
                <span className={labelClass(collapsed)}>{t(label)}</span>
                {badge > 0 && (
                  <span
                    role="status"
                    aria-label={`${badge} ${t('admin.nav.feedback.unread')}`}
                    className={`ml-auto min-w-5 rounded-full bg-red-500 px-1.5 text-center text-xs font-semibold leading-5 text-white ${
                      collapsed ? 'md:hidden' : ''
                    }`}
                  >
                    {badge > 99 ? '99+' : badge}
                  </span>
                )}
              </Link>
            )
          })}
        </nav>
      </Sidebar>

      <main className="min-w-0 flex-1">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-line px-6 py-5 md:px-8">
          <div>
            <h1 className="m-0 text-xl">{title}</h1>
            {subtitle && <p className="m-0 mt-1 text-sm">{subtitle}</p>}
          </div>
          <PrefToggles />
        </div>
        <div className="px-6 py-6 md:px-8">{children}</div>
      </main>
    </div>
  )
}
