/** Thời gian chờ: dấu phẩy thập phân kiểu Việt Nam, ví dụ "10,9s". */
export function formatSeconds(seconds: number): string {
  const number = new Intl.NumberFormat('vi-VN', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(seconds)
  return `${number}s`
}
