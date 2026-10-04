import { apiFetch } from './api'
import type { FeedbackCategory, FeedbackType } from './feedback'

export type FeedbackStatus = 'new' | 'reviewed' | 'resolved'

export const feedbackStatuses: FeedbackStatus[] = ['new', 'reviewed', 'resolved']

export type AdminFeedback = {
  id: string
  type: FeedbackType
  category: FeedbackCategory
  message: string
  user_email: string
  created_at: string
  status: FeedbackStatus
  conversation_id: string | null
  message_id: string | null
  /** Snapshot do BE gắn theo message_id; null nếu feedback chung hoặc chưa có. */
  question: string | null
  answer: string | null
}

export async function listFeedback(): Promise<AdminFeedback[]> {
  return apiFetch('/api/v1/admin/feedback')
}

export async function updateFeedbackStatus(id: string, status: FeedbackStatus): Promise<void> {
  await apiFetch(`/api/v1/admin/feedback/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  })
}
