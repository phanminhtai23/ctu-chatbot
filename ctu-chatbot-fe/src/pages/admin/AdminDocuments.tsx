import { useCallback, useEffect, useRef, useState, type DragEvent } from 'react'
import IngestFlow, { fill, jobBadgeClass, jobShortLabel } from '../../components/admin/IngestFlow'
import Icon from '../../components/Icon'
import { useFormatDate } from '../../hooks/useFormatDate'
import { useI18n } from '../../i18n'
import type { TranslationKey } from '../../i18n/vi'
import {
  activateDefault,
  activateVersion,
  downloadSource,
  getJob,
  getOverview,
  uploadDocument,
  uploadErrorCode,
  type DocumentsOverview,
  type IngestJob,
} from '../../lib/adminDocuments'
import AdminLayout from './AdminLayout'

const MAX_MB = 30
const POLL_MS = 1500

const uploadErrors: Record<string, TranslationKey> = {
  INGEST_BUSY: 'admin.doc.errBusy',
  PDF_TOO_LARGE: 'admin.doc.errTooLarge',
  INGEST_DISABLED: 'admin.doc.errDisabled',
  INVALID_PDF: 'admin.doc.errInvalid',
}

export default function AdminDocuments() {
  const { t } = useI18n()
  const formatDate = useFormatDate()
  const [overview, setOverview] = useState<DocumentsOverview | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [job, setJob] = useState<IngestJob | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [dragging, setDragging] = useState(false)
  const [switching, setSwitching] = useState<string | null>(null)
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const refreshOverview = useCallback(async () => {
    try {
      const data = await getOverview()
      setOverview(data)
      setLoadError(false)
      return data
    } catch {
      setLoadError(true)
      return null
    }
  }, [])

  // Lần đầu: nạp tổng quan và mở lần nạp đang chạy (hoặc lần gần nhất).
  useEffect(() => {
    let cancelled = false
    refreshOverview().then(async (data) => {
      const id = data?.running_job_id ?? data?.jobs[0]?.id
      if (!id || cancelled) return
      try {
        const detail = await getJob(id)
        if (!cancelled) setJob(detail)
      } catch {
        /* lần nạp bị xoá: bỏ qua */
      }
    })
    return () => {
      cancelled = true
    }
  }, [refreshOverview])

  // Đang chạy thì hỏi lại trạng thái đều đặn; xong thì cập nhật tổng quan (tài liệu đang dùng, lịch sử).
  const runningId = job?.status === 'running' ? job.id : null
  useEffect(() => {
    if (!runningId) return
    let stopped = false
    const timer = setInterval(async () => {
      try {
        const next = await getJob(runningId)
        if (stopped) return
        setJob(next)
        if (next.status !== 'running') refreshOverview()
      } catch {
        /* mất mạng thoáng qua: lần sau thử lại */
      }
    }, POLL_MS)
    return () => {
      stopped = true
      clearInterval(timer)
    }
  }, [runningId, refreshOverview])

  const busy = uploading || job?.status === 'running' || overview?.running_job_id != null
  const disabled = overview != null && !overview.enabled

  const upload = async (file: File | undefined) => {
    if (!file || busy || disabled) return
    if (!/\.pdf$/i.test(file.name) && file.type !== 'application/pdf') {
      setUploadError(t('admin.doc.errNotPdf'))
      return
    }
    setUploadError('')
    setUploading(true)
    try {
      setJob(await uploadDocument(file))
      refreshOverview()
    } catch (err) {
      const key = uploadErrors[uploadErrorCode(err)]
      setUploadError(key ? t(key) : t('admin.doc.errGeneric'))
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  const onDrop = (event: DragEvent) => {
    event.preventDefault()
    setDragging(false)
    upload(event.dataTransfer.files[0])
  }

  const openJob = async (id: string) => {
    try {
      setJob(await getJob(id))
    } catch {
      /* bỏ qua */
    }
  }

  const switchTo = async (id: string) => {
    if (busy || switching) return
    setSwitching(id)
    setNotice(null)
    try {
      if (id === 'default') await activateDefault()
      else await activateVersion(id)
      setNotice({ ok: true, text: t('admin.doc.switched') })
      await refreshOverview()
    } catch {
      setNotice({ ok: false, text: t('admin.doc.switchError') })
    } finally {
      setSwitching(null)
    }
  }

  const download = async (id: string, filename: string) => {
    try {
      await downloadSource(id, filename)
    } catch {
      setNotice({ ok: false, text: t('admin.doc.downloadError') })
    }
  }

  const active = overview?.active

  return (
    <AdminLayout title={t('admin.doc.title')} subtitle={t('admin.doc.subtitle')}>
      {loadError && !overview ? (
        <div role="alert" className="flex items-center gap-3 text-sm">
          {t('admin.doc.loadError')}
          <button
            type="button"
            onClick={refreshOverview}
            className="min-h-11 cursor-pointer rounded-lg border border-ctu-cyan bg-surface px-4 font-sans text-sm text-accent hover:bg-tint"
          >
            {t('admin.doc.retry')}
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
          <div className="flex flex-col gap-6">
            <section className="rounded-xl border border-line bg-surface p-5" aria-labelledby="doc-active">
              <h2 id="doc-active" className="m-0 mb-2 text-base">
                {t('admin.doc.active')}
              </h2>
              <div className="flex items-start gap-3">
                <span className="flex size-10 flex-none items-center justify-center rounded-lg bg-tint text-accent">
                  <Icon name="doc" />
                </span>
                <div className="min-w-0 text-sm">
                  <div className="break-words font-semibold text-heading">
                    {active ? active.filename : t('admin.doc.activeBuiltin')}
                  </div>
                  {active && (
                    <div className="mt-0.5 text-muted">
                      {fill(t('admin.doc.activeMeta'), {
                        time: formatDate(active.activated_at),
                        articles: active.articles,
                        pages: active.pages,
                      })}
                    </div>
                  )}
                </div>
              </div>
              {active && overview?.default_available && (
                <button
                  type="button"
                  onClick={() => switchTo('default')}
                  disabled={busy || switching != null}
                  className="mt-3 min-h-11 cursor-pointer rounded-lg border border-ctu-cyan bg-surface px-4 font-sans text-sm text-accent hover:bg-tint disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {switching === 'default' ? t('admin.doc.switching') : t('admin.doc.backToDefault')}
                </button>
              )}
            </section>

            <section className="rounded-xl border border-line bg-surface p-5" aria-labelledby="doc-upload">
              <h2 id="doc-upload" className="m-0 mb-3 text-base">
                {t('admin.doc.upload')}
              </h2>
              <div
                onDragOver={(e) => {
                  e.preventDefault()
                  setDragging(true)
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                className={`flex flex-col items-center gap-2 rounded-lg border-2 border-dashed px-4 py-7 text-center ${
                  dragging ? 'border-ctu-navy bg-tint' : 'border-field'
                } ${busy || disabled ? 'opacity-60' : ''}`}
              >
                <Icon name="upload" size={28} className="text-accent" />
                <p className="m-0 text-sm text-heading">{t('admin.doc.drop')}</p>
                <p className="m-0 text-xs text-muted">{fill(t('admin.doc.dropHint'), { mb: MAX_MB })}</p>
                <input
                  ref={inputRef}
                  id="doc-file"
                  type="file"
                  accept="application/pdf,.pdf"
                  className="sr-only"
                  disabled={busy || disabled}
                  onChange={(e) => upload(e.target.files?.[0])}
                />
                <label
                  htmlFor="doc-file"
                  className={`mt-1 inline-flex min-h-11 items-center rounded-lg bg-ctu-navy px-5 font-sans text-sm font-semibold text-white ${
                    busy || disabled ? 'cursor-not-allowed' : 'cursor-pointer hover:bg-ctu-navy-dark'
                  }`}
                >
                  {uploading ? t('admin.doc.job.running') : t('admin.doc.choose')}
                </label>
              </div>
              {uploadError && (
                <p role="alert" className="m-0 mt-3 text-sm font-semibold text-[#9B1C1C] dark:text-[#F5A3A3]">
                  {uploadError}
                </p>
              )}
              {disabled ? (
                <p className="m-0 mt-3 text-sm">{t('admin.doc.disabled')}</p>
              ) : busy && !uploading ? (
                <p className="m-0 mt-3 text-sm">{t('admin.doc.running')}</p>
              ) : null}
              <p className="m-0 mt-3 flex items-start gap-2 text-xs text-muted">
                <Icon name="shield" size={14} className="mt-0.5 flex-none" />
                {t('admin.doc.safe')}
              </p>
            </section>

            {overview && overview.jobs.length > 0 && (
              <section className="rounded-xl border border-line bg-surface p-5" aria-labelledby="doc-history">
                <h2 id="doc-history" className="m-0 mb-3 text-base">
                  {t('admin.doc.history')}
                </h2>
                <p className="m-0 mb-3 text-xs text-muted">{t('admin.doc.historyHint')}</p>
                {notice && (
                  <p
                    role={notice.ok ? 'status' : 'alert'}
                    className={`m-0 mb-3 text-sm font-semibold ${notice.ok ? 'text-[#14602F] dark:text-[#8AD9A8]' : 'text-[#9B1C1C] dark:text-[#F5A3A3]'}`}
                  >
                    {notice.text}
                  </p>
                )}
                <ul className="m-0 flex list-none flex-col gap-2 p-0">
                  {overview.jobs.map((item) => (
                    <li
                      key={item.id}
                      className={`rounded-lg border bg-surface ${job?.id === item.id ? 'border-ctu-navy' : 'border-line'}`}
                    >
                      <button
                        type="button"
                        onClick={() => openJob(item.id)}
                        aria-pressed={job?.id === item.id}
                        className="flex min-h-11 w-full cursor-pointer items-center gap-3 rounded-lg border-0 bg-transparent px-3 py-2 text-left font-sans hover:bg-tint"
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm text-heading">{item.filename}</span>
                          <span className="block text-xs text-muted">{formatDate(item.created_at)}</span>
                        </span>
                        {item.is_active ? (
                          <span className="flex-none rounded-full bg-ctu-navy px-2.5 py-0.5 text-xs font-semibold text-white">
                            {t('admin.doc.inUse')}
                          </span>
                        ) : (
                          <span className={`flex-none rounded-full px-2.5 py-0.5 text-xs font-semibold ${jobBadgeClass[item.status]}`}>
                            {t(jobShortLabel[item.status])}
                          </span>
                        )}
                      </button>
                      <div className="flex flex-wrap gap-2 px-3 pb-2.5">
                        {item.can_activate && (
                          <button
                            type="button"
                            onClick={() => switchTo(item.id)}
                            disabled={busy || switching != null}
                            className="min-h-9 cursor-pointer rounded-md border-0 bg-ctu-navy px-3 font-sans text-[13px] font-semibold text-white hover:bg-ctu-navy-dark disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            {switching === item.id ? t('admin.doc.switching') : t('admin.doc.switchTo')}
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => download(item.id, item.filename)}
                          className="min-h-9 cursor-pointer rounded-md border border-line bg-surface px-3 font-sans text-[13px] text-accent hover:bg-tint"
                        >
                          {t('admin.doc.download')}
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>

          <section className="min-w-0 rounded-xl border border-line bg-surface p-5 md:p-6" aria-labelledby="doc-flow">
            <h2 id="doc-flow" className="m-0 mb-4 text-base">
              {t('admin.doc.flow')}
            </h2>
            {job ? <IngestFlow job={job} /> : <p className="m-0 text-sm">{t('admin.doc.flowEmpty')}</p>}
          </section>
        </div>
      )}
    </AdminLayout>
  )
}
