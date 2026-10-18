import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import ConfirmDialog from '../../components/ConfirmDialog'
import Icon from '../../components/Icon'
import { useFormatDate } from '../../hooks/useFormatDate'
import { useI18n } from '../../i18n'
import type { TranslationKey } from '../../i18n/vi'
import {
  MAX_ANSWER,
  MAX_QUESTION,
  createEntry,
  deleteEntry,
  embedOne,
  embedPending,
  knowledgeErrorCode,
  listKnowledge,
  testQuery,
  updateEntry,
  type KnowledgeEntry,
  type KnowledgeErrorCode,
  type KnowledgeList,
  type KnowledgeState,
  type KnowledgeTest,
} from '../../lib/adminKnowledge'
import { fillTemplate } from '../../lib/format'
import AdminLayout from './AdminLayout'

type Notice = { kind: 'ok' | 'error'; text: string }

const errorKeys: Record<KnowledgeErrorCode, TranslationKey> = {
  DUPLICATE_QUESTION: 'admin.kb.err.duplicate',
  EMBEDDING_UNAVAILABLE: 'admin.kb.err.embedding',
  KNOWLEDGE_UNAVAILABLE: 'admin.kb.err.unavailable',
  EMPTY_FIELD: 'admin.kb.err.empty',
  TOO_LONG: 'admin.kb.err.tooLong',
  UNKNOWN: 'admin.kb.err.unknown',
}

const fieldClass =
  'box-border w-full rounded-lg border border-field bg-surface px-3.5 py-2.5 font-sans text-[15px] text-heading outline-accent'
const primaryButton =
  'inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-lg border-0 bg-ctu-navy px-5 py-2.5 font-sans text-[15px] font-semibold text-white hover:bg-ctu-navy-dark disabled:cursor-not-allowed disabled:opacity-50'
const secondaryButton =
  'inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-lg border border-field bg-transparent px-5 py-2.5 font-sans text-[15px] font-normal text-heading hover:bg-tint disabled:cursor-not-allowed disabled:opacity-50'
const smallButton =
  'inline-flex min-h-9 cursor-pointer items-center gap-1.5 rounded-md border border-line bg-surface px-3 font-sans text-[13px] text-heading hover:bg-tint disabled:cursor-not-allowed disabled:opacity-50'

function StatusBadge({ state }: { state: KnowledgeState }) {
  const { t } = useI18n()
  const tone =
    state === 'embedded'
      ? 'bg-[#E3F4EA] text-[#14602F] dark:bg-[#12301F] dark:text-[#8AD9A8]'
      : 'bg-[#FFF2D6] text-[#7A5200] dark:bg-[#3A2D0E] dark:text-[#F5D28A]'
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${tone}`}>
      {t(state === 'embedded' ? 'admin.kb.state.embedded' : 'admin.kb.state.pending')}
    </span>
  )
}

export default function AdminKnowledge() {
  const { t } = useI18n()
  const formatDate = useFormatDate()
  const formRef = useRef<HTMLFormElement>(null)

  const [data, setData] = useState<KnowledgeList | null>(null)
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [query, setQuery] = useState('')
  const [state, setState] = useState<'all' | KnowledgeState>('all')
  const [notice, setNotice] = useState<Notice | null>(null)
  const [busy, setBusy] = useState<string | null>(null) // 'save' | 'embed' | 'embedAll' | id đang embedding

  const [editingId, setEditingId] = useState<string | null>(null)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')

  const [deleteTarget, setDeleteTarget] = useState<KnowledgeEntry | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [confirmAll, setConfirmAll] = useState(false)

  const [testText, setTestText] = useState('')
  const [testResult, setTestResult] = useState<KnowledgeTest | null>(null)
  const [testing, setTesting] = useState(false)

  const load = useCallback(async () => {
    try {
      setData(await listKnowledge(query, state))
      setLoadState('ready')
    } catch {
      setLoadState('error')
    }
  }, [query, state])

  useEffect(() => {
    const id = setTimeout(load, query ? 250 : 0) // gõ tìm kiếm thì chờ một chút rồi mới hỏi server
    return () => clearTimeout(id)
  }, [load, query])

  const stats = data?.stats
  const mismatch = stats && stats.vector_count !== null && stats.vector_count !== stats.embedded

  const fail = (err: unknown) => setNotice({ kind: 'error', text: t(errorKeys[knowledgeErrorCode(err)]) })

  const resetForm = () => {
    setEditingId(null)
    setQuestion('')
    setAnswer('')
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy('save')
    setNotice(null)
    try {
      if (editingId) await updateEntry(editingId, question.trim(), answer.trim())
      else await createEntry(question.trim(), answer.trim())
      setNotice({ kind: 'ok', text: t(editingId ? 'admin.kb.savedEdit' : 'admin.kb.savedNew') })
      resetForm()
      await load()
    } catch (err) {
      fail(err)
    } finally {
      setBusy(null)
    }
  }

  const startEdit = (entry: KnowledgeEntry) => {
    setEditingId(entry.id)
    setQuestion(entry.question)
    setAnswer(entry.answer)
    setNotice(null)
    formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  const runEmbed = async (mode: 'embed' | 'embedAll' | string, action: () => Promise<{ embedded: number }>) => {
    setBusy(mode)
    setNotice(null)
    try {
      const res = await action()
      setNotice({ kind: 'ok', text: fillTemplate(t('admin.kb.embedded'), { n: res.embedded }) })
      await load()
    } catch (err) {
      fail(err)
      await load()
    } finally {
      setBusy(null)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteEntry(deleteTarget.id)
      if (editingId === deleteTarget.id) resetForm()
      setDeleteTarget(null)
      setDeleteError(null)
      await load()
    } catch (err) {
      setDeleteError(t(errorKeys[knowledgeErrorCode(err)]))
    }
  }

  const handleTest = async (e: FormEvent) => {
    e.preventDefault()
    if (!testText.trim()) return
    setTesting(true)
    setNotice(null)
    try {
      setTestResult(await testQuery(testText.trim()))
    } catch (err) {
      setTestResult(null)
      fail(err)
    } finally {
      setTesting(false)
    }
  }

  const statCards = useMemo(
    () =>
      [
        ['admin.kb.stat.total', stats?.total ?? 0],
        ['admin.kb.stat.embedded', stats?.embedded ?? 0],
        ['admin.kb.stat.pending', stats?.pending ?? 0],
      ] as const,
    [stats],
  )

  return (
    <AdminLayout title={t('admin.kb.title')} subtitle={t('admin.kb.subtitle')}>
      <dl className="mb-5 mt-0 grid max-w-xl grid-cols-3 gap-3">
        {statCards.map(([label, value]) => (
          <div key={label} className="rounded-xl border border-line bg-tint px-4 py-3">
            <dt className="text-xs">{t(label)}</dt>
            <dd className="m-0 mt-1 text-2xl font-semibold text-heading">{value}</dd>
          </div>
        ))}
      </dl>

      {mismatch && (
        <div role="alert" className="mb-5 flex flex-wrap items-center gap-3 rounded-lg border border-[#E7C98A] bg-[#FFF8E8] px-4 py-3 text-sm text-[#6B4A00] dark:border-[#6B5320] dark:bg-[#2A2210] dark:text-[#F5D28A]">
          <Icon name="warn" className="flex-none" />
          <span className="flex-1">{fillTemplate(t('admin.kb.mismatch'), { vectors: stats?.vector_count ?? 0, embedded: stats?.embedded ?? 0 })}</span>
        </div>
      )}

      <form
        ref={formRef}
        onSubmit={handleSubmit}
        className="mb-6 flex flex-col gap-4 rounded-2xl border border-line bg-surface p-5"
        aria-label={t(editingId ? 'admin.kb.formEdit' : 'admin.kb.formNew')}
      >
        <h2 className="m-0 text-lg">{t(editingId ? 'admin.kb.formEdit' : 'admin.kb.formNew')}</h2>
        <div>
          <label htmlFor="kb-question" className="mb-1.5 block text-sm font-normal text-heading">{t('admin.kb.question')}</label>
          <textarea id="kb-question" value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={MAX_QUESTION} rows={2} required className={`${fieldClass} resize-y`} />
          <div className="mt-1 text-right text-xs">{question.length}/{MAX_QUESTION}</div>
        </div>
        <div>
          <label htmlFor="kb-answer" className="mb-1.5 block text-sm font-normal text-heading">{t('admin.kb.answer')}</label>
          <textarea id="kb-answer" value={answer} onChange={(e) => setAnswer(e.target.value)} maxLength={MAX_ANSWER} rows={5} required className={`${fieldClass} resize-y`} />
          <div className="mt-1 text-right text-xs">{answer.length}/{MAX_ANSWER}</div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" disabled={busy !== null || !question.trim() || !answer.trim()} className={primaryButton}>
            <Icon name={editingId ? 'check' : 'plus'} size={18} />
            {t(busy === 'save' ? 'admin.kb.saving' : editingId ? 'admin.kb.saveEdit' : 'admin.kb.add')}
          </button>
          {editingId && (
            <button type="button" onClick={resetForm} className={secondaryButton}>
              {t('admin.kb.cancelEdit')}
            </button>
          )}
          <span className="text-sm">{t('admin.kb.pendingHint')}</span>
        </div>
      </form>

      {notice && (
        <p
          role={notice.kind === 'error' ? 'alert' : 'status'}
          className={`mb-5 mt-0 flex items-center gap-2 rounded-lg px-4 py-3 text-sm ${
            notice.kind === 'error'
              ? 'border border-[#E7B4B6] bg-[#FDF3F3] text-[#8A1216] dark:border-[#7A2A2E] dark:bg-[#2A1416] dark:text-[#FFB4B7]'
              : 'border border-[#B9DEC6] bg-[#EDF8F1] text-[#14602F] dark:border-[#25573A] dark:bg-[#12301F] dark:text-[#8AD9A8]'
          }`}
        >
          <Icon name={notice.kind === 'error' ? 'warn' : 'check'} size={18} className="flex-none" />
          {notice.text}
        </p>
      )}

      <section aria-labelledby="kb-test-title" className="mb-6 rounded-2xl border border-line bg-tint p-5">
        <h2 id="kb-test-title" className="mb-1 mt-0 text-lg">{t('admin.kb.testTitle')}</h2>
        <p className="mb-3 mt-0 text-sm">{t('admin.kb.testHint')}</p>
        <form onSubmit={handleTest} className="flex flex-wrap gap-3">
          <input
            type="text"
            value={testText}
            onChange={(e) => setTestText(e.target.value)}
            maxLength={MAX_QUESTION}
            placeholder={t('admin.kb.testPlaceholder')}
            aria-label={t('admin.kb.testTitle')}
            className={`${fieldClass} min-h-11 flex-1 basis-64`}
          />
          <button type="submit" disabled={testing || !testText.trim()} className={secondaryButton}>
            <Icon name="search" size={18} />
            {t(testing ? 'admin.kb.testing' : 'admin.kb.test')}
          </button>
        </form>
        {testResult && (
          <div className="mt-4">
            {testResult.hits.length === 0 ? (
              <p className="m-0 text-sm">{t('admin.kb.testEmpty')}</p>
            ) : (
              <ul className="m-0 flex list-none flex-col gap-2 p-0">
                {testResult.hits.map((hit) => (
                  <li key={hit.id} className="rounded-lg border border-line bg-surface px-4 py-3">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                      <strong className="tabular-nums text-heading">{hit.score.toFixed(3).replace('.', ',')}</strong>
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                          hit.used ? 'bg-[#E3F4EA] text-[#14602F] dark:bg-[#12301F] dark:text-[#8AD9A8]' : 'bg-tint text-muted'
                        }`}
                      >
                        {t(hit.used ? 'admin.kb.hitUsed' : 'admin.kb.hitUnused')}
                      </span>
                      {hit.score >= testResult.strong_score && <span className="text-xs font-semibold text-accent">{t('admin.kb.hitStrong')}</span>}
                    </div>
                    <div className="mt-1.5 text-sm font-semibold text-heading">{hit.question}</div>
                    <div className="mt-0.5 line-clamp-2 text-sm">{hit.answer}</div>
                  </li>
                ))}
              </ul>
            )}
            <p className="mb-0 mt-3 text-xs">
              {fillTemplate(t('admin.kb.thresholds'), {
                min: testResult.min_score.toFixed(2).replace('.', ','),
                strong: testResult.strong_score.toFixed(2).replace('.', ','),
              })}
            </p>
          </div>
        )}
      </section>

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <label htmlFor="kb-search" className="text-sm font-normal text-heading">{t('admin.kb.search')}</label>
          <input id="kb-search" type="search" value={query} onChange={(e) => setQuery(e.target.value)} className={`${fieldClass} min-h-11 w-64`} />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="kb-state" className="text-sm font-normal text-heading">{t('admin.kb.filterState')}</label>
          <select id="kb-state" value={state} onChange={(e) => setState(e.target.value as 'all' | KnowledgeState)} className={`${fieldClass} min-h-11 w-48`}>
            <option value="all">{t('admin.fb.all')}</option>
            <option value="pending">{t('admin.kb.state.pending')}</option>
            <option value="embedded">{t('admin.kb.state.embedded')}</option>
          </select>
        </div>
        <div className="ml-auto flex flex-wrap gap-3">
          <button
            type="button"
            disabled={busy !== null || !stats || stats.pending === 0}
            onClick={() => runEmbed('embed', () => embedPending(false))}
            className={primaryButton}
          >
            <Icon name="sparkles" size={18} />
            {busy === 'embed' ? t('admin.kb.embedding') : fillTemplate(t('admin.kb.embedPending'), { n: stats?.pending ?? 0 })}
          </button>
          <button type="button" disabled={busy !== null || !stats || stats.total === 0} onClick={() => setConfirmAll(true)} className={secondaryButton}>
            {busy === 'embedAll' ? t('admin.kb.embedding') : t('admin.kb.embedAll')}
          </button>
        </div>
      </div>

      {loadState === 'loading' && <p role="status">{t('admin.fb.loading')}</p>}
      {loadState === 'error' && (
        <div role="alert" className="flex flex-wrap items-center gap-4 rounded-lg border border-[#E7B4B6] bg-[#FDF3F3] px-4 py-3 text-sm text-[#8A1216] dark:border-[#7A2A2E] dark:bg-[#2A1416] dark:text-[#FFB4B7]">
          <Icon name="warn" className="flex-none" />
          <span className="flex-1">{t('admin.kb.loadError')}</span>
          <button type="button" onClick={load} className="min-h-11 cursor-pointer rounded-lg border border-current bg-transparent px-5 py-2 font-sans text-sm font-semibold text-inherit">
            {t('admin.fb.retry')}
          </button>
        </div>
      )}
      {loadState === 'ready' && data?.items.length === 0 && <p>{t(query || state !== 'all' ? 'admin.kb.noMatch' : 'admin.kb.empty')}</p>}

      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {data?.items.map((entry) => (
          <li key={entry.id} className={`rounded-xl border bg-surface px-5 py-4 ${editingId === entry.id ? 'border-accent' : 'border-line'}`}>
            <div className="flex flex-wrap items-center gap-3">
              <StatusBadge state={entry.status} />
              <span className="text-xs">
                {entry.embedded_at ? `${t('admin.kb.embeddedAt')} ${formatDate(entry.embedded_at)}` : t('admin.kb.notEmbedded')}
              </span>
            </div>
            <p className="mb-1 mt-2.5 break-words text-[15px] font-semibold text-heading">{entry.question}</p>
            <p className="m-0 whitespace-pre-wrap break-words text-[15px]">{entry.answer}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {entry.status === 'pending' && (
                <button type="button" disabled={busy !== null} onClick={() => runEmbed(entry.id, () => embedOne(entry.id))} className={smallButton}>
                  <Icon name="sparkles" size={16} />
                  {busy === entry.id ? t('admin.kb.embedding') : t('admin.kb.embedOne')}
                </button>
              )}
              <button type="button" disabled={busy !== null} onClick={() => startEdit(entry)} className={smallButton}>
                <Icon name="pencil" size={16} />
                {t('admin.kb.edit')}
              </button>
              <button type="button" disabled={busy !== null} onClick={() => { setDeleteError(null); setDeleteTarget(entry) }} className={smallButton}>
                <Icon name="trash" size={16} />
                {t('files.delete')}
              </button>
            </div>
          </li>
        ))}
      </ul>

      <ConfirmDialog
        open={deleteTarget !== null}
        title={t('admin.kb.deleteTitle')}
        message={deleteTarget ? `${t('admin.kb.deleteText')}\n\n“${deleteTarget.question}”` : ''}
        confirmLabel={t('files.delete')}
        error={deleteError}
        onConfirm={handleDelete}
        onCancel={() => {
          setDeleteTarget(null)
          setDeleteError(null)
        }}
      />
      <ConfirmDialog
        open={confirmAll}
        title={t('admin.kb.embedAllTitle')}
        message={t('admin.kb.embedAllText')}
        confirmLabel={t('admin.kb.embedAll')}
        onConfirm={async () => {
          setConfirmAll(false)
          await runEmbed('embedAll', () => embedPending(true))
        }}
        onCancel={() => setConfirmAll(false)}
      />
    </AdminLayout>
  )
}
