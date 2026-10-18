import { useEffect, useState } from 'react'
import donateGif from '../assets/donate_fee.gif'
import { useI18n } from '../i18n'
import { donateQrUrl, getDonateInfo, type DonateInfo } from '../lib/donate'
import Icon from './Icon'

type Props = {
  /** Truyền vào = dùng luôn thông tin này (trang admin xem trước). Không truyền = tự hỏi server khi hiện ra. */
  info?: DonateInfo | null
  /** Lề ngoài; mặc định cách phần trên 1.5rem (dùng trong hộp thoại hồ sơ) */
  className?: string
  /** true = dải toàn chiều ngang ở cuối trang landing: nền riêng + khoảng đệm, và biến mất hoàn toàn khi chưa có QR */
  band?: boolean
}

/** Lời kêu gọi ủng hộ + mã QR do admin tải lên + GIF. Chưa có QR (hoặc ảnh hỏng) thì không hiện gì. */
export default function DonateSection({ info: provided, className = 'mt-6', band = false }: Props) {
  const { t } = useI18n()
  const [fetched, setFetched] = useState<DonateInfo | null>(null)
  // Nhớ phiên bản ảnh bị lỗi (thay vì true/false) để khi admin đổi ảnh mới thì tự thử lại, không cần effect đặt lại.
  const [brokenVersion, setBrokenVersion] = useState<string | null>(null)

  useEffect(() => {
    if (provided !== undefined) return
    let cancelled = false
    getDonateInfo()
      .then((result) => !cancelled && setFetched(result))
      .catch(() => {}) // không lấy được thì thôi, mục này chỉ là phần thêm
    return () => {
      cancelled = true
    }
  }, [provided])

  const info = provided !== undefined ? provided : fetched

  if (!info?.has_qr || (info.version !== null && info.version === brokenVersion)) return null

  const card = (
    <section aria-labelledby="donate-title" className={`${band ? 'mx-auto max-w-[760px]' : className} rounded-2xl border border-line bg-tint p-4 sm:p-5`}>
      <div className="mb-2 flex items-center gap-2 text-heading">
        <Icon name="heart" size={20} className="flex-none text-[#C2185B] dark:text-[#F48FB1]" />
        <h3 id="donate-title" className="m-0 text-base">
          {t('donate.title')}
        </h3>
      </div>
      <p className="mb-4 mt-0 text-sm">{t('donate.text')}</p>

      <div className="flex flex-wrap items-center justify-center gap-4">
        <figure className="m-0 flex flex-col items-center gap-2">
          {/* Nền trắng cố định: mã QR nằm trên nền tối (dark mode) rất khó quét. */}
          <img
            src={donateQrUrl(info.version)}
            alt={t('donate.qrAlt')}
            onError={() => setBrokenVersion(info.version)}
            className="size-40 rounded-xl border border-line bg-white object-contain p-2 sm:size-44"
          />
          <figcaption className="max-w-44 text-center text-xs">{t('donate.scan')}</figcaption>
        </figure>
        {/* GIF chỉ để trang trí nên không có chữ thay thế. */}
        <img src={donateGif} alt="" className="h-40 w-auto max-w-full rounded-xl object-cover sm:h-44" />
      </div>

      <p className="mb-0 mt-3 text-center text-xs">{t('donate.thanks')}</p>
    </section>
  )

  return band ? (
    <div className="bg-surface">
      <div className="mx-auto max-w-[1200px] px-5 py-14 sm:px-8">{card}</div>
    </div>
  ) : (
    card
  )
}
