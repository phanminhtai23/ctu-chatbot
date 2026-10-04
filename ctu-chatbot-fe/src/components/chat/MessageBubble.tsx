import { useI18n } from '../../i18n'
import type { ChatMessage } from '../../lib/conversations'
import { formatSeconds } from '../../lib/format'
import Icon from '../Icon'
import Markdown from './Markdown'

export type UiMessage = ChatMessage & {
  /** Bot đang trả lời (tin tạm, nội dung tăng dần theo từng đoạn stream) */
  pending?: boolean
}

type Props = {
  message: UiMessage
  /** Giây đã chờ tính đến hiện tại — chỉ dùng cho tin đang trả lời */
  liveElapsed: number
  onReport: (message: UiMessage) => void
}

function TypingDots() {
  const { t } = useI18n()
  return (
    <span role="status" className="inline-flex items-center gap-1.5 py-1" aria-label={t('chat.thinking')}>
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="size-2 animate-bounce rounded-full bg-muted motion-reduce:animate-none"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </span>
  )
}

export default function MessageBubble({ message, liveElapsed, onReport }: Props) {
  const { t, lang } = useI18n()

  if (message.role === 'user') {
    return (
      <div className="max-w-[85%] self-end whitespace-pre-wrap break-words rounded-2xl rounded-br-sm bg-bubble-user px-[18px] py-3 text-[15px] font-normal text-heading">
        {message.content}
      </div>
    )
  }

  const seconds = message.pending ? liveElapsed : message.duration_seconds
  return (
    <div className="flex items-start gap-3.5">
      <div className="flex size-9 flex-none items-center justify-center rounded-full bg-ctu-navy text-ctu-gold-active">
        <Icon name="diamond" size={18} strokeWidth={2} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="break-words rounded-2xl rounded-tl-sm bg-bubble-bot px-5 py-4 text-[15px] leading-[1.75] text-heading">
          {message.content ? <Markdown>{message.content}</Markdown> : <TypingDots />}
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
          {seconds != null && (
            <span className="inline-flex items-center gap-1.5 tabular-nums" title={t('chat.waited')}>
              <Icon name="clock" size={14} />
              <span className="sr-only">{t('chat.waited')}: </span>
              {formatSeconds(lang, seconds)}
            </span>
          )}
          {!message.pending && (
            <button
              type="button"
              onClick={() => onReport(message)}
              className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border-0 bg-transparent px-2 py-1 font-sans text-[13px] font-normal text-muted hover:bg-tint hover:text-accent"
            >
              <Icon name="flag" size={16} />
              {t('chat.reportAnswer')}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
