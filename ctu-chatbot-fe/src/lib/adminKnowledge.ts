import { ApiError, apiFetch } from './api'

export type KnowledgeState = 'embedded' | 'pending'

export type KnowledgeEntry = {
  id: string
  question: string
  answer: string
  /** embedded = đã vào vector DB và chưa sửa; pending = chưa embedding hoặc đã sửa sau lần embedding gần nhất */
  status: KnowledgeState
  embedded_at: string | null
  created_at: string
  updated_at: string | null
}

export type KnowledgeStats = {
  total: number
  embedded: number
  pending: number
  /** Số vector thật sự trong ChromaDB (null = kho vector không dùng được) */
  vector_count: number | null
}

export type KnowledgeList = { total: number; items: KnowledgeEntry[]; stats: KnowledgeStats; min_score: number }

export type KnowledgeHit = { id: string; question: string; answer: string; score: number; used: boolean }
export type KnowledgeTest = { min_score: number; strong_score: number; hits: KnowledgeHit[] }

export const MAX_QUESTION = 500
export const MAX_ANSWER = 4000

export function listKnowledge(q = '', state: 'all' | KnowledgeState = 'all'): Promise<KnowledgeList> {
  const params = new URLSearchParams({ state, limit: '200' })
  if (q.trim()) params.set('q', q.trim())
  return apiFetch(`/api/v1/admin/knowledge?${params}`)
}

export const createEntry = (question: string, answer: string): Promise<KnowledgeEntry> =>
  apiFetch('/api/v1/admin/knowledge', { method: 'POST', body: JSON.stringify({ question, answer }) })

export const updateEntry = (id: string, question: string, answer: string): Promise<KnowledgeEntry> =>
  apiFetch(`/api/v1/admin/knowledge/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify({ question, answer }) })

export const deleteEntry = (id: string): Promise<null> =>
  apiFetch(`/api/v1/admin/knowledge/${encodeURIComponent(id)}`, { method: 'DELETE' })

export const embedPending = (force = false): Promise<{ embedded: number; stats: KnowledgeStats }> =>
  apiFetch(`/api/v1/admin/knowledge/embed${force ? '?force=true' : ''}`, { method: 'POST' })

export const embedOne = (id: string): Promise<{ embedded: number; stats: KnowledgeStats }> =>
  apiFetch(`/api/v1/admin/knowledge/${encodeURIComponent(id)}/embed`, { method: 'POST' })

export const testQuery = (query: string): Promise<KnowledgeTest> =>
  apiFetch('/api/v1/admin/knowledge/test', { method: 'POST', body: JSON.stringify({ query }) })

const CODES = ['DUPLICATE_QUESTION', 'EMBEDDING_UNAVAILABLE', 'KNOWLEDGE_UNAVAILABLE', 'EMPTY_FIELD', 'TOO_LONG'] as const
export type KnowledgeErrorCode = (typeof CODES)[number] | 'UNKNOWN'

export function knowledgeErrorCode(err: unknown): KnowledgeErrorCode {
  if (err instanceof ApiError) return CODES.find((c) => err.message.includes(c)) ?? 'UNKNOWN'
  return 'UNKNOWN'
}
