/**
 * GIF dễ thương cho các hộp thoại vui: chỉ nạp ĐƯỜNG DẪN (Vite tự gom mọi file .gif trong thư mục), trình duyệt chỉ tải
 * đúng file được chọn khi hộp thoại hiện ra. Thêm GIF mới = bỏ file vào thư mục tương ứng, không cần sửa code.
 */

const toList = (modules: Record<string, string>) => Object.keys(modules).sort().map((k) => modules[k])

/** GIF cho hộp thoại "bị giới hạn tốc độ / chat bị lỗi". */
export const errorGifs = toList(
  import.meta.glob<string>('../assets/exceed_rate_limit_gifs/*.gif', { eager: true, query: '?url', import: 'default' }),
)

/** GIF cho hộp thoại chào mừng người dùng mới. */
export const welcomeGifs = toList(
  import.meta.glob<string>('../assets/welcome_gifs/*.gif', { eager: true, query: '?url', import: 'default' }),
)

/** Chọn ngẫu nhiên một GIF, cố tránh lặp lại GIF vừa hiện (`previous`). Thư mục trống thì trả về null. */
export function pickGif(pool: string[], previous?: string | null, random: () => number = Math.random): string | null {
  if (pool.length === 0) return null
  const choices = pool.length > 1 ? pool.filter((g) => g !== previous) : pool
  return choices[Math.floor(random() * choices.length)]
}
