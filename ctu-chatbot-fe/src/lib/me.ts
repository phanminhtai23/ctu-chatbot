import { apiFetch } from './api'

export type Language = 'vi' | 'en'
export type ThemeMode = 'system' | 'light' | 'dark'

export type Role = 'user' | 'admin'

export type UserProfile = {
  id: string
  email: string
  name: string
  birthday: string | null // YYYY-MM-DD
  avatar_url: string | null
  role: Role
  timezone: string // IANA, ví dụ Asia/Ho_Chi_Minh
  language: Language
  theme: ThemeMode
  /** false = tài khoản mới, chưa hiện hộp thoại chào mừng */
  welcomed: boolean
}

export type UserUpdate = Partial<Pick<UserProfile, 'name' | 'birthday' | 'timezone' | 'theme'>>

export type TokenResponse = { access_token: string; refresh_token: string; user: UserProfile }

export function googleLogin(credential: string): Promise<TokenResponse> {
  return apiFetch('/api/v1/auth/google', { method: 'POST', body: JSON.stringify({ credential }) })
}

/** Đăng nhập thử bằng email — BE chỉ bật khi ENV=dev. */
export function devLogin(email: string): Promise<TokenResponse> {
  return apiFetch('/api/v1/auth/dev-login', { method: 'POST', body: JSON.stringify({ email }) })
}

/** Thu hồi refresh token ở server (đăng xuất thật sự). */
export function revokeSession(refreshToken: string): Promise<null> {
  return apiFetch('/api/v1/auth/logout', { method: 'POST', body: JSON.stringify({ refresh_token: refreshToken }) })
}

/** Báo server đã chào mừng người dùng mới (hộp thoại pháo hoa chỉ hiện một lần). */
export function markWelcomed(): Promise<UserProfile> {
  return apiFetch('/api/v1/me/welcome', { method: 'POST' })
}

export function getMe(): Promise<UserProfile> {
  return apiFetch('/api/v1/me')
}

export function updateMe(patch: UserUpdate): Promise<UserProfile> {
  return apiFetch('/api/v1/me', { method: 'PATCH', body: JSON.stringify(patch) })
}
