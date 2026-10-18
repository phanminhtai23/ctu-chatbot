/** Ngày dạng ISO (yyyy-mm-dd, dùng với server) <-> chữ dd/mm/yyyy (người dùng nhập và đọc). */

export function isoToDisplay(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  return m ? `${m[3]}/${m[2]}/${m[1]}` : ''
}

/** Tự chèn dấu "/" khi gõ: chỉ giữ chữ số, tối đa 8 (ddmmyyyy). */
export function maskDate(raw: string): string {
  const digits = raw.replace(/\D/g, '').slice(0, 8)
  if (digits.length <= 2) return digits
  if (digits.length <= 4) return `${digits.slice(0, 2)}/${digits.slice(2)}`
  return `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4)}`
}

/** "dd/mm/yyyy" -> "yyyy-mm-dd"; null nếu chưa đủ / không phải ngày có thật (ví dụ 31/02). */
export function displayToIso(text: string): string | null {
  const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(text)
  if (!m) return null
  const [day, month, year] = [Number(m[1]), Number(m[2]), Number(m[3])]
  const date = new Date(Date.UTC(year, month - 1, day))
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return null
  return `${m[3]}-${m[2]}-${m[1]}`
}
