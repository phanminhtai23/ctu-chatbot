import type { TranslationKey } from '../i18n/vi'
import { ApiError } from './api'
import { ChatStreamError } from './conversations'
import { fillTemplate, parseRateLimit } from './format'
import { nextWarning } from './warnings'

/**
 * Phân loại lỗi khi gửi tin để hiện hộp thoại phù hợp:
 * - rate: người dùng nhắn quá nhanh (vượt CHAT_RATE_LIMIT);
 * - busy: hệ thống đang đông / hết hạn mức LLM / người khác đang chat trong cuộc trò chuyện này, thử lại sau;
 * - error: lỗi khác (LLM lỗi, mất mạng, chỉ có quyền xem...);
 * - warning: tin nhắn bị chặn vì chửi thề / lời lẽ thô tục (kèm tiêu đề riêng `title`).
 */
export type ChatErrorInfo = { kind: 'rate' | 'busy' | 'error' | 'warning'; message: string; retryAfter?: number; title?: string }

type T = (key: TranslationKey) => string

export function classifyChatError(err: unknown, t: T): ChatErrorInfo {
  if (err instanceof ChatStreamError) {
    switch (err.code) {
      case 'LLM_RATE_LIMITED':
        return { kind: 'busy', message: t('chat.errRateLimited') + (err.retryAfter ?? '') + t('chat.errRateLimitedSuffix'), retryAfter: err.retryAfter }
      case 'SERVER_BUSY':
        return { kind: 'busy', message: t('chat.errBusy'), retryAfter: err.retryAfter }
      case 'CONVERSATION_BUSY':
        return { kind: 'busy', message: t('chat.errConvBusy') }
      case 'LLM_NOT_CONFIGURED':
        return { kind: 'error', message: t('chat.errNotConfigured') }
      case 'STREAM_INTERRUPTED':
        return { kind: 'error', message: t('chat.errInterrupted') }
      default:
        return { kind: 'error', message: t('chat.errLlm') }
    }
  }
  if (err instanceof ApiError) {
    const retry = /"retry_after":\s*(\d+)/.exec(err.message)
    const retryAfter = retry ? Number(retry[1]) : undefined
    if (err.status === 422 && err.message.includes('PROFANITY')) {
      const warning = nextWarning()
      return { kind: 'warning', title: warning.title, message: warning.message }
    }
    if (err.status === 403 && err.message.includes('READ_ONLY')) return { kind: 'error', message: t('chat.errReadOnly') }
    if (err.status === 409 && err.message.includes('CONVERSATION_BUSY')) return { kind: 'busy', message: t('chat.errConvBusy') }
    if (err.status === 503 && err.message.includes('SERVER_BUSY')) return { kind: 'busy', message: t('chat.errBusy'), retryAfter }
    if (err.status === 429 && err.message.includes('TURN_IN_PROGRESS')) return { kind: 'busy', message: t('chat.errTurnInProgress') }
    if (err.status === 429) {
      const info = parseRateLimit(err.message)
      // Hết lượt trong ngày: không có đồng hồ đếm ngược (chờ tới cả chục giờ), nói rõ là hẹn ngày mai.
      if (info?.unit === 'd') return { kind: 'rate', message: t('chat.errDailyLimit') }
      return {
        kind: 'rate',
        retryAfter,
        message: info
          ? fillTemplate(t('chat.errTooManyMessagesLimit'), { limit: info.limit, amount: info.amount, unit: t(`chat.unit.${info.unit}` as TranslationKey) })
          : t('chat.errTooManyMessages'),
      }
    }
    return { kind: 'error', message: t('chat.errLlm') }
  }
  return { kind: 'error', message: t('chat.errNetwork') }
}
