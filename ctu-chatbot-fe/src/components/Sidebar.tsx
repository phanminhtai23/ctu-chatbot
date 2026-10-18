import { useCallback, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useI18n } from '../i18n'
import Icon, { type IconName } from './Icon'
import Logo from './Logo'

/**
 * Trạng thái thu gọn của sidebar, lưu theo `storageKey`.
 * Lần đầu: thu gọn sẵn trên điện thoại và máy tính bảng (<1024px), mở sẵn trên desktop.
 */
export function useSidebarCollapsed(storageKey: string) {
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      const saved = localStorage.getItem(storageKey)
      if (saved === '1' || saved === '0') return saved === '1'
    } catch {
      // localStorage có thể bị chặn — rơi xuống mặc định theo kích thước màn hình.
    }
    return window.matchMedia('(max-width: 1023px)').matches
  })

  const toggle = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev
      try {
        localStorage.setItem(storageKey, next ? '1' : '0')
      } catch {
        // bỏ qua
      }
      return next
    })
  }, [storageKey])

  return [collapsed, toggle] as const
}

type Props = {
  collapsed: boolean
  onToggle: () => void
  title: string
  subtitle: string
  /** Phần thân (cuộn được). Ẩn hoàn toàn khi thu gọn trên mobile, chỉ còn icon trên desktop. */
  children: ReactNode
  footer?: ReactNode
  /** Nút nhỏ chuyển nhanh giữa khu vực chat và khu vực quản trị (chỉ admin); đặt bên trái nút thu gọn */
  switchTo?: { to: string; label: string; icon: IconName }
}

/** Class cho chữ/nhãn: ẩn trên desktop khi sidebar thu gọn thành cột icon. */
export const labelClass = (collapsed: boolean) => (collapsed ? 'md:hidden' : '')

export default function Sidebar({ collapsed, onToggle, title, subtitle, children, footer, switchTo }: Props) {
  const { t } = useI18n()

  return (
    <aside
      className={`box-border flex max-h-[70dvh] w-full flex-none flex-col bg-ctu-navy-dark text-white transition-[width] duration-200 md:sticky md:top-0 md:h-screen md:max-h-none ${
        collapsed ? 'md:w-[72px]' : 'md:w-[300px]'
      }`}
    >
      <div className={`flex items-center gap-3 p-3 ${collapsed ? 'md:flex-col md:py-4' : ''}`}>
        <Logo size={40} fill="#0D47A1" />
        <div className={`min-w-0 flex-1 leading-tight ${labelClass(collapsed)}`}>
          <div className="truncate text-[15px] font-semibold">{title}</div>
          <div className="truncate text-xs opacity-85">{subtitle}</div>
        </div>
        {switchTo && (
          <Link
            to={switchTo.to}
            aria-label={switchTo.label}
            title={switchTo.label}
            className="inline-flex size-9 flex-none items-center justify-center rounded-lg border border-white/30 text-white no-underline hover:bg-white/10"
          >
            <Icon name={switchTo.icon} size={17} />
          </Link>
        )}
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={!collapsed}
          aria-label={t(collapsed ? 'sidebar.expand' : 'sidebar.collapse')}
          title={t(collapsed ? 'sidebar.expand' : 'sidebar.collapse')}
          className="inline-flex size-11 flex-none cursor-pointer items-center justify-center rounded-lg border-0 bg-transparent text-white hover:bg-white/10"
        >
          <Icon name="panelLeft" />
        </button>
      </div>

      <div
        className={`min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-3 pb-4 ${
          collapsed ? 'hidden md:flex' : 'flex'
        }`}
      >
        {children}
      </div>

      {footer && (
        <div className={`border-t border-white/20 p-3 ${collapsed ? 'hidden md:block' : 'block'}`}>{footer}</div>
      )}
    </aside>
  )
}
