import { UNAUTHORIZED_EVENT, clearToken, getRefreshToken, getToken, setTokens } from './auth'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

const isAuthPath = (path: string) => path.startsWith('/api/v1/auth/')

function send(path: string, init: RequestInit) {
  const token = getToken()
  const headers = new Headers(init.headers)
  if (!headers.has('Content-Type') && init.body) headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  return fetch(`${API_BASE_URL}${path}`, { ...init, headers })
}

type RefreshOutcome = 'ok' | 'rejected' | 'error'

async function refreshSession(): Promise<RefreshOutcome> {
  const used = getRefreshToken()
  if (!used) return 'rejected'
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: used }),
    })
    if (res.ok) {
      const data = (await res.json()) as { access_token: string; refresh_token: string }
      setTokens(data.access_token, data.refresh_token)
      return 'ok'
    }
    // Bị từ chối, nhưng nếu tab khác vừa làm mới xong (token trong localStorage đã đổi) thì phiên vẫn sống.
    return getRefreshToken() !== used ? 'ok' : 'rejected'
  } catch {
    return 'error' // mất mạng / BE không chạy: giữ nguyên phiên, đừng đăng xuất
  }
}

// Nhiều request cùng gặp 401 thì chỉ làm mới một lần (refresh token dùng một lần rồi đổi).
let refreshing: Promise<RefreshOutcome> | null = null
function refreshOnce() {
  refreshing ??= refreshSession().finally(() => {
    refreshing = null
  })
  return refreshing
}

/** Gửi request kèm access token; gặp 401 thì tự làm mới phiên rồi thử lại một lần. */
async function sendWithRefresh(path: string, init: RequestInit): Promise<Response> {
  let res = await send(path, init)

  if (res.status === 401 && !isAuthPath(path)) {
    const outcome = getRefreshToken() ? await refreshOnce() : 'rejected'
    if (outcome === 'ok') {
      res = await send(path, init) // thử lại một lần với access token mới
    } else if (outcome === 'rejected' && getToken()) {
      clearToken()
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
    }
  }
  return res
}

async function ensureOk(res: Response): Promise<Response> {
  if (!res.ok) throw new ApiError(res.status, `API error ${res.status}: ${await res.text()}`)
  return res
}

export async function apiFetch(path: string, init: RequestInit = {}) {
  const res = await ensureOk(await sendWithRefresh(path, init))
  if (res.status === 204) return null
  return res.json()
}

/** Như apiFetch nhưng trả về Response chưa đọc body, để đọc stream (Server-Sent Events). */
export async function apiStream(path: string, init: RequestInit = {}): Promise<Response> {
  return ensureOk(await sendWithRefresh(path, init))
}
