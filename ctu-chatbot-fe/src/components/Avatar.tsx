import { useState } from 'react'

type Props = { src?: string | null; name: string; className?: string }

/** Ảnh đại diện tròn; chưa có ảnh hoặc ảnh lỗi thì hiện chữ cái đầu của tên. Kích thước đặt bằng `className` (mặc định 40px). */
export default function Avatar({ src, name, className = 'size-10' }: Props) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null)
  const initials = name.trim().split(/\s+/).slice(-2).map((w) => w[0]?.toUpperCase() ?? '').join('')
  const showImage = !!src && src !== failedSrc
  return (
    <span className={`flex flex-none items-center justify-center overflow-hidden rounded-full bg-ctu-cyan text-sm font-semibold text-ctu-navy-dark ${className}`}>
      {showImage ? (
        <img src={src} alt="" onError={() => setFailedSrc(src)} className="size-full object-cover" referrerPolicy="no-referrer" />
      ) : (
        initials
      )}
    </span>
  )
}
