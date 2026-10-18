import { useCallback, useEffect, useMemo, useState } from 'react'
import FeedbackDetailDialog, { categoryKey } from '../../components/FeedbackDetailDialog'
import Icon from '../../components/Icon'
import StatusBadge from '../../components/StatusBadge'
import { useFormatDate } from '../../hooks/useFormatDate'
import { useI18n } from '../../i18n'
import {
  FEEDBACK_CHANGED_EVENT,
  feedbackStatuses,
  listFeedback,
  updateFeedbackStatus,
  type AdminFeedback as FeedbackItem,
  type FeedbackStatus,
} from '../../lib/adminFeedback'
import type { FeedbackType } from '../../lib/feedback'
import AdminLayout from './AdminLayout'

type LoadState = 'loading' | 'ready' | 'error'

const selectClass =
  'min-h-11 rounded-lg border border-field bg-surface px-3 py-2 font-sans text-[15px] text-heading outline-accent'

export default function AdminFeedback() {
  const { t } = useI18n()
  const formatDate = useFormatDate()
  const [items, setItems] = useState<FeedbackItem[]>([])
  const [state, setState] = useState<LoadState>('loading')
  const [typeFilter, setTypeFilter] = useState<'all' | FeedbackType>('all')
  const [statusFilter, setStatusFilter] = useState<'all' | FeedbackStatus>('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const load = useCallback(async () => {
    setState('loading')
    try {
      setItems(await listFeedback())
      setState('ready')
    } catch {
      setState('error')
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const visible = useMemo(
    () =>
      items
        .filter((i) => typeFilter === 'all' || i.type === typeFilter)
        .filter((i) => statusFilter === 'all' || i.status === statusFilter)
        .sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [items, typeFilter, statusFilter],
  )

  const selected = items.find((i) => i.id === selectedId) ?? null

  const handleSaveStatus = async (id: string, status: FeedbackStatus) => {
    await updateFeedbackStatus(id, status)
    window.dispatchEvent(new Event(FEEDBACK_CHANGED_EVENT))
    setItems((prev) => prev.map((i) => (i.id === id ? { ...i, status } : i)))
  }

  return (
    <AdminLayout title={t('admin.fb.title')} subtitle={t('admin.fb.subtitle')}>
      <div className="mb-5 flex flex-wrap items-end gap-4">
        <div className="flex flex-col gap-1">
          <label htmlFor="fb-type" className="text-sm font-normal text-heading">{t('admin.fb.filterType')}</label>
          <select
            id="fb-type"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value as 'all' | FeedbackType)}
            className={selectClass}
          >
            <option value="all">{t('admin.fb.all')}</option>
            <option value="answer_issue">{t('fbtype.answer_issue')}</option>
            <option value="general">{t('fbtype.general')}</option>
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="fb-status" className="text-sm font-normal text-heading">{t('admin.fb.filterStatus')}</label>
          <select
            id="fb-status"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as 'all' | FeedbackStatus)}
            className={selectClass}
          >
            <option value="all">{t('admin.fb.all')}</option>
            {feedbackStatuses.map((s) => (
              <option key={s} value={s}>{t(`fbstatus.${s}`)}</option>
            ))}
          </select>
        </div>
        {state === 'ready' && (
          <p className="m-0 pb-2.5 text-sm" aria-live="polite">
            {visible.length} {t('admin.fb.count')}
          </p>
        )}
      </div>

      {state === 'loading' && <p role="status">{t('admin.fb.loading')}</p>}

      {state === 'error' && (
        <div
          role="alert"
          className="flex flex-wrap items-center gap-4 rounded-lg border border-[#E7B4B6] bg-[#FDF3F3] px-4 py-3 text-sm text-[#8A1216] dark:border-[#7A2A2E] dark:bg-[#2A1416] dark:text-[#FFB4B7]"
        >
          <Icon name="warn" className="flex-none" />
          <span className="flex-1">{t('admin.fb.loadError')}</span>
          <button
            type="button"
            onClick={load}
            className="min-h-11 cursor-pointer rounded-lg border border-current bg-transparent px-5 py-2 font-sans text-sm font-semibold text-inherit"
          >
            {t('admin.fb.retry')}
          </button>
        </div>
      )}

      {state === 'ready' && visible.length === 0 && <p>{t('admin.fb.empty')}</p>}

      {state === 'ready' && visible.length > 0 && (
        <ul className="m-0 flex list-none flex-col gap-3 p-0">
          {visible.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                onClick={() => setSelectedId(item.id)}
                aria-label={`${t('admin.fb.open')}: ${item.user_email}`}
                className="block w-full cursor-pointer rounded-xl border border-line bg-surface px-5 py-4 text-left font-sans hover:bg-tint"
              >
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                  <StatusBadge status={item.status} />
                  <span className="text-sm font-semibold text-heading">{t(categoryKey[item.category])}</span>
                  <span className="rounded-md border border-line px-2 py-0.5 text-xs">
                    {t(item.type === 'answer_issue' ? 'fbtype.answer_issue' : 'fbtype.general')}
                  </span>
                  <span className="ml-auto text-xs">{formatDate(item.created_at)}</span>
                </div>
                <p className="mb-0 mt-2.5 line-clamp-2 break-words text-[15px] font-light text-heading">
                  {item.message || t('admin.fb.noMessage')}
                </p>
                <div className="mt-2 break-all text-xs">{item.user_email}</div>
              </button>
            </li>
          ))}
        </ul>
      )}

      <FeedbackDetailDialog
        item={selected}
        formatDate={formatDate}
        onClose={() => setSelectedId(null)}
        onSaveStatus={handleSaveStatus}
      />
    </AdminLayout>
  )
}
