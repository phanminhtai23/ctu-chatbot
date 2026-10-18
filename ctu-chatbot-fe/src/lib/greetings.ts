/** Lời chào mừng người dùng mới: hài hài, chọn ngẫu nhiên mỗi lần (cố tránh lặp lại câu vừa rồi). */
export type Greeting = { title: string; message: string }

const make = (call: string, message: string) => (name: string): Greeting => ({ title: `Chào ${call} ${name}!`, message })

const GREETINGS = [
  make('đại ca', 'Đại ca đã tới, anh em đâu bắn pháo hoa lên! Có gì khó về học vụ cứ để đàn em lo.'),
  make('bé iu', 'Bé iu vào đây hỏi gì cũng được nha: điểm số, tín chỉ, học bổng... mình trả lời liền tay.'),
  make('cục dàng', 'Cục dàng của mình đây rồi! Hỏi điểm, hỏi tín chỉ, hỏi tốt nghiệp... mình không biết mệt đâu.'),
  make('baby', 'Baby ơi, chuyện học vụ để mình lo, bạn chỉ cần ăn no ngủ kỹ rồi lên điểm A thôi.'),
  make('sếp', 'Sếp cần xét học bổng hay tính điểm trung bình? Mình xin trình bày trong nháy mắt.'),
  make('bé cưng', 'Bé cưng đừng lo quy chế dài dòng, mình đọc hết rồi, bạn chỉ việc hỏi thôi.'),
  make('đồng chí', 'Đồng chí đã gia nhập hội yêu quy chế, tiền đồ rạng ngời, điểm số bay cao!'),
  make('thần đồng', 'Thần đồng xuất hiện! Mình xin được làm trợ lý riêng cho thiên tài học vụ.'),
  make('bạn hiền', 'Bạn hiền ơi, vào đây mình chỉ đường cho, cảnh báo học tập hay điểm F gì cũng có cách.'),
  make('đại gia điểm A', 'Đại gia điểm A đã đến! Mình xin phục vụ mọi thắc mắc từ A tới Z.'),
]

export const GREETING_COUNT = GREETINGS.length

/** Chọn một lời chào cho `name`; `previous` là chỉ số vừa dùng (để không lặp lại liền nhau). Trả về cả chỉ số đã chọn. */
export function pickGreeting(name: string, previous?: number, random: () => number = Math.random): { index: number; greeting: Greeting } {
  let index = Math.floor(random() * GREETINGS.length)
  if (previous !== undefined && GREETINGS.length > 1 && index === previous) index = (index + 1) % GREETINGS.length
  return { index, greeting: GREETINGS[index](name) }
}
