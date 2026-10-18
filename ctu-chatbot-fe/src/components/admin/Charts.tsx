import { useEffect, useRef, useState, type MouseEvent, type ReactNode } from 'react'

/**
 * Biểu đồ SVG tự vẽ (không thêm thư viện): cột, cột chồng, đường và đường nhỏ (sparkline). Bề rộng lấy theo khung chứa
 * nên chữ luôn đúng cỡ; màu theo biến theme nên đúng cả chế độ sáng/tối; rê chuột (hoặc Tab tới điểm) hiện chú thích.
 * Mỗi biểu đồ kèm bảng ẩn (sr-only) cho trình đọc màn hình.
 */

const H = 240
const PAD = { top: 18, right: 14, bottom: 30, left: 44 }

/** Đo bề rộng khung chứa để vẽ SVG đúng kích thước thật. */
function useWidth(initial = 640) {
  const ref = useRef<HTMLElement>(null)
  const [width, setWidth] = useState(initial)
  useEffect(() => {
    const el = ref.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(180, Math.floor(entry.contentRect.width))))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  return [ref, width] as const
}

/** Trục tung chia 4 khoảng đều nhau, mỗi khoảng là 1/2/5 × 10^k nên nhãn luôn là số nguyên đẹp. */
function scale(maxValue: number) {
  const raw = Math.max(1, maxValue) / 4
  const pow = 10 ** Math.floor(Math.log10(raw))
  const n = raw / pow
  const step = Math.max(1, (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * pow) // đếm số lượt nên bước là số nguyên
  return { step, max: step * 4 }
}

const compact = (n: number) => (n >= 10_000 ? `${Math.round(n / 1000)}k` : n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n))

function Grid({ width, step }: { width: number; step: number }) {
  return (
    <>
      {[0, 1, 2, 3, 4].map((i) => {
        const y = PAD.top + (H - PAD.top - PAD.bottom) * (1 - i / 4)
        return (
          <g key={i}>
            <line x1={PAD.left} x2={width - PAD.right} y1={y} y2={y} stroke="var(--line)" strokeWidth={1} />
            <text x={PAD.left - 8} y={y + 4} textAnchor="end" fontSize={11} fill="var(--muted)">
              {compact(Math.round(step * i))}
            </text>
          </g>
        )
      })}
    </>
  )
}

export type Series = { name: string; color: string; values: number[] }

type TooltipProps = { x: number; width: number; title: string; rows: { name: string; color: string; value: string }[] }

function Tooltip({ x, width, title, rows }: TooltipProps) {
  const flip = x > width * 0.6
  return (
    <div
      role="tooltip"
      className="pointer-events-none absolute top-2 z-10 min-w-[140px] rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-[0_8px_24px_rgba(0,0,0,.18)]"
      style={flip ? { right: Math.max(8, width - x + 12) } : { left: Math.min(width - 150, x + 12) }}
    >
      <div className="mb-1 font-semibold text-heading">{title}</div>
      {rows.map((r) => (
        <div key={r.name} className="flex items-center justify-between gap-4">
          <span className="inline-flex items-center gap-1.5 text-muted">
            <span className="inline-block size-2 rounded-full" style={{ background: r.color }} />
            {r.name}
          </span>
          <span className="font-semibold tabular-nums text-heading">{r.value}</span>
        </div>
      ))}
    </div>
  )
}

function Legend({ series }: { series: { name: string; color: string }[] }) {
  return (
    <div className="mt-1 flex flex-wrap gap-4 text-xs text-muted">
      {series.map((s) => (
        <span key={s.name} className="inline-flex items-center gap-1.5">
          <span className="inline-block size-2.5 rounded-sm" style={{ background: s.color }} />
          {s.name}
        </span>
      ))}
    </div>
  )
}

function DataTable({ caption, labels, series }: { caption: string; labels: string[]; series: Series[] }) {
  return (
    <table className="sr-only">
      <caption>{caption}</caption>
      <thead>
        <tr>
          <th scope="col" />
          {series.map((s) => (
            <th key={s.name} scope="col">
              {s.name}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {labels.map((l, i) => (
          <tr key={i}>
            <th scope="row">{l}</th>
            {series.map((s) => (
              <td key={s.name}>{s.values[i]}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

type CommonProps = {
  /** Nhãn ngắn dưới trục hoành */
  labels: string[]
  /** Tiêu đề đầy đủ của chú thích khi rê chuột (mặc định dùng `labels`) */
  titles?: string[]
  series: Series[]
  label: string
  /** Định dạng giá trị trong chú thích */
  format?: (n: number) => string
}

/** Cột (một hoặc nhiều chuỗi); `stacked` = xếp chồng các chuỗi lên nhau. */
export function BarChart({ labels, titles, series, label, format = String, stacked = false }: CommonProps & { stacked?: boolean }) {
  const [ref, width] = useWidth()
  const [hover, setHover] = useState<number | null>(null)
  const totals = labels.map((_, i) => (stacked ? series.reduce((a, s) => a + (s.values[i] ?? 0), 0) : Math.max(...series.map((s) => s.values[i] ?? 0))))
  const { max, step } = scale(Math.max(0, ...totals))
  const innerW = width - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom
  const slot = innerW / Math.max(1, labels.length)
  const groupW = Math.min(56, slot * 0.72)
  const barW = stacked ? groupW : groupW / series.length
  const every = Math.max(1, Math.ceil(labels.length / Math.max(2, Math.floor(innerW / 52))))

  const onMove = (e: MouseEvent<SVGSVGElement>) => {
    const x = e.clientX - e.currentTarget.getBoundingClientRect().left - PAD.left
    const i = Math.floor(x / slot)
    setHover(i >= 0 && i < labels.length ? i : null)
  }

  return (
    <figure className="relative m-0" ref={ref as never}>
      <svg width={width} height={H} role="img" aria-label={label} className="block max-w-full" onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        <Grid width={width} step={step} />
        {labels.map((l, i) => {
          const x0 = PAD.left + slot * i + (slot - groupW) / 2
          let stackTop = PAD.top + innerH
          return (
            <g key={`${l}-${i}`} opacity={hover === null || hover === i ? 1 : 0.55}>
              {hover === i && <rect x={PAD.left + slot * i} y={PAD.top} width={slot} height={innerH} fill="var(--tint)" opacity={0.6} />}
              {series.map((s, k) => {
                const v = s.values[i] ?? 0
                const h = (v / max) * innerH
                const y = stacked ? (stackTop -= h) : PAD.top + innerH - h
                return <rect key={s.name} x={stacked ? x0 : x0 + barW * k} y={y} width={Math.max(2, barW - (stacked ? 0 : 2))} height={Math.max(h, v ? 1 : 0)} rx={2.5} fill={s.color} />
              })}
              {slot >= 30 && !stacked && series.length === 1 && (series[0].values[i] ?? 0) > 0 && (
                <text x={x0 + barW / 2} y={PAD.top + innerH - ((series[0].values[i] ?? 0) / max) * innerH - 5} textAnchor="middle" fontSize={11} fill="var(--heading)">
                  {series[0].values[i]}
                </text>
              )}
              {i % every === 0 && (
                <text x={PAD.left + slot * i + slot / 2} y={H - 10} textAnchor="middle" fontSize={11} fill="var(--muted)">
                  {l}
                </text>
              )}
            </g>
          )
        })}
      </svg>
      {hover !== null && (
        <Tooltip
          x={PAD.left + slot * hover + slot / 2}
          width={width}
          title={(titles ?? labels)[hover]}
          rows={[
            ...series.map((s) => ({ name: s.name, color: s.color, value: format(s.values[hover] ?? 0) })),
            ...(stacked && series.length > 1 ? [{ name: 'Tổng', color: 'var(--muted)', value: format(totals[hover]) }] : []),
          ]}
        />
      )}
      {series.length > 1 && <Legend series={series} />}
      <DataTable caption={label} labels={labels} series={series} />
    </figure>
  )
}

export function LineChart({ labels, titles, series, label, format = String }: CommonProps) {
  const [ref, width] = useWidth()
  const [hover, setHover] = useState<number | null>(null)
  const { max, step } = scale(Math.max(0, ...series.flatMap((s) => s.values)))
  const innerW = width - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom
  const gap = innerW / Math.max(1, labels.length - 1)
  const x = (i: number) => PAD.left + (labels.length === 1 ? innerW / 2 : gap * i)
  const y = (v: number) => PAD.top + innerH * (1 - v / max)
  const every = Math.max(1, Math.ceil(labels.length / Math.max(2, Math.floor(innerW / 64))))

  const onMove = (e: MouseEvent<SVGSVGElement>) => {
    const px = e.clientX - e.currentTarget.getBoundingClientRect().left - PAD.left
    setHover(Math.max(0, Math.min(labels.length - 1, Math.round(px / (gap || 1)))))
  }

  return (
    <figure className="relative m-0" ref={ref as never}>
      <svg width={width} height={H} role="img" aria-label={label} className="block max-w-full" onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        <Grid width={width} step={step} />
        {labels.map((l, i) =>
          i % every === 0 ? (
            <text key={i} x={x(i)} y={H - 10} textAnchor="middle" fontSize={11} fill="var(--muted)">
              {l}
            </text>
          ) : null,
        )}
        {series.map((s, k) => (
          <g key={s.name}>
            {k === 0 && (
              <polygon
                fill={s.color}
                opacity={0.1}
                points={`${x(0)},${y(0)} ${s.values.map((v, i) => `${x(i)},${y(v)}`).join(' ')} ${x(s.values.length - 1)},${y(0)}`}
              />
            )}
            <polyline fill="none" stroke={s.color} strokeWidth={2.2} strokeLinejoin="round" strokeLinecap="round" points={s.values.map((v, i) => `${x(i)},${y(v)}`).join(' ')} />
            {labels.length <= 45 && s.values.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r={3} fill={s.color} />)}
          </g>
        ))}
        {hover !== null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={PAD.top + innerH} stroke="var(--muted)" strokeDasharray="3 3" />
            {series.map((s) => (
              <circle key={s.name} cx={x(hover)} cy={y(s.values[hover] ?? 0)} r={5} fill={s.color} stroke="var(--surface)" strokeWidth={2} />
            ))}
          </g>
        )}
      </svg>
      {hover !== null && (
        <Tooltip x={x(hover)} width={width} title={(titles ?? labels)[hover]} rows={series.map((s) => ({ name: s.name, color: s.color, value: format(s.values[hover] ?? 0) }))} />
      )}
      <Legend series={series} />
      <DataTable caption={label} labels={labels} series={series} />
    </figure>
  )
}

/** Đường nhỏ không trục, đặt trong thẻ số liệu để thấy xu hướng. */
export function Sparkline({ values, color = 'var(--accent)' }: { values: number[]; color?: string }): ReactNode {
  const w = 96
  const h = 28
  if (values.length < 2) return null
  const max = Math.max(1, ...values)
  const points = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - 2 - (v / max) * (h - 4)}`).join(' ')
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true" className="flex-none">
      <polyline fill="none" stroke={color} strokeWidth={1.8} strokeLinejoin="round" strokeLinecap="round" points={points} />
    </svg>
  )
}
