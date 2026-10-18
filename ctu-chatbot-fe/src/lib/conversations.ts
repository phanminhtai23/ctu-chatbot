import { apiFetch, apiStream } from './api'

/** Một Điều của quy định mà câu trả lời đã dựa vào (bấm để xem trong PDF). */
export type SourceRef = { article: number; title: string }

/** Một trang web mà câu trả lời (về chuyện ngoài quy chế) đã tra cứu. */
export type WebSourceRef = { title: string; url: string }

/** Nguồn BE trả về: có `article` là Điều của quy chế, có `url` là trang web. */
export type AnySourceRef = { article?: number | null; title: string; url?: string | null }

export const articleSources = (sources: AnySourceRef[] = []): SourceRef[] =>
  sources.filter((s): s is SourceRef => typeof s.article === 'number')

/** Chỉ nhận http(s): không để `javascript:` hay scheme lạ lọt vào href. */
export const webSources = (sources: AnySourceRef[] = []): WebSourceRef[] =>
  sources.filter((s): s is WebSourceRef => typeof s.url === 'string' && /^https?:\/\//i.test(s.url))

export type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string | null
  /** Thời gian chờ chatbot trả lời (giây); chỉ tin của bot, tin cũ có thể không có */
  duration_seconds: number | null
  /** Tham chiếu quy định; chỉ tin của bot, tin cũ có thể không có */
  sources?: AnySourceRef[]
  /** Câu trả lời có sẵn của câu hỏi gợi ý (trả ngay, không gọi LLM) */
  cached?: boolean
}

export type Conversation = {
  id: string
  title: string // rỗng nếu chưa có tin nhắn nào
  created_at: string
  updated_at: string
}

export type ConversationDetail = Conversation & { messages: ChatMessage[] }

export const listConversations = (): Promise<Conversation[]> => apiFetch('/api/v1/conversations')

export const createConversation = (): Promise<Conversation> => apiFetch('/api/v1/conversations', { method: 'POST' })

export const getConversation = (id: string): Promise<ConversationDetail> => apiFetch(`/api/v1/conversations/${id}`)

export const renameConversation = (id: string, title: string): Promise<Conversation> =>
  apiFetch(`/api/v1/conversations/${id}`, { method: 'PATCH', body: JSON.stringify({ title }) })

export const deleteConversation = (id: string): Promise<null> =>
  apiFetch(`/api/v1/conversations/${id}`, { method: 'DELETE' })

/** Lỗi trong lúc stream; `code` khớp với BE: LLM_RATE_LIMITED | SERVER_BUSY | LLM_NOT_CONFIGURED | LLM_ERROR | INTERNAL_ERROR | STREAM_INTERRUPTED */
export class ChatStreamError extends Error {
  code: string
  retryAfter?: number

  constructor(code: string, retryAfter?: number) {
    super(code)
    this.name = 'ChatStreamError'
    this.code = code
    this.retryAfter = retryAfter
  }
}

export type StreamHandlers = {
  /** Server đang đông: lượt này xếp hàng, `position` = vị trí trong hàng (1 = kế tiếp) */
  onQueued?: (position: number) => void
  onStart: (userMessage: ChatMessage) => void
  onToken: (text: string) => void
  onDone: (result: { assistant_message: ChatMessage; conversation: Conversation | null }) => void
}

/** Đọc Server-Sent Events: mỗi khối cách nhau bằng dòng trống, có dòng `event:` và `data:` (JSON). */
function parseBlock(block: string): { event: string; data: unknown } | null {
  let event = 'message'
  const dataLines: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
  }
  if (dataLines.length === 0) return null
  return { event, data: JSON.parse(dataLines.join('\n')) }
}

/**
 * Gửi tin nhắn và nhận câu trả lời theo từng đoạn.
 * Ném ChatStreamError nếu server báo lỗi hoặc stream đứt giữa chừng; ném ApiError (404/422/401...)
 * nếu bị từ chối trước khi stream bắt đầu; AbortError nếu `signal` bị huỷ.
 */
export async function streamMessage(
  conversationId: string,
  content: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const res = await apiStream(`/api/v1/conversations/${conversationId}/messages/stream`, {
    method: 'POST',
    body: JSON.stringify({ content }),
    signal,
  })
  if (!res.body) throw new ChatStreamError('STREAM_INTERRUPTED')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finished = false

  const dispatch = (block: string) => {
    const parsed = parseBlock(block)
    if (!parsed) return
    const data = parsed.data as Record<string, unknown>
    if (parsed.event === 'queued') handlers.onQueued?.(Number(data.position))
    else if (parsed.event === 'start') handlers.onStart(data.user_message as ChatMessage)
    else if (parsed.event === 'token') handlers.onToken(data.text as string)
    else if (parsed.event === 'done') {
      finished = true
      handlers.onDone(data as { assistant_message: ChatMessage; conversation: Conversation | null })
    } else if (parsed.event === 'error') {
      throw new ChatStreamError(String(data.code), typeof data.retry_after === 'number' ? data.retry_after : undefined)
    }
  }

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
    let boundary: number
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      dispatch(block)
    }
  }
  if (buffer.trim()) dispatch(buffer)
  if (!finished) throw new ChatStreamError('STREAM_INTERRUPTED')
}
