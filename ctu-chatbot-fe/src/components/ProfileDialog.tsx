import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import { useI18n } from '../i18n'
import type { TranslationKey } from '../i18n/vi'
import { listFiles, type FileListing } from '../lib/files'
import type { ThemeMode } from '../lib/me'
import { useTheme } from '../theme'
import AvatarEditor from './AvatarEditor'
import DonateSection from './DonateSection'
import Icon from './Icon'
import MyFiles from './MyFiles'

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
        <input
          id="profile-birthday"
          type="date"
          value={birthday}
          min="1900-01-01"
          max={now.toISOString().slice(0, 10)}
          autoComplete="bday"
          onChange={(e) => setBirthday(e.target.value)}
          className={`${fieldClass} sm:max-w-[240px]`}
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

      <div className="flex flex-wrap items-center gap-3 border-t border-line pt-4">
        <button
          type="submit"
          disabled={saveState === 'saving'}
          className="min-h-11 cursor-pointer rounded-lg border-0 bg-ctu-navy px-6 py-2.5 font-sans text-base font-semibold text-white hover:bg-ctu-navy-dark disabled:cursor-not-allowed disabled:opacity-50"
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
          className="ml-auto inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border border-field bg-transparent px-4 py-2 font-sans text-sm font-normal text-heading hover:bg-tint"
        >
          <Icon name="logout" size={18} />
          {t('profile.logout')}
        </button>
      </div>
    </form>
  )
}

/** Ảnh đại diện + biểu mẫu thông tin + tệp đã tải lên. Dung lượng đã dùng lấy từ server mỗi lần mở hộp thoại. */
function ProfileBody({ onClose }: { onClose: () => void }) {
  const [listing, setListing] = useState<FileListing | null>(null)
  const { user } = useAuth()

  const refresh = useCallback(() => {
    listFiles()
      .then(setListing)
      .catch(() => {}) // không lấy được thì ẩn mục tệp, phần chỉnh hồ sơ vẫn dùng được
  }, [])
  useEffect(() => {
    refresh()
  }, [refresh])
  // Đổi ảnh đại diện làm thay đổi dung lượng đã dùng: tải lại khi ảnh đổi.
  const avatar = user?.avatar_url
  useEffect(() => {
    if (avatar) refresh()
  }, [avatar, refresh])

  return (
    <>
      <AvatarEditor maxBytes={listing?.max_upload_bytes ?? 5 * 1024 * 1024} />
      <ProfileForm onClose={onClose} />
      <MyFiles listing={listing} onChange={setListing} />
    </>
  )
}

type Props = { open: boolean; onClose: () => void }

/** Hộp thoại chỉnh thông tin cá nhân (thay cho trang /profile cũ). */
export default function ProfileDialog({ open, onClose }: Props) {
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
      className="m-auto max-h-[92vh] w-[calc(100%-32px)] max-w-[520px] overflow-y-auto rounded-2xl border border-line bg-surface p-6 text-muted shadow-[0_24px_60px_rgba(0,0,0,.35)] backdrop:bg-black/50"
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
      {open && <ProfileBody onClose={onClose} />}
      {open && <DonateSection />}
    </dialog>
  )
}
