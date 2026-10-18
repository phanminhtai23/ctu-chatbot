import { ApiError, apiFetch, apiStream } from './api'

export type StepStatus = 'pending' | 'running' | 'done' | 'warning' | 'failed' | 'skipped'
export type JobStatus = 'running' | 'activated' | 'rejected' | 'failed'
export type RowStatus = 'ok' | 'warn' | 'fail' | 'info'

export type IngestStep = {
  key: string
  title: string
  status: StepStatus
  started_at: string | null
  finished_at: string | null
  summary: string
  progress: { done: number; total: number; unit: string } | null
  metrics: { label: string; value: string }[]
  rows: { label: string; status: RowStatus; note: string }[]
  preview: string
  error: string
}

export type IngestJob = {
  id: string
  filename: string
  size_bytes: number
  status: JobStatus
  activated: boolean
  created_at: string
  finished_at: string | null
  steps: IngestStep[]
}

export type IngestJobSummary = Omit<IngestJob, 'steps'> & {
  /** Đang là tài liệu chatbot dùng */
  is_active: boolean
  /** Từng qua kiểm thử và còn đủ dữ liệu: chuyển lại được */
  can_activate: boolean
}

export type ActiveDocument = {
  version: string
  collection: string
  filename: string
  activated_at: string
  articles: number
  pages: number
}

export type DocumentsOverview = {
  enabled: boolean
  active: ActiveDocument | null
  /** Còn bản mặc định kèm hệ thống để quay về */
  default_available: boolean
  running_job_id: string | null
  jobs: IngestJobSummary[]
}

export const getOverview = (): Promise<DocumentsOverview> => apiFetch('/api/v1/admin/documents')

export const getJob = (id: string): Promise<IngestJob> => apiFetch(`/api/v1/admin/documents/jobs/${encodeURIComponent(id)}`)

/** Áp dụng lại một phiên bản đã nạp trước đó. */
export const activateVersion = (id: string): Promise<{ active: ActiveDocument }> =>
  apiFetch(`/api/v1/admin/documents/versions/${encodeURIComponent(id)}/activate`, { method: 'POST' })

/** Quay về tài liệu mặc định kèm hệ thống. */
export const activateDefault = (): Promise<{ active: null }> =>
  apiFetch('/api/v1/admin/documents/versions/default/activate', { method: 'POST' })

/** Tải lại file PDF gốc của một lần nạp (cần header Authorization nên đi qua fetch rồi lưu blob). */
export async function downloadSource(id: string, filename: string): Promise<void> {
  const res = await apiStream(`/api/v1/admin/documents/jobs/${encodeURIComponent(id)}/source`)
  const url = URL.createObjectURL(await res.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

/** Gửi nguyên file PDF làm body; BE chạy cả quy trình ở nền và trả về job để theo dõi. */
export const uploadDocument = (file: File): Promise<IngestJob> =>
  apiFetch(`/api/v1/admin/documents?filename=${encodeURIComponent(file.name)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/pdf' },
    body: file,
  })

/** Mã lỗi BE trả về trong `detail` (ví dụ INGEST_BUSY, INVALID_PDF, PDF_TOO_LARGE, INGEST_DISABLED). */
export function uploadErrorCode(err: unknown): string {
  if (!(err instanceof ApiError)) return 'NETWORK'
  const match = /"detail":\s*"([A-Z_]+)/.exec(err.message)
  return match ? match[1] : `HTTP_${err.status}`
}
