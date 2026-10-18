import { useI18n } from '../../i18n'
import type { TranslationKey } from '../../i18n/vi'
import type { IngestJob, IngestStep, JobStatus, RowStatus, StepStatus } from '../../lib/adminDocuments'
import Icon from '../Icon'

export const fill = (template: string, vars: Record<string, string | number>) =>
  template.replace(/\{(\w+)\}/g, (_, key: string) => String(vars[key] ?? ''))

const stepLabel: Record<StepStatus, TranslationKey> = {
  pending: 'admin.doc.step.pending',
  running: 'admin.doc.step.running',
  done: 'admin.doc.step.done',
  warning: 'admin.doc.step.warning',
  failed: 'admin.doc.step.failed',
  skipped: 'admin.doc.step.skipped',
}

const badgeClass: Record<StepStatus, string> = {
  pending: 'bg-tint text-muted border border-line',
  running: 'bg-ctu-gold-active text-ctu-navy-dark',
  done: 'bg-[#E3F4EA] text-[#14602F] dark:bg-[#12301F] dark:text-[#8AD9A8]',
  warning: 'bg-[#FFF3D6] text-[#7A5200] dark:bg-[#3A2D0B] dark:text-[#F2CB74]',
  failed: 'bg-[#FDE7E7] text-[#9B1C1C] dark:bg-[#3B1414] dark:text-[#F5A3A3]',
  skipped: 'bg-tint text-muted border border-line',
}

const circleClass: Record<StepStatus, string> = {
  pending: 'border-line bg-surface text-muted',
  running: 'border-ctu-gold-active bg-surface text-ctu-navy',
  done: 'border-[#2E9E5B] bg-[#2E9E5B] text-white',
  warning: 'border-[#D99A00] bg-[#D99A00] text-white',
  failed: 'border-[#D13434] bg-[#D13434] text-white',
  skipped: 'border-line bg-tint text-muted',
}

const rowDot: Record<RowStatus, string> = {
  ok: 'bg-[#2E9E5B]',
  warn: 'bg-[#D99A00]',
  fail: 'bg-[#D13434]',
  info: 'bg-ctu-cyan',
}

function StepCircle({ status, index }: { status: StepStatus; index: number }) {
  return (
    <span
      className={`flex size-8 flex-none items-center justify-center rounded-full border-2 text-sm font-semibold ${circleClass[status]}`}
    >
      {status === 'running' ? (
        <span className="size-4 animate-spin rounded-full border-2 border-ctu-gold-active border-t-transparent motion-reduce:animate-none" />
      ) : status === 'done' ? (
        <Icon name="check" size={16} strokeWidth={2.6} />
      ) : status === 'warning' ? (
        <Icon name="warn" size={15} strokeWidth={2.4} />
      ) : status === 'failed' ? (
        <Icon name="close" size={15} strokeWidth={2.6} />
      ) : status === 'skipped' ? (
        <Icon name="minus" size={15} />
      ) : (
        index + 1
      )}
    </span>
  )
}

function seconds(step: IngestStep): number | null {
  if (!step.started_at) return null
  const end = step.finished_at ? new Date(step.finished_at).getTime() : Date.now()
  return Math.max(0, Math.round((end - new Date(step.started_at).getTime()) / 1000))
}

function StepBody({ step }: { step: IngestStep }) {
  const { t } = useI18n()
  const hasDetails = step.metrics.length > 0 || step.rows.length > 0 || step.preview
  return (
    <div className="min-w-0 flex-1 pb-6">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h3 className="m-0 text-[15px] font-semibold text-heading">{step.title}</h3>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${badgeClass[step.status]}`}>
          {t(stepLabel[step.status])}
        </span>
        {seconds(step) != null && step.status !== 'pending' && (
          <span className="text-xs tabular-nums text-muted">{fill(t('admin.doc.took'), { seconds: seconds(step) ?? 0 })}</span>
        )}
      </div>

      {step.progress && step.status === 'running' && (
        <div className="mt-2 max-w-md">
          <div
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={step.progress.total}
            aria-valuenow={step.progress.done}
            className="h-2 overflow-hidden rounded-full bg-tint"
          >
            <div
              className="h-full rounded-full bg-ctu-navy transition-[width] duration-300"
              style={{ width: `${Math.round((step.progress.done / Math.max(1, step.progress.total)) * 100)}%` }}
            />
          </div>
          <span className="text-xs tabular-nums text-muted">
            {step.progress.done}/{step.progress.total} {step.progress.unit}
          </span>
        </div>
      )}

      {step.summary && <p className="m-0 mt-1.5 text-sm text-heading">{step.summary}</p>}
      {step.error && (
        <p role="alert" className="m-0 mt-1.5 break-words text-sm font-semibold text-[#9B1C1C] dark:text-[#F5A3A3]">
          {step.error}
        </p>
      )}

      {hasDetails && (
        <details className="mt-2 rounded-lg border border-line bg-surface" open={step.status === 'failed' || step.status === 'warning'}>
          <summary className="cursor-pointer select-none px-3 py-2 text-[13px] text-accent">{t('admin.doc.details')}</summary>
          <div className="flex flex-col gap-3 border-t border-line px-3 py-3">
            {step.metrics.length > 0 && (
              <dl className="m-0 grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-2">
                {step.metrics.map((m) => (
                  <div key={m.label} className="flex items-baseline justify-between gap-3 text-[13px]">
                    <dt className="text-muted">{m.label}</dt>
                    <dd className="m-0 break-all text-right font-semibold tabular-nums text-heading">{m.value}</dd>
                  </div>
                ))}
              </dl>
            )}
            {step.rows.length > 0 && (
              <ul className="m-0 flex max-h-72 list-none flex-col gap-1.5 overflow-auto p-0">
                {step.rows.map((r, i) => (
                  <li key={`${r.label}-${i}`} className="flex items-start gap-2 text-[13px]">
                    <span className={`mt-1.5 size-2 flex-none rounded-full ${rowDot[r.status]}`} aria-hidden="true" />
                    <span className="min-w-0 flex-1 break-words">
                      <span className="whitespace-pre text-heading">{r.label}</span>
                      {r.note && <span className="text-muted"> — {r.note}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {step.preview && (
              <div>
                <div className="mb-1 text-xs text-muted">{t('admin.doc.preview')}</div>
                <pre className="m-0 max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-md bg-tint p-3 font-mono text-xs text-heading">
                  {step.preview}
                </pre>
              </div>
            )}
          </div>
        </details>
      )}
    </div>
  )
}

const bannerClass: Record<JobStatus, string> = {
  running: 'border-ctu-gold-active bg-[#FFF8DC] text-[#5C4500] dark:bg-[#33290A] dark:text-[#F2D98A]',
  activated: 'border-[#2E9E5B] bg-[#E3F4EA] text-[#14602F] dark:bg-[#12301F] dark:text-[#8AD9A8]',
  rejected: 'border-[#D99A00] bg-[#FFF3D6] text-[#7A5200] dark:bg-[#3A2D0B] dark:text-[#F2CB74]',
  failed: 'border-[#D13434] bg-[#FDE7E7] text-[#9B1C1C] dark:bg-[#3B1414] dark:text-[#F5A3A3]',
}

export const jobLabel: Record<JobStatus, TranslationKey> = {
  running: 'admin.doc.job.running',
  activated: 'admin.doc.job.activated',
  rejected: 'admin.doc.job.rejected',
  failed: 'admin.doc.job.failed',
}

export const jobShortLabel: Record<JobStatus, TranslationKey> = {
  running: 'admin.doc.job.short.running',
  activated: 'admin.doc.job.short.activated',
  rejected: 'admin.doc.job.short.rejected',
  failed: 'admin.doc.job.short.failed',
}

export const jobBadgeClass: Record<JobStatus, string> = {
  running: badgeClass.running,
  activated: badgeClass.done,
  rejected: badgeClass.warning,
  failed: badgeClass.failed,
}

export default function IngestFlow({ job }: { job: IngestJob }) {
  const { t } = useI18n()
  return (
    <div>
      <div role="status" className={`mb-5 rounded-lg border px-4 py-3 text-sm font-semibold ${bannerClass[job.status]}`}>
        {t(jobLabel[job.status])}
        <span className="ml-2 font-normal opacity-80">
          · {t('admin.doc.file')}: {job.filename}
        </span>
      </div>
      <ol className="m-0 list-none p-0">
        {job.steps.map((step, index) => (
          <li key={step.key} className="flex gap-4">
            <div className="flex flex-col items-center">
              <StepCircle status={step.status} index={index} />
              {index < job.steps.length - 1 && (
                <span
                  className={`mt-1 w-0.5 flex-1 ${step.status === 'done' || step.status === 'warning' ? 'bg-[#2E9E5B]' : 'bg-line'}`}
                  aria-hidden="true"
                />
              )}
            </div>
            <StepBody step={step} />
          </li>
        ))}
      </ol>
    </div>
  )
}
