import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useI18n } from '../i18n'
import type { TranslationKey } from '../i18n/vi'
import {
  FEEDBACK_MAX_LENGTH,
  categoriesByType,
  submitFeedback,
  type FeedbackCategory,
  type FeedbackType,
} from '../lib/feedback'
import Icon from './Icon'

type Props = {
  open: boolean
  type: FeedbackType
  conversationId: string | null
  messageId: string | null
  onClose: () => void
}

type Status = 'idle' | 'submitting' | 'success' | 'error'

const categoryLabel: Record<FeedbackCategory, TranslationKey> = {
  wrong_answer: 'feedback.cat.wrong_answer',
  wrong_citation: 'feedback.cat.wrong_citation',
  outdated: 'feedback.cat.outdated',
  bug: 'feedback.cat.bug',
  suggestion: 'feedback.cat.suggestion',
  other: 'feedback.cat.other',
}

export default function FeedbackModal({ open, type, conversationId, messageId, onClose }: Props) {
  const { t } = useI18n()
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [category, setCategory] = useState<FeedbackCategory | null>(null)
  const [message, setMessage] = useState('')
  const [status, setStatus] = useState<Status>('idle')

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) {
      setCategory(null)
      setMessage('')
      setStatus('idle')
      dialog.showModal()
    } else if (!open && dialog.open) {
      dialog.close()
    }
  }, [open])

  const messageRequired = category === 'other'
  const canSubmit =
    category !== null && status !== 'submitting' && (!messageRequired || message.trim().length > 0)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!category || !canSubmit) return
    setStatus('submitting')
    try {
      await submitFeedback({
        type,
        category,
        message: message.trim(),
        conversation_id: conversationId,
        message_id: messageId,
      })
      setStatus('success')
    } catch {
      setStatus('error')
    }
  }

  const titleId = 'feedback-title'

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(e) => {
        // Bấm vào lớp nền (chính thẻ dialog) thì đóng.
        if (e.target === dialogRef.current) onClose()
      }}
      className="m-auto w-[calc(100%-32px)] max-w-[520px] rounded-2xl border border-line bg-surface p-0 text-muted shadow-[0_24px_60px_rgba(0,0,0,.35)] backdrop:bg-black/50"
    >
      <div className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
        <h2 id={titleId} className="m-0 text-lg">
          {t(type === 'answer_issue' ? 'feedback.titleAnswer' : 'feedback.titleGeneral')}
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label={t('feedback.close')}
          className="-mr-2 -mt-1 inline-flex size-11 flex-none cursor-pointer items-center justify-center rounded-lg border-0 bg-transparent text-muted hover:bg-tint"
        >
          <Icon name="close" />
        </button>
      </div>

      {status === 'success' ? (
        <div className="flex flex-col items-center gap-4 px-6 py-10 text-center">
          <div className="flex size-14 items-center justify-center rounded-full bg-tint text-accent">
            <Icon name="check" size={28} strokeWidth={2.2} />
          </div>
          <div>
            <h3 className="m-0 text-xl">{t('feedback.thanksTitle')}</h3>
            <p className="mb-0 mt-2">{t('feedback.thanksText')}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="min-h-11 cursor-pointer rounded-lg border-0 bg-ctu-navy px-8 py-2.5 font-sans text-base font-semibold text-white hover:bg-ctu-navy-dark"
          >
            {t('feedback.close')}
          </button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="px-6 pb-6 pt-5">
          <p className="mb-4 mt-0 text-sm">
            {t(type === 'answer_issue' ? 'feedback.introAnswer' : 'feedback.introGeneral')}
          </p>

          <fieldset className="m-0 mb-5 border-0 p-0">
            <legend className="mb-2 p-0 text-sm font-normal text-heading">{t('feedback.categoryLabel')}</legend>
            <div className="flex flex-col gap-2">
              {categoriesByType[type].map((c) => (
                <label
                  key={c}
                  className={`flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border px-4 py-2 text-[15px] ${
                    category === c ? 'border-accent bg-tint text-heading' : 'border-line'
                  }`}
                >
                  <input
                    type="radio"
                    name="feedback-category"
                    value={c}
                    checked={category === c}
                    onChange={() => setCategory(c)}
                    className="size-4 accent-[var(--accent)]"
                  />
                  {t(categoryLabel[c])}
                </label>
              ))}
            </div>
          </fieldset>

          <label htmlFor="feedback-message" className="mb-1.5 block text-sm font-normal text-heading">
            {t('feedback.messageLabel')}
            {messageRequired ? ' *' : ` (${t('feedback.optional')})`}
          </label>
          <textarea
            id="feedback-message"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            maxLength={FEEDBACK_MAX_LENGTH}
            rows={4}
            placeholder={t('feedback.messagePlaceholder')}
            className="box-border w-full resize-y rounded-lg border border-field bg-surface px-3.5 py-2.5 font-sans text-[15px] font-light text-heading outline-accent placeholder:text-muted"
          />
          <div className="mb-5 mt-1 text-right text-xs">
            {message.length}/{FEEDBACK_MAX_LENGTH}
          </div>

          {status === 'error' && (
            <div
              role="alert"
              className="mb-4 flex items-start gap-3 rounded-lg border border-[#E7B4B6] bg-[#FDF3F3] px-4 py-3 text-sm text-[#8A1216] dark:border-[#7A2A2E] dark:bg-[#2A1416] dark:text-[#FFB4B7]"
            >
              <Icon name="warn" className="mt-[3px] flex-none" />
              <span>{t('feedback.error')}</span>
            </div>
          )}

          <div className="flex flex-wrap justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="min-h-11 cursor-pointer rounded-lg border border-field bg-transparent px-6 py-2.5 font-sans text-base font-normal text-heading hover:bg-tint"
            >
              {t('feedback.cancel')}
            </button>
            <button
              type="submit"
              disabled={!canSubmit}
              className="min-h-11 cursor-pointer rounded-lg border-0 bg-ctu-navy px-6 py-2.5 font-sans text-base font-semibold text-white hover:bg-ctu-navy-dark disabled:cursor-not-allowed disabled:opacity-50"
            >
              {t(status === 'submitting' ? 'feedback.sending' : 'feedback.submit')}
            </button>
          </div>
        </form>
      )}
    </dialog>
  )
}
