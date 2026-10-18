"""Câu hỏi KHÓ theo từng mảng học vụ. Đáp án đã tính độc lập bằng Python và đối chiếu với văn bản QĐ 3266.

Mỗi câu là một "bẫy" mà bot nhỏ hay sai: bỏ qua một bước, nhầm biên (đúng bằng ngưỡng), nhầm khóa áp dụng,
tính trung bình cộng thay vì trung bình có trọng số, hoặc quên loại học phần không tính điểm.
`lead` = câu trả lời phải mở đầu rõ ràng (Có/Không) trong khoảng 260 ký tự đầu.
"""

from tests.rag_cases import Case, c

YES = r"\bcó\b|\bđược\b|\bbị\b"
NO = r"\bkhông\b|\bchưa\b"

# ===================== HỌC BỔNG (Điều 9) =====================
SCHOLARSHIP_HARD: list[Case] = [
    c("s01", 9, "Kỳ trước mình chỉ đăng ký 10 tín chỉ (không phải do Trường bố trí), ĐTBCHK 3,7 và ĐRL 95. Mình có được xét học bổng khuyến khích học tập không?",
      r"12 (tc|tín chỉ)|12 tín", lead=NO),
    c("s02", 9, "Mình có ĐTBCHK 3,5 và ĐRL 85 nhưng kỳ trước bị một môn điểm F. Mình có được xét học bổng không?",
      r"điểm d|dưới điểm d|điểm f|học phần", lead=NO),
    c("s03", 9, "Kỳ trước mình bị khiển trách cấp Trường, ĐTBCHK 3,9 và ĐRL 92. Mình có được xét học bổng không?",
      r"khiển trách", lead=NO),
    c("s04", 9, "ĐTBCHK của mình là 3,3 còn ĐRL là 79 thì mình thuộc mức học bổng nào?",
      r"mức khá|loại khá", r"\btốt\b|chưa đủ|không đủ|dưới 80"),
    c("s05", 9, "Bạn A có ĐTBCHK 3,5 và ĐRL 88, bạn B có ĐTBCHK 3,5 và ĐRL 84, cả hai đều đủ điều kiện. Ai được ưu tiên học bổng?",
      r"\ba\b[^.\n]{0,100}(ưu tiên|trước|được)", r"đrl|rèn luyện"),
    c("s06", 9, "Học kỳ đầu tiên của khóa học thì học bổng khuyến khích học tập được xét dựa trên gì?",
      r"xét tuyển|đầu vào", r"không (bao gồm|tính|gồm)[^.\n]{0,25}ưu tiên"),
    c("s07", 9, "Học bổng khuyến khích học tập một học kỳ là bao nhiêu tiền?",
      r"hiệu trưởng", forbid=(r"\d[\d.,]*\s?(đồng|vnđ|vnd|nghìn|triệu)",)),
    # A: 3,65/91 -> xuất sắc. B: 3,9/88 (ĐRL tốt) -> giỏi. C: 3,3/80 -> giỏi. Thứ tự: A, rồi B (ĐTBCHK cao hơn C), rồi C.
    c("s08", 9, "Ba bạn: A có ĐTBCHK 3,65 và ĐRL 91; B có ĐTBCHK 3,9 và ĐRL 88; C có ĐTBCHK 3,3 và ĐRL 80. Xếp thứ tự ưu tiên xét học bổng giúp mình.",
      r"\ba\b[^.\n]{0,120}(xuất sắc)", r"\bb\b[^.\n]{0,120}giỏi",
      lead=r"\ba\b\s*(>|->|→|, rồi|rồi đến|tiếp theo)\s*\bb\b|\ba\b[^.\n]{0,160}(trước|đầu tiên|thứ nhất|ưu tiên|cao nhất)"),
]

# ===================== ĐTBCHK / ĐTBCNH / ĐTBCTL (Điều 22, 24) =====================
GPA_HARD: list[Case] = [
    # GDTC bị loại; F và Ngoại ngữ căn bản vẫn tính: (12 + 10,5 + 6 + 0) / 11 = 2,59 -> Khá
    c("b01", 24, "Học kỳ này mình học: Toán 3 TC điểm A, Lý 3 TC điểm B+, Giáo dục thể chất 1 TC điểm A, Ngoại ngữ căn bản 3 TC điểm C, Hóa 2 TC điểm F. Tính ĐTBCHK và xếp loại học tập giúp mình.",
      r"2[,.]59", r"khá", formula=True),
    # ĐTBCTL của riêng các môn này: bỏ F và học phần điều kiện (GDTC, NNCB) -> (12 + 10,5) / 6 = 3,75
    c("b02", 24, "Các môn: Toán 3 TC điểm A, Lý 3 TC điểm B+, Giáo dục thể chất 1 TC điểm A, Ngoại ngữ căn bản 3 TC điểm C, Hóa 2 TC điểm F. Điểm trung bình chung tích lũy (ĐTBCTL) của riêng những môn này là bao nhiêu, biết ĐTBCTL không tính F và học phần điều kiện?",
      r"3[,.]75", formula=True),
    # W và I không tính: (12 + 12) / 7 = 3,43
    c("b03", 24, "Mình học Toán 3 TC điểm A, Lý 2 TC rút môn (điểm W), Hóa 3 TC điểm I, Văn 4 TC điểm B. ĐTBCHK của mình là bao nhiêu?",
      r"3[,.]43", formula=True),
    # 8,4 -> B+ (3,5); 6,9 -> C+ (2,5); 5,4 -> D+ (1,5): (10,5 + 5 + 6) / 9 = 2,39 -> Trung bình
    c("b04", 22, "Môn X 3 TC được 8,4 điểm, môn Y 2 TC được 6,9 điểm, môn Z 4 TC được 5,4 điểm (thang 10). Tính ĐTBCHK và xếp loại.",
      r"2[,.]39", r"trung bình", formula=True),
    # Trung bình có trọng số: 91 / 30 = 3,03 (KHÔNG phải trung bình cộng 2,87)
    c("b05", 24, "HK1 mình học 15 TC có ĐTBCHK 3,0; HK2 học 10 TC có ĐTBCHK 3,6; HK3 học 5 TC có ĐTBCHK 2,0. Điểm trung bình chung năm học (ĐTBCNH) là bao nhiêu?",
      r"3[,.]03", forbid=(r"2[,.]87",), formula=True),
    # (60 x 3,2 + 15 x 2,4) / 75 = 3,04
    c("b06", 24, "Mình đã tích lũy 60 TC với ĐTBCTL 3,2. Học kỳ này mình học 15 TC, đều đạt, ĐTBCHK là 2,4. ĐTBCTL mới của mình là bao nhiêu?",
      r"3[,.]04", formula=True),
    # (3,2 x 75 - 60 x 3,0) / 15 = 4,0: phải được toàn A
    c("b07", 24, "Mình có 60 TC tích lũy với ĐTBCTL 3,0. Học kỳ này mình học 15 TC, cần đạt điểm trung bình học kỳ bao nhiêu để ĐTBCTL lên 3,2?",
      r"4[,.]0", r"toàn a|tất cả[^.\n]{0,25}\ba\b|điểm a|tối đa|4[,.]0", formula=True),
    # Học cải thiện: điểm mới thay điểm cũ: (90 x 3,0 + 3 x 2,0) / 90 = 3,07
    c("b08", 17, "ĐTBCTL của mình là 3,0 với 90 TC tích lũy. Mình học cải thiện một môn 3 TC từ điểm C lên điểm A thì ĐTBCTL mới là bao nhiêu?",
      r"3[,.]07", formula=True),
    c("b09", 24, "Điểm trung bình chung tích lũy khác điểm trung bình chung học kỳ ở chỗ nào, có tính điểm F và học phần điều kiện không?",
      r"điểm f|\bf\b", r"điều kiện"),
    c("b10", 24, "Môn bị điểm F có được tính vào ĐTBCHK không? Còn ĐTBCTL thì sao?",
      r"đtbchk[^.\n]{0,100}(có|được) tính|(có|được) tính[^.\n]{0,60}đtbchk", r"đtbctl[^.\n]{0,100}không|không[^.\n]{0,60}đtbctl"),
]

# ===================== HẠNG TỐT NGHIỆP (Điều 32, 34) =====================
GRADUATION_HARD: list[Case] = [
    # 6/120 = 5,00%: KHÔNG vượt quá 5% nên không bị giảm -> xuất sắc
    c("t01", 34, "Chương trình của mình 120 TC, ĐTBCTL 3,7, mình có 6 TC bị điểm F (không phải học cải thiện). Mình tốt nghiệp loại gì?",
      r"xuất sắc", lead=r"xuất sắc"),
    # 7/120 = 5,83% > 5% -> giảm một mức: xuất sắc -> giỏi
    c("t02", 34, "Chương trình 120 TC, ĐTBCTL của mình 3,7, mình có 7 TC bị điểm F (không phải học cải thiện). Mình tốt nghiệp loại gì?",
      r"giỏi", r"giảm", lead=r"giỏi"),
    # Cảnh cáo cấp Trường: giỏi -> khá
    c("t03", 34, "ĐTBCTL của mình 3,3 (loại giỏi), nhưng mình từng bị kỷ luật cảnh cáo cấp Trường. Mình tốt nghiệp loại gì?",
      r"khá", lead=r"khá"),
    # Chỉ KHIỂN TRÁCH cấp Trường: không bị giảm
    c("t04", 34, "ĐTBCTL của mình 3,3 (loại giỏi), mình chỉ từng bị khiển trách cấp Trường. Mình tốt nghiệp loại gì?",
      r"giỏi", lead=r"giỏi"),
    # F của học phần cải thiện không tính: chỉ 4/120 = 3,3% -> giữ xuất sắc
    c("t05", 34, "Chương trình 120 TC, ĐTBCTL 3,7. Mình có 4 TC bị F ở học phần thường và 5 TC bị F ở học phần đăng ký học cải thiện. Tốt nghiệp loại gì?",
      r"xuất sắc", r"cải thiện", lead=r"xuất sắc"),
    # Cả hai lý do chỉ giảm MỘT mức: xuất sắc -> giỏi (không phải khá)
    c("t06", 34, "ĐTBCTL của mình 3,8, mình có 8 TC bị F trên chương trình 120 TC và từng bị kỷ luật cảnh cáo cấp Trường. Hạng tốt nghiệp của mình là gì?",
      r"giỏi", r"một mức", lead=r"giỏi"),
    # Loại khá không bị giảm
    c("t07", 34, "ĐTBCTL của mình 3,0 (loại khá), có 10 TC bị điểm F trên chương trình 120 TC. Tốt nghiệp loại gì?",
      r"khá", lead=r"khá"),
    # Giỏi + F vượt 5%: giỏi -> khá
    c("t08", 34, "ĐTBCTL 3,5 (loại giỏi), có 8 TC bị điểm F trên chương trình 120 TC. Mình tốt nghiệp loại gì?",
      r"khá", lead=r"khá"),
    c("t09", 34, "ĐTBCTL của mình đúng 3,19. Mình tốt nghiệp loại gì?", r"khá", lead=r"khá"),
    c("t10", 32, "ĐTBCTL của mình là 1,95 và đã học đủ tín chỉ. Mình có được công nhận tốt nghiệp không?",
      r"2[,.]00?", lead=NO),
    c("t11", 32, "ĐTBCTL 3,0 nhưng điểm trung bình các học phần GDQP&AN của mình là 4,8 (thang 10). Mình có đủ điều kiện tốt nghiệp không?",
      r"5[,.]0", lead=NO),
    c("t12", 32, "Mỗi năm xét tốt nghiệp vào những tháng nào, và bao lâu sau quyết định thì nhận được bằng?",
      r"tháng[^.\n]{0,25}\b0?1\b", r"tháng[^.\n]{0,25}\b0?5\b", r"tháng[^.\n]{0,30}\b0?9\b", r"30 ngày"),
]

# ===================== ĐÃ HỌC / CÒN LẠI / KHẢ NĂNG ĐẠT LOẠI (Điều 24, 34) =====================
CREDITS_HARD: list[Case] = [
    c("k01", 8, "Chương trình của mình 151 chỉ, mình đã học 100 chỉ. Mình còn bao nhiêu chỉ nữa?", r"\b51\b"),
    c("k02", 8, "Chương trình 140 TC, trong đó có 8 TC GDQP&AN và GDTC không tính điểm. Mình đã học 90 TC (gồm cả 8 TC đó). Còn bao nhiêu TC nữa phải học?",
      r"\b50\b"),
    # C = 70, T = 121, còn 51: tối đa 3,71, cần trung bình 3,74
    c("k03", 34, "Chương trình 151 TC, mình đã học 100 TC với ĐTBCTL 3,5. Trong 100 TC đó có 30 TC điều kiện và tổng TC điều kiện của chương trình cũng là 30. Còn bao nhiêu TC phải học, và để đạt xuất sắc thì cần điểm trung bình bao nhiêu ở phần còn lại?",
      r"\b51\b", r"3[,.]7[34]", formula=True),
    # tối đa 3,25 >= 3,2 -> CÓ; cần trung bình 3,8
    c("k04", 34, "Chương trình 120 TC, mình đã học 90 TC với ĐTBCTL 3,0. Mình có thể tốt nghiệp loại giỏi không? Cần bao nhiêu điểm trung bình ở 30 TC còn lại?",
      r"3[,.]8", r"3[,.]25", lead=r"\bcó\b", formula=True),
    # tối đa 3,54 < 3,6 -> KHÔNG
    c("k05", 34, "Chương trình 130 TC, mình đã học 120 TC với ĐTBCTL 3,5. Mình có thể lên loại xuất sắc không?",
      r"3[,.]54", lead=r"không (thể|được|đạt)|không nhé|không bạn", formula=True),
    # cần 2,4 ở phần còn lại để đủ 2,0
    c("k06", 32, "Chương trình 150 TC, mình đã học 100 TC với ĐTBCTL 1,8. Để đủ điều kiện tốt nghiệp (ĐTBCTL từ 2,0) thì 50 TC còn lại cần đạt điểm trung bình bao nhiêu?",
      r"2[,.]4", formula=True),
    # cần giữ trung bình 3,3: chưa chắc chắn
    c("k07", 34, "Mình đã học 60 trên 120 TC với ĐTBCTL 3,9. Mình đã chắc chắn tốt nghiệp xuất sắc chưa, cần giữ điểm trung bình bao nhiêu ở 60 TC còn lại?",
      r"3[,.]3", lead=r"chưa|không chắc", formula=True),
    # tối đa 4,0; cần 3,52
    c("k08", 34, "Chương trình 120 TC, mình mới học 20 TC với ĐTBCTL 4,0. Mình có thể đạt loại xuất sắc không, cần điểm trung bình bao nhiêu ở phần còn lại?",
      r"3[,.]52", lead=r"\bcó\b", formula=True),
]

# ===================== CẢNH BÁO HỌC VỤ, BUỘC THÔI HỌC (Điều 18) =====================
WARNING_HARD: list[Case] = [
    c("w01", 18, "ĐTBCHK học kỳ đầu tiên của mình là 0,75. Mình có bị cảnh báo học tập không?", r"0[,.]80?", lead=YES),
    c("w02", 18, "ĐTBCHK học kỳ thứ ba của mình đúng bằng 1,00. Mình có bị cảnh báo học tập không?", r"dưới 1[,.]00?", lead=NO),
    # 9/16 = 56,25% > 50% -> cảnh báo (K47 trở về sau)
    c("w03", 18, "Mình là sinh viên K48, học kỳ này đăng ký 16 TC nhưng rớt 9 TC. Mình có bị cảnh báo học tập không?",
      r"50\s?%", lead=YES),
    # 8/16 = 50%: KHÔNG vượt quá 50%
    c("w04", 18, "Mình là sinh viên K48, học kỳ này đăng ký 16 TC và rớt đúng 8 TC, ĐTBCHK 1,5. Mình có bị cảnh báo học tập không?",
      r"50\s?%|vượt quá", lead=NO),
    c("w05", 18, "Mình K47, nợ 25 TC từ đầu khóa học, ĐTBCHK học kỳ này là 2,0. Mình có bị cảnh báo học tập không?", r"24", lead=YES),
    # Quy định nợ > 24 TC chỉ áp dụng từ Khóa 47 trở về sau
    c("w06", 18, "Mình K46, nợ 30 TC từ đầu khóa học, ĐTBCHK học kỳ này là 2,0. Mình có bị cảnh báo học tập vì nợ tín chỉ không?",
      r"47", lead=NO),
    c("w07", 18, "Mình K48 đang học năm thứ hai, ĐTBC tích lũy là 1,35. Mình có bị cảnh báo học tập không?", r"1[,.]4", lead=YES),
    c("w08", 18, "Mình K48 đang học năm thứ hai, ĐTBC tích lũy là 1,45 và các tiêu chí khác đều ổn. Mình có bị cảnh báo học tập không?",
      r"1[,.]4", lead=NO),
    c("w09", 18, "Mình K48 đang học năm thứ ba, ĐTBC tích lũy là 1,5. Mình có bị cảnh báo học tập không?", r"1[,.]6", lead=YES),
    c("w10", 18, "Mình đã bị cảnh báo học tập, học kỳ kế tiếp ĐTBCHK của mình là 0,95. Mình sẽ bị xử lý thế nào?", r"buộc thôi học"),
    c("w11", 18, "Mình đã bị cảnh báo học tập, học kỳ kế tiếp ĐTBCHK của mình đúng 1,00. Mình có bị buộc thôi học không?", r"1[,.]00?", lead=NO),
    c("w12", 18, "Điểm rèn luyện yếu hoặc kém 2 học kỳ liên tiếp thì bị gì, và nếu lặp lại lần thứ hai thì sao?",
      r"đình chỉ", r"buộc thôi học"),
    c("w13", 18, "Mình không đăng ký học 2 học kỳ liên tiếp mà không xin phép Hiệu trưởng thì bị gì?", r"buộc thôi học"),
    c("w14", 10, "Mình không đóng học phí một học kỳ thì bị xử lý thế nào, và hai học kỳ liên tiếp thì sao?",
      r"hủy", r"2 (hk|học kỳ)|hai (hk|học kỳ)", r"buộc thôi học"),
]

# ===================== THỜI GIAN HỌC, HỌC HAI CHƯƠNG TRÌNH, THI (Điều 5, 20, 28) =====================
OTHER_HARD: list[Case] = [
    c("o01", 5, "Sinh viên K50 được công nhận chuyển đổi 14 tín chỉ thì thời gian học tối đa giảm bao nhiêu học kỳ?", r"2 (hk|học kỳ)|hai (hk|học kỳ)", formula=True),
    c("o02", 5, "Sinh viên K49 được công nhận chuyển đổi 9 tín chỉ thì thời gian học tối đa giảm bao nhiêu học kỳ?", r"1 (hk|học kỳ)|một (hk|học kỳ)", formula=True),
    c("o03", 5, "Sinh viên K49 chỉ được công nhận 8 tín chỉ thì thời gian học tối đa có giảm không?", r"không", lead=NO, formula=True),
    c("o04", 5, "Chương trình đào tạo thiết kế 4,5 năm thì thời gian học tối đa là bao lâu?", r"9 năm|chín năm"),
    c("o05", 5, "Sinh viên K47 được công nhận chuyển đổi tối đa bao nhiêu phần trăm khối lượng học tập tối thiểu của chương trình?", r"50\s?%"),
    c("o06", 20, "Sinh viên K46 muốn học cùng lúc hai chương trình thì cần điều kiện gì về học kỳ và ĐTBCTL?", r"học kỳ đầu", r"2[,.]00?"),
    c("o07", 20, "Mình K48, ĐTBCTL 2,3. Mình có thể học cùng lúc hai chương trình không?", r"điểm chuẩn|trúng tuyển", r"2[,.]50?"),
    c("o08", 20, "Học cùng lúc hai chương trình thì mình được hưởng quyền lợi (học bổng, chế độ...) của chương trình nào?", r"thứ nhất|đầu tiên|chương trình thứ nhất"),
    c("o09", 28, "Mình bị đình chỉ thi 2 lần trong một năm học thì sẽ bị xử lý thế nào?", r"đình chỉ học tập 1 năm|đình chỉ học tập một năm|1 năm"),
    c("o10", 28, "Thi hộ lần thứ hai trong cả khóa học thì bị xử lý thế nào?", r"buộc thôi học"),
]

HARD_CASES: list[Case] = SCHOLARSHIP_HARD + GPA_HARD + GRADUATION_HARD + CREDITS_HARD + WARNING_HARD + OTHER_HARD
