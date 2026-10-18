import { useAuth } from '../auth'
import { useI18n } from '../i18n'
import { useTheme } from '../theme'
import Icon from './Icon'

type Props = {
  /** on-navy: đặt trên nền navy (chữ trắng); default: đặt trên nền theo theme */
  tone?: 'on-navy' | 'default'
}

export default function PrefToggles({ tone = 'default' }: Props) {
  const { theme, toggleTheme } = useTheme()
  const { t } = useI18n()
  const { user, updateProfile } = useAuth()

  // Đã đăng nhập thì lưu lựa chọn vào tài khoản; lỗi mạng không chặn việc đổi giao diện tại chỗ.
  const handleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    toggleTheme()
    if (user) updateProfile({ theme: next }).catch(() => {})
  }

  const frame =
    tone === 'on-navy' ? 'border-white/40 text-white hover:bg-white/10' : 'border-field text-accent hover:bg-tint'

  return (
    <button
      type="button"
      onClick={handleTheme}
      aria-label={theme === 'dark' ? t('toggle.toLight') : t('toggle.toDark')}
      className={`inline-flex size-11 cursor-pointer items-center justify-center rounded-lg border bg-transparent ${frame}`}
    >
      <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
    </button>
  )
}
