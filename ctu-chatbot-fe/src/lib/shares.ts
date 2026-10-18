import { ApiError, apiFetch } from './api'
import type { Access, ChatMessage } from './conversations'

export type SharePermission = 'view' | 'chat'

export type SharedPerson = {
  id: string
  email: string
  name: string | null
  /** false = chưa từng đăng nhập: chỉ là lời mời, người đó đăng nhập là thấy */
  registered: boolean
  permission: SharePermission
  created_at: string | null
}

export type ShareLink = { token: string; permission: SharePermission; created_at: string | null }

export type ShareState = { link: ShareLink | null; people: SharedPerson[] }

export type Suggestion = { email: string; name: string }

export type SharedWithMe = {
  id: string
  title: string
  owner_name: string
  permission: SharePermission
  updated_at: string | null
}

export type SharedLinkView = {
  title: string
  owner_name: string
  permission: SharePermission
  /** Người đang xem có chat tiếp được không (liên kết cho phép chat và đã đăng nhập bằng email CTU) */
  can_chat: boolean
  is_owner: boolean
  updated_at: string | null
  messages: ChatMessage[]
}

const base = (conversationId: string) => `/api/v1/conversations/${encodeURIComponent(conversationId)}/shares`

export const getShares = (conversationId: string): Promise<ShareState> => apiFetch(base(conversationId))

export const addPerson = (conversationId: string, email: string, permission: SharePermission): Promise<SharedPerson> =>
  apiFetch(`${base(conversationId)}/people`, { method: 'POST', body: JSON.stringify({ email, permission }) })

export const updatePerson = (conversationId: string, shareId: string, permission: SharePermission): Promise<SharedPerson> =>
  apiFetch(`${base(conversationId)}/people/${encodeURIComponent(shareId)}`, { method: 'PATCH', body: JSON.stringify({ permission }) })

export const removePerson = (conversationId: string, shareId: string): Promise<null> =>
  apiFetch(`${base(conversationId)}/people/${encodeURIComponent(shareId)}`, { method: 'DELETE' })

export const putLink = (conversationId: string, permission: SharePermission, regenerate = false): Promise<ShareLink> =>
  apiFetch(`${base(conversationId)}/link`, { method: 'PUT', body: JSON.stringify({ permission, regenerate }) })

export const deleteLink = (conversationId: string): Promise<null> => apiFetch(`${base(conversationId)}/link`, { method: 'DELETE' })

export const suggestPeople = (q: string): Promise<Suggestion[]> => apiFetch(`/api/v1/shares/suggestions?q=${encodeURIComponent(q)}`)

export const listSharedWithMe = (): Promise<SharedWithMe[]> => apiFetch('/api/v1/shares/with-me')

export const getSharedLink = (token: string): Promise<SharedLinkView> => apiFetch(`/api/v1/shared-links/${encodeURIComponent(token)}`)

export const sharedLinkStreamPath = (token: string) => `/api/v1/shared-links/${encodeURIComponent(token)}/messages/stream`

/** Liên kết đầy đủ để người nhận mở: trang /s/<token> của chính giao diện này. */
export const shareUrl = (token: string) => `${window.location.origin}/s/${token}`

/** Liên kết tới chính cuộc trò chuyện (trang chat): người được mời theo email mở liên kết này, đăng nhập bằng đúng email là vào được. */
export const chatUrl = (conversationId: string) => `${window.location.origin}/chat/${conversationId}`

/** Mã lỗi BE trả về trong `detail` (INVALID_EMAIL, EMAIL_NOT_ALLOWED, CANNOT_SHARE_WITH_SELF, READ_ONLY, ...). */
export function shareErrorCode(err: unknown): string {
  if (!(err instanceof ApiError)) return 'NETWORK'
  const match = /"detail":\s*"([A-Z_]+)/.exec(err.message)
  return match ? match[1] : `HTTP_${err.status}`
}

export type { Access }
