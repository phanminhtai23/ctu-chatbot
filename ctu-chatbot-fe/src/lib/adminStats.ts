import { apiFetch, apiStream } from './api'

export type Granularity = 'auto' | 'day' | 'week' | 'month'

/** Chỉ số tổng hợp của một khoảng ngày (kỳ đang xem và kỳ liền trước để so sánh). */
export type Period = {
  days: number
  messages: number
  cached_messages: number
  active_users: number
  new_users: number
  conversations: number
  avg_messages_per_day: number
  avg_active_users_per_day: number
  messages_per_active_user: number
  /** Tỉ lệ lượt hỏi là câu hỏi gợi ý có sẵn đáp án (0..1) */
  cached_ratio: number
}

export type SeriesRow = {
  /** Ngày đầu của ngày/tuần/tháng (YYYY-MM-DD) */
  date: string
  /** Ngày cuối của khoảng này (đã cắt theo khoảng đang xem) */
  end: string
  active_users: number
  messages: number
  cached_messages: number
  new_users: number
  conversations: number
  /** Tổng số tài khoản tính đến cuối khoảng này */
  total_users: number
}

export type Stats = {
  generated_at: string
  range: {
    from: string
    to: string
    days: number
    granularity: Exclude<Granularity, 'auto'>
    previous_from: string
    previous_to: string
  }
  totals: { users: number; active_accounts: number; admins: number; conversations: number; messages: number }
  period: Period
  previous: Period
  /** Người dùng hoạt động trong ngày / 7 ngày / 30 ngày tính tới ngày cuối của khoảng; stickiness = DAU / MAU */
  activity: { dau: number; wau: number; mau: number; stickiness: number }
  /** Đăng ký mới trong 1 tuần / 1 tháng / 6 tháng / 1 năm gần nhất (cố định, không phụ thuộc bộ lọc) */
  registrations: { week: number; month: number; six_months: number; year: number }
  series: SeriesRow[]
  /** Số lượt hỏi theo giờ trong ngày (0-23, giờ Việt Nam) trong khoảng đang xem */
  hourly: number[]
  /** Số lượt hỏi theo thứ (0 = thứ Hai … 6 = Chủ nhật) trong khoảng đang xem */
  weekday: number[]
  top_users: { email: string; name: string; messages: number; active_days: number; last_active: string }[]
}

/** `days` = N ngày gần nhất (server tính theo giờ Việt Nam); `from`/`to` (YYYY-MM-DD) cho khoảng tuỳ chọn. */
export type StatsQuery = { days?: number; from?: string; to?: string; granularity: Granularity }

function queryString(q: StatsQuery): string {
  const params = new URLSearchParams({ granularity: q.granularity })
  if (q.from) params.set('from', q.from)
  if (q.to) params.set('to', q.to)
  if (!q.from && q.days) params.set('days', String(q.days))
  return params.toString()
}

export const getStats = (q: StatsQuery): Promise<Stats> => apiFetch(`/api/v1/admin/stats?${queryString(q)}`)

/** Tải bảng số liệu theo ngày/tuần/tháng (CSV) của khoảng đang xem. */
export async function downloadStatsCsv(q: StatsQuery, filename: string): Promise<void> {
  const res = await apiStream(`/api/v1/admin/stats/export.csv?${queryString(q)}`)
  const url = URL.createObjectURL(await res.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export type AdminUser = {
  id: string
  email: string
  name: string
  avatar_url: string
  role: 'user' | 'admin'
  /** Quyền admin khai báo trong ADMIN_EMAILS (.env): không hạ quyền được từ giao diện */
  admin_by_env: boolean
  is_active: boolean
  created_at: string
  messages: number
  conversations: number
  last_active: string | null
  /** Dung lượng file đã tải lên (byte) và hạn mức mỗi người */
  storage_bytes: number
  storage_quota_bytes: number
  /** Số lần vượt giới hạn tốc độ (spam) và số tin chửi thề */
  spam_count: number
  profanity_count: number
}

export type AdminUserDetail = AdminUser & {
  first_active: string | null
  birthday: string | null
  timezone: string
  daily: { date: string; messages: number }[]
}

export type UserSort = 'name' | 'role' | 'state' | 'created' | 'last_active' | 'messages' | 'storage' | 'spam' | 'profanity'

export type UserFilters = {
  q: string
  role: 'all' | 'user' | 'admin'
  state: 'all' | 'active' | 'disabled'
  sort: UserSort
  order: 'asc' | 'desc'
  limit: number
  offset: number
}

export function listUsers(f: UserFilters): Promise<{ total: number; items: AdminUser[] }> {
  const params = new URLSearchParams({
    q: f.q,
    role: f.role,
    state: f.state,
    sort: f.sort,
    order: f.order,
    limit: String(f.limit),
    offset: String(f.offset),
  })
  return apiFetch(`/api/v1/admin/users?${params}`)
}

export const getUser = (id: string): Promise<AdminUserDetail> => apiFetch(`/api/v1/admin/users/${encodeURIComponent(id)}`)

export const updateUser = (id: string, patch: { is_active?: boolean; role?: 'user' | 'admin' }): Promise<AdminUser> =>
  apiFetch(`/api/v1/admin/users/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(patch) })
