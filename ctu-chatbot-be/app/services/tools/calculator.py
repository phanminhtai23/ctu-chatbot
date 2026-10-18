"""Công cụ máy tính cho chatbot: tính chính xác các phép + - * / ** và vài hàm đơn giản, an toàn (không dùng eval).

LLM nhỏ hay chia/nhân sai khi tự tính nhẩm. Công cụ này tính bằng phân số (Fraction) nên không có sai số số thực,
và trả cả giá trị làm tròn 2 chữ số thập phân (kiểu điểm học tập) lẫn giá trị chi tiết.
"""

import ast
import operator
import re
from fractions import Fraction

from langchain_core.tools import tool

MAX_EXPRESSION_LENGTH = 300
MAX_NODES = 120
MAX_EXPONENT = 8
MAX_ABS_VALUE = Fraction(10) ** 15

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


class CalculatorError(ValueError):
    """Biểu thức sai cú pháp, không được phép hoặc không tính được."""


def round_half_up(value: Fraction, digits: int = 2) -> Fraction:
    """Làm tròn kiểu thông thường (0,5 làm tròn lên) như cách làm tròn điểm; không dùng round() của Python (làm tròn chẵn)."""
    scale = Fraction(10) ** digits
    scaled = value * scale
    sign = 1 if scaled >= 0 else -1
    return Fraction(sign * int(abs(scaled) + Fraction(1, 2)), 1) / scale


def format_number(value: Fraction, digits: int = 2) -> str:
    """Số kiểu Việt Nam: dấu phẩy thập phân, giữ đủ `digits` chữ số (3,60 chứ không phải 3,6)."""
    rounded = round_half_up(value, digits)
    text = f"{float(rounded):.{digits}f}"
    return text.replace(".", ",")


def _normalize(expression: str) -> str:
    text = expression.strip()
    text = text.replace("×", "*").replace("÷", "/").replace("^", "**").replace("−", "-").replace("–", "-")
    text = re.sub(r"(?<=\d)\s*[xX]\s*(?=[\d(])", "*", text)  # "3 x 4" -> "3*4"
    text = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", text)  # "5%" -> "(5/100)"
    return text


class _Evaluator(ast.NodeVisitor):
    def __init__(self) -> None:
        self.nodes = 0

    def visit(self, node):  # noqa: D401
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise CalculatorError("Biểu thức quá dài.")
        return super().visit(node)

    def generic_visit(self, node):
        raise CalculatorError(f"Không hỗ trợ cú pháp {type(node).__name__}.")

    def visit_Expression(self, node):
        return self.visit(node.body)

    def visit_Constant(self, node):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise CalculatorError("Chỉ được dùng số.")
        return Fraction(str(node.value))  # từ chuỗi để "0.1" là đúng 1/10, không phải số thực nhị phân

    def visit_UnaryOp(self, node):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise CalculatorError("Phép toán một ngôi không được hỗ trợ.")
        return op(self.visit(node.operand))

    def visit_BinOp(self, node):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise CalculatorError("Phép toán không được hỗ trợ (chỉ + - * / ** và ngoặc).")
        left, right = self.visit(node.left), self.visit(node.right)
        if isinstance(node.op, ast.Div) and right == 0:
            raise CalculatorError("Chia cho 0.")
        if isinstance(node.op, ast.Pow):
            if right.denominator != 1 or abs(right) > MAX_EXPONENT:
                raise CalculatorError(f"Số mũ phải là số nguyên có giá trị tuyệt đối tối đa {MAX_EXPONENT}.")
            if left == 0 and right < 0:
                raise CalculatorError("Chia cho 0.")
            result = left ** int(right)
        else:
            result = op(left, right)
        if abs(result) > MAX_ABS_VALUE:
            raise CalculatorError("Kết quả quá lớn.")
        return result

    def visit_Call(self, node):
        if not isinstance(node.func, ast.Name) or node.keywords:
            raise CalculatorError("Hàm không được hỗ trợ.")
        name = node.func.id
        args = [self.visit(a) for a in node.args]
        if name in ("min", "max") and args:
            return min(args) if name == "min" else max(args)
        if name == "abs" and len(args) == 1:
            return abs(args[0])
        if name == "round" and len(args) in (1, 2):
            digits = int(args[1]) if len(args) == 2 and args[1].denominator == 1 else 0
            return round_half_up(args[0], max(0, min(6, digits)))
        raise CalculatorError(f"Hàm {name}() không được hỗ trợ (chỉ có min, max, abs, round).")


def evaluate(expression: str) -> Fraction:
    """Tính biểu thức, trả về phân số chính xác. Ném CalculatorError nếu biểu thức không hợp lệ."""
    if not expression or not expression.strip():
        raise CalculatorError("Biểu thức rỗng.")
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise CalculatorError("Biểu thức quá dài.")
    text = _normalize(expression)
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise CalculatorError("Sai cú pháp. Hãy dùng dấu chấm cho số thập phân, ví dụ 3.2 * 100.") from exc
    return _Evaluator().visit(tree)


def calculate_text(expression: str) -> str:
    """Kết quả dạng chữ cho LLM: có giá trị làm tròn 2 chữ số và giá trị chi tiết 4 chữ số."""
    try:
        value = evaluate(expression)
    except CalculatorError as exc:
        return f"LỖI: {exc}"
    if value.denominator == 1:
        return f"{expression.strip()} = {int(value)}"
    return (
        f"{expression.strip()} = {format_number(value, 4)} "
        f"(làm tròn 2 chữ số thập phân: {format_number(value, 2)})"
    )


@tool
def calculate(expression: str) -> str:
    """Máy tính chính xác. LUÔN dùng công cụ này cho MỌI phép tính (cộng, trừ, nhân, chia, trung bình có trọng số, phần trăm), không tự tính nhẩm.

    Tham số `expression` là biểu thức số học: + - * / ** và ngoặc, các hàm min, max, abs, round(x, n).
    Dùng dấu CHẤM cho số thập phân (3.2 chứ không phải 3,2); dấu phẩy chỉ để ngăn cách đối số hàm.
    Ví dụ: "(3*4 + 2*3.5 + 4*2) / 9" (trung bình có trọng số theo tín chỉ), "(100*3.2 + 51*4) / 151", "8/120*100".
    Kết quả trả về gồm giá trị chi tiết và giá trị làm tròn 2 chữ số thập phân.
    """
    return calculate_text(expression)


def compare_text(a: str, b: str) -> str:
    """So sánh hai biểu thức số: nêu rõ quan hệ và ĐÚNG/SAI cho từng cách nói trong văn bản quy định."""
    try:
        left, right = evaluate(a), evaluate(b)
    except CalculatorError as exc:
        return f"LỖI: {exc}"

    def show(v: Fraction) -> str:
        return str(int(v)) if v.denominator == 1 else f"{format_number(v, 4)}"

    def yes(cond: bool) -> str:
        return "ĐÚNG" if cond else "SAI"

    if left > right:
        relation = "A LỚN HƠN B"
    elif left < right:
        relation = "A NHỎ HƠN B"
    else:
        relation = "A BẰNG B"
    return "\n".join(
        [
            f"A = {a.strip()} = {show(left)}; B = {b.strip()} = {show(right)}. => {relation}.",
            f'- A > B  ("vượt quá", "lớn hơn", "trên", "nhiều hơn"): {yes(left > right)}',
            f'- A >= B ("từ ... trở lên", "ít nhất", "không dưới", "đạt"): {yes(left >= right)}',
            f'- A < B  ("dưới", "nhỏ hơn", "ít hơn"): {yes(left < right)}',
            f'- A <= B ("tối đa", "không quá", "không vượt quá"): {yes(left <= right)}',
            f'- A = B  ("đúng bằng"): {yes(left == right)}',
        ]
    )


@tool
def compare_numbers(a: str, b: str) -> str:
    """So sánh hai số/biểu thức một cách chính xác. LUÔN dùng công cụ này mỗi khi cần so sánh với một ngưỡng hay giới hạn, không tự so sánh.

    `a` là giá trị cần xét, `b` là ngưỡng/giới hạn (cả hai là biểu thức số, dùng dấu CHẤM cho số thập phân).
    Kết quả cho biết ĐÚNG/SAI với từng cách nói trong quy định: "vượt quá" (>), "từ ... trở lên"/"ít nhất" (>=),
    "dưới" (<), "tối đa"/"không quá" (<=), "đúng bằng" (=). Lưu ý đúng bằng ngưỡng thì "vượt quá" và "dưới" đều SAI.
    Ví dụ: a="8/16*100", b="50" (TC không đạt có vượt quá 50% không?); a="3.6", b="3.6".
    """
    return compare_text(a, b)


CALCULATOR_TOOLS = [calculate, compare_numbers]
