import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { useI18n } from '../i18n'
import type { TranslationKey } from '../i18n/vi'
import {
  addPerson,
  deleteLink,
  getShares,
  putLink,
  removePerson,
  shareErrorCode,
  shareUrl,
  suggestPeople,
  updatePerson,
  type ShareState,
  type SharePermission,
  type Suggestion,
} from '../lib/shares'
import Icon from './Icon'

const errorKeys: Record<string, TranslationKey> = {
  INVALID_EMAIL: 'share.errInvalidEmail',
  CANNOT_SHARE_WITH_SELF: 'share.errSelf',
  EMAIL_NOT_ALLOWED: 'share.errNotAllowed',
}

const selectClass =
  'min-h-11 rounded-lg border border-field bg-surface px-3 py-2 font-sans text-sm text-heading outline-accent'

function PermissionSelect({
  value,
  onChange,
  label,
  compact,
}: {
  value: SharePermission
  onChange: (value: SharePermission) => void
  label: string
  compact?: boolean
}) {
  const { t } = useI18n()
  return (
    <select
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value as SharePermission)}
      className={`${selectClass} ${compact ? 'min-h-9 px-2 py-1' : ''}`}
    >
      <option value="view">{t('share.perm.view')}</option>
      <option value="chat">{t('share.perm.chat')}</option>
    </select>
  )
}

function Body({ conversationId }: { conversationId: string }) {
  const { t } = useI18n()
  const [state, setState] = useState<ShareState | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [email, setEmail] = useState('')
  const [permission, setPermission] = useState<SharePermission>('view')
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])
  const [active, setActive] = useState(-1)
  const [inviting, setInviting] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [copied, setCopied] = useState(false)
  const [linkBusy, setLinkBusy] = useState(false)

  const load = useCallback(async () => {
    setLoadError(false)
    try {
      setState(await getShares(conversationId))
    } catch {
      setLoadError(true)
    }
  }, [conversationId])

  useEffect(() => {
    load()
  }, [load])

  // Gợi ý người dùng khi gõ email/tên (đợi 250ms sau lần gõ cuối).
  useEffect(() => {
    const q = email.trim()
    if (q.length < 2) {
      setSuggestions([])
      return
    }
    let cancelled = false
    const id = setTimeout(() => {
      suggestPeople(q)
        .then((items) => {
          if (cancelled) return
          const shared = new Set(state?.people.map((p) => p.email) ?? [])
          setSuggestions(items.filter((s) => !shared.has(s.email)))
          setActive(-1)
        })
        .catch(() => !cancelled && setSuggestions([]))
    }, 250)
    return () => {
      cancelled = true
      clearTimeout(id)
    }
  }, [email, state])

  const invite = async (address: string) => {
    const value = address.trim()
    if (!value || inviting) return
    setInviting(true)
    setError('')
    setNotice('')
    try {
      const person = await addPerson(conversationId, value, permission)
      setState((s) => (s ? { ...s, people: [...s.people.filter((p) => p.id !== person.id), person] } : s))
      setEmail('')
      setSuggestions([])
      setNotice(`${t('share.invited')} ${person.email}`)
    } catch (err) {
      const key = errorKeys[shareErrorCode(err)]
      setError(key ? t(key) : t('share.errGeneric'))
    } finally {
      setInviting(false)
    }
  }

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown' && suggestions.length) {
      e.preventDefault()
      setActive((i) => (i + 1) % suggestions.length)
    } else if (e.key === 'ArrowUp' && suggestions.length) {
      e.preventDefault()
      setActive((i) => (i <= 0 ? suggestions.length - 1 : i - 1))
    } else if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
      e.preventDefault()
      invite(active >= 0 ? suggestions[active].email : email)
    } else if (e.key === 'Escape' && suggestions.length) {
      e.stopPropagation()
      setSuggestions([])
    }
  }

  const changePerson = async (id: string, next: SharePermission) => {
    setError('')
    try {
      const updated = await updatePerson(conversationId, id, next)
      setState((s) => (s ? { ...s, people: s.people.map((p) => (p.id === id ? updated : p)) } : s))
    } catch {
      setError(t('share.errGeneric'))
    }
  }

  const remove = async (id: string) => {
    setError('')
    try {
      await removePerson(conversationId, id)
      setState((s) => (s ? { ...s, people: s.people.filter((p) => p.id !== id) } : s))
    } catch {
      setError(t('share.errGeneric'))
    }
  }

  const toggleLink = async (on: boolean) => {
    setLinkBusy(true)
    setError('')
    try {
      if (on) {
        const link = await putLink(conversationId, 'view')
        setState((s) => (s ? { ...s, link } : s))
      } else {
        await deleteLink(conversationId)
        setState((s) => (s ? { ...s, link: null } : s))
      }
    } catch {
      setError(t('share.errGeneric'))
    } finally {
      setLinkBusy(false)
    }
  }

  const changeLink = async (next: SharePermission, regenerate = false) => {
    setLinkBusy(true)
    setError('')
    try {
      const link = await putLink(conversationId, next, regenerate)
      setState((s) => (s ? { ...s, link } : s))
      if (regenerate) setNotice(t('share.regenerated'))
    } catch {
      setError(t('share.errGeneric'))
    } finally {
      setLinkBusy(false)
    }
  }

  const copy = async () => {
    if (!state?.link) return
    try {
      await navigator.clipboard.writeText(shareUrl(state.link.token))
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      document.getElementById('share-link-input')?.focus()
      ;(document.getElementById('share-link-input') as HTMLInputElement | null)?.select()
    }
  }

  if (loadError)
    return (
      <div role="alert" className="flex items-center gap-3 text-sm">
        {t('share.errLoad')}
        <button type="button" onClick={load} className="min-h-11 cursor-pointer rounded-lg border border-ctu-cyan bg-surface px-4 font-sans text-sm text-accent hover:bg-tint">
          {t('admin.doc.retry')}
        </button>
      </div>
    )
  if (!state) return <p className="m-0 text-sm">{t('admin.dash.loading')}</p>

  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="share-invite">
        <h3 id="share-invite" className="m-0 mb-2 text-base">{t('share.inviteTitle')}</h3>
        <div className="flex flex-wrap gap-2">
          <div className="relative min-w-[200px] flex-1">
            <input
              id="share-email"
              type="text"
              inputMode="email"
              autoComplete="off"
              role="combobox"
              aria-expanded={suggestions.length > 0}
              aria-controls="share-suggestions"
              aria-label={t('share.emailLabel')}
              aria-activedescendant={active >= 0 ? `share-sug-${active}` : undefined}
              value={email}
              onChange={(e) => {
                setEmail(e.target.value)
                setError('')
                setNotice('')
              }}
              onKeyDown={onKeyDown}
              placeholder={t('share.emailPlaceholder')}
              className="box-border min-h-11 w-full rounded-lg border border-field bg-surface px-3.5 py-2 font-sans text-[15px] text-heading outline-accent"
            />
            {suggestions.length > 0 && (
              <ul
                id="share-suggestions"
                role="listbox"
                className="absolute left-0 right-0 top-full z-10 m-0 mt-1 max-h-56 list-none overflow-auto rounded-lg border border-line bg-surface p-1 shadow-[0_8px_24px_rgba(0,0,0,.18)]"
              >
                {suggestions.map((s, i) => (
                  <li
                    key={s.email}
                    id={`share-sug-${i}`}
                    role="option"
                    aria-selected={i === active}
                    onMouseDown={(e) => {
                      e.preventDefault()
                      invite(s.email)
                    }}
                    className={`flex cursor-pointer flex-col rounded-md px-3 py-2 text-sm ${i === active ? 'bg-tint' : 'hover:bg-tint'}`}
                  >
                    <span className="text-heading">{s.name || s.email}</span>
                    {s.name && <span className="text-xs text-muted">{s.email}</span>}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <PermissionSelect value={permission} onChange={setPermission} label={t('share.permLabel')} />
          <button
            type="button"
            onClick={() => invite(email)}
            disabled={inviting || !email.trim()}
            className="min-h-11 cursor-pointer rounded-lg border-0 bg-ctu-navy px-5 font-sans text-sm font-semibold text-white hover:bg-ctu-navy-dark disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t('share.invite')}
          </button>
        </div>
        <p className="m-0 mt-2 text-xs text-muted">{t('share.inviteHint')}</p>
        {error && <p role="alert" className="m-0 mt-2 text-sm font-semibold text-[#9B1C1C] dark:text-[#F5A3A3]">{error}</p>}
        {notice && <p role="status" className="m-0 mt-2 text-sm font-semibold text-[#14602F] dark:text-[#8AD9A8]">{notice}</p>}
      </section>

      <section aria-labelledby="share-people">
        <h3 id="share-people" className="m-0 mb-2 text-base">{t('share.peopleTitle')}</h3>
        {state.people.length === 0 ? (
          <p className="m-0 text-sm">{t('share.peopleEmpty')}</p>
        ) : (
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {state.people.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-3 rounded-lg border border-line px-3 py-2">
                <span className="flex size-9 flex-none items-center justify-center rounded-full bg-ctu-cyan text-sm font-semibold text-ctu-navy-dark">
                  {(p.name || p.email).charAt(0).toUpperCase()}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-heading">{p.name || p.email}</span>
                  <span className="block truncate text-xs text-muted">
                    {p.name ? p.email : ''}
                    {!p.registered && ` ${p.name ? '· ' : ''}${t('share.notRegistered')}`}
                  </span>
                </span>
                <PermissionSelect compact value={p.permission} onChange={(v) => changePerson(p.id, v)} label={`${t('share.permLabel')}: ${p.email}`} />
                <button
                  type="button"
                  onClick={() => remove(p.id)}
                  aria-label={`${t('share.remove')}: ${p.email}`}
                  title={t('share.remove')}
                  className="inline-flex size-9 cursor-pointer items-center justify-center rounded-lg border-0 bg-transparent text-heading hover:bg-tint"
                >
                  <Icon name="close" size={18} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="share-link" className="rounded-xl border border-line p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 id="share-link" className="m-0 text-base">{t('share.linkTitle')}</h3>
            <p className="m-0 mt-1 text-xs text-muted">{t('share.linkHint')}</p>
          </div>
          <label className="inline-flex min-h-11 cursor-pointer items-center gap-2 text-sm text-heading">
            <input
              type="checkbox"
              role="switch"
              checked={state.link !== null}
              disabled={linkBusy}
              onChange={(e) => toggleLink(e.target.checked)}
              className="size-5 accent-[var(--accent)]"
            />
            {state.link ? t('share.linkOn') : t('share.linkOff')}
          </label>
        </div>
        {state.link && (
          <div className="mt-3 flex flex-col gap-3">
            <div className="flex flex-wrap gap-2">
              <input
                id="share-link-input"
                readOnly
                value={shareUrl(state.link.token)}
                aria-label={t('share.linkTitle')}
                onFocus={(e) => e.currentTarget.select()}
                className="box-border min-h-11 min-w-[200px] flex-1 rounded-lg border border-field bg-tint px-3 font-mono text-xs text-heading"
              />
              <button
                type="button"
                onClick={copy}
                className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border border-ctu-navy bg-surface px-4 font-sans text-sm font-semibold text-accent hover:bg-tint"
              >
                <Icon name={copied ? 'check' : 'clip'} size={16} />
                {copied ? t('share.copied') : t('share.copy')}
              </button>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-sm text-heading">{t('share.linkCan')}</span>
              <PermissionSelect value={state.link.permission} onChange={(v) => changeLink(v)} label={t('share.permLabel')} />
              <button
                type="button"
                onClick={() => changeLink(state.link!.permission, true)}
                disabled={linkBusy}
                className="ml-auto min-h-9 cursor-pointer rounded-md border border-line bg-surface px-3 font-sans text-[13px] text-accent hover:bg-tint disabled:cursor-not-allowed disabled:opacity-60"
              >
                {t('share.regenerate')}
              </button>
            </div>
            <p className="m-0 text-xs text-muted">
              {state.link.permission === 'chat' ? t('share.linkChatHint') : t('share.linkViewHint')}
            </p>
          </div>
        )}
      </section>
    </div>
  )
}

type Props = { open: boolean; conversationId: string | null; onClose: () => void }

/** Hộp thoại chia sẻ cuộc trò chuyện: mời theo email (có gợi ý), đặt quyền xem / chat tiếp, bật liên kết công khai. */
export default function ShareDialog({ open, conversationId, onClose }: Props) {
  const { t } = useI18n()
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    else if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      aria-labelledby="share-dialog-title"
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      className="m-auto max-h-[92vh] w-[calc(100%-32px)] max-w-[580px] overflow-y-auto rounded-2xl border border-line bg-surface p-6 text-muted shadow-[0_24px_60px_rgba(0,0,0,.35)] backdrop:bg-black/50"
    >
      <div className="mb-5 flex items-center justify-between gap-3">
        <h2 id="share-dialog-title" className="m-0 text-xl">{t('share.title')}</h2>
        <button type="button" onClick={onClose} aria-label={t('ref.close')} className="inline-flex size-11 cursor-pointer items-center justify-center rounded-lg border-0 bg-transparent text-heading hover:bg-tint">
          <Icon name="close" />
        </button>
      </div>
      {open && conversationId && <Body key={conversationId} conversationId={conversationId} />}
    </dialog>
  )
}
