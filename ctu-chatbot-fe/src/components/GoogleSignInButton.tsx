import { GoogleLogin } from '@react-oauth/google'
import { useEffect, useRef, useState } from 'react'
import { useI18n } from '../i18n'

type Props = {
  onCredential: (credential: string) => void
  onError: () => void
}

// Nút thật của Google chỉ cho chỉnh kích thước 200–400px và 40px cao, nên ta vẽ nút theo thiết kế
// của app rồi đặt nút Google trong suốt chồng lên: bấm vào là bấm thẳng vào nút Google (vẫn lấy
// ID token đúng chuẩn, không cần client secret).
const GOOGLE_MIN_WIDTH = 200
const GOOGLE_MAX_WIDTH = 400
const GOOGLE_HEIGHT = 40
const OUR_HEIGHT = 48

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

export default function GoogleSignInButton({ onCredential, onError }: Props) {
  const { t } = useI18n()
  const containerRef = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(320)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const update = () => setWidth(Math.round(el.getBoundingClientRect().width) || 320)
    update()
    const observer = new ResizeObserver(update)
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const googleWidth = Math.min(GOOGLE_MAX_WIDTH, Math.max(GOOGLE_MIN_WIDTH, width))

  return (
    <div
      ref={containerRef}
      style={{ height: OUR_HEIGHT }}
      className="group relative w-full overflow-hidden rounded-lg focus-within:ring-2 focus-within:ring-accent focus-within:ring-offset-2 focus-within:ring-offset-surface"
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 flex items-center justify-center gap-3.5 rounded-lg border border-field bg-surface font-sans text-base font-normal text-heading transition-colors group-hover:bg-tint"
      >
        <GoogleMark />
        {t('login.google')}
      </div>

      <div
        className="absolute left-0 top-0 opacity-[0.01]"
        style={{
          width: googleWidth,
          height: GOOGLE_HEIGHT,
          transform: `scale(${width / googleWidth}, ${OUR_HEIGHT / GOOGLE_HEIGHT})`,
          transformOrigin: 'top left',
        }}
      >
        <GoogleLogin
          onSuccess={(res) => {
            if (res.credential) onCredential(res.credential)
            else onError()
          }}
          onError={onError}
          theme="outline"
          size="large"
          shape="rectangular"
          width={String(googleWidth)}
        />
      </div>
    </div>
  )
}
