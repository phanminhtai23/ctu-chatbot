"""Bộ câu hỏi kiểm thử RAG, đáp án lấy từ vector-docs/qd3266-clean.md.

`must` là danh sách các nhóm; MỖI nhóm phải khớp ít nhất một regex (không phân biệt hoa thường) trong câu trả lời.
`forbid` là các regex KHÔNG được khớp. `article` là Điều chứa đáp án (kiểm tra truy xuất đúng Điều).
Các công thức (Điều 5, 8, 18, 19, 22, 24, 25, 28, 30, 34) được hỏi bằng nhiều con số cụ thể.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Case:
    id: str
    article: int
    question: str
    must: tuple[tuple[str, ...], ...]
    forbid: tuple[str, ...] = field(default_factory=tuple)
    formula: bool = False
    lead: str = ""  # regex phải khớp trong ~250 ký tự đầu của câu trả lời (trả lời Có/Không ngay từ đầu)


def c(id, article, question, *must, forbid=(), formula=False, lead="") -> Case:
    groups = tuple(tuple(group) if isinstance(group, (list, tuple)) else (group,) for group in must)
    return Case(id, article, question, groups, tuple(forbid), formula, lead)


# Điểm chữ B (không phải B+): B không đứng liền với chữ cái hay dấu +.
LETTER_B = r"(?<![a-zđ])b(?![+a-zđ])"

# ---- Mỗi Điều (1-36) có ít nhất một câu hỏi ----
ARTICLE_CASES: list[Case] = [
    c("d01", 1, "Quy định học vụ này áp dụng cho những sinh viên nào?", r"chính quy", r"cần thơ|ctu|đhct"),
    c("d02", 2, "Khi nhập học, sinh viên Trường được cấp những gì?", r"mã số", r"thẻ", r"email|thư điện tử"),
    c("d03", 3, "Khối lượng học trực tuyến tối đa là bao nhiêu phần trăm của chương trình đào tạo?", r"30\s?%|30 phần trăm"),
    c("d04", 4, "Kế hoạch học tập toàn khóa của sinh viên phải được ai phê duyệt?", r"cvht|cố vấn học tập"),
    c("d05", 5, "Chương trình đào tạo thiết kế 4 năm thì thời gian học tối đa cho phép là bao lâu?", r"\b8 năm|tám năm"),
    c("d06", 6, "Một học kỳ ở CTU kéo dài bao nhiêu tuần và có mấy tuần dạy và học?", r"15 tuần", r"11 tuần"),
    c("d07", 7, "Học phần tiên quyết là gì?", r"tích lũy", r"mới (được|có thể)"),
    c("d08", 8, "Một tín chỉ tương đương bao nhiêu giờ học tập định mức của sinh viên?", r"50 giờ"),
    c("d09", 9, "Điều kiện để được xét học bổng khuyến khích học tập là gì?", r"12 (tc|tín chỉ)", r"khá", r"khiển trách"),
    c("d10", 10, "Sinh viên không đóng học phí 2 học kỳ liên tiếp thì bị xử lý thế nào?", r"buộc thôi học"),
    c("d11", 11, "Trường có khuyến khích sinh viên tham gia bảo hiểm tai nạn không?", r"khuyến khích", r"tai nạn"),
    c("d12", 12, "Sinh viên học một số học phần ở cơ sở đào tạo khác thì được tích lũy tối đa bao nhiêu phần trăm chương trình?", r"25\s?%|25 phần trăm"),
    c("d13", 13, "Sinh viên mới trúng tuyển có phải đăng ký học phần cho học kỳ đầu tiên không?", r"không (phải|cần)|không đăng ký|chưa phải|không bắt buộc"),
    c("d14", 14, "Mỗi học kỳ sinh viên được đăng ký tối đa bao nhiêu tín chỉ?", r"20 (tc|tín chỉ)|20 tín|\b20\b"),
    c("d15", 15, "Đến tuần thứ mấy của học kỳ thì được rút bớt học phần và rút xong thì bị điểm gì?", r"tuần (lễ )?(thứ )?(6|sáu)|thứ (6|sáu)", r"\bw\b"),
    c("d16", 16, "Lớp học phần có ít hơn bao nhiêu sinh viên đăng ký thì bị xóa?", r"20"),
    c("d17", 17, "Nếu bị điểm F ở học phần bắt buộc thì sinh viên phải làm gì?", r"học lại|đăng ký lại"),
    c("d18", 18, "Sinh viên bị buộc thôi học trong những trường hợp nào?", r"kỷ luật", r"học phí|đóng học phí", r"giả"),
    c("d19", 19, "Sinh viên phải tham dự tối thiểu bao nhiêu phần trăm số tiết của học phần lý thuyết?", r"80\s?%|80 phần trăm"),
    c("d19b", 19, "Tiết học đầu tiên buổi sáng bắt đầu lúc mấy giờ?", r"07[:h.]00|7[:h.]00|7 giờ|07 giờ"),
    c("d20", 20, "Sinh viên khóa 47 trở về sau muốn học cùng lúc hai chương trình thì cần ĐTBCTL tối thiểu bao nhiêu?", r"2[,.]50?", r"2[,.]00?"),
    c("d21", 21, "Hình thức đánh giá trực tuyến được chiếm tối đa bao nhiêu phần trăm trọng số điểm học phần?", r"50\s?%|50 phần trăm"),
    c("d22", 22, "Học phần chỉ được tính tích lũy khi đạt từ điểm chữ nào trở lên?", r"(?<![a-zđ])d(?![+a-zđ])|điểm d\b|từ d"),
    c("d23", 23, "Kỳ thi kết thúc học phần được tổ chức mấy lần?", r"1 lần|một lần|01 lần"),
    c("d24", 24, "Điểm trung bình chung học kỳ được tính như thế nào?", r"trọng số", r"(tín chỉ|tc)"),
    c("d25", 25, "Điểm rèn luyện của sinh viên được chấm theo thang điểm bao nhiêu?", r"100"),
    c("d26", 26, "Để được xếp loại và khen thưởng, mỗi học kỳ sinh viên phải học đủ tối thiểu bao nhiêu tín chỉ?", r"12"),
    c("d27", 27, "Đến trễ bao nhiêu phút sau khi mở đề thì sinh viên không được dự thi?", r"15 phút", r"\bf\b|điểm f"),
    c("d28", 28, "Sinh viên bị khiển trách trong kỳ thi thì bị trừ bao nhiêu phần trăm điểm?", r"25\s?%|25 phần trăm"),
    c("d29", 29, "Đơn vị quản lý học phần phải lưu bài thi viết ít nhất bao nhiêu năm?", r"\b0?5 năm|năm năm"),
    c("d30", 30, "Sinh viên khóa 47 tích lũy được 141 tín chỉ thì được xếp trình độ năm thứ mấy?", r"năm (thứ )?(tư|4|bốn)"),
    c("d31", 31, "Hội đồng bảo vệ luận văn tốt nghiệp gồm bao nhiêu thành viên?", r"\b0?3 thành viên|ba thành viên"),
    c("d32", 32, "Sinh viên được xét tốt nghiệp vào những tháng nào trong năm?", r"tháng[^.\n]{0,25}\b0?1\b", r"tháng[^.\n]{0,25}\b0?5\b", r"tháng[^.\n]{0,30}\b0?9\b"),
    c("d33", 33, "Sinh viên khóa 47 đã hết thời gian học tối đa nhưng chưa xong GDTC thì có bao lâu để quay lại trường hoàn thiện điều kiện?", r"\b0?3 năm|ba năm"),
    c("d34", 34, "Hạng tốt nghiệp loại giỏi ứng với ĐTBCTL trong khoảng nào?", r"3[,.]20?", r"3[,.]59"),
    c("d35", 35, "Sau khi có quyết định tốt nghiệp, sinh viên làm thủ tục thanh toán ra trường ở đâu?", r"đơn vị đào tạo"),
    c("d36", 36, "Bằng tốt nghiệp bị mất thì sinh viên phải làm gì?", r"bản sao", r"phòng đào tạo"),
]

# ---- Công thức / tính toán với số liệu cụ thể ----
FORMULA_CASES: list[Case] = [
    # Điều 24: ĐTBCHK = tổng(TC x điểm hệ 4) / tổng TC
    c("f24a", 24, "Học kỳ này mình học 3 môn: môn A 3 tín chỉ được điểm A, môn B 2 tín chỉ được điểm B+, môn C 4 tín chỉ được điểm C. Tính giúp mình ĐTBCHK nhé!",
      r"3[,.]00?\b", formula=True),
    c("f24b", 24, "Mình có 3 môn: môn X 2 tín chỉ điểm B, môn Y 3 tín chỉ điểm C, môn Z 1 tín chỉ điểm D. ĐTBCHK của mình là bao nhiêu?",
      r"2[,.]1[67]", formula=True),
    c("f24c", 24, "Học kỳ này mình có 2 môn: môn X 3 tín chỉ được điểm A, môn Y 3 tín chỉ bị điểm F. ĐTBCHK của mình là bao nhiêu?",
      r"2[,.]00?\b", formula=True),
    c("f24d", 24, "Mình đã học 2 môn: môn X 3 tín chỉ được điểm A, môn Y 3 tín chỉ bị điểm F. Vậy ĐTBCTL (điểm trung bình chung tích lũy) của mình là bao nhiêu?",
      r"4[,.]00?\b", formula=True),
    c("f24e", 24, "ĐTBCHK của mình là 3,25 thì xếp loại học tập gì vậy?", r"giỏi", formula=True),
    c("f24f", 24, "ĐTBCHK của mình là 2,4 thì xếp loại học tập gì?", r"trung bình", formula=True),
    # Điều 22: quy đổi thang 10 -> chữ -> thang 4
    c("f22a", 22, "Mình được 7,2 điểm theo thang điểm 10, quy đổi ra điểm chữ và thang điểm 4 là bao nhiêu?", LETTER_B, r"3[,.]0", formula=True),
    c("f22b", 22, "Điểm 6,7 theo thang 10 thì quy đổi ra điểm chữ và thang 4 là gì?", r"c\+", r"2[,.]5", formula=True),
    c("f22c", 22, "Mình được 5,4 điểm thì là điểm chữ gì, tương ứng bao nhiêu theo thang 4?", r"d\+", r"1[,.]5", formula=True),
    c("f22d", 22, "Điểm 3,9 theo thang điểm 10 quy đổi sang điểm chữ là gì, có được tích lũy không?", r"\bf\b", r"không", formula=True),
    c("f22e", 22, "Điểm 4,5 theo thang 10 là điểm chữ gì và có được tích lũy học phần không?", r"(?<![a-zđ])d(?![+a-zđ])", r"(có|được) (được )?tích lũy|được tích lũy", formula=True),
    # Điều 18: cảnh báo học tập
    c("f18a", 18, "ĐTBCHK của mình là 0,9 ở học kỳ đầu tiên của khóa học. Mình có bị cảnh báo học tập không?", r"không|chưa", r"0[,.]80?", formula=True),
    c("f18b", 18, "ĐTBCHK của mình là 0,9 ở học kỳ thứ hai. Mình có bị cảnh báo học tập không?", r"1[,.]00?", lead=r"\bcó\b|bị cảnh báo", forbid=(r"(?<!để )(?<!tránh )không (bị|thuộc) (diện )?cảnh báo",), formula=True),
    # Điều 19: giờ lên lớp
    c("f19", 19, "Học phần lý thuyết của mình có 45 tiết, mình vắng tối đa bao nhiêu tiết thì không bị cấm thi?", r"\b9\b", formula=True),
    # Điều 8: tín chỉ -> giờ
    c("f08a", 8, "Một học phần lý thuyết 3 tín chỉ thì cần tối thiểu bao nhiêu giờ giảng trên lớp?", r"45", formula=True),
    c("f08b", 8, "Một học phần 3 tín chỉ tương đương bao nhiêu giờ học tập định mức của sinh viên?", r"150", formula=True),
    # Điều 5: giảm thời gian học theo tín chỉ được công nhận
    c("f05a", 5, "Sinh viên khóa 50 được công nhận chuyển đổi 12 tín chỉ thì thời gian học tập tối đa giảm bao nhiêu học kỳ?", r"\b2 (học kỳ|hk)|hai (học kỳ|hk)|\b02", formula=True),
    c("f05b", 5, "Sinh viên khóa 49 chỉ được công nhận 5 tín chỉ thì thời gian học tập tối đa có bị giảm không?", r"không", formula=True),
    # Điều 25: ĐRL cả năm = trung bình cộng 3 học kỳ
    c("f25", 25, "Điểm rèn luyện 3 học kỳ của mình lần lượt là 80, 85 và 90. Điểm rèn luyện cả năm là bao nhiêu?", r"\b85\b", formula=True),
    # Điều 28: trừ điểm khi vi phạm
    c("f28a", 28, "Mình bị khiển trách khi làm bài thi và bài thi được 8,0 điểm. Điểm còn lại sau khi bị trừ là bao nhiêu?", r"\b6([,.]0)?\b", formula=True),
    c("f28b", 28, "Mình bị cảnh cáo trong kỳ thi và bài thi được 8,0 điểm. Điểm sau khi bị xử lý là bao nhiêu?", r"50\s?%", r"\b4([,.]0)?\b", formula=True),
    # Điều 30: xếp trình độ năm học theo khóa và tín chỉ tích lũy
    c("f30a", 30, "Sinh viên khóa 42 tích lũy được 50 tín chỉ thì xếp trình độ năm thứ mấy?", r"năm (thứ )?(hai|2)", formula=True),
    c("f30b", 30, "Sinh viên khóa 47 tích lũy được 142 tín chỉ thì xếp trình độ năm thứ mấy?", r"năm (thứ )?(năm|5)", formula=True),
    # Điều 34: hạng tốt nghiệp và bị giảm một mức
    c("f34a", 34, "ĐTBCTL của mình là 3,65, mình tốt nghiệp loại gì?", r"xuất sắc", formula=True),
    c("f34b", 34, "ĐTBCTL của mình là 3,65 nhưng mình có học phần bị điểm F vượt quá 5% tổng số tín chỉ của chương trình. Hạng tốt nghiệp của mình là gì?",
      r"giỏi", r"giảm", formula=True),
    c("f34c", 34, "ĐTBCTL của mình là 2,3 thì hạng tốt nghiệp là gì?", r"trung bình", formula=True),
    # Điều 32: tốt nghiệp
    c("f32", 32, "Điểm trung bình chung các học phần GDQP&AN phải đạt tối thiểu bao nhiêu (thang điểm 10) để được xét tốt nghiệp?", r"5[,.]0?\b", formula=True),
]

# ---- Không có trong văn bản: bot không được bịa ----
UNKNOWN_CASES: list[Case] = [
    c("u01", 10, "Học phí một tín chỉ ở CTU là bao nhiêu tiền?",
      r"chưa|không (thấy|có|nêu|quy định)|hiệu trưởng quyết định|phòng", forbid=(r"\d[\d.,]*\s?(đồng|vnđ|vnd|nghìn|triệu)",)),
    c("u02", 0, "Ký túc xá khu B của trường có bao nhiêu phòng?",
      r"chưa|không (thấy|có|nêu|tìm)|ngoài|phòng (công tác|đào tạo)|học vụ", forbid=(r"\b\d+\s*phòng\b",)),
]

OFF_TOPIC = "Bạn viết giúp mình một bài thơ lục bát về mùa thu nhé"


# ---- Câu hỏi "có đạt được mục tiêu không": phải tính mức tối đa và trả lời Có/Không ngay câu đầu ----
FEASIBILITY_CASES: list[Case] = [
    # 100 TC x 3,2 = 320; toàn A ở 51 TC còn lại -> (320 + 204) / 151 = 3,47 < 3,60: KHÔNG THỂ
    c("g01", 34, "chương trình tôi học 151 chỉ tôi đã học 100 chỉ điểm tb chung tích lũy hiện 3.2 tôi có thể tốt nghiệp xuất sắc không ?",
      r"3[,.]47", r"cải thiện", r"điều kiện|điểm m\b", r"bao nhiêu",
      forbid=(r"hoàn toàn có thể (đạt|tốt nghiệp)", r"vẫn (có|còn) cơ hội"),
      lead=r"không (thể|được|đạt)|không nhé|không bạn", formula=True),
    # 100 TC x 3,4 = 340; toàn A -> (340 + 204) / 151 = 3,60: CÓ THỂ nhưng phải gần như toàn A
    c("g02", 34, "Chương trình của mình 151 tín chỉ, mình đã tích lũy 100 tín chỉ với ĐTBCTL là 3,4. Mình có thể tốt nghiệp loại xuất sắc không?",
      r"3[,.]9\d|4[,.]0|toàn a|tất cả.{0,20}\ba\b|gần như", r"3[,.]60?",
      lead=r"\bcó\b", formula=True),
    # 100 TC x 3,5 = 350; cần (543,6 - 350) / 51 = 3,80 ở phần còn lại: CÓ THỂ
    c("g03", 34, "Mình học chương trình 151 tín chỉ, đã tích lũy 100 tín chỉ, ĐTBCTL hiện tại 3,5. Mình cần điểm trung bình bao nhiêu ở phần còn lại để tốt nghiệp xuất sắc?",
      r"3[,.]8", formula=True),
    # 90 TC x 2,0 = 180; tối đa (180 + 61*4) / 151 = 2,81 < 3,2 (giỏi): KHÔNG THỂ
    c("g04", 34, "Chương trình 151 tín chỉ, mình đã học 90 tín chỉ và ĐTBCTL đang là 2,0. Mình có thể ra trường loại giỏi không?",
      r"2[,.]8", lead=r"không (thể|được|đạt)|không nhé|không bạn", formula=True),
]
