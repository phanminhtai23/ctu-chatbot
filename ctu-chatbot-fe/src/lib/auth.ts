const ACCESS_KEY = 'ctu-token' // access token (JWT, sống 7 ngày)
const REFRESH_KEY = 'ctu-refresh-token' // refresh token (sống 30 ngày)

function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

export const getToken = () => read(ACCESS_KEY)
export const getRefreshToken = () => read(REFRESH_KEY)

export function setTokens(accessToken: string, refreshToken: string) {
  try {
    localStorage.setItem(ACCESS_KEY, accessToken)
    localStorage.setItem(REFRESH_KEY, refreshToken)
  } catch {
    // localStorage bị chặn — phiên chỉ sống đến khi tải lại trang.
  }
}

export function clearToken() {
  try {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  } catch {
    // bỏ qua
  }
}

/** Bắn khi phiên không thể khôi phục nữa (refresh token hết hạn/bị thu hồi) để AuthProvider đăng xuất. */
export const UNAUTHORIZED_EVENT = 'ctu:unauthorized'
