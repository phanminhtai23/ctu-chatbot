import { useEffect, useMemo, useRef, useState } from 'react'
import { useI18n } from '../../i18n'
import type { TranslationKey } from '../../i18n/vi'
import {
  applyRouterPrompt,
  proposeRouterPrompt,
  uploadErrorCode,
  type PromptProposal,
  type RouteNode,
} from '../../lib/adminDocuments'
import { diffWords, type DiffPart } from '../../lib/textDiff'
import Icon from '../Icon'

type Props = {
  node: RouteNode
  open: boolean
  onClose: () => void
  /** Gọi sau khi admin đồng ý và lưu xong */
  onApplied: () => void
}

const errorKeys: Record<string, TranslationKey> = {
  LLM_NOT_CONFIGURED: 'admin.doc.rp.errNotConfigured',
  LLM_UNAVAILABLE: 'admin.doc.rp.errUnavailable',
  PROPOSAL_INVALID: 'admin.doc.rp.errInvalid',
  PROPOSAL_INPUT_INVALID: 'admin.doc.rp.errInput',
}

const fieldClass =
  'w-full rounded-lg border border-field bg-surface px-3 py-2 font-sans text-sm text-heading outline-none focus:border-ctu-cyan focus:ring-2 focus:ring-ctu-cyan/20 disabled:opacity-60'

function Parts({ parts }: { parts: DiffPart[] }) {
  return (
    <p className="m-0 whitespace-pre-wrap break-words text-sm leading-relaxed text-heading">
      {parts.map((part, index) =>
        part.kind === 'same' ? (
          <span key={index}>{part.text}</span>
        ) : part.kind === 'add' ? (
          <mark key={index} className="rounded-sm bg-[#CFEFDB] px-0.5 text-[#0F4A25] dark:bg-[#1B4A2E] dark:text-[#B5F0CC]">
            {part.text}
          </mark>
        ) : (
          <del key={index} className="rounded-sm bg-[#FBDADA] px-0.5 text-[#8A1216] dark:bg-[#4A1D1D] dark:text-[#FFB4B7]">
            {part.text}
          </del>
        ),
      )}
    </p>
  )
}

function Comparison({ title, before, after }: { title: string; before: string; after: string }) {
  const { t } = useI18n()
  const diff = useMemo(() => diffWords(before, after), [before, after])
  const unchanged = before.trim() === after.trim()
  return (
    <section aria-label={title} className="rounded-xl border border-line p-3 md:p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h4 className="m-0 text-sm font-semibold text-heading">{title}</h4>
        {unchanged && <span className="rounded-full border border-line px-2 py-0.5 text-xs text-muted">{t('admin.doc.rp.unchanged')}</span>}
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className="min-w-0 rounded-lg bg-tint p-3">
          <div className="mb-1 text-xs font-semibold text-muted">{t('admin.doc.rp.current')}</div>
          <Parts parts={diff.before} />
        </div>
        <div className="min-w-0 rounded-lg border border-[#2E9E5B]/40 bg-surface p-3">
          <div className="mb-1 text-xs font-semibold text-muted">{t('admin.doc.rp.proposed')}</div>
          <Parts parts={diff.after} />
        </div>
      </div>
    </section>
  )
}

/** Hộp thoại nhờ AI viết lại prompt phân loại: nhập mô tả → xem so sánh → đồng ý / từ chối / phản hồi để tạo lại. */
export default function RouterPromptAssist({ node, open, onClose, onApplied }: Props) {
  const { t } = useI18n()
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [description, setDescription] = useState(node.description ?? '')
  const [feedback, setFeedback] = useState('')
  const [result, setResult] = useState<PromptProposal | null>(null)
  const [busy, setBusy] = useState<'generate' | 'apply' | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    else if (!open && dialog.open) dialog.close()
  }, [open])

  // Mỗi lần mở bắt đầu lại từ mô tả đang lưu của tài liệu.
  useEffect(() => {
    if (!open) return
    setDescription(node.description ?? '')
    setFeedback('')
    setResult(null)
    setError('')
  }, [open, node.description, node.id])

  const generate = async (withFeedback: boolean) => {
    if (busy || !description.trim()) return
    setBusy('generate')
    setError('')
    try {
      const next = await proposeRouterPrompt({
        route_id: node.id,
        description,
        ...(withFeedback && result && feedback.trim()
          ? { feedback, previous: { router_prompt: result.proposal.router_prompt, node_prompt: result.proposal.node_prompt } }
          : {}),
      })
      setResult(next)
      setFeedback('')
    } catch (err) {
      setError(t(errorKeys[uploadErrorCode(err)] ?? 'admin.doc.rp.errFailed'))
    } finally {
      setBusy(null)
    }
  }

  const accept = async () => {
    if (!result || busy) return
    setBusy('apply')
    setError('')
    try {
      await applyRouterPrompt({
        route_id: node.id,
        description,
        router_prompt: result.proposal.router_prompt,
        node_prompt: result.proposal.node_prompt,
      })
      onApplied()
    } catch {
      setError(t('admin.doc.rp.errApply'))
    } finally {
      setBusy(null)
    }
  }

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby="rp-title"
      onClose={onClose}
      onClick={(event) => {
        if (event.target === dialogRef.current && !busy) onClose()
      }}
      className="m-auto max-h-[92vh] w-[calc(100%-32px)] max-w-[860px] overflow-y-auto rounded-2xl border border-line bg-surface p-5 text-muted shadow-[0_24px_60px_rgba(0,0,0,.35)] backdrop:bg-black/50 md:p-6"
    >
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id="rp-title" className="m-0 text-lg text-heading">
            {t('admin.doc.rp.title')}
          </h2>
          <p className="mb-0 mt-1 text-sm">{node.label}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          disabled={busy !== null}
          aria-label={t('ref.close')}
          className="inline-flex size-11 flex-none cursor-pointer items-center justify-center rounded-lg border-0 bg-transparent text-heading hover:bg-tint disabled:opacity-50"
        >
          <Icon name="close" />
        </button>
      </div>

      {open && (
        <div className="flex flex-col gap-4">
          <p className="m-0 text-sm">{t('admin.doc.rp.intro')}</p>
          <div>
            <label htmlFor="rp-description" className="mb-1.5 block text-sm font-semibold text-heading">
              {t('admin.doc.rp.descLabel')}
            </label>
            <textarea
              id="rp-description"
              value={description}
              rows={4}
              maxLength={2000}
              disabled={busy !== null}
              placeholder={t('admin.doc.rp.descHint')}
              onChange={(event) => setDescription(event.target.value)}
              className={`${fieldClass} resize-y`}
            />
          </div>
          {!result && (
            <div>
              <button
                type="button"
                onClick={() => void generate(false)}
                disabled={busy !== null || !description.trim()}
                className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border-0 bg-ctu-navy px-5 font-sans text-sm font-semibold text-white hover:bg-ctu-navy-dark disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Icon name="sparkles" size={18} />
                {t(busy === 'generate' ? 'admin.doc.rp.generating' : 'admin.doc.rp.generate')}
              </button>
            </div>
          )}

          {error && (
            <p role="alert" className="m-0 rounded-lg border border-[#D13434] bg-[#FDE7E7] px-3 py-2 text-sm font-semibold text-[#9B1C1C] dark:bg-[#3B1414] dark:text-[#F5A3A3]">
              {error}
            </p>
          )}

          {result && (
            <>
              <div className="border-t border-line pt-4">
                <h3 className="m-0 text-base text-heading">{t('admin.doc.rp.compare')}</h3>
                <p className="mb-0 mt-1 text-xs">{t('admin.doc.rp.legend')}</p>
              </div>
              <Comparison title={t('admin.doc.rp.node')} before={result.current.node_prompt} after={result.proposal.node_prompt} />
              <Comparison title={t('admin.doc.rp.router')} before={result.current.router_prompt} after={result.proposal.router_prompt} />
              {result.proposal.changes.length > 0 && (
                <section aria-label={t('admin.doc.rp.changes')} className="rounded-xl bg-tint p-3 md:p-4">
                  <h4 className="m-0 mb-1.5 text-sm font-semibold text-heading">{t('admin.doc.rp.changes')}</h4>
                  <ul className="m-0 list-disc pl-5 text-sm">
                    {result.proposal.changes.map((change) => (
                      <li key={change}>{change}</li>
                    ))}
                  </ul>
                </section>
              )}
              <div>
                <label htmlFor="rp-feedback" className="mb-1.5 block text-sm font-semibold text-heading">
                  {t('admin.doc.rp.feedback')}
                </label>
                <textarea
                  id="rp-feedback"
                  value={feedback}
                  rows={2}
                  maxLength={1000}
                  disabled={busy !== null}
                  placeholder={t('admin.doc.rp.feedbackHint')}
                  onChange={(event) => setFeedback(event.target.value)}
                  className={`${fieldClass} resize-y`}
                />
              </div>
              <div className="flex flex-wrap gap-2 border-t border-line pt-4">
                <button
                  type="button"
                  onClick={() => void accept()}
                  disabled={busy !== null}
                  className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border-0 bg-ctu-navy px-5 font-sans text-sm font-semibold text-white hover:bg-ctu-navy-dark disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Icon name="check" size={18} />
                  {t(busy === 'apply' ? 'admin.doc.rp.accepting' : 'admin.doc.rp.accept')}
                </button>
                <button
                  type="button"
                  onClick={() => void generate(true)}
                  disabled={busy !== null || !feedback.trim() || !description.trim()}
                  className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border border-ctu-cyan bg-transparent px-4 font-sans text-sm font-semibold text-accent hover:bg-tint disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Icon name="sparkles" size={18} />
                  {t(busy === 'generate' ? 'admin.doc.rp.generating' : 'admin.doc.rp.regenerate')}
                </button>
                <button
                  type="button"
                  onClick={onClose}
                  disabled={busy !== null}
                  className="min-h-11 cursor-pointer rounded-lg border border-line bg-transparent px-4 font-sans text-sm text-heading hover:bg-tint disabled:opacity-50 sm:ml-auto"
                >
                  {t('admin.doc.rp.reject')}
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </dialog>
  )
}
