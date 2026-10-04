import { useLayoutEffect, useRef, type KeyboardEvent } from 'react'
import { useI18n } from '../../i18n'
import Icon from '../Icon'

type Props = {
  value: string
  onChange: (value: string) => void
  onSend: () => void
  onStop: () => void
  busy: boolean
}

const MAX_LENGTH = 4000

export default function Composer({ value, onChange, onSend, onStop, busy }: Props) {
  const { t } = useI18n()
  const ref = useRef<HTMLTextAreaElement>(null)

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
      if (!busy && value.trim()) onSend()
    }
  }

  const canSend = !busy && value.trim().length > 0

  return (
    <div className="flex flex-col items-center gap-2.5 px-4 pb-6 pt-2 sm:px-8">
      <div className="box-border flex w-full max-w-[780px] items-end gap-2 rounded-2xl border border-field bg-surface px-3 py-2.5 focus-within:border-accent">
        <button
          type="button"
          disabled
          aria-label={t('chat.attach')}
          title={t('chat.attachSoon')}
          className="inline-flex size-11 flex-none cursor-not-allowed items-center justify-center rounded-lg border-0 bg-tint text-accent opacity-60"
        >
          <Icon name="clip" />
        </button>
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
      <p className="m-0 text-center text-xs">{t('chat.disclaimer')}</p>
    </div>
  )
}
