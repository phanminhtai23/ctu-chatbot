import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { BarChart, LineChart } from '../../components/admin/Charts'
import { useFormatDate } from '../../hooks/useFormatDate'
import { useI18n } from '../../i18n'
import { getStats, type Stats } from '../../lib/adminStats'
import AdminLayout from './AdminLayout'

const RANGES = [7, 30, 90] as const
const WEEKDAYS = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN']

const shortDate = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`
const number = (n: number) => n.toLocaleString('vi-VN')

function Card({ title, children, wide }: { title: string; children: ReactNode; wide?: boolean }) {
  return (
    <section className={`min-w-0 rounded-xl border border-line bg-surface p-5 ${wide ? 'lg:col-span-2' : ''}`}>
      <h2 className="m-0 mb-3 text-base">{title}</h2>
      {children}
    </section>
  )
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="text-[13px] text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums text-heading">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-muted">{hint}</div>}
    </div>
  )
}

export default function AdminDashboard() {
  const { t } = useI18n()
  const formatDate = useFormatDate()
  const [days, setDays] = useState<(typeof RANGES)[number]>(30)
  const [stats, setStats] = useState<Stats | null>(null)
  const [error, setError] = useState(false)

  const load = useCallback(async () => {
    setError(false)
    try {
      setStats(await getStats(days))
    } catch {
      setError(true)
    }
  }, [days])

  useEffect(() => {
    load()
  }, [load])

  const reg = stats?.registrations
  const labels = stats?.usage_daily.map((d) => shortDate(d.date)) ?? []

  return (
    <AdminLayout title={t('admin.dash.title')} subtitle={t('admin.dash.subtitle')}>
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <span className="text-sm text-heading">{t('admin.dash.range')}</span>
        <div role="group" aria-label={t('admin.dash.range')} className="flex gap-1.5">
          {RANGES.map((r) => (
            <button
              key={r}
              type="button"
              aria-pressed={days === r}
              onClick={() => setDays(r)}
              className={`min-h-11 cursor-pointer rounded-lg border px-4 font-sans text-sm ${
                days === r ? 'border-ctu-navy bg-ctu-navy font-semibold text-white' : 'border-line bg-surface text-heading hover:bg-tint'
              }`}
            >
              {r} {t('admin.dash.days')}
            </button>
          ))}
        </div>
        {stats && (
          <span className="ml-auto text-xs text-muted">
            {t('admin.dash.updated')} {formatDate(stats.generated_at)}
          </span>
        )}
      </div>

      {error && (
        <div role="alert" className="mb-4 flex items-center gap-3 text-sm">
          {t('admin.dash.loadError')}
          <button
            type="button"
            onClick={load}
            className="min-h-11 cursor-pointer rounded-lg border border-ctu-cyan bg-surface px-4 font-sans text-sm text-accent hover:bg-tint"
          >
            {t('admin.doc.retry')}
          </button>
        </div>
      )}

      {!stats && !error && <p className="text-sm">{t('admin.dash.loading')}</p>}

      {stats && reg && (
        <div className="flex flex-col gap-6">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Stat label={t('admin.dash.totalUsers')} value={number(stats.totals.users)} hint={`${stats.totals.admins} admin`} />
            <Stat label={t('admin.dash.totalMessages')} value={number(stats.totals.messages)} hint={`${number(stats.totals.messages_today)} ${t('admin.dash.today')}`} />
            <Stat label={t('admin.dash.totalConversations')} value={number(stats.totals.conversations)} />
            <Stat label={t('admin.dash.activeToday')} value={number(stats.totals.active_today)} />
            <Stat label={t('admin.dash.active7')} value={number(stats.totals.active_7d)} />
            <Stat label={t('admin.dash.active30')} value={number(stats.totals.active_30d)} />
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Card title={t('admin.dash.registrations')}>
              <BarChart
                label={t('admin.dash.registrations')}
                data={[
                  { label: t('admin.dash.reg.week'), value: reg.week },
                  { label: t('admin.dash.reg.month'), value: reg.month },
                  { label: t('admin.dash.reg.sixMonths'), value: reg.six_months },
                  { label: t('admin.dash.reg.year'), value: reg.year },
                ]}
              />
            </Card>

            <Card title={`${t('admin.dash.regDaily')} (${days} ${t('admin.dash.days')})`}>
              <LineChart
                label={t('admin.dash.regDaily')}
                labels={stats.registrations_daily.map((d) => shortDate(d.date))}
                series={[{ name: t('admin.dash.newUsers'), color: 'var(--accent)', values: stats.registrations_daily.map((d) => d.count) }]}
              />
            </Card>

            <Card wide title={`${t('admin.dash.usageDaily')} (${days} ${t('admin.dash.days')})`}>
              <LineChart
                label={t('admin.dash.usageDaily')}
                labels={labels}
                series={[
                  { name: t('admin.dash.activeUsers'), color: 'var(--accent)', values: stats.usage_daily.map((d) => d.active_users) },
                  { name: t('admin.dash.messages'), color: '#d99a00', values: stats.usage_daily.map((d) => d.messages) },
                ]}
              />
            </Card>

            <Card title={t('admin.dash.hourly')}>
              <BarChart
                label={t('admin.dash.hourly')}
                data={stats.hourly.map((value, hour) => ({ label: `${hour}h`, value }))}
              />
            </Card>

            <Card title={t('admin.dash.weekday')}>
              <BarChart label={t('admin.dash.weekday')} color="#d99a00" data={stats.weekday.map((value, i) => ({ label: WEEKDAYS[i], value }))} />
            </Card>

            <Card wide title={`${t('admin.dash.frequency')} (${days} ${t('admin.dash.days')})`}>
              <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
                <Stat label={t('admin.dash.f.msgPerDay')} value={String(stats.frequency.avg_messages_per_day)} />
                <Stat label={t('admin.dash.f.usersPerDay')} value={String(stats.frequency.avg_active_users_per_day)} />
                <Stat label={t('admin.dash.f.msgPerUserDay')} value={String(stats.frequency.avg_messages_per_active_user_per_day)} />
                <Stat label={t('admin.dash.f.msgPerUser')} value={String(stats.frequency.avg_messages_per_user)} />
              </div>
              <h3 className="m-0 mb-2 text-sm">{t('admin.dash.topUsers')}</h3>
              {stats.frequency.top_users.length === 0 ? (
                <p className="m-0 text-sm">{t('admin.dash.noUsage')}</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse text-sm">
                    <thead>
                      <tr className="border-b border-line text-left text-xs text-muted">
                        <th className="py-2 pr-3 font-normal">{t('admin.users.col.user')}</th>
                        <th className="py-2 pr-3 text-right font-normal">{t('admin.dash.messages')}</th>
                        <th className="py-2 text-right font-normal">{t('admin.dash.activeDays')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stats.frequency.top_users.map((u) => (
                        <tr key={u.email} className="border-b border-line last:border-0">
                          <td className="py-2 pr-3">
                            <div className="text-heading">{u.name || u.email}</div>
                            <div className="text-xs text-muted">{u.email}</div>
                          </td>
                          <td className="py-2 pr-3 text-right tabular-nums text-heading">{number(u.messages)}</td>
                          <td className="py-2 text-right tabular-nums text-heading">{u.active_days}</td>
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
