import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { UNAUTHORIZED_EVENT, clearToken, getRefreshToken, getToken, setTokens } from '../lib/auth'
import {
  devLogin,
  getMe,
  googleLogin,
  revokeSession,
  updateMe,
  type TokenResponse,
  type UserProfile,
  type UserUpdate,
} from '../lib/me'
import { useTheme } from '../theme'

type AuthValue = {
  user: UserProfile | null
  /** loading: đang kiểm tra token đã lưu; ready: đã biết có/không có user */
  status: 'loading' | 'ready'
  /** `credential` là Google ID token từ nút "Sign in with Google" */
  loginWithGoogle: (credential: string) => Promise<void>
  /** Đăng nhập thử bằng email — chỉ dùng khi BE bật ENV=dev */
  login: (email: string) => Promise<void>
  logout: () => void
  /** true khi người dùng tự bấm đăng xuất (khác với phiên hết hạn) — để không "quay lại trang cũ" ở lần đăng nhập sau */
  loggedOut: boolean
  updateProfile: (patch: UserUpdate) => Promise<UserProfile>
  /** Cập nhật hồ sơ trong bộ nhớ khi một API khác (đổi ảnh đại diện...) đã trả về hồ sơ mới */
  replaceUser: (user: UserProfile) => void
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const { setMode } = useTheme()
  const [user, setUser] = useState<UserProfile | null>(null)
  const [loggedOut, setLoggedOut] = useState(false)
  // Có access HOẶC refresh token là còn khả năng khôi phục phiên (access hết hạn thì apiFetch tự làm mới).
  const hasSession = () => Boolean(getToken() || getRefreshToken())
  const [status, setStatus] = useState<'loading' | 'ready'>(() => (hasSession() ? 'loading' : 'ready'))

  // Cài đặt lưu theo user: áp lại ngôn ngữ + theme của tài khoản mỗi khi nạp/đổi user.
  const applyPreferences = useCallback(
    (u: UserProfile) => {
      setMode(u.theme)
    },
    [setMode],
  )

  useEffect(() => {
    if (!hasSession()) return
    let cancelled = false
    getMe()
      .then((u) => {
        if (cancelled) return
        setUser(u)
        applyPreferences(u)
      })
      .catch(() => {
        // Token hỏng/hết hạn (apiFetch đã xoá nếu là 401) hoặc BE không chạy: coi như chưa đăng nhập.
        if (!cancelled) setUser(null)
      })
      .finally(() => {
        if (!cancelled) setStatus('ready')
      })
    return () => {
      cancelled = true
    }
    // Chỉ chạy một lần lúc khởi động.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const onUnauthorized = () => setUser(null)
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
  }, [])

  const completeLogin = useCallback(
    (res: TokenResponse) => {
      setTokens(res.access_token, res.refresh_token)
      setLoggedOut(false)
      setUser(res.user)
      setStatus('ready')
      applyPreferences(res.user)
    },
    [applyPreferences],
  )

  const loginWithGoogle = useCallback(
    async (credential: string) => completeLogin(await googleLogin(credential)),
    [completeLogin],
  )

  const login = useCallback(async (email: string) => completeLogin(await devLogin(email)), [completeLogin])

  const logout = useCallback(() => {
    const refreshToken = getRefreshToken()
    // Thu hồi ở server để refresh token không dùng lại được; lỗi mạng không được chặn việc đăng xuất.
    if (refreshToken) revokeSession(refreshToken).catch(() => {})
    clearToken()
    setLoggedOut(true)
    setUser(null)
  }, [])

  const updateProfile = useCallback(async (patch: UserUpdate) => {
    const updated = await updateMe(patch)
    setUser(updated)
    return updated
  }, [])

  const replaceUser = useCallback((updated: UserProfile) => setUser(updated), [])

  const value = useMemo(
    () => ({ user, status, loginWithGoogle, login, logout, loggedOut, updateProfile, replaceUser }),
    [user, status, loginWithGoogle, login, logout, loggedOut, updateProfile, replaceUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
