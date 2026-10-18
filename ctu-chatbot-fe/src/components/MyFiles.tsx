import { useState } from 'react'
import { useI18n } from '../i18n'
import { deleteFile, fileErrorCode, type FileListing } from '../lib/files'
import { formatBytes } from '../lib/format'
import { useFormatDate } from '../hooks/useFormatDate'
import { fileErrorMessage } from './fileErrors'
import Icon from './Icon'

/** Thanh dung lượng đã dùng / tối đa. Đổi màu khi gần đầy. `sidebar` = bản gọn chữ trắng cho thanh bên tối. */
export function UsageBar({ used, quota, variant = 'card' }: { used: number; quota: number; variant?: 'card' | 'sidebar' }) {
  const { t } = useI18n()
  const percent = quota > 0 ? Math.min(100, Math.round((used / quota) * 100)) : 0
  const sidebar = variant === 'sidebar'
  const tone = percent >= 90 ? 'bg-[#FF6B6B]' : percent >= 70 ? 'bg-ctu-gold-active' : sidebar ? 'bg-ctu-cyan' : 'bg-accent'
  return (
    <div>
      <div className={`flex items-baseline justify-between gap-3 ${sidebar ? 'mb-1 text-xs text-white/85' : 'mb-1.5 text-sm'}`}>
        <span>{t('files.usage')}</span>
        <strong className={`font-semibold tabular-nums ${sidebar ? 'text-white' : 'text-heading'}`}>
          {formatBytes(used)} / {formatBytes(quota)}
        </strong>
      </div>
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={quota}
        aria-valuenow={used}
        aria-label={t('files.usage')}
        className={`overflow-hidden rounded-full ${sidebar ? 'h-1.5 bg-white/20' : 'h-2.5 bg-tint'}`}
      >
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${percent}%` }} />
      </div>
    </div>
  )
}

/** Tệp (PDF / ảnh) người dùng đã gửi trong lúc trò chuyện: xem dung lượng đã dùng và xoá bớt. Không có nút tải lên ở đây. */
export default function MyFiles({ listing, onChange }: { listing: FileListing | null; onChange: (next: FileListing) => void }) {
  const { t } = useI18n()
  const formatDate = useFormatDate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmId, setConfirmId] = useState<string | null>(null)

  if (!listing) return null
  const attachments = listing.items.filter((f) => f.kind === 'attachment')

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
    <section id="my-files" aria-labelledby="my-files-title" className="mt-6 rounded-2xl border border-line bg-tint p-4 sm:p-5">
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

      {error && (
        <p role="alert" className="mb-0 mt-3 text-sm text-[#8A1216] dark:text-[#FFB4B7]">
          {error}
        </p>
      )}
    </section>
  )
}
