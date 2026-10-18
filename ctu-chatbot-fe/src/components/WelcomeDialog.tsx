import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../auth'
import { useI18n } from '../i18n'
import { welcomeGifs, pickGif } from '../lib/gifs'
import { pickGreeting, type Greeting } from '../lib/greetings'
import { markWelcomed } from '../lib/me'
import Fireworks from './Fireworks'
import FunDialog from './FunDialog'

/**
 * Hộp thoại chào mừng người dùng mới: pháo hoa, GIF ngẫu nhiên, lời chúc mừng. Hiện đúng MỘT lần cho mỗi tài khoản
 * (server ghi nhận ngay khi hộp thoại hiện ra nên dù đóng tab giữa chừng cũng không hiện lại).
 */
export default function WelcomeDialog() {
  const { t } = useI18n()
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  const [gif, setGif] = useState<string | null>(null)
  const [greeting, setGreeting] = useState<Greeting | null>(null)
  const [shown, setShown] = useState(false) // đã hiện trong phiên làm việc này: không bật lại dù `user` chưa nạp lại

  const needsWelcome = Boolean(user && !user.welcomed)
  const nameRef = useRef('')
  useEffect(() => {
    if (!needsWelcome || shown) return
    // eslint-disable-next-line react-hooks/set-state-in-effect -- mở hộp thoại đúng một lần khi phát hiện tài khoản mới
    setOpen(true)
    setShown(true)
    setGif(pickGif(welcomeGifs))
    setGreeting(pickGreeting(nameRef.current).greeting)
    markWelcomed().catch(() => {}) // lỗi mạng thì lần sau vào sẽ chào lại, chấp nhận được
  }, [needsWelcome, shown])

  // Gọi bằng tên (từ cuối của họ tên); chưa có tên thì lấy phần trước @ của email ("nguyen.van.minh" -> "Minh").
  const raw = (user?.name?.trim() || user?.email.split('@')[0] || '').replace(/[._-]+/g, ' ').trim()
  const last = raw.split(/\s+/).slice(-1)[0] ?? ''
  const name = last.charAt(0).toUpperCase() + last.slice(1)
  nameRef.current = name

  return (
    <FunDialog
      open={open}
      onClose={() => setOpen(false)}
      labelId="welcome-title"
      layout="center"
      gif={gif}
      tone="love"
      icon="heart"
      title={greeting?.title ?? `${t('welcome.title')} ${name}!`}
      message={greeting?.message ?? t('welcome.message')}
      actionLabel={t('welcome.start')}
      overlay={<Fireworks sides />}
      extra={<p className="m-0 text-sm text-muted">{t('welcome.congrats')}</p>}
    />
  )
}
