/**
 * Biểu đồ SVG tự vẽ (không thêm thư viện): đủ cho cột và đường, co giãn theo bề rộng khung chứa,
 * tô màu bằng biến theme nên đúng cả chế độ sáng/tối. Mỗi biểu đồ kèm bảng ẩn (sr-only) cho trình đọc màn hình.
 */

const W = 640
const H = 240
const PAD = { top: 16, right: 12, bottom: 30, left: 40 }

const niceMax = (value: number) => {
  if (value <= 5) return 5
  const pow = 10 ** Math.floor(Math.log10(value))
  const n = value / pow
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * pow
}

function Grid({ max }: { max: number }) {
  const lines = [0, 0.25, 0.5, 0.75, 1]
  return (
    <>
      {lines.map((f) => {
        const y = PAD.top + (H - PAD.top - PAD.bottom) * (1 - f)
        return (
          <g key={f}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y} y2={y} stroke="var(--line)" strokeWidth={1} />
            <text x={PAD.left - 6} y={y + 4} textAnchor="end" fontSize={11} fill="var(--muted)">
              {Math.round(max * f)}
            </text>
          </g>
        )
      })}
    </>
  )
}

type Point = { label: string; value: number }

export function BarChart({ data, label, color = 'var(--accent)' }: { data: Point[]; label: string; color?: string }) {
  const max = niceMax(Math.max(0, ...data.map((d) => d.value)))
  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom
  const slot = innerW / Math.max(1, data.length)
  const barW = Math.min(48, slot * 0.7)
  const every = Math.ceil(data.length / 12)
  return (
    <figure className="m-0">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} className="h-auto w-full">
        <Grid max={max} />
        {data.map((d, i) => {
          const h = (d.value / max) * innerH
          const x = PAD.left + slot * i + (slot - barW) / 2
          return (
            <g key={`${d.label}-${i}`}>
              <rect x={x} y={PAD.top + innerH - h} width={barW} height={Math.max(h, d.value ? 1 : 0)} rx={3} fill={color}>
                <title>{`${d.label}: ${d.value}`}</title>
              </rect>
              {data.length <= 12 && d.value > 0 && (
                <text x={x + barW / 2} y={PAD.top + innerH - h - 4} textAnchor="middle" fontSize={11} fill="var(--heading)">
                  {d.value}
                </text>
              )}
              {i % every === 0 && (
                <text x={x + barW / 2} y={H - 10} textAnchor="middle" fontSize={11} fill="var(--muted)">
                  {d.label}
                </text>
              )}
            </g>
          )
        })}
      </svg>
      <table className="sr-only">
        <caption>{label}</caption>
        <tbody>
          {data.map((d, i) => (
            <tr key={i}>
              <th scope="row">{d.label}</th>
              <td>{d.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  )
}

export type Series = { name: string; color: string; values: number[] }

export function LineChart({ labels, series, label }: { labels: string[]; series: Series[]; label: string }) {
  const max = niceMax(Math.max(0, ...series.flatMap((s) => s.values)))
  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom
  const step = innerW / Math.max(1, labels.length - 1)
  const x = (i: number) => PAD.left + (labels.length === 1 ? innerW / 2 : step * i)
  const y = (v: number) => PAD.top + innerH * (1 - v / max)
  const every = Math.ceil(labels.length / 8)
  return (
    <figure className="m-0">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} className="h-auto w-full">
        <Grid max={max} />
        {labels.map((l, i) =>
          i % every === 0 ? (
            <text key={i} x={x(i)} y={H - 10} textAnchor="middle" fontSize={11} fill="var(--muted)">
              {l}
            </text>
          ) : null,
        )}
        {series.map((s) => (
          <g key={s.name}>
            <polyline
              fill="none"
              stroke={s.color}
              strokeWidth={2.2}
              strokeLinejoin="round"
              strokeLinecap="round"
              points={s.values.map((v, i) => `${x(i)},${y(v)}`).join(' ')}
            />
            {s.values.map((v, i) => (
              <circle key={i} cx={x(i)} cy={y(v)} r={labels.length > 40 ? 2 : 3.2} fill={s.color}>
                <title>{`${labels[i]} · ${s.name}: ${v}`}</title>
              </circle>
            ))}
          </g>
        ))}
      </svg>
      <div className="mt-1 flex flex-wrap gap-4 text-xs text-muted">
        {series.map((s) => (
          <span key={s.name} className="inline-flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4 rounded" style={{ background: s.color }} />
            {s.name}
          </span>
        ))}
      </div>
      <table className="sr-only">
        <caption>{label}</caption>
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
    </figure>
  )
}
