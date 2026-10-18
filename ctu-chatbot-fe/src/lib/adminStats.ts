import { apiFetch } from './api'

export type Stats = {
  generated_at: string
  days: number
  totals: {
    users: number
    active_accounts: number
    admins: number
    conversations: number
    messages: number
    messages_today: number
    active_today: number
    active_7d: number
    active_30d: number
  }
  /** Số tài khoản đăng ký mới trong 7 ngày / 30 ngày / 6 tháng / 1 năm gần nhất */
  registrations: { week: number; month: number; six_months: number; year: number }
  registrations_daily: { date: string; count: number }[]
  usage_daily: { date: string; active_users: number; messages: number }[]
  /** Số lượt hỏi theo giờ trong ngày (0-23, giờ Việt Nam) */
  hourly: number[]
  /** Số lượt hỏi theo thứ (0 = thứ Hai … 6 = Chủ nhật) */
  weekday: number[]
  frequency: {
    window_messages: number
    avg_messages_per_day: number
    avg_active_users_per_day: number
    avg_messages_per_active_user_per_day: number
    avg_messages_per_user: number
    top_users: { email: string; name: string; messages: number; active_days: number }[]
  }
}

export const getStats = (days: number): Promise<Stats> => apiFetch(`/api/v1/admin/stats?days=${days}`)

export type AdminUser = {
  id: string
  email: string
  name: string
  avatar_url: string | null
  role: 'user' | 'admin'
  /** Quyền admin khai báo trong ADMIN_EMAILS (.env): không hạ quyền được từ giao diện */
  admin_by_env: boolean
  is_active: boolean
  created_at: string
  messages: number
  conversations: number
  last_active: string | null
}

export type AdminUserDetail = AdminUser & {
  first_active: string | null
  birthday: string | null
  timezone: string
  daily: { date: string; messages: number }[]
}

export type UserFilters = {
  q: string
  role: 'all' | 'user' | 'admin'
  state: 'all' | 'active' | 'disabled'
  limit: number
  offset: number
}

export function listUsers(f: UserFilters): Promise<{ total: number; items: AdminUser[] }> {
  const params = new URLSearchParams({
    q: f.q,
    role: f.role,
    state: f.state,
    limit: String(f.limit),
    offset: String(f.offset),
  })
  return apiFetch(`/api/v1/admin/users?${params}`)
}

export const getUser = (id: string): Promise<AdminUserDetail> => apiFetch(`/api/v1/admin/users/${encodeURIComponent(id)}`)

export const updateUser = (id: string, patch: { is_active?: boolean; role?: 'user' | 'admin' }): Promise<AdminUser> =>
  apiFetch(`/api/v1/admin/users/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(patch) })
