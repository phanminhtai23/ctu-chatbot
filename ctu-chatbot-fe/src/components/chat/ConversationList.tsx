import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useI18n } from '../../i18n'
import type { Conversation } from '../../lib/conversations'
import Icon from '../Icon'

type Props = {
  conversations: Conversation[]
  state: 'loading' | 'ready' | 'error'
  activeId: string | undefined
  /** Đang nhận câu trả lời: chưa cho chuyển/xoá để khỏi mất câu hỏi đang chờ */
  disabled: boolean
  onRename: (id: string, title: string) => Promise<void>
  onDelete: (conversation: Conversation) => void
  onRetry: () => void
}

const iconButton =
  'inline-flex size-11 flex-none cursor-pointer items-center justify-center rounded-md border-0 bg-transparent text-white hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-40'

export default function ConversationList({
  conversations,
  state,
  activeId,
  disabled,
  onRename,
  onDelete,
  onRetry,
}: Props) {
  const { t } = useI18n()
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [renameError, setRenameError] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editingId) inputRef.current?.select()
  }, [editingId])

  const startEdit = (c: Conversation) => {
    setEditingId(c.id)
    setDraft(c.title)
    setRenameError(false)
  }

  const cancelEdit = () => {
    setEditingId(null)
    setRenameError(false)
  }

  const submit = async (e: FormEvent, c: Conversation) => {
    e.preventDefault()
    const title = draft.trim()
    if (!title || title === c.title) return cancelEdit()
    setSaving(true)
    try {
      await onRename(c.id, title)
      setEditingId(null)
    } catch {
      setRenameError(true)
    } finally {
      setSaving(false)
    }
  }

  if (state === 'loading') return <p className="px-2 text-sm opacity-80">{t('chat.listLoading')}</p>
  if (state === 'error') {
    return (
      <div className="px-2 text-sm">
        <p className="mb-2 mt-0">{t('chat.listError')}</p>
        <button
          type="button"
          onClick={onRetry}
          className="min-h-11 cursor-pointer rounded-lg border border-white/40 bg-transparent px-4 font-sans text-sm text-white hover:bg-white/10"
        >
          {t('chat.listRetry')}
        </button>
      </div>
    )
  }
  if (conversations.length === 0) return <p className="px-2 text-sm opacity-80">{t('chat.listEmpty')}</p>

  return (
    <ul className="m-0 flex list-none flex-col gap-1 p-0">
      {conversations.map((c) => {
        const active = c.id === activeId
        const label = c.title || t('chat.untitled')

        if (editingId === c.id) {
          return (
            <li key={c.id}>
              <form onSubmit={(e) => submit(e, c)} className="flex items-center gap-1 rounded-lg bg-white/15 p-1.5">
                <label htmlFor={`rename-${c.id}`} className="sr-only">{t('chat.renameLabel')}</label>
                <input
                  id={`rename-${c.id}`}
                  ref={inputRef}
                  value={draft}
                  maxLength={200}
                  disabled={saving}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => e.key === 'Escape' && cancelEdit()}
                  aria-invalid={renameError}
                  className="min-h-11 min-w-0 flex-1 rounded-md border border-white/40 bg-ctu-navy-dark px-2 font-sans text-sm text-white outline-ctu-gold-active"
                />
                <button type="submit" disabled={saving} aria-label={t('chat.renameSave')} title={t('chat.renameSave')} className={iconButton}>
                  <Icon name="check" size={18} strokeWidth={2.2} />
                </button>
                <button type="button" onClick={cancelEdit} disabled={saving} aria-label={t('chat.renameCancel')} title={t('chat.renameCancel')} className={iconButton}>
                  <Icon name="close" size={18} />
                </button>
              </form>
              {renameError && <p role="alert" className="mx-2 mb-0 mt-1 text-xs text-[#FFB4B7]">{t('chat.errRename')}</p>}
            </li>
          )
        }

        return (
          <li
            key={c.id}
            className={`group flex items-center rounded-lg hover:bg-white/10 focus-within:bg-white/10 ${
              active ? 'bg-white/15' : ''
            }`}
          >
            <Link
              to={`/chat/${c.id}`}
              aria-current={active ? 'page' : undefined}
              aria-disabled={disabled && !active}
              onClick={(e) => {
                if (disabled && !active) e.preventDefault()
              }}
              title={label}
              className={`min-h-11 min-w-0 flex-1 truncate rounded-lg px-3 py-2.5 text-sm text-white no-underline ${
                active ? 'font-normal' : ''
              } ${disabled && !active ? 'opacity-60' : ''}`}
            >
              {label}
            </Link>
            {/* Nút hiện khi rê chuột/focus, và luôn hiện ở cuộc trò chuyện đang mở (màn hình cảm ứng không có hover). */}
            <span
              className={`flex pr-1 ${active ? '' : 'md:hidden md:group-hover:flex md:group-focus-within:flex'} `}
            >
              <button type="button" onClick={() => startEdit(c)} disabled={disabled} aria-label={`${t('chat.rename')}: ${label}`} title={t('chat.rename')} className={iconButton}>
                <Icon name="pencil" size={16} />
              </button>
              <button type="button" onClick={() => onDelete(c)} disabled={disabled} aria-label={`${t('chat.delete')}: ${label}`} title={t('chat.delete')} className={iconButton}>
                <Icon name="trash" size={16} />
              </button>
            </span>
          </li>
        )
      })}
    </ul>
  )
}
