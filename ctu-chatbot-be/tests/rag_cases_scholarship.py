"""Học bổng khuyến khích học tập (Điều 9): phải xếp MỨC học bổng (cả ĐTBCHK lẫn ĐRL) trước,
rồi mới so ĐTBCHK, rồi mới so ĐRL. Xếp loại ĐRL theo Thông tư 16/2015/TT-BGDĐT: 90-100 xuất sắc, 80-dưới 90 tốt."""

from tests.rag_cases import Case, c

SCHOLARSHIP_CASES: list[Case] = [
    # A: 3,8 / ĐRL 89 ("tốt") chỉ đủ mức giỏi.  B: 3,6 / ĐRL 90 ("xuất sắc") đủ mức xuất sắc -> B được xét trước.
    c(
        "h01", 9,
        "có 2 người cao điểm nhất lớp, gpa 3,8 đrl 89, 1 người gpa 3,6 đrl 90 thì ai sẽ giành được học bổng ?",
        r"mức xuất sắc|loại xuất sắc",
        r"\btốt\b|mức giỏi|loại giỏi",
        r"(người thứ hai|người thứ 2|bạn thứ hai|người có gpa 3[,.]6|gpa 3[,.]6|3[,.]6 và đrl 90|đrl 90)",
        forbid=(r"(người|bạn) (thứ nhất|thứ 1) (sẽ )?(được|giành)", r"gpa 3[,.]8[^.\n]{0,40}(sẽ )?(được ưu tiên|giành được)"),
        formula=True,
    ),
    # Cùng mức xuất sắc (ĐTBCHK >= 3,60 và ĐRL >= 90) -> so ĐTBCHK: A (3,8) được xét trước.
    c(
        "h02", 9,
        "Hai bạn cùng lớp, bạn A có ĐTBCHK 3,8 và ĐRL 92, bạn B có ĐTBCHK 3,7 và ĐRL 95. Ai được xét học bổng trước?",
        r"\ba\b[^.\n]{0,120}(trước|ưu tiên|được)",
        r"đtbchk",
        formula=True,
    ),
    # Cùng mức và cùng ĐTBCHK -> so ĐRL: B (95) được ưu tiên.
    c(
        "h03", 9,
        "Bạn A có ĐTBCHK 3,7 và ĐRL 91, bạn B có ĐTBCHK 3,7 và ĐRL 95. Ai được ưu tiên học bổng?",
        r"\bb\b[^.\n]{0,120}(ưu tiên|trước|được)",
        r"đrl|rèn luyện",
        formula=True,
    ),
]
