import { useCallback, useEffect, useRef, useState, type DragEvent } from 'react'
import Icon from '../../components/Icon'
import DocumentPipeline, { PipelineSummary, currentStage } from '../../components/admin/DocumentPipeline'
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
  const [tab, setTab] = useState<'flow' | 'routes'>('flow')
  const [title, setTitle] = useState('')
  const [titleTouched, setTitleTouched] = useState(false)
  const [file, setFile] = useState<File | null>(null)
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

  const pickFile = (picked: File | undefined) => {
    if (!picked) return
    if (!/\.pdf$/i.test(picked.name) && picked.type !== 'application/pdf') {
      setNotice({ ok: false, text: t('admin.doc.errNotPdf') })
      return
    }
    setNotice(null)
    setFile(picked)
    if (!titleTouched) setTitle(picked.name.replace(/\.pdf$/i, '').replace(/[_]+/g, ' ').trim().slice(0, 100))
  }

  const clearFile = () => {
    setFile(null)
    if (!titleTouched) setTitle('')
    if (inputRef.current) inputRef.current.value = ''
  }

  const upload = async () => {
    if (!file || uploading || !overview?.editable) return
    if (!title.trim()) {
      setNotice({ ok: false, text: t('admin.doc.errName') })
      return
    }
    setUploading(true)
    setNotice(null)
    try {
      const created = await uploadCatalogDocument(file, title.trim())
      setTitle('')
      setTitleTouched(false)
      clearFile()
      setTab('flow')
      await refreshAfterAction(created)
      setNotice({ ok: true, text: t('admin.doc.uploadSaved') })
    } catch (error) {
      const code = uploadErrorCode(error)
      setNotice({ ok: false, text: t(uploadErrors[code] ?? 'admin.doc.errGeneric') })
    } finally {
      setUploading(false)
    }
  }

  const onDrop = (event: DragEvent) => {
    event.preventDefault()
    setDragging(false)
    if (overview?.editable && !uploading) pickFile(event.dataTransfer.files[0])
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

  const stage = job ? currentStage(job) : null
  const pendingRoutes = routeDraft?.nodes.filter((node) => node.status === 'pending').length ?? 0
  const locked = !overview?.editable || uploading
  const statusTone = (status: CatalogJob['status']) => stepClass[status === 'failed' ? 'failed' : status === 'synced' ? 'done' : 'pending']

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
        <div className="flex flex-col gap-5">
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

          <div role="tablist" aria-label={t('admin.doc.title')} className="flex gap-1 border-b border-line">
            {(
              [
                ['flow', 'admin.doc.tab.flow'],
                ['routes', 'admin.doc.tab.routes'],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                role="tab"
                id={`tab-${key}`}
                aria-selected={tab === key}
                aria-controls={`panel-${key}`}
                onClick={() => setTab(key)}
                className={`-mb-px flex min-h-11 flex-1 cursor-pointer items-center justify-center gap-2 whitespace-nowrap border-0 border-b-2 bg-transparent px-2 font-sans text-sm font-semibold sm:flex-none sm:px-4 ${
                  tab === key ? 'border-ctu-navy text-heading dark:border-ctu-gold-active' : 'border-transparent text-muted hover:text-heading'
                }`}
              >
                {t(label)}
                {key === 'routes' && pendingRoutes > 0 && (
                  <span
                    title={`${pendingRoutes} ${t('admin.doc.pendingRoutes')}`}
                    className="rounded-full border border-ctu-gold-active bg-[#FFF8E1] px-2 py-0.5 text-[11px] text-[#7A5200] dark:bg-[#302711] dark:text-[#F2CB74]"
                  >
                    {pendingRoutes}
                  </span>
                )}
              </button>
            ))}
          </div>

          {tab === 'routes' ? (
            <section
              role="tabpanel"
              id="panel-routes"
              aria-labelledby="tab-routes"
              className="rounded-xl border border-line bg-surface p-4 md:p-6"
            >
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="m-0 text-base font-semibold text-heading">{t('admin.doc.routeFlow')}</h2>
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
          ) : (
            <div
              role="tabpanel"
              id="panel-flow"
              aria-labelledby="tab-flow"
              className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,360px)_minmax(0,1fr)]"
            >
              <div className={`flex min-w-0 flex-col gap-5 ${job ? 'order-2 xl:order-none' : ''}`}>
                <section className="rounded-xl border border-line bg-surface p-4 md:p-5" aria-labelledby="doc-upload-title">
                  <h2 id="doc-upload-title" className="m-0 mb-3 text-base font-semibold text-heading">
                    {t('admin.doc.upload')}
                  </h2>
                  {!overview?.editable && <p className="m-0 mb-3 text-sm text-muted">{t('admin.doc.readOnly')}</p>}
                  <input
                    ref={inputRef}
                    id="doc-file"
                    type="file"
                    accept="application/pdf,.pdf"
                    className="sr-only"
                    disabled={locked}
                    onChange={(event) => pickFile(event.target.files?.[0])}
                  />
                  {file ? (
                    <div className="mb-3 flex items-center gap-3 rounded-lg border border-line bg-tint px-3 py-2.5">
                      <Icon name="doc" size={22} className="flex-none text-accent" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-semibold text-heading">{file.name}</span>
                        <span className="block text-xs text-muted">{(file.size / 1024 / 1024).toFixed(2)} MB</span>
                      </span>
                      <button
                        type="button"
                        onClick={clearFile}
                        disabled={uploading}
                        className="min-h-11 cursor-pointer rounded-lg border-0 bg-transparent px-2 font-sans text-xs font-semibold text-accent hover:underline disabled:opacity-50"
                      >
                        {t('admin.doc.clearFile')}
                      </button>
                    </div>
                  ) : (
                    <label
                      htmlFor="doc-file"
                      onDragOver={(event) => {
                        event.preventDefault()
                        setDragging(true)
                      }}
                      onDragLeave={() => setDragging(false)}
                      onDrop={onDrop}
                      className={`mb-3 flex flex-col items-center gap-1.5 rounded-lg border-2 border-dashed px-4 py-6 text-center ${
                        dragging ? 'border-ctu-navy bg-tint' : 'border-field'
                      } ${locked ? 'cursor-not-allowed opacity-60' : 'cursor-pointer hover:bg-tint'}`}
                    >
                      <Icon name="upload" size={26} className="text-accent" />
                      <span className="text-sm font-semibold text-heading">{t('admin.doc.drop')}</span>
                      <span className="text-xs text-muted">{t('admin.doc.dropHint')}</span>
                    </label>
                  )}
                  <label htmlFor="doc-title" className="mb-1.5 block text-sm font-semibold text-heading">
                    {t('admin.doc.documentName')}
                  </label>
                  <input
                    id="doc-title"
                    value={title}
                    onChange={(event) => {
                      setTitle(event.target.value)
                      setTitleTouched(true)
                    }}
                    maxLength={100}
                    disabled={locked}
                    placeholder={t('admin.doc.documentNamePlaceholder')}
                    className="mb-3 min-h-11 w-full rounded-lg border border-field bg-surface px-3 font-sans text-sm text-heading outline-none focus:border-ctu-cyan focus:ring-2 focus:ring-ctu-cyan/20 disabled:opacity-60"
                  />
                  <button
                    type="button"
                    onClick={() => void upload()}
                    disabled={locked || !file || !title.trim()}
                    className="min-h-11 w-full cursor-pointer rounded-lg bg-ctu-navy px-5 font-sans text-sm font-semibold text-white hover:bg-ctu-navy-dark disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {uploading ? t('admin.doc.uploading') : t('admin.doc.uploadSubmit')}
                  </button>
                  <p className="mb-0 mt-3 flex items-start gap-2 text-xs text-muted">
                    <Icon name="shield" size={14} className="mt-0.5 flex-none" />
                    {t('admin.doc.versionStorage')}
                  </p>
                </section>

                <section className="rounded-xl border border-line bg-surface p-4 md:p-5" aria-labelledby="doc-history-title">
                  <h2 id="doc-history-title" className="m-0 mb-3 text-base font-semibold text-heading">
                    {t('admin.doc.versions')}
                  </h2>
                  {overview && overview.jobs.length > 0 ? (
                    <ul className="m-0 flex max-h-96 list-none flex-col gap-2 overflow-y-auto p-0">
                      {overview.jobs.map((item) => (
                        <li key={`${item.slug}-${item.id}`}>
                          <button
                            type="button"
                            onClick={() => void openJob(item)}
                            aria-pressed={job?.id === item.id}
                            className={`flex min-h-14 w-full cursor-pointer items-center gap-3 rounded-lg border-2 bg-surface px-3 py-2 text-left font-sans hover:bg-tint ${
                              job?.id === item.id ? 'border-ctu-cyan' : 'border-line'
                            }`}
                          >
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-sm font-semibold text-heading">{item.title}</span>
                              <span className="block truncate text-xs text-muted">
                                {item.filename} · {formatDate(item.created_at)}
                              </span>
                            </span>
                            <span className={`flex-none rounded-full border px-2 py-0.5 text-[11px] font-semibold ${statusTone(item.status)}`}>
                              {t(stageLabel[item.status])}
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="m-0 text-sm text-muted">{t('admin.doc.noVersions')}</p>
                  )}
                </section>

                {overview?.sync_enabled && (
                  <section className="rounded-xl border border-line bg-surface p-4 md:p-5" aria-labelledby="catalog-sync-title">
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
              </div>

              <section
                className={`min-w-0 rounded-xl border border-line bg-surface p-4 md:p-6 ${job ? 'order-1 xl:order-none' : ''}`}
                aria-labelledby="doc-workflow-title"
              >
                <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 id="doc-workflow-title" className="m-0 text-base font-semibold text-heading">
                      {job ? job.title : t('admin.doc.reviewFlow')}
                    </h2>
                    {job && (
                      <p className="mb-0 mt-1 break-all text-xs text-muted">
                        {job.filename} · {job.id}
                      </p>
                    )}
                  </div>
                  {job && (
                    <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${statusTone(job.status)}`}>
                      {t(stageLabel[job.status])}
                    </span>
                  )}
                </div>
                {job ? (
                  <div className="flex flex-col gap-5">
                    <PipelineSummary job={job} />
                    {job.error && stage && (
                      <p
                        role="alert"
                        className="m-0 break-words rounded-lg border border-[#D13434] bg-[#FDE7E7] px-3 py-2 text-sm font-semibold text-[#9B1C1C] dark:bg-[#3B1414] dark:text-[#F5A3A3]"
                      >
                        {job.error}
                      </p>
                    )}
                    <DocumentPipeline
                      job={job}
                      editable={Boolean(overview?.editable)}
                      syncEnabled={Boolean(overview?.sync_enabled)}
                      action={action}
                      onRun={(next) => void runStage(next)}
                    />
                    {job.status === 'synced' && (
                      <p className="m-0 rounded-lg border border-[#2E9E5B] bg-[#E3F4EA] px-3 py-2 text-sm text-[#14602F] dark:bg-[#12301F] dark:text-[#8AD9A8]">
                        {t('admin.doc.allDone')}
                      </p>
                    )}
                  </div>
                ) : (
                  <p className="m-0 text-sm text-muted">{t('admin.doc.flowEmpty')}</p>
                )}
              </section>
            </div>
          )}
        </div>
      )}
    </AdminLayout>
  )
}
