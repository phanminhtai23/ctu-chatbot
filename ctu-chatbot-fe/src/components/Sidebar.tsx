import { useCallback, useEffect, useState, type ReactNode } from 'react'
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
  /** Ngăn kéo trên điện thoại (< 768px): đang mở hay đóng, và hàm đóng. Trên máy tính thanh bên luôn hiện và chỉ thu gọn / mở rộng. */
  mobileOpen: boolean
  onMobileClose: () => void
  title: string
  subtitle: string
  /** Phần thân (cuộn được). */
  children: ReactNode
  footer?: ReactNode
  /** Nút nhỏ chuyển nhanh giữa khu vực chat và khu vực quản trị (chỉ admin); đặt bên trái nút thu gọn */
  switchTo?: { to: string; label: string; icon: IconName }
}

/** Class cho chữ/nhãn: ẩn trên desktop khi sidebar thu gọn thành cột icon. */
export const labelClass = (collapsed: boolean) => (collapsed ? 'md:hidden' : '')

const MOBILE_QUERY = '(max-width: 767px)'

/** Trạng thái mở/đóng ngăn kéo trên điện thoại; tự đóng khi màn hình rộng ra thành máy tính. */
export function useMobileNav() {
  const [open, setOpen] = useState(false)
  useEffect(() => {
    const media = window.matchMedia(MOBILE_QUERY)
    const onChange = () => !media.matches && setOpen(false)
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [])
  return [open, setOpen] as const
}

/** Nút "hamburger" mở ngăn kéo: chỉ hiện trên điện thoại. */
export function MobileNavButton({ onClick, className = '' }: { onClick: () => void; className?: string }) {
  const { t } = useI18n()
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={t('sidebar.open')}
      title={t('sidebar.open')}
      className={`inline-flex size-11 flex-none cursor-pointer items-center justify-center rounded-lg border border-line bg-transparent text-heading hover:bg-tint md:hidden ${className}`}
    >
      <Icon name="menu" />
    </button>
  )
}

function useIsMobile() {
  const [mobile, setMobile] = useState(() => window.matchMedia(MOBILE_QUERY).matches)
  useEffect(() => {
    const media = window.matchMedia(MOBILE_QUERY)
    const onChange = () => setMobile(media.matches)
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [])
  return mobile
}

export default function Sidebar({ collapsed, onToggle, mobileOpen, onMobileClose, title, subtitle, children, footer, switchTo }: Props) {
  const { t } = useI18n()
  const isMobile = useIsMobile()

  // Ngăn kéo đang mở: Esc để đóng, và khoá cuộn nền để cuộn trong ngăn kéo không kéo theo cả trang.
  useEffect(() => {
    if (!mobileOpen) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onMobileClose()
    window.addEventListener('keydown', onKey)
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = previous
    }
  }, [mobileOpen, onMobileClose])

  return (
    <>
      <div
        aria-hidden="true"
        onClick={onMobileClose}
        className={`fixed inset-0 z-30 bg-black/50 transition-opacity duration-200 md:hidden ${
          mobileOpen ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
      />
      <aside
        // Đóng trên điện thoại thì nằm ngoài màn hình và không cho Tab vào (inert).
        inert={isMobile && !mobileOpen}
        className={`fixed bottom-0 left-0 top-0 z-40 box-border flex h-dvh w-[min(86vw,320px)] flex-none flex-col bg-ctu-navy-dark text-white transition-transform duration-200 md:sticky md:bottom-auto md:left-auto md:z-auto md:translate-x-0 md:transition-[width] ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        } ${collapsed ? 'md:w-[72px]' : 'md:w-[300px]'}`}
      >
        <div className={`flex items-center gap-3 p-3 ${collapsed ? 'md:flex-col md:py-4' : ''}`}>
          <Logo size={40} />
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
            onClick={onMobileClose}
            aria-label={t('sidebar.close')}
            title={t('sidebar.close')}
            className="inline-flex size-11 flex-none cursor-pointer items-center justify-center rounded-lg border-0 bg-transparent text-white hover:bg-white/10 md:hidden"
          >
            <Icon name="close" />
          </button>
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={!collapsed}
            aria-label={t(collapsed ? 'sidebar.expand' : 'sidebar.collapse')}
            title={t(collapsed ? 'sidebar.expand' : 'sidebar.collapse')}
            className="hidden size-11 flex-none cursor-pointer items-center justify-center rounded-lg border-0 bg-transparent text-white hover:bg-white/10 md:inline-flex"
          >
            <Icon name="panelLeft" />
          </button>
        </div>

        {/* Bấm vào một liên kết trong ngăn kéo (chọn cuộc trò chuyện, đổi trang quản trị...) thì đóng ngăn kéo. */}
        <div
          onClickCapture={(e) => {
            if (mobileOpen && (e.target as HTMLElement).closest('a[href]')) onMobileClose()
          }}
          className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto overscroll-contain px-3 pb-4"
        >
          {children}
        </div>

        {footer && <div className="border-t border-white/20 p-3">{footer}</div>}
      </aside>
    </>
  )
}
