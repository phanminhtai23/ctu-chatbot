import { useCallback, useEffect, useState } from 'react'
import ConfirmDialog from '../../components/ConfirmDialog'
import DonateSection from '../../components/DonateSection'
import Icon from '../../components/Icon'
import { useI18n } from '../../i18n'
import {
  QR_ACCEPT,
  QR_MAX_MB,
  checkQrFile,
  deleteQr,
  donateQrUrl,
  getDonateInfo,
  qrErrorCode,
  uploadQr,
  type DonateInfo,
} from '../../lib/donate'
import AdminLayout from './AdminLayout'

type Pending = { file: File; url: string }
type Notice = { kind: 'ok' | 'error'; text: string }

const buttonBase =
  'inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-lg px-5 py-2.5 font-sans text-[15px] disabled:cursor-not-allowed disabled:opacity-50'

export default function AdminDonate() {
  const { t } = useI18n()
  const [info, setInfo] = useState<DonateInfo | null>(null)
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [pending, setPending] = useState<Pending | null>(null)
  const [saving, setSaving] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [notice, setNotice] = useState<Notice | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoadState('loading')
    try {
      setInfo(await getDonateInfo())
      setLoadState('ready')
    } catch {
      setLoadState('error')
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // Ảnh đang chọn (chưa lưu) được xem trước bằng object URL; trả lại bộ nhớ khi đổi/huỷ/rời trang.
  useEffect(
    () => () => {
      if (pending) URL.revokeObjectURL(pending.url)
    },
    [pending],
  )

  const pick = (file: File | undefined) => {
    if (!file) return
    setNotice(null)
    const problem = checkQrFile(file)
    if (problem) {
      setPending(null)
      setNotice({ kind: 'error', text: t(problem === 'TYPE' ? 'admin.donate.errType' : 'admin.donate.errSize') })
      return
    }
    setPending({ file, url: URL.createObjectURL(file) })
  }

  const save = async () => {
    if (!pending) return
    setSaving(true)
    setNotice(null)
    try {
      setInfo(await uploadQr(pending.file))
      setPending(null)
      setNotice({ kind: 'ok', text: t('admin.donate.saved') })
    } catch (err) {
      const code = qrErrorCode(err)
      const key =
        code === 'IMAGE_TOO_LARGE' ? 'admin.donate.errSize' : code === 'INVALID_IMAGE' ? 'admin.donate.errInvalid' : 'admin.donate.errNetwork'
      setNotice({ kind: 'error', text: t(key) })
    } finally {
      setSaving(false)
    }
  }

  const remove = async () => {
    try {
      await deleteQr()
    } catch {
      setDeleteError(t('admin.donate.errDelete'))
      return // hộp thoại vẫn mở để thử lại
    }
    setInfo({ has_qr: false, version: null })
    setConfirmDelete(false)
    setDeleteError(null)
    setNotice({ kind: 'ok', text: t('admin.donate.deleted') })
  }

  const hasQr = info?.has_qr === true

  return (
    <AdminLayout title={t('admin.donate.title')} subtitle={t('admin.donate.subtitle')}>
      <ConfirmDialog
        open={confirmDelete}
        title={t('admin.donate.deleteTitle')}
        message={t('admin.donate.deleteText')}
        confirmLabel={t('admin.donate.delete')}
        error={deleteError}
        onConfirm={remove}
        onCancel={() => {
          setConfirmDelete(false)
          setDeleteError(null)
        }}
      />

      {loadState === 'loading' && <p role="status">{t('admin.donate.loading')}</p>}
      {loadState === 'error' && (
        <div role="alert" className="flex flex-wrap items-center gap-4 text-[#8A1216] dark:text-[#FFB4B7]">
          <span>{t('admin.donate.loadError')}</span>
          <button
            type="button"
            onClick={load}
            className={`${buttonBase} border border-current bg-transparent font-semibold text-inherit`}
          >
            {t('admin.donate.retry')}
          </button>
        </div>
      )}

      {loadState === 'ready' && (
        <div className="grid items-start gap-6 lg:grid-cols-2">
          <section aria-labelledby="qr-manage" className="rounded-2xl border border-line bg-surface p-5">
            <h2 id="qr-manage" className="mb-4 mt-0 text-lg">
              {t('admin.donate.current')}
            </h2>

            {pending ? (
              <div className="mb-4 flex flex-col items-start gap-3">
                <img
                  src={pending.url}
                  alt={t('admin.donate.selected')}
                  className="size-48 rounded-xl border border-line bg-white object-contain p-2"
                />
                <p className="m-0 break-all text-sm">
                  <strong className="font-semibold text-heading">{pending.file.name}</strong> · {Math.max(1, Math.round(pending.file.size / 1024))} KB
                </p>
                <div className="flex flex-wrap gap-3">
                  <button
                    type="button"
                    onClick={save}
                    disabled={saving}
                    className={`${buttonBase} border-0 bg-ctu-navy font-semibold text-white hover:bg-ctu-navy-dark`}
                  >
                    {t(saving ? 'admin.donate.saving' : 'admin.donate.save')}
                  </button>
                  <button
                    type="button"
                    onClick={() => setPending(null)}
                    disabled={saving}
                    className={`${buttonBase} border border-field bg-transparent font-normal text-heading hover:bg-tint`}
                  >
                    {t('admin.donate.cancel')}
                  </button>
                </div>
              </div>
            ) : hasQr ? (
              <div className="mb-4 flex flex-col items-start gap-3">
                <img
                  src={donateQrUrl(info?.version ?? null)}
                  alt={t('donate.qrAlt')}
                  className="size-48 rounded-xl border border-line bg-white object-contain p-2"
                />
                <button
                  type="button"
                  onClick={() => setConfirmDelete(true)}
                  className={`${buttonBase} border border-field bg-transparent font-normal text-heading hover:bg-tint`}
                >
                  <Icon name="trash" size={18} />
                  {t('admin.donate.delete')}
                </button>
              </div>
            ) : (
              <p className="mb-4 mt-0 text-sm">{t('admin.donate.none')}</p>
            )}

            <label
              htmlFor="qr-file"
              onDragOver={(e) => {
                e.preventDefault()
                setDragging(true)
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDragging(false)
                pick(e.dataTransfer.files[0])
              }}
              className={`relative flex min-h-32 cursor-pointer flex-col items-center justify-center gap-1.5 rounded-xl border-2 border-dashed px-4 py-5 text-center text-sm focus-within:ring-2 focus-within:ring-accent ${
                dragging ? 'border-accent bg-tint' : 'border-field'
              }`}
            >
              <Icon name="upload" size={26} className="text-accent" />
              <span className="font-normal text-heading">{t(hasQr || pending ? 'admin.donate.replace' : 'admin.donate.drop')}</span>
              <span className="text-xs">
                {t('admin.donate.hint')} {QR_MAX_MB} MB.
              </span>
              <input
                id="qr-file"
                type="file"
                accept={QR_ACCEPT}
                className="sr-only"
                onChange={(e) => {
                  pick(e.target.files?.[0])
                  e.target.value = '' // chọn lại đúng file cũ vẫn kích hoạt onChange
                }}
              />
            </label>

            {notice && (
              <p
                role={notice.kind === 'error' ? 'alert' : 'status'}
                className={`mb-0 mt-4 text-sm ${
                  notice.kind === 'error' ? 'text-[#8A1216] dark:text-[#FFB4B7]' : 'text-[#14602F] dark:text-[#8AD9A8]'
                }`}
              >
                {notice.text}
              </p>
            )}
          </section>

          <section aria-labelledby="qr-preview" className="rounded-2xl border border-line bg-surface p-5">
            <h2 id="qr-preview" className="mb-1 mt-0 text-lg">
              {t('admin.donate.preview')}
            </h2>
            {hasQr ? (
              <DonateSection info={info} className="mt-3" />
            ) : (
              <p className="m-0 mt-2 text-sm">{t('admin.donate.previewEmpty')}</p>
            )}
          </section>
        </div>
      )}
    </AdminLayout>
  )
}
