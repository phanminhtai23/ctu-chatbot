import { useMemo } from 'react'
import { useFormatDate } from '../../hooks/useFormatDate'
import { useI18n } from '../../i18n'
import { articleSources, webSources, type ChatMessage, type SourceRef } from '../../lib/conversations'
import { formatBytes, formatSeconds } from '../../lib/format'
import Icon from '../Icon'
import Markdown from './Markdown'

export type UiMessage = ChatMessage & {
  /** Bot đang trả lời (tin tạm, nội dung tăng dần theo từng đoạn stream) */
  pending?: boolean
  /** Đang xếp hàng chờ tới lượt (server đông); undefined khi không phải chờ */
  queuePosition?: number
}

type Props = {
  message: UiMessage
  /** Giây đã chờ tính đến hiện tại — chỉ dùng cho tin đang trả lời */
  liveElapsed: number
  /** Không truyền = ẩn nút "Báo câu trả lời sai" (ví dụ khách xem qua liên kết chia sẻ) */
  onReport?: (message: UiMessage) => void
  /** Mở cửa sổ xem Điều được tham chiếu; kèm danh sách tham chiếu của tin này để chuyển qua lại trong cửa sổ */
  onOpenReference: (article: number, sources: SourceRef[]) => void
  /** Điều đang mở trong cửa sổ tham chiếu (null nếu đang đóng) */
  activeArticle: number | null
}

function TypingDots({ queuePosition }: { queuePosition?: number }) {
  const { t } = useI18n()
  return (
    <span role="status" className="inline-flex items-center gap-2 py-1" aria-label={t('chat.thinking')}>
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="size-2 animate-bounce rounded-full bg-muted motion-reduce:animate-none"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
      {queuePosition != null && (
        <span className="text-[13px] text-muted">
          {t('chat.queued')} {queuePosition}
        </span>
      )}
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

/**
 * Giờ gửi tin theo múi giờ đã cài của người dùng. Nằm NỔI phía trên tin nhắn (không chiếm chỗ trong bố cục) và chỉ hiện khi
 * rê chuột / focus vào tin; cha phải có `group relative`.
 */
function SentAt({ iso, align = 'left' }: { iso: string | null; align?: 'left' | 'right' }) {
  const { t } = useI18n()
  const formatDate = useFormatDate()
  if (!iso) return null
  return (
    <span
      className={`pointer-events-none absolute -top-5 z-10 whitespace-nowrap text-xs text-muted opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100 ${
        align === 'right' ? 'right-1' : 'left-[50px]'
      }`}
    >
      {t('chat.sentAt')} {formatDate(iso)}
    </span>
  )
}

export default function MessageBubble({ message, liveElapsed, onReport, onOpenReference, activeArticle }: Props) {
  const { t } = useI18n()
  const sources = useMemo(() => articleSources(message.sources), [message.sources])
  const web = useMemo(() => webSources(message.sources), [message.sources])
  const content = useMemo(
    () => (message.pending ? message.content : linkifyArticles(message.content, new Set(sources.map((s) => s.article)))),
    [message.content, message.pending, sources],
  )

  if (message.role === 'user') {
    return (
      <div className="group relative flex max-w-[85%] flex-col items-end gap-1 self-end">
        {message.author_name && <span className="px-1 text-xs text-muted">{message.author_name}</span>}
        {message.attachments && message.attachments.length > 0 && (
          <ul className="m-0 flex list-none flex-wrap justify-end gap-2 p-0" aria-label={t('chat.attach')}>
            {message.attachments.map((file) => (
              <li key={file.id} className="max-w-full">
                {/* Mở tab mới: trình duyệt tự xem trước PDF / ảnh. Chỉ nhận http(s). */}
                <a
                  href={/^https?:\/\//i.test(file.url) ? file.url : undefined}
                  target="_blank"
                  rel="noopener noreferrer"
                  title={`${t('chat.attach.open')}: ${file.filename}`}
                  className="flex max-w-full items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2 text-[13px] text-heading no-underline hover:border-ctu-cyan hover:bg-tint"
                >
                  <Icon name={file.content_type === 'application/pdf' ? 'doc' : 'image'} size={18} className="flex-none text-accent" />
                  <span className="min-w-0 max-w-[16rem] truncate font-normal">{file.filename}</span>
                  <span className="flex-none text-xs text-muted">{formatBytes(file.size_bytes)}</span>
                </a>
              </li>
            ))}
          </ul>
        )}
        {message.content && (
          <div className="whitespace-pre-wrap break-words rounded-2xl rounded-br-sm bg-bubble-user px-[18px] py-3 text-[15px] font-normal text-heading">
            {message.content}
          </div>
        )}
        <SentAt iso={message.created_at} align="right" />
      </div>
    )
  }

  const seconds = message.pending ? liveElapsed : message.duration_seconds
  const open = (article: number) => onOpenReference(article, sources)
  return (
    <div className="group relative flex items-start gap-3.5">
      {!message.pending && <SentAt iso={message.created_at} />}
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
            <TypingDots queuePosition={message.queuePosition} />
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

        {!message.pending && web.length > 0 && (
          <div className="mt-2 flex flex-col gap-1.5" aria-label={t('ref.webLabel')}>
            <span className="text-[13px] text-muted">{t('ref.webLabel')}</span>
            <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
              {web.map((source) => (
                <li key={source.url}>
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    title={source.url}
                    className="flex min-h-9 w-full items-center gap-2 rounded-md border border-ctu-cyan bg-surface px-3 py-1.5 text-left font-sans text-[13px] font-normal text-accent no-underline hover:bg-tint"
                  >
                    {source.n != null ? (
                      <span className="flex-none rounded bg-tint px-1.5 text-xs font-semibold text-accent">[{source.n}]</span>
                    ) : (
                      <Icon name="doc" size={14} className="flex-none" />
                    )}
                    <span className="min-w-0 flex-1 truncate">{source.title || source.url}</span>
                    <span className="flex-none text-xs text-muted">{new URL(source.url).hostname}</span>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
          {seconds != null && (
            <span className="inline-flex items-center gap-1.5 tabular-nums" title={t('chat.waited')}>
              <Icon name="clock" size={14} />
              <span className="sr-only">{t('chat.waited')}: </span>
              {formatSeconds(seconds)}
            </span>
          )}
          {!message.pending && onReport && (
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
