import { useEffect, useRef, type ReactNode } from 'react'
import Icon, { type IconName } from './Icon'

export type FunTone = 'warn' | 'error' | 'love'

const badgeTone: Record<FunTone, string> = {
  warn: 'bg-ctu-gold-active text-ctu-navy-dark',
  error: 'bg-[#FF8A8A] text-white',
  love: 'bg-[#FF6F91] text-white',
}

type Props = {
  open: boolean
  onClose: () => void
  /** Đường dẫn GIF (null = không có ảnh) */
  gif: string | null
  tone: FunTone
  icon: IconName
  title: string
  message: string
  /** Nội dung thêm dưới lời nhắn (ví dụ đồng hồ đếm ngược) */
  extra?: ReactNode
  actionLabel: string
  /** Phủ lên trên cùng của hộp thoại (ví dụ pháo hoa) */
  overlay?: ReactNode
  labelId: string
  /** 'side': GIF bên trái, chữ bên phải (mặc định); 'center': GIF to ở giữa, huy hiệu + lời chào ở dưới */
  layout?: 'side' | 'center'
}

/**
 * Khung hộp thoại "vui" dùng chung, bố cục NGANG: GIF ngẫu nhiên bên trái, bên phải là huy hiệu icon tròn xinh + tiêu đề +
 * lời nhắn + một nút (trên điện thoại thì xếp dọc). Dùng <dialog> gốc nên có sẵn khoá cuộn nền, bắt phím Esc, trả focus khi đóng.
 */
export default function FunDialog({ open, onClose, gif, tone, icon, title, message, extra, actionLabel, overlay, labelId, layout = 'side' }: Props) {
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
      aria-labelledby={labelId}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      className={`m-auto w-[calc(100%-32px)] ${layout === 'center' ? 'max-w-[640px]' : 'max-w-[780px]'} overflow-visible rounded-3xl border border-line bg-surface p-0 text-muted shadow-[0_24px_60px_rgba(0,0,0,.4)] backdrop:bg-black/60`}
    >
      {open && overlay}
      {layout === 'center' ? (
        <div className="flex flex-col items-center overflow-hidden rounded-3xl text-center">
          <div className="flex h-[280px] w-full items-center justify-center bg-tint p-4 sm:h-[400px]">
            {gif ? <img src={gif} alt="" className="h-full w-full object-contain" /> : <Icon name={icon} size={96} className="text-accent" />}
          </div>
          <span className={`-mt-7 flex size-14 flex-none items-center justify-center rounded-full border-4 border-surface shadow-md ${badgeTone[tone]}`}>
            <Icon name={icon} size={28} strokeWidth={2.2} />
          </span>
          <div className="flex w-full flex-col items-center gap-2.5 px-6 pb-7 pt-3 sm:px-10">
            <h2 id={labelId} className="m-0 text-[26px] leading-tight text-heading sm:text-[30px]">
              {title}
            </h2>
            <p className="m-0 text-base leading-relaxed text-heading">{message}</p>
            {extra && <div>{extra}</div>}
            <button
              type="button"
              onClick={onClose}
              autoFocus
              className="mt-3 min-h-12 w-full cursor-pointer rounded-xl border-0 bg-ctu-navy px-8 py-3 font-sans text-base font-semibold text-white hover:bg-ctu-navy-dark sm:w-auto sm:min-w-[260px]"
            >
              {actionLabel}
            </button>
          </div>
        </div>
      ) : (
      <div className="grid overflow-hidden rounded-3xl sm:grid-cols-[minmax(0,330px)_minmax(0,1fr)]">
        <div className="flex h-[220px] items-center justify-center bg-tint p-3 sm:h-auto sm:min-h-[340px]">
          {gif ? (
            <img src={gif} alt="" className="max-h-full max-w-full object-contain" />
          ) : (
            <Icon name={icon} size={72} className="text-accent" />
          )}
        </div>
        <div className="flex flex-col justify-center gap-3 px-6 py-6 text-left sm:px-8 sm:py-8">
          <div className="flex items-center gap-3">
            <span className={`flex size-12 flex-none items-center justify-center rounded-full shadow-md ${badgeTone[tone]}`}>
              <Icon name={icon} size={24} strokeWidth={2.2} />
            </span>
            <h2 id={labelId} className="m-0 text-2xl leading-tight text-heading">
              {title}
            </h2>
          </div>
          <p className="m-0 text-base leading-relaxed text-heading">{message}</p>
          {extra && <div>{extra}</div>}
          <button
            type="button"
            onClick={onClose}
            autoFocus
            className="mt-2 min-h-11 w-full cursor-pointer self-start rounded-xl border-0 bg-ctu-navy px-8 py-2.5 font-sans text-base font-semibold text-white hover:bg-ctu-navy-dark sm:w-auto"
          >
            {actionLabel}
          </button>
        </div>
      </div>
      )}
    </dialog>
  )
}
