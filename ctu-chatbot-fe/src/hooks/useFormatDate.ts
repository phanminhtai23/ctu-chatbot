import { useCallback } from 'react'
import { useAuth } from '../auth'
import { useI18n } from '../i18n'

/** Định dạng thời gian theo ngôn ngữ và múi giờ đã lưu của user (chưa đăng nhập: múi giờ trình duyệt). */
export function useFormatDate() {
  const { lang } = useI18n()
  const { user } = useAuth()
  const timeZone = user?.timezone

  return useCallback(
    (iso: string) =>
      new Intl.DateTimeFormat(lang === 'vi' ? 'vi-VN' : 'en-GB', {
        dateStyle: 'medium',
        timeStyle: 'short',
        timeZone,
      }).format(new Date(iso)),
    [lang, timeZone],
  )
}
