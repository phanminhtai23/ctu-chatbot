import { API_BASE_URL, ApiError, apiFetch } from './api'

export type DonateInfo = { has_qr: boolean; version: string | null }

/** Khớp giới hạn mặc định ở BE (DONATE_QR_MAX_MB=2); BE vẫn là nơi kiểm tra cuối cùng. */
export const QR_MAX_BYTES = 2 * 1024 * 1024
export const QR_MAX_MB = QR_MAX_BYTES / (1024 * 1024)
const QR_TYPES = ['image/png', 'image/jpeg', 'image/webp']
export const QR_ACCEPT = QR_TYPES.join(',')

/** Công khai (không cần đăng nhập). */
export const getDonateInfo = (): Promise<DonateInfo> => apiFetch('/api/v1/donate')

/** Địa chỉ ảnh QR để đặt vào <img src>. `version` đổi mỗi khi admin thay ảnh nên trình duyệt không giữ ảnh cũ. */
export const donateQrUrl = (version: string | null): string =>
  `${API_BASE_URL}/api/v1/donate/qr${version ? `?v=${encodeURIComponent(version)}` : ''}`

/** Gửi nguyên file làm body (giống cách tải PDF). BE tự xác định kiểu ảnh từ nội dung, không tin header. */
export const uploadQr = (file: File): Promise<DonateInfo> =>
  apiFetch('/api/v1/admin/donate/qr', {
    method: 'PUT',
    headers: { 'Content-Type': file.type || 'application/octet-stream' },
    body: file,
  })

export const deleteQr = (): Promise<null> => apiFetch('/api/v1/admin/donate/qr', { method: 'DELETE' })

export type QrFileProblem = 'TYPE' | 'TOO_LARGE'

/** Kiểm tra nhanh ở trình duyệt để báo lỗi ngay, khỏi gửi file chắc chắn bị từ chối. */
export function checkQrFile(file: File): QrFileProblem | null {
  if (!QR_TYPES.includes(file.type)) return 'TYPE'
  if (file.size > QR_MAX_BYTES) return 'TOO_LARGE'
  return null
}

/** Mã lỗi BE trả về trong `detail` (IMAGE_TOO_LARGE, INVALID_IMAGE...); 'NETWORK' nếu không phải lỗi từ BE. */
export function qrErrorCode(err: unknown): string {
  if (!(err instanceof ApiError)) return 'NETWORK'
  const match = /"detail":\s*"([A-Z_]+)/.exec(err.message)
  return match ? match[1] : `HTTP_${err.status}`
}
