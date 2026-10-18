import { useEffect, useRef } from 'react'

type Spark = { x: number; y: number; vx: number; vy: number; life: number; ttl: number; color: string; size: number }
type Rocket = { x: number; y: number; vx: number; vy: number; targetY: number; color: string }
type Confetto = { x: number; y: number; vx: number; vy: number; life: number; ttl: number; color: string; size: number; spin: number; angle: number }

const COLORS = ['#ffd23f', '#22b8f0', '#ff4d8d', '#7ee081', '#ffffff', '#ff9f1c', '#b388ff', '#4dd0e1']

/**
 * `sides`: pháo hoa bắn LIÊN TỤC ở hai bên màn hình (hai bên hộp thoại) cho tới khi component bị gỡ.
 * Pháo hoa thật sự: tên lửa bay lên từ cạnh dưới, nổ thành chùm tia sáng có vệt đuôi, kèm giấy confetti rơi.
 * Vẽ bằng canvas (không dùng thư viện), phủ toàn màn hình và không chặn chuột. Phải đặt BÊN TRONG <dialog> đang mở vì
 * dialog nằm ở "top layer" của trình duyệt, nội dung ngoài nó bị che.
 * Máy bật "giảm chuyển động" (Windows: tắt Hiệu ứng động) thì KHÔNG tắt hẳn mà chỉ bắn ngắn khoảng 4 giây rồi dừng
 * (đây là màn chào mừng một lần duy nhất; tắt hẳn thì người dùng sẽ không thấy pháo hoa nào).
 */
export default function Fireworks({ durationMs = 7500, sides = false }: { durationMs?: number; sides?: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const limit = reducedMotion ? Math.min(durationMs, 4000) : durationMs // giảm chuyển động: chỉ bắn ngắn
    const continuous = sides && !reducedMotion
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const resize = () => {
      canvas.width = window.innerWidth * dpr
      canvas.height = window.innerHeight * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()
    window.addEventListener('resize', resize)

    const rand = (a: number, b: number) => a + Math.random() * (b - a)
    const pick = () => COLORS[Math.floor(Math.random() * COLORS.length)]
    const sparks: Spark[] = []
    const rockets: Rocket[] = []
    const confetti: Confetto[] = []
    let leftNext = true

    const launch = () => {
      const w = window.innerWidth
      const h = window.innerHeight
      // sides: luân phiên bắn bên trái / bên phải (chừa khoảng giữa cho hộp thoại); mặc định bắn khắp màn hình.
      const x = sides ? (leftNext ? rand(w * 0.03, w * 0.24) : rand(w * 0.76, w * 0.97)) : rand(w * 0.08, w * 0.92)
      leftNext = !leftNext
      rockets.push({ x, y: h + 10, vx: rand(-0.6, 0.6), vy: rand(-13.5, -10.5), targetY: rand(h * 0.1, h * 0.5), color: pick() })
    }
    const explode = (x: number, y: number, color: string) => {
      const count = Math.round(rand(70, 100))
      const ring = Math.random() < 0.4 // một số quả nổ thành vòng tròn đều
      const second = pick()
      for (let i = 0; i < count; i++) {
        const angle = (Math.PI * 2 * i) / count + rand(-0.05, 0.05)
        const speed = ring ? 5.2 : rand(1.5, 7.5)
        sparks.push({ x, y, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed, life: 0, ttl: rand(60, 105), color: i % 3 === 0 ? second : color, size: rand(2, 3.6) })
      }
    }
    const rain = (n: number) => {
      for (let i = 0; i < n; i++) {
        confetti.push({ x: rand(0, window.innerWidth), y: rand(-60, -5), vx: rand(-1.2, 1.2), vy: rand(1.6, 3.8), life: 0, ttl: rand(170, 300), color: pick(), size: rand(6, 11), spin: rand(-0.25, 0.25), angle: rand(0, Math.PI) })
      }
    }

    const start = performance.now()
    let nextLaunch = 0
    let nextRain = 0
    let raf = 0
    const frame = (now: number) => {
      const elapsed = now - start
      const w = window.innerWidth
      const h = window.innerHeight
      const spawning = continuous || elapsed < limit
      if (spawning && now >= nextLaunch) {
        launch()
        if (!sides && Math.random() < 0.5) launch()
        nextLaunch = now + (sides ? rand(260, 480) : rand(350, 700))
      }
      if (spawning && now >= nextRain) {
        rain(10)
        nextRain = now + 500
      }

      // Làm mờ dần khung hình trước (thay vì xoá hẳn) để tia sáng để lại vệt đuôi.
      ctx.globalCompositeOperation = 'destination-out'
      ctx.fillStyle = 'rgba(0,0,0,0.2)'
      ctx.fillRect(0, 0, w, h)
      ctx.globalCompositeOperation = 'source-over'

      for (let i = rockets.length - 1; i >= 0; i--) {
        const r = rockets[i]
        r.x += r.vx
        r.y += r.vy
        r.vy += 0.1
        ctx.fillStyle = '#fff'
        ctx.beginPath()
        ctx.arc(r.x, r.y, 2.6, 0, Math.PI * 2)
        ctx.fill()
        if (r.y <= r.targetY || r.vy >= -1) {
          explode(r.x, r.y, r.color)
          rockets.splice(i, 1)
        }
      }
      for (let i = sparks.length - 1; i >= 0; i--) {
        const p = sparks[i]
        p.life++
        if (p.life > p.ttl) {
          sparks.splice(i, 1)
          continue
        }
        p.x += p.vx
        p.y += p.vy
        p.vy += 0.065
        p.vx *= 0.985
        ctx.globalAlpha = Math.max(0, 1 - p.life / p.ttl)
        ctx.fillStyle = p.color
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2)
        ctx.fill()
      }
      for (let i = confetti.length - 1; i >= 0; i--) {
        const c = confetti[i]
        c.life++
        if (c.life > c.ttl || c.y > h + 30) {
          confetti.splice(i, 1)
          continue
        }
        c.angle += c.spin
        c.x += c.vx + Math.sin(c.life / 14) * 0.5
        c.y += c.vy
        ctx.globalAlpha = Math.max(0, 1 - c.life / c.ttl)
        ctx.fillStyle = c.color
        ctx.save()
        ctx.translate(c.x, c.y)
        ctx.rotate(c.angle)
        ctx.fillRect(-c.size / 2, -c.size / 4, c.size, c.size / 2)
        ctx.restore()
      }
      ctx.globalAlpha = 1

      if (spawning || rockets.length || sparks.length || confetti.length) raf = requestAnimationFrame(frame)
      else ctx.clearRect(0, 0, w, h)
    }
    raf = requestAnimationFrame(frame)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
    }
  }, [durationMs, sides])

  return <canvas ref={ref} aria-hidden="true" data-testid="fireworks" className="pointer-events-none fixed inset-0 z-10 h-full w-full" />
}
