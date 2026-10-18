import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { BarChart } from '../../components/admin/Charts'
import Avatar from '../../components/Avatar'
import ConfirmDialog from '../../components/ConfirmDialog'
import Icon from '../../components/Icon'
import { useAuth } from '../../auth'
import { useFormatDate } from '../../hooks/useFormatDate'
import { useI18n } from '../../i18n'
import type { TranslationKey } from '../../i18n/vi'
import { ApiError } from '../../lib/api'
import { formatBytes } from '../../lib/format'
import { getUser, listUsers, updateUser, type AdminUser, type AdminUserDetail, type UserFilters } from '../../lib/adminStats'
import AdminLayout from './AdminLayout'

const PAGE = 15
const selectClass = 'min-h-11 rounded-lg border border-field bg-surface px-3 py-2 font-sans text-[15px] text-heading outline-accent'
const badge = 'inline-block whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold'

const errorKeys: Record<string, TranslationKey> = {
  CANNOT_CHANGE_SELF: 'admin.users.errSelf',
  LAST_ADMIN: 'admin.users.errLastAdmin',
  ADMIN_BY_ENV: 'admin.users.errByEnv',
}

function errorText(err: unknown, t: (k: TranslationKey) => string): string {
  if (err instanceof ApiError) {
    const code = Object.keys(errorKeys).find((k) => err.message.includes(k))
    if (code) return t(errorKeys[code])
  }
  return t('admin.users.errGeneric')
}

function UserAvatar({ user }: { user: AdminUser }) {
  return <Avatar src={user.avatar_url} name={user.name || user.email} className="size-9" />
}

function DetailDialog({ id, onClose }: { id: string | null; onClose: () => void }) {
  const { t } = useI18n()
  const formatDate = useFormatDate()
  const ref = useRef<HTMLDialogElement>(null)
  const [detail, setDetail] = useState<AdminUserDetail | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (id && !dialog.open) dialog.showModal()
    else if (!id && dialog.open) dialog.close()
  }, [id])

  useEffect(() => {
    if (!id) return
    let cancelled = false
    getUser(id)
      .then((d) => !cancelled && (setDetail(d), setFailed(false)))
      .catch(() => !cancelled && setFailed(true))
    return () => {
      cancelled = true
      setDetail(null)
    }
  }, [id])

  return (
    <dialog
      ref={ref}
      aria-labelledby="user-detail-title"
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      className="m-auto max-h-[92vh] w-[calc(100%-32px)] max-w-[600px] overflow-y-auto rounded-2xl border border-line bg-surface p-6 text-muted shadow-[0_24px_60px_rgba(0,0,0,.35)] backdrop:bg-black/50"
    >
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 id="user-detail-title" className="m-0 text-lg">
          {t('admin.users.detail')}
        </h2>
        <button type="button" onClick={onClose} aria-label={t('ref.close')} className="inline-flex size-11 cursor-pointer items-center justify-center rounded-lg border-0 bg-transparent text-heading hover:bg-tint">
          <Icon name="close" />
        </button>
      </div>
      {failed && <p role="alert" className="m-0 text-sm">{t('admin.users.errGeneric')}</p>}
      {id && !detail && !failed && <p className="m-0 text-sm">{t('admin.dash.loading')}</p>}
      {detail && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <UserAvatar user={detail} />
            <div className="min-w-0">
              <div className="break-words font-semibold text-heading">{detail.name || detail.email}</div>
              <div className="break-all text-sm">{detail.email}</div>
            </div>
          </div>
          <dl className="m-0 grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
            {(
              [
                [t('admin.users.col.role'), detail.role === 'admin' ? 'Admin' : t('admin.users.roleUser')],
                [t('admin.users.col.state'), detail.is_active ? t('admin.users.active') : t('admin.users.disabled')],
                [t('admin.users.col.created'), formatDate(detail.created_at)],
                [t('admin.users.col.lastActive'), detail.last_active ? formatDate(detail.last_active) : '—'],
                [t('admin.users.firstActive'), detail.first_active ? formatDate(detail.first_active) : '—'],
                [t('admin.users.col.messages'), String(detail.messages)],
                [t('admin.users.col.conversations'), String(detail.conversations)],
                [t('admin.users.col.storage'), `${formatBytes(detail.storage_bytes)} / ${formatBytes(detail.storage_quota_bytes)}`],
                [t('profile.timezone'), detail.timezone],
              ] as const
            ).map(([label, value]) => (
              <div key={label} className="flex justify-between gap-3">
                <dt>{label}</dt>
                <dd className="m-0 text-right font-semibold text-heading">{value}</dd>
              </div>
            ))}
          </dl>
          <div>
            <h3 className="m-0 mb-1 text-sm">{t('admin.users.daily30')}</h3>
            <BarChart
              label={t('admin.users.daily30')}
              labels={detail.daily.map((d) => `${d.date.slice(8, 10)}/${d.date.slice(5, 7)}`)}
              series={[{ name: t('admin.dash.messages'), color: 'var(--accent)', values: detail.daily.map((d) => d.messages) }]}
            />
          </div>
        </div>
      )}
    </dialog>
  )
}

export default function AdminUsers() {
  const { t } = useI18n()
  const formatDate = useFormatDate()
  const { user: me } = useAuth()
  const [searchParams] = useSearchParams()
  const initialQuery = searchParams.get('q') ?? ''
  const [query, setQuery] = useState(initialQuery)
  const [debounced, setDebounced] = useState(initialQuery.trim())
  const [role, setRole] = useState<UserFilters['role']>('all')
  const [state, setState] = useState<UserFilters['state']>('all')
  const [offset, setOffset] = useState(0)
  const [data, setData] = useState<{ total: number; items: AdminUser[] } | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null)
  const [detailId, setDetailId] = useState<string | null>(null)
  const [toggleTarget, setToggleTarget] = useState<AdminUser | null>(null)
  const [dialogError, setDialogError] = useState<string | null>(null)

  useEffect(() => {
    const id = setTimeout(() => {
      setDebounced(query.trim())
      setOffset(0)
    }, 300)
    return () => clearTimeout(id)
  }, [query])

  const load = useCallback(async () => {
    setLoadError(false)
    try {
      setData(await listUsers({ q: debounced, role, state, limit: PAGE, offset }))
    } catch {
      setLoadError(true)
    }
  }, [debounced, role, state, offset])

  useEffect(() => {
    load()
  }, [load])

  const replaceRow = (row: AdminUser) =>
    setData((d) => (d ? { ...d, items: d.items.map((u) => (u.id === row.id ? { ...u, ...row, messages: u.messages, conversations: u.conversations, last_active: row.last_active ?? u.last_active } : u)) } : d))

  const changeRole = async (u: AdminUser, next: 'user' | 'admin') => {
    setNotice(null)
    try {
      replaceRow(await updateUser(u.id, { role: next }))
      setNotice({ ok: true, text: t('admin.users.roleChanged') })
    } catch (err) {
      setNotice({ ok: false, text: errorText(err, t) })
    }
  }

  const confirmToggle = async () => {
    if (!toggleTarget) return
    setDialogError(null)
    try {
      replaceRow(await updateUser(toggleTarget.id, { is_active: !toggleTarget.is_active }))
      setNotice({ ok: true, text: toggleTarget.is_active ? t('admin.users.disabledDone') : t('admin.users.enabledDone') })
      setToggleTarget(null)
    } catch (err) {
      setDialogError(errorText(err, t))
    }
  }

  const total = data?.total ?? 0
  const from = total === 0 ? 0 : offset + 1
  const to = Math.min(offset + PAGE, total)

  return (
    <AdminLayout title={t('admin.users.title')} subtitle={t('admin.users.subtitle')}>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="min-w-[220px] flex-1">
          <label htmlFor="user-search" className="mb-1.5 block text-sm text-heading">{t('admin.users.search')}</label>
          <input
            id="user-search"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('admin.users.searchHint')}
            className={`${selectClass} box-border w-full`}
          />
        </div>
        <div>
          <label htmlFor="user-role" className="mb-1.5 block text-sm text-heading">{t('admin.users.col.role')}</label>
          <select id="user-role" value={role} onChange={(e) => { setRole(e.target.value as UserFilters['role']); setOffset(0) }} className={selectClass}>
            <option value="all">{t('admin.fb.all')}</option>
            <option value="user">{t('admin.users.roleUser')}</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        <div>
          <label htmlFor="user-state" className="mb-1.5 block text-sm text-heading">{t('admin.users.col.state')}</label>
          <select id="user-state" value={state} onChange={(e) => { setState(e.target.value as UserFilters['state']); setOffset(0) }} className={selectClass}>
            <option value="all">{t('admin.fb.all')}</option>
            <option value="active">{t('admin.users.active')}</option>
            <option value="disabled">{t('admin.users.disabled')}</option>
          </select>
        </div>
      </div>

      {notice && (
        <p role={notice.ok ? 'status' : 'alert'} className={`m-0 mb-3 text-sm font-semibold ${notice.ok ? 'text-[#14602F] dark:text-[#8AD9A8]' : 'text-[#9B1C1C] dark:text-[#F5A3A3]'}`}>
          {notice.text}
        </p>
      )}
      {loadError && (
        <div role="alert" className="mb-3 flex items-center gap-3 text-sm">
          {t('admin.users.loadError')}
          <button type="button" onClick={load} className="min-h-11 cursor-pointer rounded-lg border border-ctu-cyan bg-surface px-4 font-sans text-sm text-accent hover:bg-tint">
            {t('admin.doc.retry')}
          </button>
        </div>
      )}

      <div className="overflow-x-auto rounded-xl border border-line bg-surface">
        <table className="w-full min-w-[960px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs text-muted">
              <th className="px-4 py-3 font-normal">{t('admin.users.col.user')}</th>
              <th className="px-3 py-3 font-normal">{t('admin.users.col.role')}</th>
              <th className="px-3 py-3 font-normal">{t('admin.users.col.state')}</th>
              <th className="px-3 py-3 font-normal">{t('admin.users.col.created')}</th>
              <th className="px-3 py-3 text-right font-normal">{t('admin.users.col.messages')}</th>
              <th className="px-3 py-3 text-right font-normal">{t('admin.users.col.storage')}</th>
              <th className="px-3 py-3 font-normal">{t('admin.users.col.lastActive')}</th>
              <th className="px-4 py-3 text-right font-normal">{t('admin.users.col.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((u) => {
              const isMe = u.id === me?.id
              return (
                <tr key={u.id} className="border-b border-line last:border-0">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <UserAvatar user={u} />
                      <div className="min-w-0">
                        <div className="truncate font-semibold text-heading">{u.name || u.email}{isMe && <span className="ml-2 text-xs font-normal text-muted">({t('admin.users.you')})</span>}</div>
                        <div className="truncate text-xs text-muted">{u.email}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    <select
                      aria-label={`${t('admin.users.col.role')}: ${u.email}`}
                      value={u.role}
                      disabled={isMe || u.admin_by_env}
                      title={u.admin_by_env ? t('admin.users.errByEnv') : undefined}
                      onChange={(e) => changeRole(u, e.target.value as 'user' | 'admin')}
                      className="min-h-9 rounded-md border border-field bg-surface px-2 font-sans text-sm text-heading disabled:cursor-not-allowed disabled:opacity-70"
                    >
                      <option value="user">{t('admin.users.roleUser')}</option>
                      <option value="admin">Admin</option>
                    </select>
                    {u.admin_by_env && <span className="ml-1.5 text-xs text-muted">.env</span>}
                  </td>
                  <td className="px-3 py-3">
                    <span className={`${badge} ${u.is_active ? 'bg-[#E3F4EA] text-[#14602F] dark:bg-[#12301F] dark:text-[#8AD9A8]' : 'bg-[#FDE7E7] text-[#9B1C1C] dark:bg-[#3B1414] dark:text-[#F5A3A3]'}`}>
                      {u.is_active ? t('admin.users.active') : t('admin.users.disabled')}
                    </span>
                  </td>
                  <td className="max-w-[7.5rem] px-3 py-3 text-heading">{formatDate(u.created_at)}</td>
                  <td className="px-3 py-3 text-right tabular-nums text-heading">{u.messages}</td>
                  <td className={`whitespace-nowrap px-3 py-3 text-right tabular-nums ${u.storage_bytes >= u.storage_quota_bytes * 0.9 ? 'font-semibold text-[#B42318] dark:text-[#F5A3A3]' : 'text-heading'}`} title={`${formatBytes(u.storage_bytes)} / ${formatBytes(u.storage_quota_bytes)}`}>
                    {formatBytes(u.storage_bytes)}
                  </td>
                  <td className="max-w-[7.5rem] px-3 py-3 text-heading">{u.last_active ? formatDate(u.last_active) : '—'}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    <button type="button" onClick={() => setDetailId(u.id)} className="mr-2 min-h-9 cursor-pointer rounded-md border border-line bg-surface px-3 font-sans text-[13px] text-accent hover:bg-tint">
                      {t('admin.users.view')}
                    </button>
                    <button
                      type="button"
                      disabled={isMe}
                      onClick={() => { setDialogError(null); setToggleTarget(u) }}
                      className={`min-h-9 cursor-pointer rounded-md border px-3 font-sans text-[13px] disabled:cursor-not-allowed disabled:opacity-50 ${u.is_active ? 'border-[#D13434] bg-surface text-[#9B1C1C] hover:bg-[#FDE7E7] dark:text-[#F5A3A3] dark:hover:bg-[#3B1414]' : 'border-ctu-navy bg-ctu-navy text-white hover:bg-ctu-navy-dark'}`}
                    >
                      {u.is_active ? t('admin.users.disable') : t('admin.users.enable')}
                    </button>
                  </td>
                </tr>
              )
            })}
            {data && data.items.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center">{t('admin.users.empty')}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm">
        <span>{from}–{to} / {total} {t('admin.users.accounts')}</span>
        <div className="flex gap-2">
          <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))} className="min-h-11 cursor-pointer rounded-lg border border-line bg-surface px-4 font-sans text-sm text-heading hover:bg-tint disabled:cursor-not-allowed disabled:opacity-50">
            {t('admin.users.prev')}
          </button>
          <button type="button" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)} className="min-h-11 cursor-pointer rounded-lg border border-line bg-surface px-4 font-sans text-sm text-heading hover:bg-tint disabled:cursor-not-allowed disabled:opacity-50">
            {t('admin.users.next')}
          </button>
        </div>
      </div>

      <DetailDialog id={detailId} onClose={() => setDetailId(null)} />
      <ConfirmDialog
        open={toggleTarget != null}
        title={toggleTarget?.is_active ? t('admin.users.disableTitle') : t('admin.users.enableTitle')}
        message={`${toggleTarget?.email ?? ''} — ${toggleTarget?.is_active ? t('admin.users.disableMsg') : t('admin.users.enableMsg')}`}
        confirmLabel={toggleTarget?.is_active ? t('admin.users.disable') : t('admin.users.enable')}
        error={dialogError}
        onConfirm={confirmToggle}
        onCancel={() => setToggleTarget(null)}
      />
    </AdminLayout>
  )
}
