import { apiFetch } from './api'

export type FeedbackType = 'answer_issue' | 'general'

export type FeedbackCategory =
  | 'wrong_answer'
  | 'wrong_citation'
  | 'outdated'
  | 'bug'
  | 'suggestion'
  | 'other'

export type FeedbackPayload = {
  type: FeedbackType
  category: FeedbackCategory
  message: string
  conversation_id: string | null
  message_id: string | null
}

export const FEEDBACK_MAX_LENGTH = 1000

export const categoriesByType: Record<FeedbackType, FeedbackCategory[]> = {
  answer_issue: ['wrong_answer', 'wrong_citation', 'outdated', 'other'],
  general: ['bug', 'suggestion', 'other'],
}

export async function submitFeedback(payload: FeedbackPayload): Promise<{ id: string }> {
  return apiFetch('/api/v1/feedback', { method: 'POST', body: JSON.stringify(payload) })
}
