import { useEffect, useState } from 'react'
import Icon from '../Icon'
import { useI18n } from '../../i18n'
import type { TranslationKey } from '../../i18n/vi'
import type { CatalogJob, CatalogStep } from '../../lib/adminDocuments'

export type StageKey = 'upload' | 'extract' | 'clean' | 'sync'
export type RunnableStage = Exclude<StageKey, 'upload'>
type StageState = 'pending' | 'running' | 'done' | 'failed'

const STAGES: { key: StageKey; steps: CatalogStep['key'][]; icon: 'upload' | 'image' | 'doc' | 'sparkles'; live?: boolean }[] = [
  { key: 'upload', steps: ['upload'], icon: 'upload' },
  { key: 'extract', steps: ['render', 'ocr'], icon: 'image' },
  { key: 'clean', steps: ['normalize', 'chunk'], icon: 'doc' },
  { key: 'sync', steps: ['embed', 'sync'], icon: 'sparkles', live: true },
]

const stateClass: Record<StageState, { ring: string; dot: string; pill: string }> = {
  pending: {
    ring: 'border-ctu-cyan',
    dot: 'border-line bg-tint text-muted',
    pill: 'border-line bg-tint text-muted',
  },
  running: {
    ring: 'border-ctu-gold-active',
    dot: 'border-ctu-gold-active bg-[#FFF8E1] text-ctu-navy-dark dark:bg-[#302711] dark:text-[#F2CB74]',
    pill: 'border-ctu-gold-active bg-[#FFF8E1] text-ctu-navy-dark dark:bg-[#302711] dark:text-[#F2CB74]',
  },
  done: {
    ring: 'border-[#2E9E5B]/60',
    dot: 'border-[#2E9E5B] bg-[#E3F4EA] text-[#14602F] dark:bg-[#12301F] dark:text-[#8AD9A8]',
    pill: 'border-[#2E9E5B] bg-[#E3F4EA] text-[#14602F] dark:bg-[#12301F] dark:text-[#8AD9A8]',
  },
  failed: {
    ring: 'border-[#D13434]',
    dot: 'border-[#D13434] bg-[#FDE7E7] text-[#9B1C1C] dark:bg-[#3B1414] dark:text-[#F5A3A3]',
    pill: 'border-[#D13434] bg-[#FDE7E7] text-[#9B1C1C] dark:bg-[#3B1414] dark:text-[#F5A3A3]',
  },
}

const stateLabel: Record<StageState, TranslationKey> = {
  pending: 'admin.doc.step.pending',
  running: 'admin.doc.step.running',
  done: 'admin.doc.step.done',
  failed: 'admin.doc.step.failed',
}

function stageState(job: CatalogJob, steps: CatalogStep['key'][]): StageState {
  const own = job.steps.filter((step) => steps.includes(step.key))
  if (own.some((step) => step.status === 'failed')) return 'failed'
  if (own.some((step) => step.status === 'running')) return 'running'
  if (own.length > 0 && own.every((step) => step.status === 'done' || step.status === 'warning')) return 'done'
  return 'pending'
}

/** Giai đoạn đang chờ thao tác của admin: giai đoạn lỗi đầu tiên, nếu không thì giai đoạn chưa xong đầu tiên. */
export function currentStage(job: CatalogJob): StageKey | null {
  const states = STAGES.map((stage) => ({ key: stage.key, state: stageState(job, stage.steps) }))
  return (states.find((item) => item.state === 'failed') ?? states.find((item) => item.state !== 'done'))?.key ?? null
}

/** Số giây một bước đã chạy: bước đang chạy tính tới `now`, bước đã xong tính theo mốc kết thúc; chưa có mốc thì null. */
function stepSeconds(step: CatalogStep, now: number): number | null {
  if (!step.started_at) return null
  const start = Date.parse(step.started_at)
  const end = step.status === 'running' ? now : step.finished_at ? Date.parse(step.finished_at) : null
  if (Number.isNaN(start) || end === null || Number.isNaN(end)) return null
  return Math.max(0, (end - start) / 1000)
}

/** Tổng thời gian các bước của một giai đoạn (chỉ tính khi mọi bước đã có số liệu). */
function stageSeconds(steps: CatalogStep[], now: number): number | null {
  const parts = steps.map((step) => stepSeconds(step, now))
  if (parts.length === 0 || parts.some((value) => value === null)) return null
  return parts.reduce<number>((sum, value) => sum + (value ?? 0), 0)
}

function formatSeconds(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`
  const minutes = Math.floor(seconds / 60)
  return `${minutes}p ${String(Math.round(seconds - minutes * 60)).padStart(2, '0')}s`
}

/** Đồng hồ nhịp 1 giây, chỉ chạy khi có bước đang chạy. */
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    setNow(Date.now())
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [active])
  return now
}

function Duration({ seconds, running }: { seconds: number | null; running?: boolean }) {
  if (seconds === null) return null
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[11px] font-semibold tabular-nums ${running ? 'bg-[#FFF8E1] text-[#7A5200] dark:bg-[#302711] dark:text-[#F2CB74]' : 'text-muted'}`}
      title="Thời gian chạy"
    >
      {formatSeconds(seconds)}
    </span>
  )
}

function Dot({ state, index }: { state: StageState; index: number }) {
  return (
    <span
      className={`flex size-7 flex-none items-center justify-center rounded-full border-2 sm:size-8 text-xs font-bold ${stateClass[state].dot}`}
      aria-hidden="true"
    >
      {state === 'done' ? '✓' : state === 'failed' ? '!' : state === 'running' ? <span className="size-2.5 animate-pulse rounded-full bg-current" /> : index + 1}
    </span>
  )
}

/** Thanh tóm tắt nằm ngang: nhìn một lần biết đang ở đâu trong 4 giai đoạn. */
export function PipelineSummary({ job }: { job: CatalogJob }) {
  const { t } = useI18n()
  const current = currentStage(job)
  return (
    <ol className="m-0 flex list-none items-center gap-0 overflow-x-auto p-0 pb-1" aria-label={t('admin.doc.reviewFlow')}>
      {STAGES.map((stage, index) => {
        const state = stageState(job, stage.steps)
        return (
          <li key={stage.key} className="flex min-w-0 flex-1 items-center">
            <div className="flex min-w-0 flex-col items-center gap-1.5 px-1 text-center">
              <Dot state={state} index={index} />
              <span
                className={`text-xs font-semibold leading-tight ${stage.key === current ? 'text-heading' : 'text-muted'}`}
                aria-current={stage.key === current ? 'step' : undefined}
              >
                {t(`admin.doc.stage.${stage.key}` as TranslationKey)}
              </span>
            </div>
            {index < STAGES.length - 1 && (
              <span
                aria-hidden="true"
                className={`mb-5 h-0.5 min-w-4 flex-1 rounded-full ${state === 'done' ? 'bg-[#2E9E5B]' : 'bg-line'}`}
              />
            )}
          </li>
        )
      })}
    </ol>
  )
}

function SubStep({ step, now }: { step: CatalogStep; now: number }) {
  const { t } = useI18n()
  const state: StageState = step.status === 'warning' ? 'done' : step.status
  const hasDetails = (step.metrics?.length ?? 0) > 0 || (step.rows?.length ?? 0) > 0 || Boolean(step.preview)
  return (
    <li className="min-w-0 rounded-lg border border-line bg-surface p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`size-2.5 flex-none rounded-full border ${stateClass[state].dot}`} aria-hidden="true" />
        <span className="min-w-0 flex-1 text-sm font-semibold text-heading">{step.title}</span>
        <Duration seconds={stepSeconds(step, now)} running={step.status === 'running'} />
        <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${stateClass[state].pill}`}>
          {t(`admin.doc.step.${step.status}` as TranslationKey)}
        </span>
      </div>
      {step.summary && <p className="mb-0 ml-[18px] mt-1.5 break-words text-xs text-muted">{step.summary}</p>}
      {step.progress && step.progress.total > 0 && (
        <div className="ml-[18px] mt-2">
          <div
            role="progressbar"
            aria-label={step.title}
            aria-valuemin={0}
            aria-valuemax={step.progress.total}
            aria-valuenow={step.progress.done}
            className="h-2 overflow-hidden rounded-full bg-tint"
          >
            <div
              className={`h-full rounded-full transition-[width] ${step.status === 'done' ? 'bg-[#2E9E5B]' : 'bg-ctu-navy dark:bg-ctu-gold-active'}`}
              style={{ width: `${Math.min(100, Math.round((step.progress.done / step.progress.total) * 100))}%` }}
            />
          </div>
          <p className="mb-0 mt-1 text-xs tabular-nums text-muted">
            {step.progress.done}/{step.progress.total} {step.progress.unit}
          </p>
        </div>
      )}
      {step.error && (
        <p role="alert" className="mb-0 ml-[18px] mt-2 break-words text-xs font-semibold text-[#9B1C1C] dark:text-[#F5A3A3]">
          {step.error}
        </p>
      )}
      {hasDetails && (
        <details className="ml-[18px] mt-2 rounded-md border border-line bg-surface">
          <summary className="cursor-pointer px-3 py-2 text-xs font-semibold text-accent">{t('admin.doc.details')}</summary>
          <div className="flex flex-col gap-2 border-t border-line p-3">
            {(step.metrics?.length ?? 0) > 0 && (
              <dl className="m-0 grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2">
                {step.metrics?.map((metric) => (
                  <div key={metric.label} className="min-w-0 text-xs">
                    <dt className="inline text-muted">{metric.label}: </dt>
                    <dd className="m-0 inline break-words font-semibold text-heading">{metric.value}</dd>
                  </div>
                ))}
              </dl>
            )}
            {(step.rows?.length ?? 0) > 0 && (
              <ul className="m-0 flex list-none flex-col gap-1 p-0 text-xs text-heading">
                {step.rows?.map((row, rowIndex) => (
                  <li key={`${row.label}-${rowIndex}`} className="break-words">
                    <span className="font-semibold">{row.label}</span>
                    {row.note && <span className="text-muted"> — {row.note}</span>}
                  </li>
                ))}
              </ul>
            )}
            {step.preview && (
              <pre className="m-0 max-h-56 overflow-auto whitespace-pre-wrap break-words rounded bg-tint p-2 font-mono text-[11px] text-heading">
                {step.preview}
              </pre>
            )}
          </div>
        </details>
      )}
    </li>
  )
}

type Props = {
  job: CatalogJob
  editable: boolean
  syncEnabled: boolean
  action: string
  onRun: (stage: RunnableStage) => void
}

/** Dòng thời gian dọc: mỗi giai đoạn là một thẻ, nút hành động nằm ngay trong giai đoạn đang chờ. */
export default function DocumentPipeline({ job, editable, syncEnabled, action, onRun }: Props) {
  const { t } = useI18n()
  const current = currentStage(job)
  const now = useNow(job.steps.some((step) => step.status === 'running'))

  return (
    <ol className="m-0 flex list-none flex-col p-0">
      {STAGES.map((stage, index) => {
        const state = stageState(job, stage.steps)
        const isCurrent = stage.key === current
        const runnable = stage.key !== 'upload' && isCurrent && editable && (stage.key !== 'sync' || syncEnabled)
        const own = job.steps.filter((step) => stage.steps.includes(step.key))
        const previewText = stage.key === 'extract' ? job.ocr_preview : stage.key === 'clean' ? job.clean_preview : ''
        const last = index === STAGES.length - 1
        return (
          <li key={stage.key} className="flex gap-3">
            <div className="flex flex-col items-center">
              <Dot state={state} index={index} />
              {!last && <span aria-hidden="true" className={`my-1 w-0.5 flex-1 ${state === 'done' ? 'bg-[#2E9E5B]' : 'bg-line'}`} />}
            </div>
            <section
              aria-label={t(`admin.doc.stage.${stage.key}` as TranslationKey)}
              className={`mb-4 min-w-0 flex-1 rounded-xl border-2 bg-surface p-3 sm:p-4 ${
                isCurrent ? `${stateClass[state].ring} shadow-sm` : state === 'done' ? 'border-line' : 'border-line opacity-80'
              } ${last ? 'mb-0' : ''}`}
            >
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
                <Icon name={stage.icon} size={18} className="flex-none text-accent" />
                <h3 className="m-0 min-w-0 flex-1 basis-24 text-sm font-semibold text-heading">
                  {t(`admin.doc.stage.${stage.key}` as TranslationKey)}
                </h3>
                <span className="flex flex-wrap items-center gap-1.5">
                  <Duration seconds={stageSeconds(own, now)} running={state === 'running'} />
                  <span
                    className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${
                      stage.live
                        ? 'border-ctu-gold-active bg-[#FFF8E1] text-[#7A5200] dark:bg-[#302711] dark:text-[#F2CB74]'
                        : 'border-line bg-tint text-muted'
                    }`}
                  >
                    {t(stage.live ? 'admin.doc.liveBadge' : 'admin.doc.draftBadge')}
                  </span>
                  <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${stateClass[state].pill}`}>
                    {t(stateLabel[state])}
                  </span>
                </span>
              </div>
              <p className="mb-0 mt-1.5 text-xs text-muted">{t(`admin.doc.stage.${stage.key}.desc` as TranslationKey)}</p>

              {stage.key === 'sync' && !syncEnabled && (
                <p className="mb-0 mt-2 text-xs font-semibold text-[#7A5200] dark:text-[#F2CB74]">{t('admin.doc.syncDisabled')}</p>
              )}

              {own.length > 0 && stage.key !== 'upload' && (
                <ul className="m-0 mt-3 flex list-none flex-col gap-2 p-0">
                  {own.map((step) => (
                    <SubStep key={step.key} step={step} now={now} />
                  ))}
                </ul>
              )}
              {stage.key === 'upload' && own[0]?.summary && <p className="mb-0 mt-2 break-words text-xs text-heading">{own[0].summary}</p>}

              {previewText && (
                <details className="mt-3 rounded-lg border border-line bg-surface" open={isCurrent && state === 'done'}>
                  <summary className="cursor-pointer px-3 py-2 text-sm font-semibold text-accent">
                    {t(stage.key === 'extract' ? 'admin.doc.ocrPreview' : 'admin.doc.cleanPreview')}
                  </summary>
                  <pre className="m-0 max-h-80 overflow-auto whitespace-pre-wrap break-words border-t border-line bg-tint p-3 font-mono text-xs text-heading">
                    {previewText}
                  </pre>
                </details>
              )}

              {runnable && (
                <button
                  type="button"
                  onClick={() => onRun(stage.key as RunnableStage)}
                  disabled={action !== ''}
                  className="mt-4 min-h-11 w-full cursor-pointer rounded-lg bg-ctu-navy px-5 font-sans text-sm font-semibold text-white hover:bg-ctu-navy-dark disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
                >
                  {action === stage.key
                    ? t(`admin.doc.${stage.key}Running` as TranslationKey)
                    : state === 'failed'
                      ? t('admin.doc.retryStage')
                      : t(`admin.doc.${stage.key}Action` as TranslationKey)}
                </button>
              )}
            </section>
          </li>
        )
      })}
    </ol>
  )
}
