import { useEffect, useState } from 'react'
import warningGif from '../assets/warning.gif'
import { useI18n } from '../i18n'
import type { TranslationKey } from '../i18n/vi'
import type { ChatErrorInfo } from '../lib/chatErrors'
import { errorGifs, pickGif } from '../lib/gifs'
import type { IconName } from './Icon'
import FunDialog, { type FunTone } from './FunDialog'

const looks: Record<ChatErrorInfo['kind'], { icon: IconName; tone: FunTone; title: TranslationKey }> = {
  rate: { icon: 'hourglass', tone: 'warn', title: 'chat.fun.rate.title' },
  busy: { icon: 'sparkles', tone: 'warn', title: 'chat.fun.busy.title' },
  error: { icon: 'warn', tone: 'error', title: 'chat.fun.error.title' },
  warning: { icon: 'warn', tone: 'warn', title: 'chat.fun.warning.title' },
}

const mmss = (seconds: number) => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`

/** Hộp thoại vui khi người dùng bị giới hạn tốc độ hoặc chat bị lỗi: GIF ngẫu nhiên + lời nhắn + (nếu có) đếm ngược. */
export default function ChatErrorDialog({ error, onClose }: { error: ChatErrorInfo | null; onClose: () => void }) {
  const { t } = useI18n()
  const [gif, setGif] = useState<string | null>(null)
  const [remaining, setRemaining] = useState(0)

  // Mỗi lần hiện một GIF khác (cố tránh lặp lại GIF vừa rồi) và đặt lại đồng hồ đếm ngược.
  useEffect(() => {
    if (!error) return
    // eslint-disable-next-line react-hooks/set-state-in-effect -- chọn GIF ngẫu nhiên đúng một lần mỗi khi hộp thoại mở
    setGif((previous) => pickGif(errorGifs, previous))
    setRemaining(error.retryAfter && error.retryAfter > 0 ? Math.min(error.retryAfter, 3600) : 0)
  }, [error])

  useEffect(() => {
    if (!error || remaining <= 0) return
    const id = setTimeout(() => setRemaining((s) => s - 1), 1000)
    return () => clearTimeout(id)
  }, [error, remaining])

  const look = looks[error?.kind ?? 'error']
  const isWarning = error?.kind === 'warning'
  const hasTimer = error?.retryAfter != null && error.retryAfter > 0

  return (
    <FunDialog
      open={error !== null}
      onClose={onClose}
      labelId="chat-error-title"
      gif={isWarning ? warningGif : gif}
      layout={isWarning ? 'center' : 'side'}
      tone={look.tone}
      icon={look.icon}
      title={error?.title ?? t(look.title)}
      message={error?.message ?? ''}
      actionLabel={t(isWarning ? 'chat.fun.warning.ok' : 'chat.fun.ok')}
      extra={
        hasTimer ? (
          <p role="timer" aria-live="off" className="m-0 rounded-xl bg-tint px-4 py-2.5 text-sm text-heading">
            {remaining > 0 ? (
              <>
                {t('chat.fun.retryIn')} <strong className="tabular-nums text-[18px]">{mmss(remaining)}</strong>
              </>
            ) : (
              <strong>{t('chat.fun.ready')}</strong>
            )}
          </p>
        ) : null
      }
    />
  )
}
