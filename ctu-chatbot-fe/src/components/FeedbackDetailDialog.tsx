import { useEffect, useRef, useState } from 'react'
import { useI18n } from '../i18n'
import type { TranslationKey } from '../i18n/vi'
import { feedbackStatuses, type AdminFeedback, type FeedbackStatus } from '../lib/adminFeedback'
import type { FeedbackCategory } from '../lib/feedback'
import Icon from './Icon'
import StatusBadge from './StatusBadge'

type Props = {
  item: AdminFeedback | null
  formatDate: (iso: string) => string
  onClose: () => void
  onSaveStatus: (id: string, status: FeedbackStatus) => Promise<void>
}

export const categoryKey: Record<FeedbackCategory, TranslationKey> = {
  wrong_answer: 'feedback.cat.wrong_answer',
  wrong_citation: 'feedback.cat.wrong_citation',
  outdated: 'feedback.cat.outdated',
  bug: 'feedback.cat.bug',
  suggestion: 'feedback.cat.suggestion',
  other: 'feedback.cat.other',
}

const statusKey: Record<FeedbackStatus, TranslationKey> = {
  new: 'fbstatus.new',
  reviewed: 'fbstatus.reviewed',
  resolved: 'fbstatus.resolved',
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider">{label}</dt>
      <dd className="m-0 mt-0.5 break-words text-[15px] font-normal text-heading">{children}</dd>
    </div>
  )
}

export default function FeedbackDetailDialog({ item, formatDate, onClose, onSaveStatus }: Props) {
  const { t } = useI18n()
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [status, setStatus] = useState<FeedbackStatus>('new')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(false)

  const itemId = item?.id ?? null
  const itemStatus = item?.status ?? 'new'

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (itemId && !dialog.open) {
      dialog.showModal()
    } else if (!itemId && dialog.open) {
      dialog.close()
    }
  }, [itemId])

  useEffect(() => {
    setStatus(itemStatus)
    setSaving(false)
    setError(false)
  }, [itemId, itemStatus])

  const handleSave = async () => {
    if (!item) return
    setSaving(true)
    setError(false)
    try {
      await onSaveStatus(item.id, status)
      onClose()
    } catch {
      setError(true)
      setSaving(false)
    }
  }

  const titleId = 'feedback-detail-title'

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === dialogRef.current) onClose()
      }}
      className="m-auto max-h-[90vh] w-[calc(100%-32px)] max-w-[640px] rounded-2xl border border-line bg-surface p-0 text-muted shadow-[0_24px_60px_rgba(0,0,0,.35)] backdrop:bg-black/50"
    >
      {item && (
        <>
          <div className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
            <h2 id={titleId} className="m-0 text-lg">{t('admin.fb.detail.title')}</h2>
            <button
              type="button"
              onClick={onClose}
              aria-label={t('feedback.close')}
              className="-mr-2 -mt-1 inline-flex size-11 flex-none cursor-pointer items-center justify-center rounded-lg border-0 bg-transparent text-muted hover:bg-tint"
            >
              <Icon name="close" />
            </button>
          </div>

          <div className="flex flex-col gap-5 px-6 py-5">
            <dl className="m-0 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label={t('admin.fb.detail.user')}>{item.user_email}</Field>
              <Field label={t('admin.fb.detail.time')}>{formatDate(item.created_at)}</Field>
              <Field label={t('admin.fb.detail.type')}>
                {t(item.type === 'answer_issue' ? 'fbtype.answer_issue' : 'fbtype.general')}
              </Field>
              <Field label={t('admin.fb.detail.category')}>{t(categoryKey[item.category])}</Field>
            </dl>

            <div>
              <div className="mb-1.5 text-xs uppercase tracking-wider">{t('admin.fb.detail.message')}</div>
              <p className="m-0 whitespace-pre-wrap break-words rounded-lg bg-tint px-4 py-3 text-[15px] text-heading">
                {item.message || t('admin.fb.noMessage')}
              </p>
            </div>

            {item.type === 'answer_issue' && (
              <div className="flex flex-col gap-3">
                {item.question || item.answer ? (
                  <>
                    <div>
                      <div className="mb-1.5 text-xs uppercase tracking-wider">{t('admin.fb.detail.question')}</div>
                      <p className="m-0 break-words rounded-lg bg-bubble-user px-4 py-3 text-[15px] text-heading">{item.question}</p>
                    </div>
                    <div>
                      <div className="mb-1.5 text-xs uppercase tracking-wider">{t('admin.fb.detail.answer')}</div>
                      <p className="m-0 break-words rounded-lg bg-bubble-bot px-4 py-3 text-[15px] text-heading">{item.answer}</p>
                    </div>
                  </>
                ) : (
                  <p className="m-0 text-sm">{t('admin.fb.detail.noSnapshot')}</p>
                )}
              </div>
            )}

            <fieldset className="m-0 border-0 p-0">
              <legend className="mb-2 flex items-center gap-3 p-0 text-sm font-normal text-heading">
                {t('admin.fb.detail.status')}
                <StatusBadge status={item.status} />
              </legend>
              <div className="flex flex-wrap gap-2">
                {feedbackStatuses.map((s) => (
                  <label
                    key={s}
                    className={`flex min-h-11 cursor-pointer items-center gap-2.5 rounded-lg border px-4 py-2 text-[15px] ${
                      status === s ? 'border-accent bg-tint text-heading' : 'border-line'
                    }`}
                  >
                    <input
                      type="radio"
                      name="feedback-status"
                      value={s}
                      checked={status === s}
                      onChange={() => setStatus(s)}
                      className="size-4 accent-[var(--accent)]"
                    />
                    {t(statusKey[s])}
                  </label>
                ))}
              </div>
            </fieldset>

            {error && (
              <div
                role="alert"
                className="flex items-start gap-3 rounded-lg border border-[#E7B4B6] bg-[#FDF3F3] px-4 py-3 text-sm text-[#8A1216] dark:border-[#7A2A2E] dark:bg-[#2A1416] dark:text-[#FFB4B7]"
              >
                <Icon name="warn" className="mt-[3px] flex-none" />
                <span>{t('admin.fb.detail.saveError')}</span>
              </div>
            )}

            <div className="flex flex-wrap justify-end gap-3">
              <button
                type="button"
                onClick={onClose}
                className="min-h-11 cursor-pointer rounded-lg border border-field bg-transparent px-6 py-2.5 font-sans text-base font-normal text-heading hover:bg-tint"
              >
                {t('feedback.close')}
              </button>
              <button
                type="button"
                onClick={handleSave}
                disabled={saving || status === item.status}
                className="min-h-11 cursor-pointer rounded-lg border-0 bg-ctu-navy px-6 py-2.5 font-sans text-base font-semibold text-white hover:bg-ctu-navy-dark disabled:cursor-not-allowed disabled:opacity-50"
              >
                {t(saving ? 'admin.fb.detail.saving' : 'admin.fb.detail.save')}
              </button>
            </div>
          </div>
        </>
      )}
    </dialog>
  )
}
