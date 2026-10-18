import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { BarChart, LineChart, Sparkline } from '../../components/admin/Charts'
import Icon from '../../components/Icon'
import { useFormatDate } from '../../hooks/useFormatDate'
import { useI18n } from '../../i18n'
import type { TranslationKey } from '../../i18n/vi'
import { downloadStatsCsv, getStats, type Granularity, type Period, type Stats, type StatsQuery } from '../../lib/adminStats'
import AdminLayout from './AdminLayout'

const PRESETS = ['1', '7', '30', '90', '180', '365', '730', 'custom'] as const
type Preset = (typeof PRESETS)[number]
const GRANULARITIES: Granularity[] = ['auto', 'day', 'week', 'month']
const WEEKDAYS = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN']
const WEEKDAYS_FULL = ['Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy', 'Chủ nhật']

const presetLabel: Record<Preset, TranslationKey> = {
  '1': 'admin.dash.preset.1',
  '7': 'admin.dash.preset.7',
  '30': 'admin.dash.preset.30',
  '90': 'admin.dash.preset.90',
  '180': 'admin.dash.preset.180',
  '365': 'admin.dash.preset.365',
  '730': 'admin.dash.preset.730',
  custom: 'admin.dash.preset.custom',
}
const granLabel: Record<Granularity, TranslationKey> = {
  auto: 'admin.dash.g.auto',
  day: 'admin.dash.g.day',
  week: 'admin.dash.g.week',
  month: 'admin.dash.g.month',
}

const nf = new Intl.NumberFormat('vi-VN')
const number = (n: number) => nf.format(n)
const dmy = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`
const dm = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`
const percent = (n: number) => `${(n * 100).toFixed(n < 0.1 && n > 0 ? 1 : 0)}%`
const localToday = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** Nhãn trục hoành và chú thích theo cách gom (ngày / tuần / tháng). */
function bucketLabel(date: string, end: string, g: Stats['range']['granularity']): { short: string; full: string } {
  if (g === 'month') return { short: `${date.slice(5, 7)}/${date.slice(2, 4)}`, full: `Tháng ${date.slice(5, 7)}/${date.slice(0, 4)}` }
  if (g === 'week') return { short: dm(date), full: `Tuần ${dm(date)} – ${dm(end)}/${end.slice(0, 4)}` }
  return { short: dm(date), full: dmy(date) }
}

type Delta = { kind: 'new' | 'same' | 'up' | 'down'; text: string }

/** So sánh với kỳ trước: phần trăm thay đổi (hoặc "mới" nếu kỳ trước bằng 0). */
function delta(current: number, previous: number): Delta | null {
  if (previous === 0) return current === 0 ? null : { kind: 'new', text: '' }
  const ratio = (current - previous) / previous
  if (Math.abs(ratio) < 0.005) return { kind: 'same', text: '0%' }
  return { kind: ratio > 0 ? 'up' : 'down', text: `${Math.abs(ratio * 100).toFixed(Math.abs(ratio) < 0.1 ? 1 : 0)}%` }
}

function DeltaBadge({ d, previous, label }: { d: Delta | null; previous: string; label: string }) {
  if (!d) return <span className="text-xs text-muted">{label}: {previous}</span>
  const tone =
    d.kind === 'up'
      ? 'bg-[#E3F4EA] text-[#14602F] dark:bg-[#12301F] dark:text-[#8AD9A8]'
      : d.kind === 'down'
        ? 'bg-[#FDE7E7] text-[#9B1C1C] dark:bg-[#3B1414] dark:text-[#F5A3A3]'
        : 'bg-tint text-muted'
  const arrow = d.kind === 'up' || d.kind === 'new' ? '▲' : d.kind === 'down' ? '▼' : '■'
  return (
    <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted">
      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-semibold ${d.kind === 'new' ? 'bg-[#E3F4EA] text-[#14602F] dark:bg-[#12301F] dark:text-[#8AD9A8]' : tone}`}>
        <span aria-hidden="true" className="text-[9px]">{arrow}</span>
        {d.kind === 'new' ? 'mới' : d.text}
      </span>
      <span>{label}: {previous}</span>
    </span>
  )
}

function Card({ title, hint, children, wide, actions }: { title: string; hint?: string; children: ReactNode; wide?: boolean; actions?: ReactNode }) {
  return (
    <section className={`min-w-0 rounded-xl border border-line bg-surface p-5 ${wide ? 'lg:col-span-2' : ''}`}>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h2 className="m-0 text-base">{title}</h2>
          {hint && <p className="m-0 mt-0.5 text-xs text-muted">{hint}</p>}
        </div>
        {actions}
      </div>
      {children}
    </section>
  )
}

function Kpi({
  label, value, current, previous, previousText, spark, compare, vsLabel,
}: {
  label: string; value: string; current: number; previous: number; previousText: string; spark?: number[]; compare: boolean; vsLabel: string
}) {
  return (
    <div className="flex min-w-0 flex-col justify-between gap-2 rounded-xl border border-line bg-surface p-4">
      <div className="text-[13px] text-muted">{label}</div>
      <div className="flex items-end justify-between gap-2">
        <div className="text-2xl font-semibold tabular-nums leading-none text-heading">{value}</div>
        {spark && <Sparkline values={spark} />}
      </div>
      {compare && <DeltaBadge d={delta(current, previous)} previous={previousText} label={vsLabel} />}
    </div>
  )
}

function Mini({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg bg-tint px-4 py-3">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-0.5 text-xl font-semibold tabular-nums text-heading">{value}</div>
      {hint && <div className="text-xs text-muted">{hint}</div>}
    </div>
  )
}

function Skeleton() {
  return (
    <div className="flex flex-col gap-6" aria-hidden="true">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="h-[112px] animate-pulse rounded-xl border border-line bg-tint motion-reduce:animate-none" />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="h-[320px] animate-pulse rounded-xl border border-line bg-tint motion-reduce:animate-none" />
        ))}
      </div>
    </div>
  )
}

export default function AdminDashboard() {
  const { t } = useI18n()
  const formatDate = useFormatDate()
  const [params, setParams] = useSearchParams()

  // Bộ lọc nằm trên URL (?r=30&g=auto hoặc ?r=custom&from=...&to=...) nên tải lại trang / gửi link vẫn giữ nguyên.
  const preset: Preset = (PRESETS as readonly string[]).includes(params.get('r') ?? '') ? (params.get('r') as Preset) : '30'
  const granularity: Granularity = (GRANULARITIES as string[]).includes(params.get('g') ?? '') ? (params.get('g') as Granularity) : 'auto'
  const compare = params.get('cmp') !== '0'
  const customFrom = params.get('from') ?? ''
  const customTo = params.get('to') ?? ''

  const query = useMemo<StatsQuery | null>(() => {
    if (preset === 'custom') return customFrom ? { from: customFrom, to: customTo || undefined, granularity } : null
    return { days: Number(preset), granularity }
  }, [preset, customFrom, customTo, granularity])

  const [draftFrom, setDraftFrom] = useState(customFrom)
  const [draftTo, setDraftTo] = useState(customTo || localToday())
  const [rangeError, setRangeError] = useState('')
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  const setParam = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(changes)) {
      if (v === null || v === '') next.delete(k)
      else next.set(k, v)
    }
    setParams(next, { replace: true })
  }

  const load = useCallback(async () => {
    if (!query) return
    setLoading(true)
    setError(false)
    try {
      setStats(await getStats(query))
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [query])

  useEffect(() => {
    load()
  }, [load])

  const applyCustom = () => {
    if (!draftFrom || !draftTo || draftFrom > draftTo) {
      setRangeError(t('admin.dash.errRange'))
      return
    }
    setRangeError('')
    setParam({ r: 'custom', from: draftFrom, to: draftTo })
  }

  const exportCsv = async () => {
    if (!query || !stats) return
    try {
      await downloadStatsCsv(query, `thong-ke_${stats.range.from}_${stats.range.to}.csv`)
    } catch {
      setError(true)
    }
  }

  const g = stats?.range.granularity ?? 'day'
  const labels = useMemo(() => (stats ? stats.series.map((r) => bucketLabel(r.date, r.end, g)) : []), [stats, g])
  const short = labels.map((l) => l.short)
  const full = labels.map((l) => l.full)
  const col = (key: 'active_users' | 'messages' | 'cached_messages' | 'new_users' | 'conversations' | 'total_users') => stats?.series.map((r) => r[key]) ?? []

  const p = stats?.period
  const prev = stats?.previous
  const vs = t('admin.dash.prev')
  const kpi = (key: keyof Period) => ({ current: (p?.[key] as number) ?? 0, previous: (prev?.[key] as number) ?? 0 })

  return (
    <AdminLayout title={t('admin.dash.title')} subtitle={t('admin.dash.subtitle')}>
      {/* ---- Bộ lọc ---- */}
      <div className="mb-6 flex flex-col gap-4 rounded-xl border border-line bg-surface p-4">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
          <div role="group" aria-label={t('admin.dash.range')} className="flex flex-wrap gap-1.5">
            {PRESETS.map((r) => (
              <button
                key={r}
                type="button"
                aria-pressed={preset === r}
                onClick={() => (r === 'custom' ? setParam({ r, from: customFrom || draftFrom || null, to: customTo || draftTo || null }) : setParam({ r, from: null, to: null }))}
                className={`min-h-11 cursor-pointer rounded-lg border px-3.5 font-sans text-sm ${
                  preset === r ? 'border-ctu-navy bg-ctu-navy font-semibold text-white' : 'border-line bg-surface text-heading hover:bg-tint'
                }`}
              >
                {t(presetLabel[r])}
              </button>
            ))}
          </div>

          <label className="ml-auto flex items-center gap-2 text-sm text-heading">
            {t('admin.dash.granularity')}
            <select
              value={granularity}
              onChange={(e) => setParam({ g: e.target.value === 'auto' ? null : e.target.value })}
              className="min-h-11 rounded-lg border border-field bg-surface px-3 font-sans text-sm text-heading outline-accent"
            >
              {GRANULARITIES.map((x) => (
                <option key={x} value={x}>{t(granLabel[x])}</option>
              ))}
            </select>
          </label>
          <label className="inline-flex min-h-11 cursor-pointer items-center gap-2 text-sm text-heading">
            <input type="checkbox" checked={compare} onChange={(e) => setParam({ cmp: e.target.checked ? null : '0' })} className="size-4 accent-[var(--accent)]" />
            {t('admin.dash.compare')}
          </label>
        </div>

        {preset === 'custom' && (
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-sm text-heading">
              {t('admin.dash.from')}
              <input type="date" value={draftFrom} max={draftTo || localToday()} onChange={(e) => setDraftFrom(e.target.value)} className="min-h-11 rounded-lg border border-field bg-surface px-3 font-sans text-sm text-heading outline-accent" />
            </label>
            <label className="flex flex-col gap-1 text-sm text-heading">
              {t('admin.dash.to')}
              <input type="date" value={draftTo} min={draftFrom || undefined} max={localToday()} onChange={(e) => setDraftTo(e.target.value)} className="min-h-11 rounded-lg border border-field bg-surface px-3 font-sans text-sm text-heading outline-accent" />
            </label>
            <button type="button" onClick={applyCustom} className="min-h-11 cursor-pointer rounded-lg border-0 bg-ctu-navy px-5 font-sans text-sm font-semibold text-white hover:bg-ctu-navy-dark">
              {t('admin.dash.apply')}
            </button>
            {rangeError && <span role="alert" className="text-sm font-semibold text-[#9B1C1C] dark:text-[#F5A3A3]">{rangeError}</span>}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-line pt-3 text-sm">
          {stats ? (
            <p className="m-0 text-heading" aria-live="polite">
              <strong>{dmy(stats.range.from)}</strong> – <strong>{dmy(stats.range.to)}</strong>
              <span className="text-muted"> · {stats.range.days} {t('admin.dash.days')} · {t(granLabel[stats.range.granularity])}</span>
              {compare && (
                <span className="text-muted"> · {t('admin.dash.prevRange')} {dmy(stats.range.previous_from)} – {dmy(stats.range.previous_to)}</span>
              )}
            </p>
          ) : (
            <p className="m-0 text-muted">{preset === 'custom' ? t('admin.dash.pickRange') : t('admin.dash.loading')}</p>
          )}
          <div className="ml-auto flex items-center gap-2">
            {stats && <span className="text-xs text-muted">{t('admin.dash.updated')} {formatDate(stats.generated_at)}</span>}
            <button type="button" onClick={load} disabled={loading || !query} className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border border-line bg-surface px-3 font-sans text-sm text-heading hover:bg-tint disabled:cursor-not-allowed disabled:opacity-60">
              <Icon name="swap" size={16} />
              {t('admin.dash.refresh')}
            </button>
            <button type="button" onClick={exportCsv} disabled={!stats} className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border border-ctu-navy bg-surface px-3 font-sans text-sm font-semibold text-accent hover:bg-tint disabled:cursor-not-allowed disabled:opacity-60">
              <Icon name="upload" size={16} className="rotate-180" />
              {t('admin.dash.export')}
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div role="alert" className="mb-4 flex items-center gap-3 text-sm">
          {t('admin.dash.loadError')}
          <button type="button" onClick={load} className="min-h-11 cursor-pointer rounded-lg border border-ctu-cyan bg-surface px-4 font-sans text-sm text-accent hover:bg-tint">
            {t('admin.doc.retry')}
          </button>
        </div>
      )}

      {!stats && !error && query && <Skeleton />}

      {stats && p && prev && (
        <div className={`flex flex-col gap-6 transition-opacity ${loading ? 'opacity-60' : ''}`} aria-busy={loading}>
          {/* ---- Chỉ số của khoảng đang xem ---- */}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Kpi label={t('admin.dash.k.messages')} value={number(p.messages)} {...kpi('messages')} previousText={number(prev.messages)} spark={col('messages')} compare={compare} vsLabel={vs} />
            <Kpi label={t('admin.dash.k.activeUsers')} value={number(p.active_users)} {...kpi('active_users')} previousText={number(prev.active_users)} spark={col('active_users')} compare={compare} vsLabel={vs} />
            <Kpi label={t('admin.dash.k.newUsers')} value={number(p.new_users)} {...kpi('new_users')} previousText={number(prev.new_users)} spark={col('new_users')} compare={compare} vsLabel={vs} />
            <Kpi label={t('admin.dash.k.conversations')} value={number(p.conversations)} {...kpi('conversations')} previousText={number(prev.conversations)} spark={col('conversations')} compare={compare} vsLabel={vs} />
            <Kpi label={t('admin.dash.k.perUser')} value={String(p.messages_per_active_user)} {...kpi('messages_per_active_user')} previousText={String(prev.messages_per_active_user)} compare={compare} vsLabel={vs} />
            <Kpi label={t('admin.dash.k.cached')} value={percent(p.cached_ratio)} current={p.cached_ratio} previous={prev.cached_ratio} previousText={percent(prev.cached_ratio)} compare={compare} vsLabel={vs} />
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Card wide title={t('admin.dash.chart.activity')} hint={t('admin.dash.chart.activityHint')}>
              <LineChart
                label={t('admin.dash.chart.activity')}
                labels={short}
                titles={full}
                format={number}
                series={[
                  { name: t('admin.dash.messages'), color: '#d99a00', values: col('messages') },
                  { name: t('admin.dash.activeUsers'), color: 'var(--accent)', values: col('active_users') },
                ]}
              />
            </Card>

            <Card title={t('admin.dash.chart.signups')} hint={t('admin.dash.chart.signupsHint')}>
              <BarChart label={t('admin.dash.chart.signups')} labels={short} titles={full} format={number} series={[{ name: t('admin.dash.newUsers'), color: 'var(--accent)', values: col('new_users') }]} />
            </Card>

            <Card title={t('admin.dash.chart.totalUsers')} hint={t('admin.dash.chart.totalUsersHint')}>
              <LineChart label={t('admin.dash.chart.totalUsers')} labels={short} titles={full} format={number} series={[{ name: t('admin.dash.totalUsers'), color: '#2e9e5b', values: col('total_users') }]} />
            </Card>

            <Card title={t('admin.dash.registrations')} hint={t('admin.dash.registrationsHint')}>
              <BarChart
                label={t('admin.dash.registrations')}
                labels={[t('admin.dash.reg.week'), t('admin.dash.reg.month'), t('admin.dash.reg.sixMonths'), t('admin.dash.reg.year')]}
                format={number}
                series={[{ name: t('admin.dash.newUsers'), color: 'var(--accent)', values: [stats.registrations.week, stats.registrations.month, stats.registrations.six_months, stats.registrations.year] }]}
              />
            </Card>

            <Card title={t('admin.dash.chart.cached')} hint={t('admin.dash.chart.cachedHint')}>
              <BarChart
                stacked
                label={t('admin.dash.chart.cached')}
                labels={short}
                titles={full}
                format={number}
                series={[
                  { name: t('admin.dash.free'), color: 'var(--accent)', values: col('messages').map((m, i) => m - col('cached_messages')[i]) },
                  { name: t('admin.dash.suggested'), color: '#d99a00', values: col('cached_messages') },
                ]}
              />
            </Card>

            <Card title={t('admin.dash.hourly')} hint={t('admin.dash.hourlyHint')}>
              <BarChart label={t('admin.dash.hourly')} labels={stats.hourly.map((_, h) => `${h}h`)} titles={stats.hourly.map((_, h) => `${h}:00 – ${h}:59`)} format={number} series={[{ name: t('admin.dash.messages'), color: 'var(--accent)', values: stats.hourly }]} />
            </Card>

            <Card title={t('admin.dash.weekday')}>
              <BarChart label={t('admin.dash.weekday')} labels={WEEKDAYS} titles={WEEKDAYS_FULL} format={number} series={[{ name: t('admin.dash.messages'), color: '#d99a00', values: stats.weekday }]} />
            </Card>
          </div>

          {/* ---- Toàn hệ thống & mức độ gắn bó ---- */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Card title={t('admin.dash.system')}>
              <div className="grid grid-cols-2 gap-3">
                <Mini label={t('admin.dash.totalUsers')} value={number(stats.totals.users)} />
                <Mini label={t('admin.dash.activeAccounts')} value={number(stats.totals.active_accounts)} hint={`${number(stats.totals.users - stats.totals.active_accounts)} ${t('admin.dash.locked')}`} />
                <Mini label={t('admin.dash.admins')} value={number(stats.totals.admins)} />
                <Mini label={t('admin.dash.allMessages')} value={number(stats.totals.messages)} hint={`${number(stats.totals.conversations)} ${t('admin.dash.totalConversations').toLowerCase()}`} />
              </div>
            </Card>

            <Card title={t('admin.dash.engagement')} hint={`${t('admin.dash.engagementHint')} ${dmy(stats.range.to)}`}>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Mini label="DAU" value={number(stats.activity.dau)} hint={t('admin.dash.dau')} />
                <Mini label="WAU" value={number(stats.activity.wau)} hint={t('admin.dash.wau')} />
                <Mini label="MAU" value={number(stats.activity.mau)} hint={t('admin.dash.mau')} />
                <Mini label={t('admin.dash.stickiness')} value={percent(stats.activity.stickiness)} hint="DAU / MAU" />
              </div>
              <dl className="m-0 mt-4 grid grid-cols-1 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
                <div className="flex justify-between gap-3"><dt className="text-muted">{t('admin.dash.f.msgPerDay')}</dt><dd className="m-0 font-semibold tabular-nums text-heading">{p.avg_messages_per_day}</dd></div>
                <div className="flex justify-between gap-3"><dt className="text-muted">{t('admin.dash.f.usersPerDay')}</dt><dd className="m-0 font-semibold tabular-nums text-heading">{p.avg_active_users_per_day}</dd></div>
              </dl>
            </Card>

            <Card wide title={t('admin.dash.topUsers')} hint={t('admin.dash.topUsersHint')}>
              {stats.top_users.length === 0 ? (
                <p className="m-0 text-sm">{t('admin.dash.noUsage')}</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[520px] border-collapse text-sm">
                    <thead>
                      <tr className="border-b border-line text-left text-xs text-muted">
                        <th className="py-2 pr-3 font-normal">#</th>
                        <th className="py-2 pr-3 font-normal">{t('admin.users.col.user')}</th>
                        <th className="py-2 pr-3 text-right font-normal">{t('admin.dash.messages')}</th>
                        <th className="py-2 pr-3 text-right font-normal">{t('admin.dash.activeDays')}</th>
                        <th className="py-2 text-right font-normal">{t('admin.users.col.lastActive')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stats.top_users.map((u, i) => (
                        <tr key={u.email} className="border-b border-line last:border-0">
                          <td className="py-2 pr-3 tabular-nums text-muted">{i + 1}</td>
                          <td className="py-2 pr-3">
                            <Link to={`/admin/users?q=${encodeURIComponent(u.email)}`} className="text-heading no-underline hover:underline" title={t('admin.dash.openUser')}>
                              {u.name || u.email}
                            </Link>
                            <div className="text-xs text-muted">{u.email}</div>
                          </td>
                          <td className="py-2 pr-3 text-right tabular-nums text-heading">{number(u.messages)}</td>
                          <td className="py-2 pr-3 text-right tabular-nums text-heading">{u.active_days}</td>
                          <td className="whitespace-nowrap py-2 text-right text-heading">{formatDate(u.last_active)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </div>
        </div>
      )}
    </AdminLayout>
  )
}
