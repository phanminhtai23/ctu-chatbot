/**
 * Đoán nam / nữ từ HỌ TÊN tiếng Việt để chào cho đúng (đăng nhập Google chỉ cho tên, không có giới tính).
 * Chỉ là đoán theo tên đệm + tên gọi nên không chắc chắn 100%: không đủ căn cứ (hoặc tên dùng cho cả hai giới) thì trả về
 * 'unknown' và dùng lời chào trung tính. Danh sách bên dưới sửa tuỳ ý (viết thường, CÓ dấu như tên thật; tên không dấu
 * như phần trước @ của email cũng được hiểu, khi đó các tên chỉ khác nhau ở dấu như "Dung/Dũng" sẽ triệt tiêu nhau).
 */
export type Gender = 'male' | 'female' | 'unknown'

/** Tên đệm gần như chắc chắn: "Thị" -> nữ, "Văn" -> nam (điểm mạnh). */
const STRONG_FEMALE_MIDDLE = ['thị']
const STRONG_MALE_MIDDLE = ['văn']

/** Tên đệm thường gặp ở nữ / nam (điểm nhẹ). */
const FEMALE_MIDDLE = ['ngọc', 'kim', 'mỹ', 'thùy', 'thuỷ', 'bích', 'hồng', 'diễm', 'tường', 'phương', 'mai', 'lan', 'hoài', 'nhã', 'khánh']
const MALE_MIDDLE = ['hữu', 'đức', 'quốc', 'trọng', 'đình', 'công', 'gia', 'hoàng', 'mạnh', 'tiến', 'quang', 'bá', 'nhật', 'đăng', 'trung', 'xuân', 'minh', 'anh']

/** Tên gọi (từ cuối của họ tên) thường gặp ở nữ / nam (điểm vừa). */
const FEMALE_GIVEN = [
  'lan', 'hoa', 'hương', 'linh', 'ngọc', 'trang', 'thảo', 'mai', 'châu', 'my', 'nhi', 'phương', 'quỳnh', 'thủy', 'thuỷ', 'trinh', 'uyên', 'vy',
  'yến', 'hà', 'hạnh', 'liên', 'loan', 'nga', 'nhung', 'oanh', 'thu', 'trâm', 'diễm', 'hân', 'hiền', 'ly', 'nguyệt', 'sương', 'tuyết', 'vân',
  'vi', 'dung', 'duyên', 'hằng', 'huệ', 'kiều', 'ngân', 'thương', 'thy', 'ánh', 'bình', 'chi', 'đào', 'hồng', 'lệ', 'my', 'như', 'phượng',
  'quyên', 'tâm', 'thanh', 'thúy', 'trà', 'tú', 'xuân',
]
const MALE_GIVEN = [
  'nam', 'hưng', 'huy', 'khoa', 'long', 'quân', 'sơn', 'tài', 'tuấn', 'tùng', 'vinh', 'đức', 'bảo', 'hiếu', 'khang', 'kiệt', 'lộc', 'nghĩa',
  'phát', 'phong', 'quốc', 'tân', 'thắng', 'thiện', 'toàn', 'trung', 'trí', 'vũ', 'việt', 'đạt', 'duy', 'hải', 'hậu', 'hoàng', 'hòa', 'bách',
  'cường', 'dân', 'đăng', 'đông', 'hào', 'hiệp', 'khải', 'lâm', 'lập', 'luân', 'mạnh', 'minh', 'nhật', 'phước', 'quang', 'quyền', 'sang',
  'thái', 'thịnh', 'thuận', 'tiến', 'tín', 'trường', 'tuyên', 'vương', 'ân', 'cảnh', 'dũng', 'đại', 'hùng', 'huân', 'khôi', 'kiên', 'thành',
  'bình', 'tâm', 'anh', 'phúc', 'hoà', 'nhân', 'danh', 'đăng', 'thông', 'trọng', 'văn', 'nguyên', 'khánh', 'tú', 'thanh',
]

const strip = (text: string) =>
  text
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/đ/g, 'd')
    .replace(/Đ/g, 'D')

/** Tách thành các từ viết thường (giữ dấu nếu có). */
const words = (text: string) =>
  text
    .normalize('NFC')
    .toLowerCase()
    .split(/[^\p{L}]+/u)
    .filter(Boolean)

/** Từ `token` có thuộc `list` không? Tên có dấu thì so đúng dấu; tên không dấu (từ email) thì so bản đã bỏ dấu của danh sách. */
const inList = (token: string, list: string[]) => {
  const plain = strip(token) === token
  return list.some((item) => (plain ? strip(item) === token : item === token))
}

function givenScore(given: string): number {
  const female = inList(given, FEMALE_GIVEN)
  const male = inList(given, MALE_GIVEN)
  if (female === male) return 0 // không thấy trong danh sách nào, hoặc tên dùng cho cả hai giới
  return female ? -2 : 2
}

/** Đoán giới tính từ họ tên (hoặc phần trước @ của email, ví dụ "nguyen.thi.lan"). */
export function guessGender(fullName: string): Gender {
  const tokens = words(fullName)
  if (tokens.length === 0) return 'unknown'
  const given = tokens[tokens.length - 1]
  let score = givenScore(given) // dương = nam, âm = nữ
  // Tên đệm: các từ ở giữa (bỏ họ ở đầu và tên gọi ở cuối).
  for (const m of tokens.slice(1, -1)) {
    if (inList(m, STRONG_FEMALE_MIDDLE)) score -= 3
    else if (inList(m, STRONG_MALE_MIDDLE)) score += 3
    else if (inList(m, FEMALE_MIDDLE)) score -= 1
    else if (inList(m, MALE_MIDDLE)) score += 1
  }
  return score >= 2 ? 'male' : score <= -2 ? 'female' : 'unknown'
}
