import { useCallback, useEffect, useRef, useState, type DragEvent } from 'react'
import Icon from '../../components/Icon'
import RouteGraph from '../../components/admin/RouteGraph'
import { useFormatDate } from '../../hooks/useFormatDate'
import { useI18n } from '../../i18n'
import type { TranslationKey } from '../../i18n/vi'
import {
  cleanCatalogDocument,
  extractCatalogDocument,
  getCatalogJob,
  getCatalogOverview,
  saveRouteConfig,
  syncCatalog,
  syncCatalogDocument,
  uploadCatalogDocument,
  uploadErrorCode,
  type CatalogJob,
  type RouteConfig,
} from '../../lib/adminDocuments'
import AdminLayout from './AdminLayout'

const uploadErrors: Record<string, TranslationKey> = {
  PDF_TOO_LARGE: 'admin.doc.errTooLarge',
  INVALID_PDF: 'admin.doc.errInvalid',
  DOCUMENT_NAME_INVALID: 'admin.doc.errName',
  CATALOG_READ_ONLY: 'admin.doc.readOnly',
}

const stageLabel: Record<CatalogJob['status'], TranslationKey> = {
  uploaded: 'admin.doc.status.uploaded',
  extracted: 'admin.doc.status.extracted',
  cleaned: 'admin.doc.status.cleaned',
  synced: 'admin.doc.status.synced',
  failed: 'admin.doc.status.failed',
}

const stepClass: Record<CatalogJob['steps'][number]['status'], string> = {
  pending: 'border-line bg-tint text-muted',
  running: 'border-ctu-gold-active bg-[#FFF8E1] text-ctu-navy-dark dark:bg-[#302711] dark:text-[#F2CB74]',
  done: 'border-[#2E9E5B] bg-[#E3F4EA] text-[#14602F] dark:bg-[#12301F] dark:text-[#8AD9A8]',
  warning: 'border-[#D99A00] bg-[#FFF3D6] text-[#7A5200] dark:bg-[#3A2D0B] dark:text-[#F2CB74]',
  failed: 'border-[#D13434] bg-[#FDE7E7] text-[#9B1C1C] dark:bg-[#3B1414] dark:text-[#F5A3A3]',
}

export default function AdminDocuments() {
  const { t } = useI18n()
  const formatDate = useFormatDate()
  const inputRef = useRef<HTMLInputElement>(null)
  const [overview, setOverview] = useState<Awaited<ReturnType<typeof getCatalogOverview>> | null>(null)
  const [job, setJob] = useState<CatalogJob | null>(null)
  const [routeDraft, setRouteDraft] = useState<RouteConfig | null>(null)
  const [routeDirty, setRouteDirty] = useState(false)
  const [title, setTitle] = useState('')
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [action, setAction] = useState('')
  const [loadError, setLoadError] = useState(false)
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null)

  const loadCatalog = useCallback(async () => {
    try {
      const data = await getCatalogOverview()
      setOverview(data)
      setLoadError(false)
      return data
    } catch {
      setLoadError(true)
      return null
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    loadCatalog().then(async (data) => {
      if (!data || cancelled) return
      setRouteDraft(data.routes)
      const newest = data.jobs[0]
      if (newest) {
        try {
          const detail = await getCatalogJob(newest.slug, newest.id)
          if (!cancelled) setJob(detail)
        } catch {
          if (!cancelled) setNotice({ ok: false, text: t('admin.doc.loadError') })
        }
      }
    })
    return () => {
      cancelled = true
    }
  }, [loadCatalog, t])

  useEffect(() => {
    if (!job || !['extract', 'clean', 'sync'].includes(action)) return
    let cancelled = false
    const refreshProgress = () => {
      getCatalogJob(job.slug, job.id)
        .then((detail) => {
          if (!cancelled) setJob(detail)
        })
        .catch(() => {
          if (!cancelled) setNotice({ ok: false, text: t('admin.doc.progressLoadError') })
        })
    }
    const timer = window.setInterval(refreshProgress, 1500)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [action, job?.id, job?.slug, t])

  const refreshAfterAction = async (nextJob?: CatalogJob) => {
    if (nextJob) setJob(nextJob)
    const data = await loadCatalog()
    if (data && !routeDirty) setRouteDraft(data.routes)
  }

  const upload = async (file: File | undefined) => {
    if (!file || uploading || !overview?.editable) return
    if (!/\.pdf$/i.test(file.name) && file.type !== 'application/pdf') {
      setNotice({ ok: false, text: t('admin.doc.errNotPdf') })
      return
    }
    if (!title.trim()) {
      setNotice({ ok: false, text: t('admin.doc.errName') })
      return
    }
    setUploading(true)
    setNotice(null)
    try {
      const created = await uploadCatalogDocument(file, title.trim())
      setTitle('')
      await refreshAfterAction(created)
      setNotice({ ok: true, text: t('admin.doc.uploadSaved') })
    } catch (error) {
      const code = uploadErrorCode(error)
      setNotice({ ok: false, text: t(uploadErrors[code] ?? 'admin.doc.errGeneric') })
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  const onDrop = (event: DragEvent) => {
    event.preventDefault()
    setDragging(false)
    void upload(event.dataTransfer.files[0])
  }

  const openJob = async (item: CatalogJob) => {
    try {
      setJob(await getCatalogJob(item.slug, item.id))
      setNotice(null)
    } catch {
      setNotice({ ok: false, text: t('admin.doc.loadError') })
    }
  }

  const runStage = async (stage: 'extract' | 'clean' | 'sync') => {
    if (!job || action) return
    setAction(stage)
    setNotice(null)
    try {
      let result: CatalogJob
      if (stage === 'extract') result = await extractCatalogDocument(job)
      else if (stage === 'clean') result = await cleanCatalogDocument(job)
      else result = (await syncCatalogDocument(job)).job
      await refreshAfterAction(result)
      setNotice({ ok: true, text: t(`admin.doc.${stage}Done` as TranslationKey) })
    } catch (error) {
      const code = uploadErrorCode(error)
      const messageKey: TranslationKey =
        code === 'CATALOG_READ_ONLY'
          ? 'admin.doc.readOnly'
          : code === 'CATALOG_SYNC_DISABLED'
            ? 'admin.doc.syncDisabled'
            : code === 'EXTRACT_FAILED' || code === 'CLEAN_FAILED' || code === 'SYNC_FAILED'
              ? `admin.doc.${stage}Failed`
              : 'admin.doc.errGeneric'
      setNotice({ ok: false, text: t(messageKey) })
      try {
        const detail = await getCatalogJob(job.slug, job.id)
        await refreshAfterAction(detail)
      } catch {
        // Keep the stage error visible if the follow-up read also fails.
      }
    } finally {
      setAction('')
    }
  }

  const syncAll = async () => {
    if (action || !overview?.sync_enabled) return
    setAction('catalog-sync')
    setNotice(null)
    try {
      const result = await syncCatalog()
      await loadCatalog()
      setNotice({
        ok: true,
        text: `${t('admin.doc.catalogSynced')} (${result.count})`,
      })
    } catch (error) {
      const code = uploadErrorCode(error)
      setNotice({
        ok: false,
        text: t(code === 'CATALOG_SYNC_DISABLED' ? 'admin.doc.syncDisabled' : 'admin.doc.catalogSyncFailed'),
      })
    } finally {
      setAction('')
    }
  }

  const saveRoutes = async () => {
    if (!routeDraft || !overview?.editable || action) return
    setAction('routes')
    setNotice(null)
    try {
      const saved = await saveRouteConfig(routeDraft)
      setRouteDraft(saved)
      setRouteDirty(false)
      setNotice({ ok: true, text: t('admin.doc.routesSaved') })
      await loadCatalog()
    } catch {
      setNotice({ ok: false, text: t('admin.doc.routesSaveFailed') })
    } finally {
      setAction('')
    }
  }

  const failedStep = job?.steps.find((step) => step.status === 'failed')?.key
  const nextStage =
    job?.status === 'uploaded' || (job?.status === 'failed' && (!failedStep || ['render', 'ocr'].includes(failedStep)))
      ? 'extract'
      : job?.status === 'extracted' || (job?.status === 'failed' && ['normalize', 'chunk'].includes(failedStep ?? ''))
        ? 'clean'
        : job?.status === 'cleaned' || (job?.status === 'failed' && ['embed', 'sync'].includes(failedStep ?? ''))
          ? 'sync'
          : null

  return (
    <AdminLayout title={t('admin.doc.title')} subtitle={t('admin.doc.subtitle')}>
      {loadError && !overview ? (
        <div role="alert" className="flex flex-wrap items-center gap-3 text-sm">
          {t('admin.doc.loadError')}
          <button
            type="button"
            onClick={loadCatalog}
            className="min-h-11 cursor-pointer rounded-lg border border-ctu-cyan bg-surface px-4 font-sans text-sm text-accent hover:bg-tint"
          >
            {t('admin.doc.retry')}
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-6">
          {notice && (
            <p
              role={notice.ok ? 'status' : 'alert'}
              className={`m-0 rounded-lg border px-4 py-3 text-sm font-semibold ${
                notice.ok
                  ? 'border-[#2E9E5B] bg-[#E3F4EA] text-[#14602F] dark:bg-[#12301F] dark:text-[#8AD9A8]'
                  : 'border-[#D13434] bg-[#FDE7E7] text-[#9B1C1C] dark:bg-[#3B1414] dark:text-[#F5A3A3]'
              }`}
            >
              {notice.text}
            </p>
          )}

          <section className="rounded-xl border border-line bg-surface p-5 md:p-6" aria-labelledby="route-flow-title">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 id="route-flow-title" className="m-0 text-base font-semibold text-heading">
                  {t('admin.doc.routeFlow')}
                </h2>
                <p className="mb-0 mt-1 text-sm text-muted">{t('admin.doc.routeFlowHint')}</p>
              </div>
              <button
                type="button"
                onClick={saveRoutes}
                disabled={!overview?.editable || !routeDirty || action !== ''}
                className="min-h-11 cursor-pointer rounded-lg bg-ctu-navy px-4 font-sans text-sm font-semibold text-white hover:bg-ctu-navy-dark disabled:cursor-not-allowed disabled:opacity-50"
              >
                {action === 'routes' ? t('admin.doc.savingRoutes') : t('admin.doc.saveRoutes')}
              </button>
            </div>
            {routeDraft && (
              <RouteGraph
                config={routeDraft}
                editable={Boolean(overview?.editable)}
                onChange={(next) => {
                  setRouteDraft(next)
                  setRouteDirty(true)
                }}
              />
            )}
          </section>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
            <div className="flex flex-col gap-6">
              <section className="rounded-xl border border-line bg-surface p-5" aria-labelledby="doc-upload-title">
                <h2 id="doc-upload-title" className="m-0 mb-3 text-base font-semibold text-heading">
                  {t('admin.doc.upload')}
                </h2>
                {!overview?.editable && <p className="m-0 mb-3 text-sm text-muted">{t('admin.doc.readOnly')}</p>}
                <label htmlFor="doc-title" className="mb-1.5 block text-sm font-semibold text-heading">
                  {t('admin.doc.documentName')}
                </label>
                <input
                  id="doc-title"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  maxLength={100}
                  disabled={!overview?.editable || uploading}
                  placeholder={t('admin.doc.documentNamePlaceholder')}
                  className="mb-3 min-h-11 w-full rounded-lg border border-field bg-surface px-3 font-sans text-sm text-heading outline-none focus:border-ctu-cyan focus:ring-2 focus:ring-ctu-cyan/20 disabled:opacity-60"
                />
                <div
                  onDragOver={(event) => {
                    event.preventDefault()
                    setDragging(true)
                  }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={onDrop}
                  className={`flex flex-col items-center gap-2 rounded-lg border-2 border-dashed px-4 py-6 text-center ${
                    dragging ? 'border-ctu-navy bg-tint' : 'border-field'
                  } ${!overview?.editable || uploading ? 'opacity-60' : ''}`}
                >
                  <Icon name="upload" size={26} className="text-accent" />
                  <p className="m-0 text-sm text-heading">{t('admin.doc.drop')}</p>
                  <p className="m-0 text-xs text-muted">{t('admin.doc.dropHint')}</p>
                  <input
                    ref={inputRef}
                    id="doc-file"
                    type="file"
                    accept="application/pdf,.pdf"
                    className="sr-only"
                    disabled={!overview?.editable || uploading}
                    onChange={(event) => void upload(event.target.files?.[0])}
                  />
                  <label
                    htmlFor="doc-file"
                    className={`mt-1 inline-flex min-h-11 items-center rounded-lg bg-ctu-navy px-5 font-sans text-sm font-semibold text-white ${
                      !overview?.editable || uploading ? 'cursor-not-allowed' : 'cursor-pointer hover:bg-ctu-navy-dark'
                    }`}
                  >
                    {uploading ? t('admin.doc.uploading') : t('admin.doc.choose')}
                  </label>
                </div>
                <p className="mb-0 mt-3 flex items-start gap-2 text-xs text-muted">
                  <Icon name="shield" size={14} className="mt-0.5 flex-none" />
                  {t('admin.doc.versionStorage')}
                </p>
              </section>

              {overview?.sync_enabled && (
                <section className="rounded-xl border border-line bg-surface p-5" aria-labelledby="catalog-sync-title">
                  <h2 id="catalog-sync-title" className="m-0 mb-2 text-base font-semibold text-heading">
                    {t('admin.doc.productionSync')}
                  </h2>
                  <p className="mb-3 mt-0 text-sm text-muted">{t('admin.doc.productionSyncHint')}</p>
                  <button
                    type="button"
                    onClick={syncAll}
                    disabled={action !== ''}
                    className="min-h-11 cursor-pointer rounded-lg border border-ctu-cyan bg-surface px-4 font-sans text-sm font-semibold text-accent hover:bg-tint disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {action === 'catalog-sync' ? t('admin.doc.syncingCatalog') : t('admin.doc.syncCatalog')}
                  </button>
                </section>
              )}

              {overview && overview.jobs.length > 0 && (
                <section className="rounded-xl border border-line bg-surface p-5" aria-labelledby="doc-history-title">
                  <h2 id="doc-history-title" className="m-0 mb-3 text-base font-semibold text-heading">
                    {t('admin.doc.history')}
                  </h2>
                  <ul className="m-0 flex list-none flex-col gap-2 p-0">
                    {overview.jobs.map((item) => (
                      <li key={`${item.slug}-${item.id}`}>
                        <button
                          type="button"
                          onClick={() => void openJob(item)}
                          aria-pressed={job?.id === item.id}
                          className={`flex min-h-14 w-full cursor-pointer items-center gap-3 rounded-lg border bg-surface px-3 py-2 text-left font-sans hover:bg-tint ${
                            job?.id === item.id ? 'border-ctu-cyan' : 'border-line'
                          }`}
                        >
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm font-semibold text-heading">{item.title}</span>
                            <span className="block truncate text-xs text-muted">
                              {item.filename} · {formatDate(item.created_at)}
                            </span>
                          </span>
                          <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${stepClass[item.status === 'failed' ? 'failed' : item.status === 'synced' ? 'done' : 'pending']}`}>
                            {t(stageLabel[item.status])}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </div>

            <section className="min-w-0 rounded-xl border border-line bg-surface p-5 md:p-6" aria-labelledby="doc-workflow-title">
              <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 id="doc-workflow-title" className="m-0 text-base font-semibold text-heading">
                    {t('admin.doc.reviewFlow')}
                  </h2>
                  {job && (
                    <p className="mb-0 mt-1 break-words text-sm text-muted">
                      {job.title} · {job.filename} · {job.id}
                    </p>
                  )}
                </div>
                {job && (
                  <span className="rounded-full border border-line bg-tint px-3 py-1 text-xs font-semibold text-heading">
                    {t(stageLabel[job.status])}
                  </span>
                )}
              </div>
              {job ? (
                <>
                  <ol className="m-0 grid list-none grid-cols-1 gap-2 p-0 md:grid-cols-2">
                    {job.steps.map((step, index) => (
                      <li key={step.key} className={`min-w-0 rounded-lg border p-3 ${stepClass[step.status]}`}>
                        <div className="flex items-start gap-2">
                          <span className="flex size-7 flex-none items-center justify-center rounded-full bg-surface text-xs font-bold">
                            {step.status === 'done' ? '✓' : step.status === 'running' ? '…' : index + 1}
                          </span>
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-sm font-semibold">{step.title}</span>
                              <span className="rounded-full bg-surface/70 px-2 py-0.5 text-[11px] font-semibold">
                                {t(`admin.doc.step.${step.status}` as TranslationKey)}
                              </span>
                            </div>
                            {step.summary && <p className="mb-0 mt-1.5 break-words text-xs">{step.summary}</p>}
                            {step.progress && step.progress.total > 0 && (
                              <div className="mt-2">
                                <div
                                  role="progressbar"
                                  aria-label={step.title}
                                  aria-valuemin={0}
                                  aria-valuemax={step.progress.total}
                                  aria-valuenow={step.progress.done}
                                  className="h-2 overflow-hidden rounded-full bg-surface"
                                >
                                  <div
                                    className="h-full rounded-full bg-ctu-navy transition-[width] dark:bg-ctu-gold-active"
                                    style={{ width: `${Math.min(100, Math.round((step.progress.done / step.progress.total) * 100))}%` }}
                                  />
                                </div>
                                <p className="mb-0 mt-1 text-xs tabular-nums">
                                  {step.progress.done}/{step.progress.total} {step.progress.unit}
                                </p>
                              </div>
                            )}
                            {step.error && <p role="alert" className="mb-0 mt-2 break-words text-xs font-semibold">{step.error}</p>}
                          </div>
                        </div>
                        {((step.metrics?.length ?? 0) > 0 || (step.rows?.length ?? 0) > 0 || step.preview) && (
                          <details className="mt-2 rounded-md border border-line bg-surface text-heading">
                            <summary className="cursor-pointer px-3 py-2 text-xs font-semibold text-accent">
                              {t('admin.doc.details')}
                            </summary>
                            <div className="flex flex-col gap-2 border-t border-line p-3">
                              {(step.metrics?.length ?? 0) > 0 && (
                                <dl className="m-0 grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2">
                                  {step.metrics?.map((metric) => (
                                    <div key={metric.label} className="min-w-0 text-xs">
                                      <dt className="inline text-muted">{metric.label}: </dt>
                                      <dd className="m-0 inline break-words font-semibold">{metric.value}</dd>
                                    </div>
                                  ))}
                                </dl>
                              )}
                              {(step.rows?.length ?? 0) > 0 && (
                                <ul className="m-0 flex list-none flex-col gap-1 p-0 text-xs">
                                  {step.rows?.map((row, rowIndex) => (
                                    <li key={`${row.label}-${rowIndex}`} className="break-words">
                                      <span className="font-semibold">{row.label}</span>
                                      {row.note && <span className="text-muted"> — {row.note}</span>}
                                    </li>
                                  ))}
                                </ul>
                              )}
                              {step.preview && (
                                <pre className="m-0 max-h-56 overflow-auto whitespace-pre-wrap break-words bg-tint p-2 font-mono text-[11px]">
                                  {step.preview}
                                </pre>
                              )}
                            </div>
                          </details>
                        )}
                      </li>
                    ))}
                  </ol>
                  {job.error && (
                    <p role="alert" className="mb-0 mt-4 break-words text-sm font-semibold text-[#9B1C1C] dark:text-[#F5A3A3]">
                      {job.error}
                    </p>
                  )}
                  {nextStage && overview?.editable && (
                    <button
                      type="button"
                      onClick={() => void runStage(nextStage)}
                      disabled={action !== ''}
                      className="mt-4 min-h-11 cursor-pointer rounded-lg bg-ctu-navy px-5 font-sans text-sm font-semibold text-white hover:bg-ctu-navy-dark disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {action === nextStage
                        ? t(`admin.doc.${nextStage}Running` as TranslationKey)
                        : t(`admin.doc.${nextStage}Action` as TranslationKey)}
                    </button>
                  )}
                  {job.status === 'synced' && <p className="mb-0 mt-4 text-sm text-muted">{t('admin.doc.syncedHint')}</p>}
                  {job.ocr_preview && (
                    <details className="mt-5 rounded-lg border border-line bg-surface">
                      <summary className="cursor-pointer px-3 py-2 text-sm font-semibold text-accent">
                        {t('admin.doc.ocrPreview')}
                      </summary>
                      <pre className="m-0 max-h-80 overflow-auto whitespace-pre-wrap break-words border-t border-line bg-tint p-3 font-mono text-xs text-heading">
                        {job.ocr_preview}
                      </pre>
                    </details>
                  )}
                  {job.clean_preview && (
                    <details className="mt-3 rounded-lg border border-line bg-surface" open={job.status === 'cleaned'}>
                      <summary className="cursor-pointer px-3 py-2 text-sm font-semibold text-accent">
                        {t('admin.doc.cleanPreview')}
                      </summary>
                      <pre className="m-0 max-h-[32rem] overflow-auto whitespace-pre-wrap break-words border-t border-line bg-tint p-3 font-mono text-xs text-heading">
                        {job.clean_preview}
                      </pre>
                    </details>
                  )}
                </>
              ) : (
                <p className="m-0 text-sm text-muted">{t('admin.doc.flowEmpty')}</p>
              )}
            </section>
          </div>
        </div>
      )}
    </AdminLayout>
  )
}
