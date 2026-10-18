import { apiFetch } from './api'

/** Câu hỏi gợi ý: gửi đúng nội dung này vào chat thì nhận câu trả lời có sẵn (không gọi LLM). */
export type Suggestion = { id: string; category: string; question: string }

let cached: Promise<Suggestion[]> | null = null

/** Danh sách câu hỏi gợi ý (công khai); chỉ tải một lần cho cả phiên. */
export function getSuggestions(): Promise<Suggestion[]> {
  cached ??= (apiFetch('/api/v1/suggestions') as Promise<Suggestion[]>).catch((err) => {
    cached = null // lần sau thử lại
    throw err
  })
  return cached
}
