import { useEffect, useRef, useState } from 'react'
import { useI18n } from '../i18n'

type Props = {
  open: boolean
  title: string
  message: string
  confirmLabel: string
  /** Lỗi hiển thị trong hộp thoại khi hành động thất bại (hộp thoại vẫn mở để thử lại) */
  error?: string | null
  onConfirm: () => Promise<void>
  onCancel: () => void
}

export default function ConfirmDialog({ open, title, message, confirmLabel, error, onConfirm, onCancel }: Props) {
  const { t } = useI18n()
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [working, setWorking] = useState(false)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    else if (!open && dialog.open) dialog.close()
  }, [open])

  const handleConfirm = async () => {
    setWorking(true)
    try {
      await onConfirm()
    } finally {
      setWorking(false)
    }
  }

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby="confirm-title"
      aria-describedby="confirm-text"
      onClose={onCancel}
      onClick={(e) => {
        if (e.target === dialogRef.current && !working) onCancel()
      }}
      className="m-auto w-[calc(100%-32px)] max-w-[440px] rounded-2xl border border-line bg-surface p-6 text-muted shadow-[0_24px_60px_rgba(0,0,0,.35)] backdrop:bg-black/50"
    >
      <h2 id="confirm-title" className="mb-2 mt-0 text-lg">{title}</h2>
      <p id="confirm-text" className="mb-5 mt-0 text-[15px]">{message}</p>
      {error && (
        <p role="alert" className="mb-4 mt-0 text-sm text-[#8A1216] dark:text-[#FFB4B7]">{error}</p>
      )}
      <div className="flex flex-wrap justify-end gap-3">
        <button
          type="button"
          onClick={onCancel}
          disabled={working}
          className="min-h-11 cursor-pointer rounded-lg border border-field bg-transparent px-6 py-2.5 font-sans text-base font-normal text-heading hover:bg-tint disabled:cursor-not-allowed disabled:opacity-50"
        >
          {t('feedback.cancel')}
        </button>
        <button
          type="button"
          onClick={handleConfirm}
          disabled={working}
          className="min-h-11 cursor-pointer rounded-lg border-0 bg-[#B3261E] px-6 py-2.5 font-sans text-base font-semibold text-white hover:bg-[#8C1D18] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {confirmLabel}
        </button>
      </div>
    </dialog>
  )
}
