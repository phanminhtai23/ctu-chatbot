import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../auth'
import Icon from '../../components/Icon'
import PrefToggles from '../../components/PrefToggles'
import Sidebar, { labelClass, useSidebarCollapsed } from '../../components/Sidebar'
import { useI18n } from '../../i18n'

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
  const [collapsed, toggleSidebar] = useSidebarCollapsed('ctu-admin-sidebar')

  return (
    <div className="flex min-h-screen flex-col bg-surface md:flex-row">
      <Sidebar
        collapsed={collapsed}
        onToggle={toggleSidebar}
        title={t('admin.title')}
        subtitle={t('brand.app')}
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
          <Link
            to="/chat"
            title={t('admin.nav.chat')}
            className={`flex min-h-11 items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-white no-underline hover:bg-white/10 ${
              collapsed ? 'md:justify-center' : ''
            }`}
          >
            <Icon name="chat" />
            <span className={labelClass(collapsed)}>{t('admin.nav.chat')}</span>
          </Link>
          <Link
            to="/admin/feedback"
            aria-current="page"
            title={t('admin.nav.feedback')}
            className={`flex min-h-11 items-center gap-3 rounded-lg bg-white/15 px-3 py-2.5 text-sm font-normal text-white no-underline ${
              collapsed ? 'md:justify-center' : ''
            }`}
          >
            <Icon name="inbox" />
            <span className={labelClass(collapsed)}>{t('admin.nav.feedback')}</span>
          </Link>
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
