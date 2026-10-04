import type { Lang } from '../i18n'

/** Thời gian chờ: tiếng Anh "10.9s", tiếng Việt "10,9s" (dấu phẩy thập phân). */
export function formatSeconds(lang: Lang, seconds: number): string {
  const number = new Intl.NumberFormat(lang === 'vi' ? 'vi-VN' : 'en-US', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(seconds)
  return `${number}s`
}
