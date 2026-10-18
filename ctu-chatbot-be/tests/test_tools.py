"""Công cụ máy tính / so sánh số và vòng lặp gọi công cụ của đồ thị chat."""

import uuid
from fractions import Fraction

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.services.chat.graph import build_chat_graph
from app.services.chat.tooling import MAX_TOOL_ROUNDS, stream_with_tools
from app.services.tools.calculator import (
    CALCULATOR_TOOLS,
    CalculatorError,
    calculate,
    calculate_text,
    compare_numbers,
    compare_text,
    evaluate,
    format_number,
    round_half_up,
)

# =====================================================================================================
# Máy tính
# =====================================================================================================


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("1+2*3", Fraction(7)),
        ("(1+2)*3", Fraction(9)),
        ("13/6", Fraction(13, 6)),
        ("524/151", Fraction(524, 151)),
        ("0.1+0.2", Fraction(3, 10)),  # không có sai số số thực: 0,1 + 0,2 đúng bằng 0,3
        ("2**3", Fraction(8)),
        ("-3+5", Fraction(2)),
        ("3 x 4", Fraction(12)),
        ("3×4÷2", Fraction(6)),
        ("2^3", Fraction(8)),
        ("5%", Fraction(1, 20)),
        ("120*5%", Fraction(6)),
        ("min(3, 4, 2)", Fraction(2)),
        ("max(3.5, 4)", Fraction(4)),
        ("abs(-2.5)", Fraction(5, 2)),
    ],
)
def test_evaluate_is_exact(expression, expected):
    assert evaluate(expression) == expected


def test_weighted_average_example_from_the_bot_mistake():
    # 13/6 từng bị bot viết thành 2,33; máy tính phải ra 2,1667 và làm tròn 2,17
    text = calculate_text("(2*3 + 3*2 + 1*1) / 6")
    assert "2,1667" in text and "2,17" in text and "2,33" not in text
    assert "3,4702" in calculate_text("524/151") and "3,47" in calculate_text("524/151")


def test_integers_are_not_padded_with_decimals():
    assert calculate_text("6*7") == "6*7 = 42"


@pytest.mark.parametrize(
    "value,digits,expected",
    [(Fraction(1, 8), 2, "0,13"), (Fraction("2.675"), 2, "2,68"), (Fraction("3.6"), 2, "3,60"), (Fraction(2, 3), 2, "0,67"), (Fraction(-5, 8), 2, "-0,63"), (Fraction("3.4702"), 4, "3,4702")],
)
def test_round_half_up_and_vietnamese_format(value, digits, expected):
    assert format_number(value, digits) == expected


def test_round_half_up_differs_from_python_round():
    assert round(2.5) == 2  # Python làm tròn chẵn
    assert round_half_up(Fraction(5, 2), 0) == 3  # điểm học tập làm tròn lên


def test_round_function_inside_expressions():
    assert evaluate("round(3.4702, 2)") == Fraction("3.47")
    assert evaluate("round(2.5)") == 3


@pytest.mark.parametrize(
    "expression",
    [
        "",
        "   ",
        "1/0",
        "0**-1",
        "__import__('os').system('echo hi')",
        "open('x')",
        "a + 1",
        "[1, 2]",
        "'abc'",
        "True + 1",
        "(1).__class__",
        "lambda: 1",
        "2**100",
        "9" * 400,
        "1 +",
        "sqrt(4)",
        "max()",
        "3,2 * 2",  # dấu phẩy thập phân kiểu Việt: phải dùng dấu chấm
    ],
)
def test_unsafe_or_invalid_expressions_are_rejected(expression):
    with pytest.raises(CalculatorError):
        evaluate(expression)


def test_text_result_reports_errors_instead_of_raising():
    assert calculate_text("1/0").startswith("LỖI")
    assert calculate_text("__import__('os')").startswith("LỖI")


def test_huge_numbers_are_refused():
    with pytest.raises(CalculatorError):
        evaluate("999999999999999*999999999999999")


# =====================================================================================================
# So sánh
# =====================================================================================================


def test_compare_exactly_equal_is_not_exceeding_nor_below():
    text = compare_text("8/16*100", "50")  # 8/16 TC = 50%: "vượt quá 50%" phải SAI
    assert 'A > B  ("vượt quá", "lớn hơn", "trên", "nhiều hơn"): SAI' in text
    assert 'A >= B ("từ ... trở lên", "ít nhất", "không dưới", "đạt"): ĐÚNG' in text
    assert 'A < B  ("dưới", "nhỏ hơn", "ít hơn"): SAI' in text
    assert 'A <= B ("tối đa", "không quá", "không vượt quá"): ĐÚNG' in text
    assert 'A = B  ("đúng bằng"): ĐÚNG' in text
    assert "A BẰNG B" in text


def test_compare_threshold_at_360_the_case_the_bot_got_wrong():
    # (340 + 51*4) / 151 = 3,6026: đạt ngưỡng 3,60 (từng bị bot nói là "không thể")
    text = compare_text("(100*3.4 + 51*4)/151", "3.6")
    assert "A LỚN HƠN B" in text and 'A >= B ("từ ... trở lên", "ít nhất", "không dưới", "đạt"): ĐÚNG' in text


def test_compare_below_and_above():
    assert "A NHỎ HƠN B" in compare_text("524/151", "3.6")
    assert "A LỚN HƠN B" in compare_text("9/16*100", "50")


def test_compare_reports_errors():
    assert compare_text("1/0", "2").startswith("LỖI")


# =====================================================================================================
# Công cụ LangChain
# =====================================================================================================


def test_langchain_tools_are_wired():
    assert {t.name for t in CALCULATOR_TOOLS} == {"calculate", "compare_numbers"}
    assert calculate.invoke({"expression": "13/6"}).startswith("13/6 = 2,1667")
    assert "A BẰNG B" in compare_numbers.invoke({"a": "6", "b": "6"})
    assert "expression" in calculate.args and set(compare_numbers.args) == {"a", "b"}


# =====================================================================================================
# Vòng lặp gọi công cụ
# =====================================================================================================


class ToolLLM:
    """LLM giả: lượt 1 yêu cầu gọi công cụ, lượt 2 (sau khi nhận ToolMessage) viết câu trả lời có dùng kết quả."""

    supports_tools = True

    def __init__(self, calls: list[dict] | None = None, answer: str = "Kết quả: {result}", loops_forever: bool = False):
        self.calls = calls if calls is not None else [{"name": "calculate", "args": {"expression": "13/6"}, "id": "c1"}]
        self.answer = answer
        self.loops_forever = loops_forever
        self.seen: list[list] = []
        self.tools_seen = []

    def stream(self, messages, tools=None):
        self.seen.append(list(messages))
        self.tools_seen.append([t.name for t in tools] if tools else [])
        results = [m.content for m in messages if isinstance(m, ToolMessage)]
        if (not results or self.loops_forever) and self.calls:
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {"name": c["name"], "args": __import__("json").dumps(c["args"]), "id": c["id"], "index": i}
                    for i, c in enumerate(self.calls)
                ],
            )
            return
        text = self.answer.format(result=" | ".join(results))
        for word in text.split(" "):
            yield AIMessageChunk(content=word + " ")


def run(llm, **kw):
    log: list = []
    text = "".join(c.content for c in stream_with_tools(llm, [HumanMessage(content="hỏi")], tool_log=log, **kw))
    return text, log


def test_tool_result_is_fed_back_and_answer_streams_afterwards():
    llm = ToolLLM()
    text, log = run(llm)
    assert "13/6 = 2,1667" in text and "2,17" in text
    assert log == [{"name": "calculate", "args": {"expression": "13/6"}, "result": log[0]["result"]}]
    assert len(llm.seen) == 2  # đúng hai lượt gọi model
    assert llm.tools_seen[0] == ["calculate", "compare_numbers"]  # công cụ được gắn ở mọi lượt


def test_several_tool_calls_in_one_round_are_all_executed():
    llm = ToolLLM(
        calls=[
            {"name": "calculate", "args": {"expression": "2*3"}, "id": "a"},
            {"name": "compare_numbers", "args": {"a": "8/16*100", "b": "50"}, "id": "b"},
        ]
    )
    text, log = run(llm)
    assert [entry["name"] for entry in log] == ["calculate", "compare_numbers"]
    assert "2*3 = 6" in text and "A BẰNG B" in text


def test_no_tool_call_streams_directly_with_a_single_model_call():
    llm = ToolLLM(calls=[])
    text, log = run(llm)
    assert log == [] and len(llm.seen) == 1


def test_unknown_tool_and_bad_arguments_do_not_crash():
    llm = ToolLLM(calls=[{"name": "xoa_du_lieu", "args": {}, "id": "x"}])
    text, log = run(llm)
    assert "LỖI: không có công cụ" in text
    llm = ToolLLM(calls=[{"name": "calculate", "args": {"sai_ten": 1}, "id": "y"}])
    text, log = run(llm)
    assert "LỖI" in text  # thiếu tham số `expression`


def test_calculator_error_is_reported_back_to_the_model():
    text, log = run(ToolLLM(calls=[{"name": "calculate", "args": {"expression": "1/0"}, "id": "z"}]))
    assert "LỖI: Chia cho 0" in text


def test_model_that_never_stops_calling_tools_is_cut_off():
    llm = ToolLLM(loops_forever=True)
    text, log = run(llm)
    assert text == ""  # không có chữ nào
    assert len(llm.seen) == MAX_TOOL_ROUNDS + 1


# =====================================================================================================
# Trong đồ thị chat
# =====================================================================================================


def test_graph_uses_the_tool_loop_for_clients_that_support_tools_and_logs_calls():
    llm = ToolLLM()
    graph = build_chat_graph(llm, InMemorySaver())
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    result = graph.invoke({"messages": [HumanMessage(content="xin chào")]}, config)
    reply = result["messages"][-1]
    assert "2,1667" in reply.content
    assert reply.additional_kwargs["tools"][0]["name"] == "calculate"
    assert "CÔNG CỤ" in str(llm.seen[0][0].content)  # prompt hệ thống dặn phải dùng công cụ


def test_graph_still_works_with_clients_without_tool_support():
    from tests.fakes import FakeLLM

    graph = build_chat_graph(FakeLLM(), InMemorySaver())
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    result = graph.invoke({"messages": [HumanMessage(content="xin chào")]}, config)
    assert result["messages"][-1].additional_kwargs["tools"] == []


# =====================================================================================================
# Câu trả lời rỗng của Gemini: thử lại
# =====================================================================================================


class FlakyLLM:
    """Client gọi được công cụ nhưng trả về RỖNG (không chữ, không gọi công cụ) trong `empty_with_tools` lần đầu có công cụ."""

    supports_tools = True

    def __init__(self, empty_with_tools: int, plain_text: str = "trả lời không công cụ"):
        self.empty_with_tools = empty_with_tools
        self.plain_text = plain_text
        self.with_tools = 0
        self.plain = 0

    def stream(self, messages, tools=None):
        if tools:
            self.with_tools += 1
            if self.with_tools <= self.empty_with_tools:
                return
            yield AIMessageChunk(content="đã hồi phục")
        else:
            self.plain += 1
            if self.plain_text:
                yield AIMessageChunk(content=self.plain_text)


def ask_graph(llm):
    graph = build_chat_graph(llm, InMemorySaver())
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    return graph.invoke({"messages": [HumanMessage(content="xin chào")]}, config)["messages"][-1].content


def test_empty_reply_is_retried_once_with_tools():
    llm = FlakyLLM(empty_with_tools=1)
    assert ask_graph(llm) == "đã hồi phục"
    assert (llm.with_tools, llm.plain) == (2, 0)


def test_two_empty_replies_fall_back_to_a_plain_answer_without_tools():
    llm = FlakyLLM(empty_with_tools=2)
    assert ask_graph(llm) == "trả lời không công cụ"
    assert (llm.with_tools, llm.plain) == (2, 1)


def test_reply_that_stays_empty_raises_an_llm_error():
    from app.services.llm.gemini import LLMError

    llm = FlakyLLM(empty_with_tools=5, plain_text="")
    with pytest.raises(LLMError):
        ask_graph(llm)


def test_non_empty_reply_is_not_retried():
    llm = FlakyLLM(empty_with_tools=0)
    assert ask_graph(llm) == "đã hồi phục"
    assert llm.with_tools == 1
