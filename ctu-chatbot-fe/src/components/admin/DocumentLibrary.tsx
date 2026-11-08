import { useMemo, useState, type FormEvent } from 'react'
import { useFormatDate } from '../../hooks/useFormatDate'
import { useI18n } from '../../i18n'
import type { TranslationKey } from '../../i18n/vi'
import {
  activateCatalogVersion,
  deleteCatalogDocument,
  updateCatalogDocument,
  uploadErrorCode,
  type CatalogJob,
  type RouteConfig,
  type RouteNode,
} from '../../lib/adminDocuments'
import Icon from '../Icon'
import RouterPromptAssist from './RouterPromptAssist'

type Props = {
  routes: RouteConfig
  jobs: CatalogJob[]
  editable: boolean
  /** Gọi sau khi sửa / xoá xong để tải lại danh mục */
  onChanged: (change: { deletedSlug?: string; message: string }) => void
  onError: (message: string) => void
  /** Mở quy trình xử lý của một version (chuyển sang tab Quy trình) */
  onOpenJob: (job: CatalogJob) => void
  /** Tải lên phiên bản mới cho tài liệu này (chuyển sang tab Quy trình với biểu mẫu upload) */
  onUploadVersion: (node: RouteNode) => void
}

type Entry = { node: RouteNode; versions: number; pending: boolean; builtin: boolean; jobs: CatalogJob[] }

const fieldClass =
  'min-h-11 w-full rounded-lg border border-field bg-surface px-3 font-sans text-sm text-heading outline-none focus:border-ctu-cyan focus:ring-2 focus:ring-ctu-cyan/20 disabled:opacity-60'

/** Gộp các node cùng `document_slug` thành một tài liệu: ưu tiên node đã đồng bộ, chưa có thì lấy bản chờ mới nhất. */
function groupDocuments(routes: RouteConfig, jobs: CatalogJob[]): Entry[] {
  const groups = new Map<string, RouteNode[]>()
  for (const node of routes.nodes) {
    if (node.kind !== 'document') continue
    const key = node.document_slug ?? node.id
    groups.set(key, [...(groups.get(key) ?? []), node])
  }
  return [...groups.entries()].map(([key, nodes]) => {
    const synced = nodes.find((n) => n.status !== 'pending')
    const node = synced ?? nodes[nodes.length - 1]
    const builtin = !node.document_slug
    const docJobs = builtin ? [] : jobs.filter((job) => job.slug === key)
    return {
      node,
      builtin,
      pending: !synced,
      jobs: docJobs,
      versions: builtin ? 1 : docJobs.length || nodes.length,
    }
  })
}

function DocumentCard({
  entry,
  editable,
  onChanged,
  onError,
  onOpenJob,
  onUploadVersion,
}: { entry: Entry } & Pick<Props, 'editable' | 'onChanged' | 'onError' | 'onOpenJob' | 'onUploadVersion'>) {
  const { t } = useI18n()
  const formatDate = useFormatDate()
  const { node, builtin, pending, versions, jobs } = entry
  const [showVersions, setShowVersions] = useState(false)
  const [switching, setSwitching] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [label, setLabel] = useState(node.label)
  const [decisionNo, setDecisionNo] = useState(node.decision_no ?? '')
  const [officialUrl, setOfficialUrl] = useState(node.official_url ?? '')
  const [busy, setBusy] = useState<'save' | 'delete' | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [assistOpen, setAssistOpen] = useState(false)

  const startEdit = () => {
    setLabel(node.label)
    setDecisionNo(node.decision_no ?? '')
    setOfficialUrl(node.official_url ?? '')
    setEditing(true)
  }

  const save = async (event: FormEvent) => {
    event.preventDefault()
    if (!label.trim() || busy) return
    setBusy('save')
    try {
      await updateCatalogDocument(node.id, { label, decision_no: decisionNo, official_url: officialUrl })
      setEditing(false)
      onChanged({ message: t('admin.doc.lib.saved') })
    } catch {
      onError(t('admin.doc.lib.saveFailed'))
    } finally {
      setBusy(null)
    }
  }

  const remove = async () => {
    if (!confirming) {
      setConfirming(true) // bấm lần đầu: hỏi lại, tránh xoá nhầm
      return
    }
    setBusy('delete')
    try {
      await deleteCatalogDocument(node.id)
      onChanged({ deletedSlug: node.document_slug, message: t('admin.doc.lib.deleted') })
    } catch (error) {
      const code = uploadErrorCode(error)
      onError(t(code === 'DOCUMENT_PROTECTED' ? 'admin.doc.lib.protected' : code === 'CATALOG_READ_ONLY' ? 'admin.doc.readOnly' : 'admin.doc.lib.deleteFailed'))
      setConfirming(false)
    } finally {
      setBusy(null)
    }
  }

  const activate = async (job: CatalogJob) => {
    if (switching) return
    setSwitching(job.id)
    try {
      await activateCatalogVersion(node.id, job.id)
      onChanged({ message: t('admin.doc.ver.switched') })
    } catch (error) {
      onError(t(uploadErrorCode(error) === 'ACTIVATE_NOT_ALLOWED' ? 'admin.doc.ver.notAllowed' : 'admin.doc.ver.switchFailed'))
    } finally {
      setSwitching(null)
    }
  }

  const statusKey: TranslationKey = pending ? 'admin.doc.lib.pending' : 'admin.doc.lib.synced'

  return (
    <li className="rounded-2xl border border-line bg-surface p-4 shadow-sm md:p-5">
      {editing ? (
        <form onSubmit={save} className="flex flex-col gap-3">
          <div>
            <label htmlFor={`lib-name-${node.id}`} className="mb-1.5 block text-sm font-semibold text-heading">
              {t('admin.doc.lib.name')}
            </label>
            <input id={`lib-name-${node.id}`} value={label} maxLength={100} onChange={(e) => setLabel(e.target.value)} className={fieldClass} />
          </div>
          <div>
            <label htmlFor={`lib-decision-${node.id}`} className="mb-1.5 block text-sm font-semibold text-heading">
              {t('admin.doc.lib.decision')}
            </label>
            <input
              id={`lib-decision-${node.id}`}
              value={decisionNo}
              maxLength={100}
              placeholder={t('admin.doc.lib.decisionHint')}
              onChange={(e) => setDecisionNo(e.target.value)}
              className={fieldClass}
            />
          </div>
          <div>
            <label htmlFor={`lib-url-${node.id}`} className="mb-1.5 block text-sm font-semibold text-heading">
              {t('admin.doc.lib.officialUrl')}
            </label>
            <input
              id={`lib-url-${node.id}`}
              type="url"
              inputMode="url"
              value={officialUrl}
              maxLength={500}
              placeholder={t('admin.doc.lib.officialUrlHint')}
              onChange={(e) => setOfficialUrl(e.target.value)}
              className={fieldClass}
            />
            <p className="mb-0 mt-1.5 text-xs text-muted">{t('admin.doc.lib.officialUrlNote')}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="submit"
              disabled={!label.trim() || busy !== null}
              className="min-h-11 cursor-pointer rounded-lg border-0 bg-ctu-navy px-5 font-sans text-sm font-semibold text-white hover:bg-ctu-navy-dark disabled:cursor-not-allowed disabled:opacity-50"
            >
              {t(busy === 'save' ? 'admin.doc.lib.saving' : 'admin.doc.lib.save')}
            </button>
            <button
              type="button"
              onClick={() => setEditing(false)}
              disabled={busy !== null}
              className="min-h-11 cursor-pointer rounded-lg border border-line bg-transparent px-4 font-sans text-sm text-heading hover:bg-tint disabled:opacity-50"
            >
              {t('admin.doc.lib.cancel')}
            </button>
          </div>
        </form>
      ) : (
        <>
          <div className="flex flex-wrap items-start gap-3">
            <span className="flex size-11 flex-none items-center justify-center rounded-2xl bg-tint text-accent">
              <Icon name="doc" size={22} />
            </span>
            <div className="min-w-0 flex-1">
              <h3 className="m-0 break-words text-base font-semibold text-heading">{node.label}</h3>
              <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs">
                {node.decision_no && (
                  <span className="rounded-md border border-ctu-cyan bg-tint px-2 py-0.5 font-semibold text-accent" title={t('admin.doc.lib.decision')}>
                    {node.decision_no}
                  </span>
                )}
                <span
                  className={`rounded-full border px-2 py-0.5 font-semibold ${
                    pending
                      ? 'border-ctu-gold-active bg-[#FFF8E1] text-[#7A5200] dark:bg-[#302711] dark:text-[#F2CB74]'
                      : 'border-[#2E9E5B] bg-[#E3F4EA] text-[#14602F] dark:bg-[#12301F] dark:text-[#8AD9A8]'
                  }`}
                >
                  {t(statusKey)}
                </span>
                {builtin && <span className="rounded-full border border-line px-2 py-0.5 text-muted">{t('admin.doc.lib.builtin')}</span>}
                {!builtin && (
                  <span className="text-muted">
                    {versions} {t('admin.doc.lib.versions')}
                  </span>
                )}
              </div>
            </div>
            {editable && (
              <div className="flex flex-none items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setAssistOpen(true)}
                  aria-label={`${t('admin.doc.rp.open')}: ${node.label}`}
                  title={t('admin.doc.rp.open')}
                  className="inline-flex size-11 cursor-pointer items-center justify-center rounded-lg border border-line bg-transparent text-heading hover:bg-tint"
                >
                  <Icon name="sparkles" size={18} />
                </button>
                <button
                  type="button"
                  onClick={startEdit}
                  aria-label={`${t('admin.doc.lib.edit')}: ${node.label}`}
                  title={t('admin.doc.lib.edit')}
                  className="inline-flex size-11 cursor-pointer items-center justify-center rounded-lg border border-line bg-transparent text-heading hover:bg-tint"
                >
                  <Icon name="pencil" size={18} />
                </button>
                {!builtin && (
                  <button
                    type="button"
                    onClick={() => void remove()}
                    onBlur={() => setConfirming(false)}
                    disabled={busy !== null}
                    aria-label={`${t('admin.doc.lib.delete')}: ${node.label}`}
                    title={t('admin.doc.lib.deleteWarn')}
                    className={`inline-flex min-h-11 cursor-pointer items-center justify-center gap-1.5 rounded-lg border px-3 font-sans text-sm disabled:cursor-not-allowed disabled:opacity-50 ${
                      confirming ? 'border-[#D64545] bg-[#D64545] text-white' : 'border-line bg-transparent text-heading hover:bg-tint'
                    }`}
                  >
                    <Icon name="trash" size={18} />
                    {confirming && <span>{t('admin.doc.lib.confirmDelete')}</span>}
                  </button>
                )}
              </div>
            )}
          </div>
          {node.description && <p className="mb-0 mt-3 break-words text-sm text-muted">{node.description}</p>}
          <p className="mb-0 mt-3 text-sm">
            {node.official_url ? (
              <a
                href={node.official_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex min-h-11 items-center gap-1.5 break-all font-semibold text-accent"
              >
                <Icon name="share" size={16} className="flex-none" />
                {t('admin.doc.lib.openOfficial')}
              </a>
            ) : (
              <span className="text-muted">{t('admin.doc.lib.noOfficialUrl')}</span>
            )}
          </p>
          {!builtin && (
            <div className="mt-3 border-t border-line pt-3">
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowVersions((value) => !value)}
                  aria-expanded={showVersions}
                  aria-controls={`versions-${node.id}`}
                  className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border-0 bg-transparent px-2 font-sans text-sm font-semibold text-accent hover:bg-tint"
                >
                  <Icon name="swap" size={16} />
                  {t('admin.doc.ver.toggle')} ({jobs.length})
                </button>
                {editable && (
                  <button
                    type="button"
                    onClick={() => onUploadVersion(node)}
                    className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border border-ctu-cyan bg-transparent px-3 font-sans text-sm font-semibold text-accent hover:bg-tint"
                  >
                    <Icon name="upload" size={16} />
                    {t('admin.doc.ver.upload')}
                  </button>
                )}
              </div>
              {showVersions && (
                <ul id={`versions-${node.id}`} className="m-0 mt-2 flex list-none flex-col gap-2 p-0">
                  {jobs.length === 0 && <li className="text-sm text-muted">{t('admin.doc.ver.none')}</li>}
                  {jobs.map((job) => {
                    const active = !pending && node.version === job.id
                    return (
                      <li
                        key={job.id}
                        className={`flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 ${active ? 'border-[#2E9E5B]' : 'border-line'}`}
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-semibold text-heading" title={job.filename}>
                            {job.filename}
                          </span>
                          <span className="block text-xs text-muted">{formatDate(job.created_at)}</span>
                        </span>
                        {active && (
                          <span className="rounded-full border border-[#2E9E5B] px-2 py-0.5 text-xs font-semibold text-[#14602F] dark:text-[#8AD9A8]">
                            {t('admin.doc.ver.active')}
                          </span>
                        )}
                        {!active && job.status === 'synced' && editable && (
                          <button
                            type="button"
                            onClick={() => void activate(job)}
                            disabled={switching !== null}
                            className="min-h-11 cursor-pointer rounded-lg border border-ctu-cyan bg-transparent px-3 font-sans text-sm font-semibold text-accent hover:bg-tint disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {t(switching === job.id ? 'admin.doc.ver.using' : 'admin.doc.ver.use')}
                          </button>
                        )}
                        {job.status !== 'synced' && (
                          <span className="rounded-full border border-line px-2 py-0.5 text-xs text-muted">
                            {t(`admin.doc.status.${job.status}` as TranslationKey)}
                          </span>
                        )}
                        <button
                          type="button"
                          onClick={() => onOpenJob(job)}
                          className="min-h-11 cursor-pointer rounded-lg border-0 bg-transparent px-2 font-sans text-sm text-accent hover:underline"
                        >
                          {t('admin.doc.ver.open')}
                        </button>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          )}
        </>
      )}
      {editable && (
        <RouterPromptAssist
          node={node}
          open={assistOpen}
          onClose={() => setAssistOpen(false)}
          onApplied={() => {
            setAssistOpen(false)
            onChanged({ message: t('admin.doc.rp.accepted') })
          }}
        />
      )}
    </li>
  )
}

/** Danh sách tài liệu chatbot hỗ trợ: đổi tên, ghi số quyết định + mô tả, xoá tài liệu đã upload. */
export default function DocumentLibrary({ routes, jobs, editable, onChanged, onError, onOpenJob, onUploadVersion }: Props) {
  const { t } = useI18n()
  const entries = useMemo(() => groupDocuments(routes, jobs), [routes, jobs])
  return (
    <section role="tabpanel" id="panel-library" aria-labelledby="tab-library" className="rounded-xl border border-line bg-surface p-4 md:p-6">
      <h2 className="m-0 text-base font-semibold text-heading">{t('admin.doc.lib.title')}</h2>
      <p className="mb-4 mt-1 text-sm text-muted">{t('admin.doc.lib.hint')}</p>
      {entries.length === 0 ? (
        <p className="m-0 text-sm text-muted">{t('admin.doc.lib.empty')}</p>
      ) : (
        <ul className="m-0 grid list-none grid-cols-1 gap-3 p-0 lg:grid-cols-2">
          {entries.map((entry) => (
            <DocumentCard
              key={entry.node.id}
              entry={entry}
              editable={editable}
              onChanged={onChanged}
              onError={onError}
              onOpenJob={onOpenJob}
              onUploadVersion={onUploadVersion}
            />
          ))}
        </ul>
      )}
    </section>
  )
}
