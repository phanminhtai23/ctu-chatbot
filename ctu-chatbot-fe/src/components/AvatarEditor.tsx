import { useRef, useState } from 'react'
import { useAuth } from '../auth'
import { useI18n } from '../i18n'
import { defaultAvatar, fileErrorCode, randomAvatar, uploadAvatar } from '../lib/files'
import { fillTemplate, formatBytes } from '../lib/format'
import { fileErrorMessage } from './fileErrors'
import Avatar from './Avatar'
import Icon from './Icon'

const buttonClass =
  'inline-flex min-h-10 min-w-0 cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-field bg-transparent px-2 py-1.5 font-sans text-[13px] font-normal text-heading hover:bg-tint disabled:cursor-not-allowed disabled:opacity-50'

/** Đổi ảnh đại diện: tải ảnh riêng lên hoặc "quay" một ảnh ngẫu nhiên mặc định. */
export default function AvatarEditor({ maxBytes }: { maxBytes: number }) {
  const { t } = useI18n()
  const { user, replaceUser } = useAuth()
  const inputRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!user) return null

  const run = async (action: () => Promise<Parameters<typeof replaceUser>[0]>) => {
    setBusy(true)
    setError(null)
    try {
      replaceUser(await action())
    } catch (err) {
      setError(fileErrorMessage(fileErrorCode(err), t, maxBytes))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mb-5 flex flex-col items-start gap-4 sm:flex-row sm:items-center">
      <Avatar src={user.avatar_url} name={user.name || user.email} className="size-20 text-2xl" />
      <div className="w-full min-w-0 sm:flex-1">
        <div className="grid grid-cols-3 gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => inputRef.current?.click()}
            title={t('files.avatar.upload.hint')}
            aria-label={t('files.avatar.upload.hint')}
            className={buttonClass}
          >
            <Icon name="upload" size={18} className="hidden flex-none sm:block" />
            {t('files.avatar.upload')}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => run(randomAvatar)}
            title={t('files.avatar.random.hint')}
            aria-label={t('files.avatar.random.hint')}
            className={buttonClass}
          >
            <Icon name="sparkles" size={18} className="hidden flex-none sm:block" />
            {t('files.avatar.random')}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => run(defaultAvatar)}
            title={t('files.avatar.default.hint')}
            aria-label={t('files.avatar.default.hint')}
            className={buttonClass}
          >
            <Icon name="swap" size={18} className="hidden flex-none sm:block" />
            {t('files.avatar.default')}
          </button>
        </div>
        <p className="mb-0 mt-2 text-xs">{fillTemplate(t('files.avatar.hint'), { max: formatBytes(maxBytes) })}</p>
        {error && (
          <p role="alert" className="mb-0 mt-1.5 text-sm text-[#8A1216] dark:text-[#FFB4B7]">
            {error}
          </p>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          e.target.value = '' // cho phép chọn lại đúng file vừa chọn
          if (file) run(() => uploadAvatar(file))
        }}
      />
    </div>
  )
}
