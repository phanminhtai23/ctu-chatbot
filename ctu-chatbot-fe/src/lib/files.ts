import { ApiError, apiFetch } from './api'
import type { UserProfile } from './me'

export type UserFile = {
  id: string
  kind: 'avatar' | 'attachment'
  filename: string
  content_type: string
  size_bytes: number
  url: string
  created_at: string
}

export type FileListing = {
  items: UserFile[]
  used_bytes: number
  quota_bytes: number
  max_upload_bytes: number
}

export const listFiles = (): Promise<FileListing> => apiFetch('/api/v1/me/files')

/** Tải PDF hoặc ảnh lên: gửi nguyên file làm body, tên file ở `?name=` (cùng kiểu với tải ảnh QR). */
export type UploadResult = FileListing & { file: UserFile }

export const uploadFile = (file: File): Promise<UploadResult> =>
  apiFetch(`/api/v1/me/files?name=${encodeURIComponent(file.name)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: file,
  })

export const deleteFile = (id: string): Promise<null> =>
  apiFetch(`/api/v1/me/files/${encodeURIComponent(id)}`, { method: 'DELETE' })

export const uploadAvatar = (file: File): Promise<UserProfile> =>
  apiFetch(`/api/v1/me/avatar?name=${encodeURIComponent(file.name)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: file,
  })

/** Bỏ ảnh đã tải lên và đổi sang một ảnh ngẫu nhiên MỚI. */
export const randomAvatar = (): Promise<UserProfile> => apiFetch('/api/v1/me/avatar', { method: 'DELETE' })

/** Bỏ ảnh đã tải lên và về ảnh mặc định của tài khoản (ảnh lúc mới đăng ký, cố định). */
export const defaultAvatar = (): Promise<UserProfile> => apiFetch('/api/v1/me/avatar?random=false', { method: 'DELETE' })

const CODES = ['FILE_TOO_LARGE', 'QUOTA_EXCEEDED', 'UNSUPPORTED_TYPE', 'EMPTY_FILE', 'STORAGE_NOT_CONFIGURED', 'STORAGE_ERROR', 'UPLOAD_RATE_LIMITED'] as const
export type FileErrorCode = (typeof CODES)[number] | 'UNKNOWN'

export function fileErrorCode(err: unknown): FileErrorCode {
  if (err instanceof ApiError) return CODES.find((c) => err.message.includes(c)) ?? 'UNKNOWN'
  return 'UNKNOWN'
}
