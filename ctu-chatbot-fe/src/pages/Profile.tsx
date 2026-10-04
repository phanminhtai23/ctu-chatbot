import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import Icon from '../components/Icon'
import Logo from '../components/Logo'
import { useI18n } from '../i18n'
import type { TranslationKey } from '../i18n/vi'
import type { Language, ThemeMode } from '../lib/me'
import { useTheme } from '../theme'

const themeOptions: { value: ThemeMode; label: TranslationKey }[] = [
  { value: 'system', label: 'profile.theme.system' },
  { value: 'light', label: 'profile.theme.light' },
  { value: 'dark', label: 'profile.theme.dark' },
]

const languageOptions: { value: Language; label: string }[] = [
  { value: 'vi', label: 'Tiếng Việt' },
  { value: 'en', label: 'English' },
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
  const set = new Set([...FALLBACK_TIMEZONES, ...zones, current])
  return [...set].sort((a, b) => a.localeCompare(b))
}

type SaveState = 'idle' | 'saving' | 'saved' | 'error'

const fieldClass =
  'box-border min-h-11 w-full rounded-lg border border-field bg-surface px-3.5 py-2 font-sans text-[15px] text-heading outline-accent'
const labelClass = 'mb-1.5 block text-sm font-normal text-heading'

export default function Profile() {
  const { t, lang, setLang } = useI18n()
  const { setMode } = useTheme()
  const { user, updateProfile, logout } = useAuth()
  const navigate = useNavigate()

  const [name, setName] = useState(user?.name ?? '')
  const [birthday, setBirthday] = useState(user?.birthday ?? '')
  const [language, setLanguage] = useState<Language>(user?.language ?? 'vi')
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
      return new Intl.DateTimeFormat(lang === 'vi' ? 'vi-VN' : 'en-GB', {
        dateStyle: 'medium',
        timeStyle: 'short',
        timeZone: timezone,
      }).format(now)
    } catch {
      return ''
    }
  }, [now, timezone, lang])

  if (!user) return null // RequireAuth đã chặn; giữ cho TypeScript.

  const today = now.toISOString().slice(0, 10)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSaveState('saving')
    try {
      await updateProfile({
        name: name.trim(),
        birthday: birthday || null,
        timezone,
        language,
        theme,
      })
      // Áp ngay ngôn ngữ/giao diện vừa lưu cho phiên hiện tại.
      setLang(language)
      setMode(theme)
      setSaveState('saved')
    } catch {
      setSaveState('error')
    }
  }

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  const dirtyReset = () => {
    if (saveState !== 'idle') setSaveState('idle')
  }

  return (
    <div className="min-h-screen bg-tint">
      <header className="bg-ctu-navy text-white">
        <div className="mx-auto flex max-w-[720px] flex-wrap items-center justify-between gap-3 px-6 py-3">
          <div className="flex items-center gap-3">
            <Logo size={36} />
            <span className="text-[15px] font-semibold">{t('brand.app')}</span>
          </div>
          <Link
            to="/chat"
            className="inline-flex min-h-11 items-center gap-2 text-sm text-white no-underline hover:text-ctu-gold"
          >
            <Icon name="arrow" className="rotate-180" size={18} />
            {t('profile.back')}
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-[720px] px-6 py-8">
        <h1 className="mb-6 mt-0 text-2xl">{t('profile.title')}</h1>

        <form onSubmit={handleSubmit} onChange={dirtyReset} className="flex flex-col gap-6">
          <section className="rounded-2xl border border-line bg-surface p-6">
            <h2 className="mb-4 mt-0 text-lg">{t('profile.sectionInfo')}</h2>

            <label htmlFor="profile-email" className={labelClass}>{t('profile.email')}</label>
            <input
              id="profile-email"
              type="email"
              value={user.email}
              readOnly
              className={`${fieldClass} mb-4 cursor-not-allowed bg-tint`}
            />

            <label htmlFor="profile-name" className={labelClass}>{t('profile.name')}</label>
            <input
              id="profile-name"
              type="text"
              value={name}
              maxLength={100}
              autoComplete="name"
              onChange={(e) => setName(e.target.value)}
              className={`${fieldClass} mb-4`}
            />

            <label htmlFor="profile-birthday" className={labelClass}>{t('profile.birthday')}</label>
            <input
              id="profile-birthday"
              type="date"
              value={birthday}
              min="1900-01-01"
              max={today}
              autoComplete="bday"
              onChange={(e) => setBirthday(e.target.value)}
              className={`${fieldClass} sm:max-w-[240px]`}
            />
          </section>

          <section className="rounded-2xl border border-line bg-surface p-6">
            <h2 className="mb-4 mt-0 text-lg">{t('profile.sectionPrefs')}</h2>

            <label htmlFor="profile-language" className={labelClass}>{t('profile.language')}</label>
            <select
              id="profile-language"
              value={language}
              onChange={(e) => setLanguage(e.target.value as Language)}
              className={`${fieldClass} mb-4 sm:max-w-[240px]`}
            >
              {languageOptions.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>

            <fieldset className="m-0 mb-4 border-0 p-0">
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

            <label htmlFor="profile-timezone" className={labelClass}>{t('profile.timezone')}</label>
            <select
              id="profile-timezone"
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
              className={`${fieldClass} sm:max-w-[360px]`}
            >
              {zones.map((z) => (
                <option key={z} value={z}>{z}</option>
              ))}
            </select>
            {timePreview && (
              <p className="mb-0 mt-2 text-sm">
                {t('profile.timezoneNow')} <strong className="font-semibold text-heading">{timePreview}</strong>
              </p>
            )}
          </section>

          <div className="flex flex-wrap items-center gap-4">
            <button
              type="submit"
              disabled={saveState === 'saving'}
              className="min-h-11 cursor-pointer rounded-lg border-0 bg-ctu-navy px-8 py-2.5 font-sans text-base font-semibold text-white hover:bg-ctu-navy-dark disabled:cursor-not-allowed disabled:opacity-50"
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
              {saveState === 'error' && (
                <span className="text-[#8A1216] dark:text-[#FFB4B7]">{t('profile.saveError')}</span>
              )}
            </span>
            <button
              type="button"
              onClick={handleLogout}
              className="ml-auto inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border border-field bg-transparent px-5 py-2 font-sans text-sm font-normal text-heading hover:bg-surface"
            >
              <Icon name="logout" size={18} />
              {t('profile.logout')}
            </button>
          </div>
        </form>
      </main>
    </div>
  )
}
