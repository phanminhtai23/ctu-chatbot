import { useCallback } from 'react'
import { useAuth } from '../auth'

/** Định dạng thời gian theo múi giờ đã lưu của user (chưa đăng nhập: múi giờ trình duyệt). */
export function useFormatDate() {
  const { user } = useAuth()
  const timeZone = user?.timezone

  return useCallback(
    (iso: string) =>
      new Intl.DateTimeFormat('vi-VN', {
        dateStyle: 'medium',
        timeStyle: 'short',
        timeZone,
      }).format(new Date(iso)),
    [timeZone],
  )
}
