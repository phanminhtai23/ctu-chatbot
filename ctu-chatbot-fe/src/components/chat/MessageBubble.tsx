import { useMemo } from 'react'
import { useI18n } from '../../i18n'
import type { ChatMessage, SourceRef } from '../../lib/conversations'
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
  /** Mở cửa sổ xem Điều được tham chiếu; kèm danh sách tham chiếu của tin này để chuyển qua lại trong cửa sổ */
  onOpenReference: (article: number, sources: SourceRef[]) => void
  /** Điều đang mở trong cửa sổ tham chiếu (null nếu đang đóng) */
  activeArticle: number | null
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

/** "Điều 34" trong câu trả lời -> "[Điều 34](#ref-34)" cho những Điều có tham chiếu, để bấm vào xem được ngay. */
function linkifyArticles(text: string, articles: Set<number>): string {
  if (articles.size === 0) return text
  return text.replace(/(Điều|điều)\s+(\d{1,2})\b/g, (match, _word: string, num: string) =>
    articles.has(Number(num)) ? `[${match}](#ref-${num})` : match,
  )
}

export default function MessageBubble({ message, liveElapsed, onReport, onOpenReference, activeArticle }: Props) {
  const { t, lang } = useI18n()
  const sources = useMemo(() => message.sources ?? [], [message.sources])
  const content = useMemo(
    () => (message.pending ? message.content : linkifyArticles(message.content, new Set(sources.map((s) => s.article)))),
    [message.content, message.pending, sources],
  )

  if (message.role === 'user') {
    return (
      <div className="max-w-[85%] self-end whitespace-pre-wrap break-words rounded-2xl rounded-br-sm bg-bubble-user px-[18px] py-3 text-[15px] font-normal text-heading">
        {message.content}
      </div>
    )
  }

  const seconds = message.pending ? liveElapsed : message.duration_seconds
  const open = (article: number) => onOpenReference(article, sources)
  return (
    <div className="flex items-start gap-3.5">
      <div className="flex size-9 flex-none items-center justify-center rounded-full bg-ctu-navy text-ctu-gold-active">
        <Icon name="diamond" size={18} strokeWidth={2} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="break-words rounded-2xl rounded-tl-sm bg-bubble-bot px-5 py-4 text-[15px] leading-[1.75] text-heading">
          {message.content ? (
            <Markdown onReference={sources.length > 0 ? open : undefined} activeArticle={activeArticle}>
              {content}
            </Markdown>
          ) : (
            <TypingDots />
          )}
        </div>

        {!message.pending && sources.length > 0 && (
          <div className="mt-2 flex flex-col gap-1.5" aria-label={t('ref.label')}>
            <span className="text-[13px] text-muted">{t('ref.label')}</span>
            <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
              {sources.map((source) => {
                const active = source.article === activeArticle
                return (
                  <li key={source.article}>
                    <button
                      type="button"
                      onClick={() => open(source.article)}
                      aria-pressed={active}
                      title={`${t('ref.open')}: ${t('ref.articlePrefix')} ${source.article}. ${source.title}`}
                      className={`flex min-h-9 w-full cursor-pointer items-center gap-2 rounded-md border bg-surface px-3 py-1.5 text-left font-sans text-[13px] font-normal text-accent hover:bg-tint ${
                        active ? 'border-ctu-gold-active ring-2 ring-ctu-gold-active/60' : 'border-ctu-cyan'
                      }`}
                    >
                      <Icon name="doc" size={14} className="flex-none" />
                      <span className="min-w-0 flex-1 truncate">
                        <strong className="font-semibold">
                          {t('ref.articlePrefix')} {source.article}
                        </strong>
                        {`. ${source.title}`}
                      </span>
                      <span className="flex-none text-xs text-muted">{active ? t('ref.viewing') : t('ref.view')}</span>
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>
        )}

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
