import type { Gender } from './gender'

/**
 * ============================================================================================
 *  LỜI CHÀO MỪNG NGƯỜI DÙNG MỚI — CHỈNH TAY Ở ĐÂY
 * ============================================================================================
 * Mỗi dòng là [cách gọi, lời nhắn]. Hộp thoại hiện:
 *     Tiêu đề:  "Chào {cách gọi} {tên}!"      ví dụ "Chào đại ca Minh!"
 *     Lời nhắn: {lời nhắn}
 * Mỗi lần mở hộp thoại chọn NGẪU NHIÊN một dòng trong nhóm phù hợp với giới tính đoán được từ họ tên (xem lib/gender.ts).
 * Muốn thêm / bớt / sửa câu: cứ sửa các dòng trong ba mảng dưới đây (không cần sửa chỗ khác).
 * Câu hiển thị thêm bên dưới lời nhắn ("Chúc mừng bạn đã gia nhập...") nằm ở i18n/vi.ts, khoá 'welcome.congrats'.
 */

/** Nhóm cho NAM. */
const MALE: [string, string][] = [
  ['đại ca', 'Đại ca đã tới, anh em đâu bắn pháo hoa lên! Có gì khó về học vụ cứ để đàn em lo.'],
  ['anh zai', 'Anh zai vào đây hỏi gì cũng được nha: điểm số, tín chỉ, học bổng... em trả lời liền tay.'],
  ['sếp', 'Sếp cần xét học bổng hay tính điểm trung bình? Em xin trình bày trong nháy mắt.'],
  ['bro', 'Bro ơi, chuyện học vụ để em lo, bro chỉ cần ăn no ngủ kỹ rồi lên điểm A thôi.'],
  ['chiến thần', 'Chiến thần điểm A xuất hiện! Em xin làm trợ lý riêng cho chiến thần.'],
  ['đồng chí', 'Đồng chí đã gia nhập hội yêu quy chế, tiền đồ rạng ngời, điểm số bay cao!'],
]

/** Nhóm cho NỮ. */
const FEMALE: [string, string][] = [
  ['bé iu', 'Bé iu vào đây hỏi gì cũng được nha: điểm số, tín chỉ, học bổng... mình trả lời liền tay.'],
  ['chị đại', 'Chị đại đã tới, cả hội đứng dậy bắn pháo hoa! Có gì khó về học vụ cứ để em lo.'],
  ['công chúa', 'Công chúa điểm A đã đến! Chuyện học vụ rắc rối cứ để mình xử lý giúp bạn.'],
  ['nữ thần', 'Nữ thần giá lâm! Mình xin phục vụ mọi thắc mắc từ điểm số tới tốt nghiệp.'],
  ['bé cưng', 'Bé cưng đừng lo quy chế dài dòng, mình đọc hết rồi, bạn chỉ việc hỏi thôi.'],
  ['bà chủ', 'Bà chủ cần xét học bổng hay tính điểm trung bình? Mình xin trình bày ngay!'],
]

/** Nhóm TRUNG TÍNH: dùng khi không đoán được nam hay nữ (không dùng từ chỉ giới tính). */
const NEUTRAL: [string, string][] = [
  ['baby', 'Baby ơi, chuyện học vụ để mình lo, bạn chỉ cần ăn no ngủ kỹ rồi lên điểm A thôi.'],
  ['cục dàng', 'Cục dàng của mình đây rồi! Hỏi điểm, hỏi tín chỉ, hỏi tốt nghiệp... mình không biết mệt đâu.'],
  ['bạn hiền', 'Bạn hiền ơi, vào đây mình chỉ đường cho, cảnh báo học tập hay điểm F gì cũng có cách.'],
  ['thần đồng', 'Thần đồng xuất hiện! Mình xin được làm trợ lý riêng cho thiên tài học vụ.'],
  ['đại gia điểm A', 'Đại gia điểm A đã đến! Mình xin phục vụ mọi thắc mắc từ A tới Z.'],
  ['cậu chủ nhỏ', 'Cậu chủ nhỏ ơi, hỏi gì về quy chế mình cũng có sẵn câu trả lời nhé.'],
]

/* ============================================================================================ */

export type Greeting = { title: string; message: string }

const pool = (gender: Gender) => (gender === 'male' ? MALE : gender === 'female' ? FEMALE : NEUTRAL)

/**
 * Chọn lời chào cho `name` theo giới tính. `previous` là chỉ số vừa dùng ở nhóm đó (để không lặp lại liền nhau).
 * Trả về cả chỉ số đã chọn.
 */
export function pickGreeting(
  name: string,
  gender: Gender = 'unknown',
  previous?: number,
  random: () => number = Math.random,
): { index: number; greeting: Greeting } {
  const list = pool(gender)
  let index = Math.floor(random() * list.length)
  if (previous !== undefined && list.length > 1 && index === previous) index = (index + 1) % list.length
  const [call, message] = list[index]
  return { index, greeting: { title: `Chào ${call} ${name}!`, message } }
}
