type Props = {
  size?: number
  /** Màu nền hình thoi: dùng navy-dark trên nền navy, ngược lại trên sidebar */
  fill?: string
}

// Huy hiệu tạm — thay bằng logo thật của trường khi có file.
export default function Logo({ size = 52, fill = '#0E346F' }: Props) {
  return (
    <svg width={size} height={size} viewBox="0 0 52 52" role="img" aria-label="Biểu tượng CTU">
      <polygon points="26,2 50,26 26,50 2,26" fill={fill} stroke="#22B8F0" strokeWidth="3" />
      <circle cx="26" cy="26" r="11" fill="none" stroke="#FBC500" strokeWidth="3" strokeDasharray="4 2.5" />
      <path d="M26 17 C30 22 29 26 26 30 C23 26 22 22 26 17Z" fill="#F70004" />
      <rect x="21" y="31" width="10" height="5" fill="#FFFFFF" />
    </svg>
  )
}
