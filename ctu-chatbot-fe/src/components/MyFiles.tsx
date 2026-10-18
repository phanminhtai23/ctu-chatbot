import { useRef, useState } from 'react'
import { useI18n } from '../i18n'
import { deleteFile, fileErrorCode, uploadFile, type FileListing } from '../lib/files'
import { fillTemplate, formatBytes } from '../lib/format'
import { useFormatDate } from '../hooks/useFormatDate'
import { fileErrorMessage } from './fileErrors'
import Icon from './Icon'

/** Thanh dung lượng đã dùng / tối đa. Đổi màu khi gần đầy. */
export function UsageBar({ used, quota }: { used: number; quota: number }) {
  const { t } = useI18n()
  const percent = quota > 0 ? Math.min(100, Math.round((used / quota) * 100)) : 0
  const tone = percent >= 90 ? 'bg-[#D64545]' : percent >= 70 ? 'bg-ctu-gold-active' : 'bg-accent'
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-3 text-sm">
        <span>{t('files.usage')}</span>
        <strong className="font-semibold tabular-nums text-heading">
          {formatBytes(used)} / {formatBytes(quota)}
        </strong>
      </div>
      <div role="progressbar" aria-valuemin={0} aria-valuemax={quota} aria-valuenow={used} aria-label={t('files.usage')} className="h-2.5 overflow-hidden rounded-full bg-tint">
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${percent}%` }} />
      </div>
    </div>
  )
}

/** Tệp (PDF / ảnh) người dùng đã tải lên: xem dung lượng đã dùng, tải thêm, xoá bớt. */
export default function MyFiles({ listing, onChange }: { listing: FileListing | null; onChange: (next: FileListing) => void }) {
  const { t } = useI18n()
  const formatDate = useFormatDate()
  const inputRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmId, setConfirmId] = useState<string | null>(null)

  if (!listing) return null
  const attachments = listing.items.filter((f) => f.kind === 'attachment')

  const handleUpload = async (file: File) => {
    setBusy(true)
    setError(null)
    try {
      onChange(await uploadFile(file))
    } catch (err) {
      setError(fileErrorMessage(fileErrorCode(err), t, listing.max_upload_bytes))
    } finally {
      setBusy(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (confirmId !== id) {
      setConfirmId(id) // bấm lần đầu: hỏi lại, tránh xoá nhầm
      return
    }
    setBusy(true)
    setError(null)
    try {
      await deleteFile(id)
      onChange({ ...listing, items: listing.items.filter((f) => f.id !== id), used_bytes: listing.used_bytes - (listing.items.find((f) => f.id === id)?.size_bytes ?? 0) })
    } catch (err) {
      setError(fileErrorMessage(fileErrorCode(err), t, listing.max_upload_bytes))
    } finally {
      setConfirmId(null)
      setBusy(false)
    }
  }

  return (
    <section aria-labelledby="my-files-title" className="mt-6 rounded-2xl border border-line bg-tint p-4 sm:p-5">
      <h3 id="my-files-title" className="mb-3 mt-0 text-base">
        {t('files.title')}
      </h3>
      <UsageBar used={listing.used_bytes} quota={listing.quota_bytes} />

      {attachments.length === 0 ? (
        <p className="mb-0 mt-4 text-sm">{t('files.empty')}</p>
      ) : (
        <ul className="mb-0 mt-4 flex list-none flex-col gap-2 p-0">
          {attachments.map((f) => (
            <li key={f.id} className="flex items-center gap-3 rounded-lg border border-line bg-surface px-3 py-2">
              <Icon name={f.content_type === 'application/pdf' ? 'doc' : 'image'} size={20} className="flex-none text-accent" />
              <div className="min-w-0 flex-1">
                <a href={f.url} target="_blank" rel="noopener noreferrer" className="block truncate text-sm font-normal text-heading no-underline hover:underline" title={f.filename}>
                  {f.filename}
                </a>
                <div className="text-xs">
                  {formatBytes(f.size_bytes)} · {formatDate(f.created_at)}
                </div>
              </div>
              <button
                type="button"
                disabled={busy}
                onClick={() => handleDelete(f.id)}
                onBlur={() => setConfirmId((current) => (current === f.id ? null : current))}
                aria-label={`${t('files.delete')}: ${f.filename}`}
                className={`inline-flex min-h-9 cursor-pointer items-center gap-1.5 rounded-md border px-2.5 font-sans text-[13px] disabled:cursor-not-allowed disabled:opacity-50 ${
                  confirmId === f.id
                    ? 'border-[#D64545] bg-[#D64545] text-white'
                    : 'border-line bg-transparent text-heading hover:bg-tint'
                }`}
              >
                <Icon name="trash" size={16} />
                {t(confirmId === f.id ? 'files.confirmDelete' : 'files.delete')}
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={busy || listing.used_bytes >= listing.quota_bytes}
          onClick={() => inputRef.current?.click()}
          className="inline-flex min-h-10 cursor-pointer items-center gap-2 rounded-lg border-0 bg-ctu-navy px-4 py-2 font-sans text-sm font-semibold text-white hover:bg-ctu-navy-dark disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Icon name="upload" size={18} />
          {t(busy ? 'files.uploading' : 'files.upload')}
        </button>
        <span className="text-xs">{fillTemplate(t('files.uploadHint'), { max: formatBytes(listing.max_upload_bytes) })}</span>
      </div>
      {error && (
        <p role="alert" className="mb-0 mt-3 text-sm text-[#8A1216] dark:text-[#FFB4B7]">
          {error}
        </p>
      )}
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,image/png,image/jpeg,image/webp"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          e.target.value = ''
          if (file) handleUpload(file)
        }}
      />
    </section>
  )
}
