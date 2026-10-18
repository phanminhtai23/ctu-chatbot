/** Thời gian chờ: dấu phẩy thập phân kiểu Việt Nam, ví dụ "10,9s". */
export function formatSeconds(seconds: number): string {
  const number = new Intl.NumberFormat('vi-VN', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(seconds)
  return `${number}s`
}

/** Thay {tên} trong câu bằng giá trị tương ứng. */
export const fillTemplate = (template: string, vars: Record<string, string | number>) =>
  template.replace(/\{(\w+)\}/g, (_, key: string) => String(vars[key] ?? ''))

/** Dung lượng dễ đọc, dấu thập phân kiểu Việt Nam: "850 KB", "3,2 MB". */
export function formatBytes(bytes: number): string {
  const number = (n: number) => new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 }).format(n)
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${number(bytes / 1024)} KB`
  return `${number(bytes / (1024 * 1024))} MB`
}

export type RateLimitInfo = { limit: number; amount: number; unit: 's' | 'm' | 'h' | 'd' }

/** Đọc giới hạn chat từ lỗi 429 của server ("tối đa N tin trong M phút"); null nếu lỗi không kèm thông tin này. */
export function parseRateLimit(message: string): RateLimitInfo | null {
  const match = /"limit":\s*(\d+).*?"amount":\s*(\d+).*?"unit":\s*"([smhd])"/.exec(message)
  return match ? { limit: Number(match[1]), amount: Number(match[2]), unit: match[3] as 's' | 'm' | 'h' | 'd' } : null
}
