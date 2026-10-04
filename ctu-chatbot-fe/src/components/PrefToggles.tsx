import { useAuth } from '../auth'
import { useI18n, type Lang } from '../i18n'
import { useTheme } from '../theme'
import Icon from './Icon'

type Props = {
  /** on-navy: đặt trên nền navy (chữ trắng); default: đặt trên nền theo theme */
  tone?: 'on-navy' | 'default'
}

const langs: Lang[] = ['vi', 'en']

export default function PrefToggles({ tone = 'default' }: Props) {
  const { theme, toggleTheme } = useTheme()
  const { lang, setLang, t } = useI18n()
  const { user, updateProfile } = useAuth()

  // Đã đăng nhập thì lưu lựa chọn vào tài khoản; lỗi mạng không chặn việc đổi giao diện tại chỗ.
  const saveToAccount = (patch: { language?: Lang; theme?: 'light' | 'dark' }) => {
    if (user) updateProfile(patch).catch(() => {})
  }

  const handleLang = (code: Lang) => {
    setLang(code)
    saveToAccount({ language: code })
  }

  const handleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    toggleTheme()
    saveToAccount({ theme: next })
  }

  const onNavy = tone === 'on-navy'
  const frame = onNavy
    ? 'border-white/40 text-white hover:bg-white/10'
    : 'border-field text-accent hover:bg-tint'
  const activeLang = onNavy ? 'bg-white text-ctu-navy' : 'bg-ctu-navy text-white'

  return (
    <div className="flex items-center gap-2">
      <div role="group" aria-label={t('toggle.lang')} className={`flex overflow-hidden rounded-lg border ${frame}`}>
        {langs.map((code) => (
          <button
            key={code}
            type="button"
            onClick={() => handleLang(code)}
            aria-pressed={lang === code}
            className={`min-h-11 min-w-11 cursor-pointer border-0 px-3 font-sans text-sm font-semibold uppercase ${
              lang === code ? activeLang : 'bg-transparent text-inherit'
            }`}
          >
            {code}
          </button>
        ))}
      </div>
      <button
        type="button"
        onClick={handleTheme}
        aria-label={theme === 'dark' ? t('toggle.toLight') : t('toggle.toDark')}
        className={`inline-flex size-11 cursor-pointer items-center justify-center rounded-lg border bg-transparent ${frame}`}
      >
        <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
      </button>
    </div>
  )
}
