import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth'
import GoogleSignInButton from '../components/GoogleSignInButton'
import Icon from '../components/Icon'
import Logo from '../components/Logo'
import PrefToggles from '../components/PrefToggles'
import { useI18n } from '../i18n'
import { ApiError } from '../lib/api'
import { GOOGLE_CLIENT_ID } from '../lib/google'

// Đăng nhập thử bằng email, không cần Google (BE chỉ chấp nhận khi ENV=dev). Tắt ở production.
const DEV_LOGIN = import.meta.env.VITE_DEV_LOGIN === 'true'

function GoogleMark() {
  return (
    <svg width="22" height="22" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.5 5.4 2.6 13.3l7.9 6.1C12.4 13.6 17.7 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.5 5.8c4.4-4.1 7.1-10.1 7.1-17.5z" />
      <path fill="#FBBC05" d="M10.5 28.6A14.5 14.5 0 0 1 9.5 24c0-1.6.3-3.2.8-4.6l-7.9-6.1A24 24 0 0 0 0 24c0 3.9.9 7.5 2.6 10.7l7.9-6.1z" />
      <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.5-5.8c-2.1 1.4-4.9 2.3-8.4 2.3-6.3 0-11.6-4.1-13.5-9.9l-7.9 6.1C6.5 42.6 14.6 48 24 48z" />
    </svg>
  )
}

export default function Login() {
  const location = useLocation()
  const { t } = useI18n()
  const { user, loginWithGoogle, login } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // Admin luôn vào thẳng khu quản trị; user thường quay lại trang đang định vào (nếu bị chặn giữa chừng) hoặc /chat.
  const from = (location.state as { from?: string } | null)?.from
  if (user) return <Navigate to={user.role === 'admin' ? '/admin/dashboard' : (from ?? '/chat')} replace />

  const reportError = (err: unknown) =>
    setError(t(err instanceof ApiError && err.status === 403 ? 'login.errDomain' : 'login.errGeneric'))

  const handleGoogleCredential = async (credential: string) => {
    setError(null)
    try {
      await loginWithGoogle(credential) // có user rồi thì <Navigate> ở trên tự chuyển trang
    } catch (err) {
      reportError(err)
    }
  }

  const handleDevLogin = async (e: FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await login(email.trim())
    } catch (err) {
      reportError(err)
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen flex-wrap bg-surface">
      <div className="box-border flex min-w-0 flex-[1_1_480px] flex-col justify-between gap-4 bg-ctu-navy px-6 py-6 text-white sm:px-10 lg:gap-12 lg:px-16 lg:py-14">
        <Link to="/" className="flex items-center gap-3.5 text-white no-underline">
          <Logo />
          <div className="leading-tight">
            <div className="text-[17px] font-semibold tracking-wide">{t('brand.uni')}</div>
            <div className="text-[13px] font-light">{t('brand.sub')}</div>
          </div>
        </Link>
        <div>
          <h1 className="m-0 text-2xl leading-[1.2] text-white md:mb-5 md:text-[length:clamp(1.9rem,3.2vw,2.75rem)]">
            {t('login.heroTitle')}
          </h1>
          <p className="m-0 hidden max-w-[460px] text-lg text-white/90 md:block">{t('login.heroDesc')}</p>
          <div className="mt-8 hidden h-1 w-[72px] rounded-sm bg-ctu-gold-active md:block" />
        </div>
        <p className="m-0 hidden text-[13px] text-white/85 md:block">{t('brand.disclaimer')}</p>
      </div>

      <div className="box-border flex min-w-0 flex-[1_1_480px] flex-col px-8 py-6">
        <div className="flex justify-end">
          <PrefToggles />
        </div>
        <div className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-[420px]">
            <h2 className="mb-2 text-[2rem]">{t('login.title')}</h2>
            <p className="mb-8">{t('login.welcome')}</p>

            {GOOGLE_CLIENT_ID ? (
              <GoogleSignInButton
                onCredential={handleGoogleCredential}
                onError={() => setError(t('login.errGoogle'))}
              />
            ) : (
              <>
                <button
                  type="button"
                  disabled
                  aria-describedby="google-soon"
                  className="flex min-h-12 w-full cursor-not-allowed items-center justify-center gap-3.5 rounded-lg border border-field bg-white px-5 py-3.5 font-sans text-base font-normal text-[#132C33] opacity-60"
                >
                  <GoogleMark />
                  {t('login.google')}
                </button>
                <p id="google-soon" className="mb-0 mt-2 text-sm">{t('login.googleSoon')}</p>
              </>
            )}

            {error && (
              <div
                role="alert"
                className="mt-4 flex items-start gap-3 rounded-lg border border-[#E7B4B6] bg-[#FDF3F3] px-4 py-3 text-sm text-[#8A1216] dark:border-[#7A2A2E] dark:bg-[#2A1416] dark:text-[#FFB4B7]"
              >
                <Icon name="warn" className="mt-[3px] flex-none" />
                <span>{error}</span>
              </div>
            )}

            <div className="mt-5 flex items-start gap-3 rounded-lg border border-line bg-tint px-4 py-3.5 text-sm">
              <Icon name="info" className="mt-[3px] flex-none text-accent" />
              <span>
                {t('login.domainPre')}
                <strong className="font-semibold text-heading">.edu.ctu.vn</strong>
                {t('login.domainPost')}
              </span>
            </div>

            {DEV_LOGIN && (
              <form onSubmit={handleDevLogin} className="mt-8 border-t border-line pt-6">
                <h3 className="mb-3 mt-0 text-base">{t('login.devTitle')}</h3>
                <label htmlFor="dev-email" className="mb-1.5 block text-sm font-normal text-heading">
                  {t('login.devEmail')}
                </label>
                <input
                  id="dev-email"
                  type="email"
                  required
                  autoComplete="email"
                  placeholder="b2100001@student.edu.ctu.vn"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="mb-3 box-border min-h-11 w-full rounded-lg border border-field bg-surface px-3.5 py-2 font-sans text-[15px] text-heading outline-accent placeholder:text-muted"
                />
                <button
                  type="submit"
                  disabled={submitting || !email.trim()}
                  className="min-h-11 w-full cursor-pointer rounded-lg border-0 bg-ctu-navy px-5 py-3 font-sans text-base font-semibold text-white hover:bg-ctu-navy-dark disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {t(submitting ? 'login.devSubmitting' : 'login.devSubmit')}
                </button>
              </form>
            )}

            <p className="mt-8 text-sm">
              {t('login.terms')}{' '}
              <Link to="/" className="text-link hover:text-link-hover">{t('login.back')}</Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
