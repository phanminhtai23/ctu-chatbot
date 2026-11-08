import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import { useI18n } from '../i18n'
import type { TranslationKey } from '../i18n/vi'
import { getDonateInfo, type DonateInfo } from '../lib/donate'
import { listFiles, type FileListing } from '../lib/files'
import type { ThemeMode } from '../lib/me'
import { useTheme } from '../theme'
import AvatarEditor from './AvatarEditor'
import DateField from './DateField'
import DonateSection from './DonateSection'
import Icon from './Icon'
import MyFiles from './MyFiles'
import SourcePicker from './SourcePicker'

const themeOptions: { value: ThemeMode; label: TranslationKey }[] = [
  { value: 'system', label: 'profile.theme.system' },
  { value: 'light', label: 'profile.theme.light' },
  { value: 'dark', label: 'profile.theme.dark' },
]

const FALLBACK_TIMEZONES = ['Asia/Ho_Chi_Minh', 'UTC']

function listTimezones(current: string): string[] {
  let zones: string[]
  try {
    zones = Intl.supportedValuesOf('timeZone')
  } catch {
    zones = FALLBACK_TIMEZONES
  }
  // Intl không liệt kê "UTC" và có thể thiếu giá trị đang lưu — luôn đảm bảo có mặt.
  return [...new Set([...FALLBACK_TIMEZONES, ...zones, current])].sort((a, b) => a.localeCompare(b))
}

type SaveState = 'idle' | 'saving' | 'saved' | 'error'

const fieldClass =
  'box-border min-h-11 w-full rounded-lg border border-field bg-surface px-3.5 py-2 font-sans text-[15px] text-heading outline-accent'
const labelClass = 'mb-1.5 block text-sm font-normal text-heading'

/** Biểu mẫu chỉnh thông tin: chỉ được gắn khi hộp thoại mở nên mỗi lần mở đều bắt đầu từ dữ liệu mới nhất của tài khoản. */
function ProfileForm({ onClose }: { onClose: () => void }) {
  const { t } = useI18n()
  const { setMode } = useTheme()
  const { user, updateProfile, logout } = useAuth()
  const navigate = useNavigate()

  const [name, setName] = useState(user?.name ?? '')
  const [birthday, setBirthday] = useState(user?.birthday ?? '')
  const [birthdayValid, setBirthdayValid] = useState(true) // false = đang gõ dở / ngày không hợp lệ: chặn nút Lưu
  const [theme, setTheme] = useState<ThemeMode>(user?.theme ?? 'system')
  const [timezone, setTimezone] = useState(user?.timezone ?? 'Asia/Ho_Chi_Minh')
  const [saveState, setSaveState] = useState<SaveState>('idle')

  // Đồng hồ xem trước múi giờ, cập nhật mỗi 30 giây.
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30_000)
    return () => clearInterval(id)
  }, [])

  const zones = useMemo(() => listTimezones(timezone), [timezone])
  const timePreview = useMemo(() => {
    try {
      return new Intl.DateTimeFormat('vi-VN', { dateStyle: 'medium', timeStyle: 'short', timeZone: timezone }).format(now)
    } catch {
      return ''
    }
  }, [now, timezone])

  if (!user) return null

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!birthdayValid) return
    setSaveState('saving')
    try {
      await updateProfile({ name: name.trim(), birthday: birthday || null, timezone, theme })
      setMode(theme) // áp ngay giao diện vừa lưu
      setSaveState('saved')
    } catch {
      setSaveState('error')
    }
  }

  const handleLogout = () => {
    onClose()
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <form onSubmit={handleSubmit} onChange={() => saveState !== 'idle' && setSaveState('idle')} className="flex flex-col gap-5">
      <div>
        <label htmlFor="profile-email" className={labelClass}>
          {t('profile.email')}
        </label>
        <input id="profile-email" type="email" value={user.email} readOnly className={`${fieldClass} cursor-not-allowed bg-tint`} />
      </div>

      <div>
        <label htmlFor="profile-name" className={labelClass}>
          {t('profile.name')}
        </label>
        <input
          id="profile-name"
          type="text"
          value={name}
          maxLength={100}
          autoComplete="name"
          onChange={(e) => setName(e.target.value)}
          className={fieldClass}
        />
      </div>

      <div>
        <label htmlFor="profile-birthday" className={labelClass}>
          {t('profile.birthday')}
        </label>
        <DateField
          id="profile-birthday"
          value={birthday}
          min="1900-01-01"
          max={now.toISOString().slice(0, 10)}
          onChange={(iso, valid) => {
            setBirthday(iso)
            setBirthdayValid(valid)
          }}
          className="sm:max-w-[300px]"
        />
      </div>

      <fieldset className="m-0 border-0 p-0">
        <legend className={`${labelClass} p-0`}>{t('profile.theme')}</legend>
        <div className="flex flex-wrap gap-2">
          {themeOptions.map((o) => (
            <label
              key={o.value}
              className={`flex min-h-11 cursor-pointer items-center gap-2.5 rounded-lg border px-4 py-2 text-[15px] ${
                theme === o.value ? 'border-accent bg-tint text-heading' : 'border-line'
              }`}
            >
              <input
                type="radio"
                name="profile-theme"
                value={o.value}
                checked={theme === o.value}
                onChange={() => setTheme(o.value)}
                className="size-4 accent-[var(--accent)]"
              />
              {t(o.label)}
            </label>
          ))}
        </div>
      </fieldset>

      <div>
        <label htmlFor="profile-timezone" className={labelClass}>
          {t('profile.timezone')}
        </label>
        <select id="profile-timezone" value={timezone} onChange={(e) => setTimezone(e.target.value)} className={fieldClass}>
          {zones.map((z) => (
            <option key={z} value={z}>
              {z}
            </option>
          ))}
        </select>
        {timePreview && (
          <p className="mb-0 mt-2 text-sm">
            {t('profile.timezoneNow')} <strong className="font-semibold text-heading">{timePreview}</strong>
          </p>
        )}
      </div>

      <div className="flex flex-col gap-3 border-t border-line pt-4 sm:flex-row sm:flex-wrap sm:items-center">
        <button
          type="submit"
          disabled={saveState === 'saving' || !birthdayValid}
          className="min-h-11 w-full cursor-pointer rounded-lg border-0 bg-ctu-navy px-6 py-2.5 font-sans text-base font-semibold text-white hover:bg-ctu-navy-dark disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
        >
          {t(saveState === 'saving' ? 'profile.saving' : 'profile.save')}
        </button>
        <span role="status" aria-live="polite" className="text-sm">
          {saveState === 'saved' && (
            <span className="inline-flex items-center gap-1.5 text-[#14602F] dark:text-[#8AD9A8]">
              <Icon name="check" size={18} strokeWidth={2.2} />
              {t('profile.saved')}
            </span>
          )}
          {saveState === 'error' && <span className="text-[#8A1216] dark:text-[#FFB4B7]">{t('profile.saveError')}</span>}
        </span>
        <button
          type="button"
          onClick={handleLogout}
          className="inline-flex min-h-11 w-full cursor-pointer items-center justify-center gap-2 rounded-lg border-0 bg-[#B3261E] px-4 py-2 font-sans text-sm font-semibold text-white hover:bg-[#8C1D18] dark:bg-[#C93C3C] dark:hover:bg-[#A82F2F] sm:ml-auto sm:w-auto"
        >
          <Icon name="logout" size={18} />
          {t('profile.logout')}
        </button>
      </div>
    </form>
  )
}

type TabId = 'settings' | 'sources' | 'storage' | 'donate'

const tabLabels: Record<TabId, TranslationKey> = {
  settings: 'profile.tab.settings',
  sources: 'profile.tab.sources',
  storage: 'profile.tab.storage',
  donate: 'profile.tab.donate',
}

/** Thanh tab: mũi tên trái/phải đổi tab, Home/End nhảy về đầu/cuối (mẫu WAI-ARIA tabs). */
function Tabs({ tabs, active, onChange }: { tabs: TabId[]; active: TabId; onChange: (tab: TabId) => void }) {
  const { t } = useI18n()
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const index = tabs.indexOf(active)
    let next = index
    if (e.key === 'ArrowRight') next = (index + 1) % tabs.length
    else if (e.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length
    else if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = tabs.length - 1
    else return
    e.preventDefault()
    onChange(tabs[next])
    document.getElementById(`profile-tab-${tabs[next]}`)?.focus()
  }
  return (
    <div role="tablist" aria-label={t('profile.title')} onKeyDown={onKeyDown} className="mb-5 flex gap-1 border-b border-line">
      {tabs.map((id) => {
        const selected = id === active
        return (
          <button
            key={id}
            type="button"
            role="tab"
            id={`profile-tab-${id}`}
            aria-selected={selected}
            aria-controls={`profile-panel-${id}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(id)}
            className={`-mb-px min-h-11 cursor-pointer border-0 border-b-2 bg-transparent px-4 py-2 font-sans text-[15px] ${
              selected ? 'border-accent font-semibold text-heading' : 'border-transparent font-normal text-muted hover:text-heading'
            }`}
          >
            {t(tabLabels[id])}
          </button>
        )
      })}
    </div>
  )
}

/** Các tab của hộp thoại. Mọi tab đều giữ nguyên khi chuyển qua lại (chỉ ẩn) để không mất chỗ đang nhập dở. Dung lượng đã dùng lấy từ server mỗi lần mở hộp thoại. */
function ProfileBody({ onClose, initialTab }: { onClose: () => void; initialTab: TabId }) {
  const { t } = useI18n()
  const [tab, setTab] = useState<TabId>(initialTab)
  const [listing, setListing] = useState<FileListing | null>(null)
  const [listingFailed, setListingFailed] = useState(false)
  const [donate, setDonate] = useState<DonateInfo | null>(null)
  const { user } = useAuth()

  const refresh = useCallback(() => {
    listFiles()
      .then((next) => {
        setListing(next)
        setListingFailed(false)
      })
      .catch(() => setListingFailed(true)) // không lấy được thì tab Dung lượng báo lỗi, phần chỉnh hồ sơ vẫn dùng được
  }, [])
  useEffect(() => {
    refresh()
  }, [refresh])
  // Đổi ảnh đại diện làm thay đổi dung lượng đã dùng: tải lại khi ảnh đổi.
  const avatar = user?.avatar_url
  useEffect(() => {
    if (avatar) refresh()
  }, [avatar, refresh])

  useEffect(() => {
    let cancelled = false
    getDonateInfo()
      .then((info) => !cancelled && setDonate(info))
      .catch(() => {}) // không lấy được thì ẩn tab Ủng hộ
    return () => {
      cancelled = true
    }
  }, [])

  // Chưa có mã QR thì không có gì để hiện: ẩn hẳn tab Ủng hộ.
  const tabs: TabId[] = donate?.has_qr ? ['settings', 'sources', 'storage', 'donate'] : ['settings', 'sources', 'storage']
  const active = tabs.includes(tab) ? tab : 'settings'

  return (
    <>
      <Tabs tabs={tabs} active={active} onChange={setTab} />
      <div id="profile-panel-settings" role="tabpanel" aria-labelledby="profile-tab-settings" hidden={active !== 'settings'}>
        <AvatarEditor maxBytes={listing?.max_upload_bytes ?? 5 * 1024 * 1024} />
        <ProfileForm onClose={onClose} />
      </div>
      <div id="profile-panel-sources" role="tabpanel" aria-labelledby="profile-tab-sources" hidden={active !== 'sources'}>
        <SourcePicker />
      </div>
      <div id="profile-panel-storage" role="tabpanel" aria-labelledby="profile-tab-storage" hidden={active !== 'storage'}>
        {listing ? (
          <MyFiles listing={listing} onChange={setListing} className="mt-0" />
        ) : (
          <p role={listingFailed ? 'alert' : 'status'} className="m-0 text-sm">
            {t(listingFailed ? 'files.loadError' : 'files.loading')}
          </p>
        )}
      </div>
      {donate?.has_qr && (
        <div id="profile-panel-donate" role="tabpanel" aria-labelledby="profile-tab-donate" hidden={active !== 'donate'}>
          <DonateSection info={donate} className="mt-0" />
        </div>
      )}
    </>
  )
}

type Props = { open: boolean; onClose: () => void; /** true = mở thẳng tab Dung lượng */ scrollToFiles?: boolean }

/** Hộp thoại thông tin cá nhân (thay cho trang /profile cũ): tab Cài đặt, Dung lượng và Ủng hộ. */
export default function ProfileDialog({ open, onClose, scrollToFiles = false }: Props) {
  const { t } = useI18n()
  const dialogRef = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    else if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby="profile-dialog-title"
      onClose={onClose}
      onClick={(e) => {
        if (e.target === dialogRef.current) onClose() // bấm ra ngoài thì đóng
      }}
      className="m-auto h-[min(92vh,760px)] w-[calc(100%-32px)] max-w-[1080px] overflow-y-auto rounded-2xl border border-line bg-surface p-6 text-muted shadow-[0_24px_60px_rgba(0,0,0,.35)] backdrop:bg-black/50"
    >
      <div className="mb-5 flex items-center justify-between gap-3">
        <h2 id="profile-dialog-title" className="m-0 text-xl">
          {t('profile.title')}
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label={t('ref.close')}
          className="inline-flex size-11 cursor-pointer items-center justify-center rounded-lg border-0 bg-transparent text-heading hover:bg-tint"
        >
          <Icon name="close" />
        </button>
      </div>
      {open && <ProfileBody onClose={onClose} initialTab={scrollToFiles ? 'storage' : 'settings'} />}
    </dialog>
  )
}
