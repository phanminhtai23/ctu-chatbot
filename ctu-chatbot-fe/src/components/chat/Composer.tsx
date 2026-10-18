import { useLayoutEffect, useRef, type KeyboardEvent } from 'react'
import { useI18n } from '../../i18n'
import type { UserFile } from '../../lib/files'
import { fillTemplate, formatBytes } from '../../lib/format'
import Icon from '../Icon'

/** Tệp đang chuẩn bị đính kèm: tải lên ngay khi chọn, gửi cùng tin nhắn. */
export type PendingFile = {
  key: string
  name: string
  size: number
  kind: 'pdf' | 'image'
  status: 'uploading' | 'ready' | 'error'
  /** Tệp đã lưu trên server (khi status = ready) */
  file?: UserFile
  error?: string
}

export const ATTACH_ACCEPT_TYPES = ['application/pdf', 'image/png', 'image/jpeg', 'image/webp']
export const ATTACH_ACCEPT = ATTACH_ACCEPT_TYPES.join(',')
export const MAX_ATTACHMENTS = 3

type Props = {
  value: string
  onChange: (value: string) => void
  onSend: () => void
  onStop: () => void
  busy: boolean
  /** Có giá trị = không cho gửi (ví dụ chỉ có quyền xem): hiện câu giải thích thay cho ô nhập */
  disabledReason?: string
  /** Không truyền `onAddFiles` = không có đính kèm (ví dụ khách chat qua liên kết chia sẻ): ẩn nút kẹp giấy */
  attachments?: PendingFile[]
  onAddFiles?: (files: File[]) => void
  onRemoveAttachment?: (key: string) => void
  maxUploadBytes?: number
}

const MAX_LENGTH = 4000

export default function Composer({
  value,
  onChange,
  onSend,
  onStop,
  busy,
  disabledReason,
  attachments = [],
  onAddFiles,
  onRemoveAttachment,
  maxUploadBytes = 5 * 1024 * 1024,
}: Props) {
  const { t } = useI18n()
  const ref = useRef<HTMLTextAreaElement>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const uploading = attachments.some((a) => a.status === 'uploading')
  const hasReadyFile = attachments.some((a) => a.status === 'ready')

  // Ô nhập tự cao dần theo nội dung (tối đa ~6 dòng).
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }, [value])

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter gửi, Shift+Enter xuống dòng; đang gõ dấu tiếng Việt (IME) thì Enter không được gửi.
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      if (!busy && !uploading && (value.trim() || hasReadyFile)) onSend()
    }
  }

  const canSend = !busy && !uploading && (value.trim().length > 0 || hasReadyFile)

  if (disabledReason) {
    return (
      <div className="flex justify-center px-4 pb-6 pt-2 sm:px-8">
        <p role="status" className="m-0 w-full max-w-[860px] rounded-2xl border border-line bg-tint px-5 py-3.5 text-center text-sm text-heading">
          {disabledReason}
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center gap-2.5 px-4 pb-6 pt-2 sm:px-8">
      <div className="box-border flex w-full max-w-[860px] flex-col gap-2 rounded-2xl border border-field bg-surface px-3 py-2.5 focus-within:border-accent">
      {attachments.length > 0 && (
        <ul className="m-0 flex list-none flex-wrap gap-2 p-0" aria-label={t('chat.attach')}>
          {attachments.map((a) => (
            <li
              key={a.key}
              className={`flex max-w-full items-center gap-2 rounded-lg border px-2.5 py-1.5 text-[13px] ${
                a.status === 'error' ? 'border-[#E7B4B6] bg-[#FDF3F3] text-[#8A1216] dark:border-[#7A2A2E] dark:bg-[#2A1416] dark:text-[#FFB4B7]' : 'border-line bg-tint text-heading'
              }`}
            >
              <Icon name={a.kind === 'pdf' ? 'doc' : 'image'} size={16} className="flex-none" />
              <span className="min-w-0 max-w-[14rem] truncate" title={a.name}>
                {a.name}
              </span>
              <span className="flex-none text-xs">
                {a.status === 'uploading' ? t('chat.attach.uploading') : a.status === 'error' ? a.error : formatBytes(a.size)}
              </span>
              <button
                type="button"
                onClick={() => onRemoveAttachment?.(a.key)}
                aria-label={`${t('chat.attach.remove')}: ${a.name}`}
                title={t('chat.attach.remove')}
                className="inline-flex size-6 flex-none cursor-pointer items-center justify-center rounded-md border-0 bg-transparent text-current hover:bg-black/10"
              >
                <Icon name="close" size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex items-end gap-2">
        {onAddFiles && (
          <>
            <button
              type="button"
              disabled={busy || attachments.length >= MAX_ATTACHMENTS}
              onClick={() => fileInput.current?.click()}
              aria-label={t('chat.attach')}
              title={fillTemplate(t('chat.attachHint'), { max: formatBytes(maxUploadBytes), count: MAX_ATTACHMENTS })}
              className="inline-flex size-11 flex-none cursor-pointer items-center justify-center rounded-lg border-0 bg-tint text-accent hover:bg-bubble-user disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Icon name="clip" />
            </button>
            <input
              ref={fileInput}
              type="file"
              multiple
              accept={ATTACH_ACCEPT}
              className="hidden"
              onChange={(e) => {
                const files = Array.from(e.target.files ?? [])
                e.target.value = '' // cho phép chọn lại đúng tệp vừa bỏ
                if (files.length > 0) onAddFiles(files)
              }}
            />
          </>
        )}
        <label htmlFor="question" className="sr-only">{t('chat.questionLabel')}</label>
        <textarea
          ref={ref}
          id="question"
          rows={1}
          value={value}
          maxLength={MAX_LENGTH}
          placeholder={t('chat.placeholder')}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          className="min-h-11 min-w-0 flex-1 resize-none border-0 bg-transparent px-1 py-2.5 font-sans text-[15px] font-light leading-6 text-heading outline-0 placeholder:text-muted"
        />
        {busy ? (
          <button
            type="button"
            onClick={onStop}
            aria-label={t('chat.stop')}
            title={t('chat.stop')}
            className="inline-flex size-11 flex-none cursor-pointer items-center justify-center rounded-full border-0 bg-heading text-surface hover:opacity-85"
          >
            <Icon name="stop" size={18} fill="currentColor" />
          </button>
        ) : (
          <button
            type="button"
            onClick={onSend}
            disabled={!canSend}
            aria-label={t('chat.send')}
            className="inline-flex size-11 flex-none cursor-pointer items-center justify-center rounded-full border-0 bg-ctu-navy text-white hover:bg-ctu-navy-dark disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Icon name="arrow" size={18} strokeWidth={2} />
          </button>
        )}
      </div>
      </div>
      <p className="m-0 text-center text-xs">{t('chat.disclaimer')}</p>
    </div>
  )
}
