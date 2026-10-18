/**
 * ============================================================================================
 *  LỜI CHÀO MỪNG NGƯỜI DÙNG MỚI — CHỈNH TAY Ở ĐÂY
 * ============================================================================================
 * Mỗi dòng là [cách gọi, lời nhắn]. Hộp thoại hiện:
 *     Tiêu đề:  "Chào {cách gọi} {tên}!"      ví dụ "Chào đại ca Minh!"
 *     Lời nhắn: {lời nhắn}
 * Mỗi lần mở hộp thoại chọn NGẪU NHIÊN một dòng (không phân biệt nam / nữ).
 * Muốn thêm / bớt / sửa câu: cứ sửa các dòng trong mảng dưới đây (không cần sửa chỗ khác).
 * Câu hiển thị thêm bên dưới lời nhắn ("Chúc mừng bạn đã gia nhập...") nằm ở i18n/vi.ts, khoá 'welcome.congrats'.
 */
const GREETINGS: [string, string][] = [
  ['đại ca', 'Đại ca đã tới, anh em đâu bắn pháo hoa lên! Có gì khó về học vụ cứ để mình lo.'],
  ['bé iu', 'Bé iu vào đây hỏi gì cũng được nha: điểm số, tín chỉ, học bổng... mình trả lời liền tay.'],
  ['cục dàng', 'Cục dàng của mình đây rồi! Hỏi điểm, hỏi tín chỉ, hỏi tốt nghiệp... mình không biết mệt đâu.'],
  ['baby', 'Baby ơi, chuyện học vụ để mình lo, bạn chỉ cần ăn no ngủ kỹ rồi lên điểm A thôi.'],
  ['sếp', 'Sếp cần xét học bổng hay tính điểm trung bình? Mình xin trình bày trong nháy mắt.'],
  ['bạn hiền', 'Bạn hiền ơi, vào đây mình chỉ đường cho, cảnh báo học tập hay điểm F gì cũng có cách.'],
  ['thần đồng', 'Thần đồng xuất hiện! Mình xin được làm trợ lý riêng cho thiên tài học vụ.'],
  ['đại gia điểm A', 'Đại gia điểm A đã đến! Mình xin phục vụ mọi thắc mắc từ A tới Z.'],
  ['đồng chí', 'Đồng chí đã gia nhập hội yêu quy chế, tiền đồ rạng ngời, điểm số bay cao!'],
  ['chiến thần', 'Chiến thần điểm A xuất hiện! Mình xin làm trợ lý riêng cho chiến thần.'],
  ['bé cưng', 'Bé cưng đừng lo quy chế dài dòng, mình đọc hết rồi, bạn chỉ việc hỏi thôi.'],
  ['bồ tèo', 'Bồ tèo ơi, hỏi gì về quy chế mình cũng có sẵn câu trả lời nhé.'],
]

/* ============================================================================================ */

export type Greeting = { title: string; message: string }

/**
 * Chọn ngẫu nhiên một lời chào cho `name`. `previous` là chỉ số vừa dùng (để không lặp lại liền nhau).
 * Trả về cả chỉ số đã chọn.
 */
export function pickGreeting(
  name: string,
  previous?: number,
  random: () => number = Math.random,
): { index: number; greeting: Greeting } {
  let index = Math.floor(random() * GREETINGS.length)
  if (previous !== undefined && GREETINGS.length > 1 && index === previous) index = (index + 1) % GREETINGS.length
  const [call, message] = GREETINGS[index]
  return { index, greeting: { title: `Chào ${call} ${name}!`, message } }
}
