/**
 * ============================================================================================
 *  LỜI CẢNH BÁO KHI NGƯỜI DÙNG CHỬI THỀ / NÓI TỤC — CHỈNH TAY Ở ĐÂY
 * ============================================================================================
 * Mỗi dòng là [tiêu đề, lời nhắn]. Mỗi lần bị chặn chọn NGẪU NHIÊN một dòng (cố không lặp liền nhau).
 * Muốn thêm / bớt / sửa câu: cứ sửa mảng dưới đây (không cần sửa chỗ khác).
 */
const WARNINGS: [string, string][] = [
  ['Ây da, nhẹ nhàng thôi nè!', 'Bạn ơi, mình là chatbot hiền lành, nghe lời nặng là mình buồn lắm đó 🥺 Mình nói chuyện lịch sự với nhau nhé!'],
  ['Khoan khoan bạn ơi!', 'Lời lẽ hơi mạnh rồi nha 😅 Hít một hơi thật sâu, rồi hỏi mình về học vụ nhẹ nhàng hơn nhé!'],
  ['Cho mình xin lỗi cái!', 'Mình không trả lời được những câu có lời lẽ thô tục đâu 🙏 Bạn đổi cách nói giúp mình, mình sẽ hỗ trợ ngay!'],
  ['Bình tĩnh, bình tĩnh nào!', 'Thi cử, điểm số có căng thẳng cỡ nào cũng đừng nóng nha 🍵 Uống miếng nước rồi hỏi lại mình nhé!'],
  ['Ui, từ này không ổn đâu!', 'Tin nhắn của bạn có từ ngữ không phù hợp nên mình xin phép không xử lý nha 🙈 Bạn nhắn lại lịch sự hơn giúp mình!'],
  ['Bạn ơi, lịch sự một chút nha!', 'Ở đây ai cũng là sinh viên CTU thân thiện hết 🌸 Mình cùng nói chuyện văn minh để mình giúp bạn tốt nhất nhé!'],
  ['Thẻ vàng nhẹ nhàng nè!', 'Mình tặng bạn một thẻ vàng nhỏ vì lời lẽ chưa đẹp 🟨 Lần sau nói nhẹ nhàng hơn thì mình trả lời liền!'],
  ['Mình nghe thấy rồi nha!', 'Có vẻ bạn đang bực chuyện gì đó 😌 Kể mình nghe bằng lời nhẹ nhàng hơn, biết đâu mình giúp được!'],
  ['Từ từ nào bạn hiền!', 'Chatbot nhỏ bé này sợ lời nặng lắm 🥹 Đổi sang cách nói dễ thương hơn rồi mình trả lời ngay nhé!'],
  ['Ơ kìa, nói tục là mình dỗi đó!', 'Mình dỗi 3 giây thôi 😤 Bạn nhắn lại tử tế là mình hết dỗi và giải đáp thắc mắc liền!'],
  ['Cảnh báo dễ thương!', 'Phát hiện lời lẽ hơi mạnh 🚨 Mình chỉ trả lời những câu hỏi lịch sự thôi, bạn thử lại nhé!'],
  ['Ôi không, lời nói chẳng mất tiền mua!', 'Lựa lời mà nói cho vừa lòng nhau nha bạn 💛 Nói nhẹ nhàng thì chuyện học vụ nào mình cũng giải đáp được!'],
]

export type Warning = { title: string; message: string }

/** Chọn ngẫu nhiên một lời cảnh báo. `previous` là chỉ số vừa dùng (để không lặp lại liền nhau). */
export function pickWarning(previous?: number, random: () => number = Math.random): { index: number; warning: Warning } {
  let index = Math.floor(random() * WARNINGS.length)
  if (previous !== undefined && WARNINGS.length > 1 && index === previous) index = (index + 1) % WARNINGS.length
  const [title, message] = WARNINGS[index]
  return { index, warning: { title, message } }
}

let lastIndex: number | undefined

/** Lời cảnh báo kế tiếp (nhớ chỉ số lần trước ở mức module). */
export function nextWarning(): Warning {
  const { index, warning } = pickWarning(lastIndex)
  lastIndex = index
  return warning
}
